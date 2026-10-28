"""Discover scene definitions and react to state and scene lifecycle events."""

import asyncio
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from homeassistant.components.homeassistant.scene import DATA_PLATFORM, EVENT_SCENE_RELOADED
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er, label_registry as lr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .comparison import EntityState, compare_scene
from .const import (
    CONF_SCENE_SCOPE, CONF_SCENE_TAG, DEFAULT_IGNORED_ATTRIBUTES, DEFAULT_TOLERANCE, DOMAIN, SCOPE_ALL, SCOPE_TAG, STORAGE_VERSION,
)


@dataclass
class SceneDefinition:
    key: str
    entity_id: str
    name: str
    states: dict[str, EntityState] | None
    area_id: str | None = None
    area_name: str | None = None
    members: tuple[str, ...] = ()


class SceneManager:
    def __init__(self, hass: HomeAssistant, config: dict[str, Any] | None = None) -> None:
        self.hass = hass
        self.config = config or {}
        self.scenes: dict[str, SceneDefinition] = {}
        self.available_scenes: dict[str, SceneDefinition] = {}
        self.settings: dict[str, Any] = {
            "brightness_tolerance": DEFAULT_TOLERANCE,
            "ignored_attributes": list(DEFAULT_IGNORED_ATTRIBUTES), "scenes": {},
        }
        self._store = Store(hass, STORAGE_VERSION, DOMAIN)
        self._listeners: set[Callable[[], None]] = set()
        self._unsubs: list[Callable[[], None]] = []
        self._timer: asyncio.TimerHandle | None = None
        self._members: set[str] = set()
        self._save_lock = asyncio.Lock()

    async def async_start(self) -> None:
        if saved := await self._store.async_load():
            self.settings.update(saved)
        self._unsubs = [
            self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._state_changed),
            self.hass.bus.async_listen(EVENT_SCENE_RELOADED, self._schedule_discovery),
            self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self._schedule_discovery),
            self.hass.bus.async_listen(lr.EVENT_LABEL_REGISTRY_UPDATED, self._schedule_discovery),
            self.hass.bus.async_listen(ar.EVENT_AREA_REGISTRY_UPDATED, self._schedule_discovery),
            self.hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, self._schedule_discovery),
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, self._schedule_discovery),
        ]
        self.discover()

    @callback
    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    @callback
    def notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()
        async_dispatcher_send(self.hass, f"{DOMAIN}_updated")

    @callback
    def _state_changed(self, event: Event) -> None:
        entity_id = event.data["entity_id"]
        if entity_id.startswith("scene."):
            self._schedule_discovery()
        elif entity_id in self._members:
            self.notify()

    @callback
    def _schedule_discovery(self, event: Event | None = None) -> None:
        if self._timer:
            self._timer.cancel()
        self._timer = self.hass.loop.call_later(0.2, self.discover)

    @callback
    def discover(self) -> None:
        """Isolate HA's internal scene API here; opaque scenes stay unavailable."""
        self._timer = None
        platform = self.hass.data.get(DATA_PLATFORM)
        native = getattr(platform, "entities", {})
        registry = er.async_get(self.hass)
        found = {}
        for state in self.hass.states.async_all("scene"):
            entity = native.get(state.entity_id)
            config = getattr(entity, "scene_config", None)
            registered = registry.async_get(state.entity_id)
            if registered:
                key = f"{registered.platform}:{registered.unique_id}"
            else:
                key = f"scene:{state.entity_id}"
            states = None
            if config is not None:
                states = {
                    entity_id: EntityState(target.state, dict(target.attributes))
                    for entity_id, target in config.states.items()
                }
            area_id = registered.area_id if registered else None
            if area_id is None and registered and registered.device_id:
                device = dr.async_get(self.hass).async_get(registered.device_id)
                if device:
                    area_id = dr.async_get_effective_area_id(self.hass, device)
            area = ar.async_get(self.hass).async_get_area(area_id) if area_id else None
            found[key] = SceneDefinition(
                key, state.entity_id, state.attributes.get("friendly_name", state.entity_id), states,
                area.id if area else None, area.name if area else None,
                tuple(states) if states is not None else tuple(state.attributes.get("entity_id", [])),
            )
        self.available_scenes = found
        tag = self.config.get(CONF_SCENE_TAG)
        self.scenes = {
            key: scene for key, scene in found.items()
            if self.config.get(CONF_SCENE_SCOPE) != SCOPE_TAG
            or ((entry := registry.async_get(scene.entity_id)) and tag in entry.labels)
        }
        self._members = {entity_id for scene in found.values() for entity_id in scene.members}
        self.notify()

    def options(self, key: str) -> dict[str, Any]:
        stored = self.settings["scenes"].get(key, {})
        override = stored.get("brightness_tolerance")
        return {
            "brightness_tolerance": self.settings["brightness_tolerance"] if override is None else override,
            "brightness_tolerance_override": override,
            "ignore_attributes": stored.get("ignore_attributes", False),
            "ignored_attributes": stored.get("ignored_attributes", []),
        }

    def result(self, key: str) -> dict[str, Any]:
        scene = self.available_scenes[key]
        options = self.options(key)
        supported = bool(scene.states)
        current = {}
        for entity_id in scene.members:
            if state := self.hass.states.get(entity_id):
                current[entity_id] = EntityState(state.state, state.attributes)
        comparison = compare_scene(
            scene.states or {}, current, options["brightness_tolerance"],
            options["ignore_attributes"], tuple(self.settings["ignored_attributes"] + options["ignored_attributes"]),
            include_matches=True,
        )
        differences = [row for row in comparison if row["reason"] not in ("match", "ignored")]
        if not supported:
            comparison = [
                {"entity_id": entity_id, "field": "state", "expected": None,
                 "actual": current[entity_id].state if entity_id in current else None,
                 "reason": "target_unavailable"}
                for entity_id in scene.members
            ]
        return {
            "key": key, "entity_id": scene.entity_id, "name": scene.name,
            "area_id": scene.area_id, "area_name": scene.area_name,
            "switch_entity_id": er.async_get(self.hass).async_get_entity_id(
                "switch", DOMAIN, f"{DOMAIN}:{key}",
            ) if key in self.scenes else None,
            "monitored": key in self.scenes, "supported": supported, "matches": supported and not differences,
            "issue": None if supported else "This scene does not expose target states. Listed members cannot be compared; the switch remains unavailable.",
            "differences": differences, "comparison": comparison,
            "entity_count": len(scene.members),
            "attributes": sorted({a for s in (scene.states or {}).values() for a in s.attributes}),
            "options": options,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "brightness_tolerance": self.settings["brightness_tolerance"],
            "ignored_attributes": list(self.settings["ignored_attributes"]),
            "scene_scope": self.config.get(CONF_SCENE_SCOPE, SCOPE_ALL),
            "scene_tag": self.config.get(CONF_SCENE_TAG),
            "tags": [{"id": label.label_id, "name": label.name} for label in sorted(
                lr.async_get(self.hass).async_list_labels(), key=lambda label: label.name.casefold()
            )],
            "scenes": [self.result(key) for key in sorted(self.available_scenes, key=lambda k: self.available_scenes[k].name.casefold())],
        }

    async def async_save(self, changes: dict[str, Any]) -> None:
        async with self._save_lock:
            updated = deepcopy(self.settings)
            if "scene_key" in changes:
                key = changes["scene_key"]
                if key not in self.available_scenes:
                    raise ValueError("Scene no longer exists")
                updated["scenes"][key] = {
                    field: changes[field]
                    for field in ("brightness_tolerance", "ignore_attributes", "ignored_attributes")
                }
            else:
                for field in ("brightness_tolerance", "ignored_attributes"):
                    if field in changes:
                        updated[field] = changes[field]
            await self._store.async_save(updated)
            self.settings = updated
            self.notify()

    @callback
    def stop(self) -> None:
        if self._timer:
            self._timer.cancel()
        for unsub in self._unsubs:
            unsub()
        self._listeners.clear()
