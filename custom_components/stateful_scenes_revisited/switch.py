"""One non-optimistic switch per discovered scene."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    manager = hass.data[DOMAIN][entry.entry_id]
    registry = er.async_get(hass)
    active_ids = {f"{DOMAIN}:{key}" for key in manager.scenes}
    for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registered.platform == DOMAIN and registered.domain == "switch" and registered.unique_id not in active_ids:
            registry.async_remove(registered.entity_id)
    entities = {}
    removing = set()

    async def remove(key, entity):
        try:
            await entity.async_remove()
            registry = er.async_get(hass)
            if entity_id := registry.async_get_entity_id("switch", DOMAIN, entity.unique_id):
                registry.async_remove(entity_id)
        finally:
            entities.pop(key, None)
            removing.discard(key)
            sync()

    @callback
    def sync():
        added = []
        for key in manager.scenes:
            if key not in entities:
                entities[key] = SceneSwitch(manager, key)
                added.append(entities[key])
        if added:
            async_add_entities(added)
        for key, entity in tuple(entities.items()):
            if key not in manager.scenes and key not in removing:
                removing.add(key)
                entry.async_create_task(hass, remove(key, entity), "Remove deleted scene switch")
        for key, entity in entities.items():
            if key in manager.scenes and entity.hass is not None:
                entity.async_write_ha_state()

    entry.async_on_unload(manager.subscribe(sync))
    sync()


class SceneSwitch(SwitchEntity):
    _attr_should_poll = False
    _attr_icon = "mdi:palette"

    def __init__(self, manager, key):
        self.manager = manager
        self.key = key
        self._attr_unique_id = f"{DOMAIN}:{key}"
        self._attr_name = f"{manager.scenes[key].name} Stateful Scenes Revisited"

    @property
    def name(self):
        scene = self.manager.scenes.get(self.key)
        return f"{scene.name} Stateful Scenes Revisited" if scene else self._attr_name

    @property
    def available(self):
        scene = self.manager.scenes.get(self.key)
        return bool(scene and scene.states)

    @property
    def is_on(self):
        return self.available and self.manager.result(self.key)["matches"]

    @property
    def extra_state_attributes(self):
        if self.key not in self.manager.scenes:
            return {}
        result = self.manager.result(self.key)
        return {
            "scene_entity_id": result["entity_id"],
            "brightness_tolerance": result["options"]["brightness_tolerance"],
            "difference_count": len(result["differences"]),
        }

    async def async_turn_on(self, **kwargs):
        await self.hass.services.async_call(
            "scene", "turn_on", {"entity_id": self.manager.scenes[self.key].entity_id},
            blocking=True, context=self._context,
        )
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """No action: the switch always reflects the real scene match."""
        self.async_write_ha_state()
