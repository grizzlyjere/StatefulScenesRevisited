import asyncio
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import probatio as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.setup import async_setup_component
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.components.homeassistant.scene import DATA_PLATFORM

from custom_components.stateful_scenes_revisited.const import DOMAIN
from custom_components.stateful_scenes_revisited.manager import SceneManager
from custom_components.stateful_scenes_revisited.switch import SceneSwitch
from custom_components.stateful_scenes_revisited.websocket import tolerance, scene_settings, subscribe


async def setup_scenes(hass):
    assert await async_setup_component(hass, "scene", {"scene": [
        {"id": "desk-scene", "name": "Desk scene", "entities": {
            "light.desk": {"state": "on", "brightness": 100},
            "switch.fan": "off",
        }},
    ]})
    await hass.async_block_till_done()
    hass.states.async_set("light.desk", "on", {"brightness": 100})
    hass.states.async_set("switch.fan", "off")
    manager = SceneManager(hass)
    await manager.async_start()
    return manager


async def test_real_scenes_live_updates_and_settings_storage(hass):
    manager = await setup_scenes(hass)
    try:
        key = next(iter(manager.scenes))
        assert manager.result(key)["matches"]
        changed = MagicMock()
        manager.subscribe(changed)
        hass.states.async_set("light.desk", "on", {"brightness": 120})
        await hass.async_block_till_done()
        assert changed.called
        assert not manager.result(key)["matches"]
        await manager.async_save({"brightness_tolerance": 10})
        assert manager.result(key)["matches"]
        await manager.async_save({"scene_key": key, "brightness_tolerance": 0, "ignore_attributes": False, "ignored_attributes": []})
        assert not manager.result(key)["matches"]
        reloaded = SceneManager(hass)
        await reloaded.async_start()
        assert reloaded.options(key)["brightness_tolerance"] == 0
        reloaded.stop()
        await manager.async_save({"scene_key": key, "brightness_tolerance": None, "ignore_attributes": True, "ignored_attributes": []})
        assert manager.result(key)["matches"]
        hass.states.async_remove("switch.fan")
        await hass.async_block_till_done()
        assert not manager.result(key)["matches"]
    finally:
        manager.stop()


async def test_scene_create_replace_delete_and_unsupported(hass):
    manager = await setup_scenes(hass)
    try:
        await hass.services.async_call("scene", "create", {"scene_id": "dynamic", "entities": {"light.desk": {"state": "off"}}}, blocking=True)
        await asyncio.sleep(.3)
        assert len(manager.scenes) == 2
        key = next(k for k, s in manager.scenes.items() if s.entity_id == "scene.dynamic")
        assert not manager.result(key)["matches"]
        await hass.services.async_call("scene", "create", {"scene_id": "dynamic", "entities": {"light.desk": {"state": "on", "brightness": 100}}}, blocking=True)
        await asyncio.sleep(.3)
        assert manager.result(key)["matches"]
        await hass.services.async_call("scene", "delete", {"entity_id": "scene.dynamic"}, blocking=True)
        await asyncio.sleep(.3)
        assert key not in manager.scenes
        hass.states.async_set("scene.opaque", "unknown", {"friendly_name": "Vendor scene"})
        await asyncio.sleep(.3)
        opaque = next(k for k, s in manager.scenes.items() if s.entity_id == "scene.opaque")
        assert not manager.result(opaque)["supported"]
        assert not manager.result(opaque)["matches"]
    finally:
        manager.stop()


async def test_scene_definition_reload_same_entity_id(hass):
    manager = await setup_scenes(hass)
    try:
        key = next(iter(manager.scenes))
        platform = hass.data[DATA_PLATFORM]
        entity = platform.entities[manager.scenes[key].entity_id]
        entity.scene_config = entity.scene_config._replace(states={"switch.fan": hass.states.get("switch.fan")})
        hass.bus.async_fire("scene_reloaded")
        await asyncio.sleep(.3)
        assert manager.result(key)["entity_count"] == 1
    finally:
        manager.stop()


async def test_scene_area_metadata_tracks_registry_changes(hass):
    manager = await setup_scenes(hass)
    try:
        key = next(iter(manager.scenes))
        areas = ar.async_get(hass)
        registry = er.async_get(hass)
        office = areas.async_create("Office")
        living = areas.async_create("Living room")
        assert manager.result(key)["area_id"] is None
        registry.async_update_entity("scene.desk_scene", area_id=office.id)
        await asyncio.sleep(.3)
        assert manager.result(key)["area_id"] == office.id
        assert manager.result(key)["area_name"] == "Office"
        areas.async_update(office.id, name="Study")
        await asyncio.sleep(.3)
        assert manager.result(key)["area_name"] == "Study"

        entry = ConfigEntry(domain=DOMAIN, title="Test", data={}, options={}, source="user", unique_id="area-test",
                            version=1, minor_version=1, subentries_data=[], discovery_keys=MappingProxyType({}))
        hass.config_entries._entries[entry.entry_id] = entry
        devices = dr.async_get(hass)
        device = devices.async_get_or_create(config_entry_id=entry.entry_id,
                                             identifiers={(DOMAIN, "scene-device")})
        devices.async_update_device(device.id, area_id=living.id)
        registry.async_update_entity("scene.desk_scene", device_id=device.id)
        await asyncio.sleep(.3)
        assert manager.result(key)["area_id"] == office.id
        registry.async_update_entity("scene.desk_scene", area_id=None)
        await asyncio.sleep(.3)
        assert manager.result(key)["area_id"] == living.id
        devices.async_update_device(device.id, area_id=office.id)
        await asyncio.sleep(.3)
        assert manager.result(key)["area_id"] == office.id
        areas.async_delete(office.id)
        await asyncio.sleep(.3)
        assert manager.result(key)["area_id"] is None
        assert manager.result(key)["area_name"] is None
    finally:
        manager.stop()


async def test_switch_activation_and_noop_off(hass):
    manager = await setup_scenes(hass)
    try:
        switch = SceneSwitch(manager, next(iter(manager.scenes)))
        switch.hass = hass
        switch.entity_id = "switch.desk_stateful"
        switch.async_write_ha_state = MagicMock()
        with patch.object(type(hass.services), "async_call", new_callable=AsyncMock) as call:
            await switch.async_turn_on()
            call.assert_awaited_once_with("scene", "turn_on", {"entity_id": "scene.desk_scene"}, blocking=True, context=switch._context)
            call.reset_mock()
            await switch.async_turn_off()
            call.assert_not_called()
        assert switch.is_on
    finally:
        manager.stop()


@pytest.mark.parametrize("value", [-1, 101, float("nan"), float("inf"), True, "3"])
def test_invalid_tolerance_rejected(value):
    with pytest.raises(vol.Invalid):
        tolerance(value)


async def test_websocket_admin_enforcement_and_unsubscribe(hass):
    from homeassistant.exceptions import Unauthorized
    manager = await setup_scenes(hass)
    hass.data[DOMAIN] = {"test": manager}
    try:
        connection = MagicMock()
        connection.user.is_admin = False
        with pytest.raises(Unauthorized):
            subscribe(hass, connection, {"id": 1})
        with pytest.raises(Unauthorized):
            scene_settings(hass, connection, {"id": 2})
        connection.user.is_admin = True
        connection.subscriptions = {}
        subscribe(hass, connection, {"id": 1})
        connection.send_event.assert_called_once()
        connection.subscriptions[1]()
        manager.notify()
        connection.send_event.assert_called_once()
    finally:
        manager.stop()


async def test_native_switch_platform_adds_and_removes_registry_entries(hass):
    from custom_components.stateful_scenes_revisited.switch import async_setup_entry
    manager = await setup_scenes(hass)
    hass.data[DOMAIN] = {"test": manager}
    entry = ConfigEntry(domain=DOMAIN, title="Stateful Scenes Revisited", data={}, options={}, source="user", unique_id=DOMAIN,
                        version=1, minor_version=1, subentries_data=[], discovery_keys=MappingProxyType({}), entry_id="test")
    added = []
    def add(entities):
        for entity in entities:
            entity.hass = hass
            entity.entity_id = "switch.test_scene"
            entity.async_write_ha_state = MagicMock()
            entity.async_remove = AsyncMock()
            added.append(entity)
    try:
        await async_setup_entry(hass, entry, add)
        assert len(added) == 1
        registry = er.async_get(hass)
        registered = registry.async_get_or_create("switch", DOMAIN, added[0].unique_id)
        assert registered
        manager.scenes = {}
        manager.notify()
        await hass.async_block_till_done()
        added[0].async_remove.assert_awaited_once()
        assert registry.async_get_entity_id("switch", DOMAIN, added[0].unique_id) is None
    finally:
        manager.stop()


async def test_entry_setup_real_switch_platform_and_unload(hass):
    from homeassistant.config_entries import ConfigEntryState
    from custom_components.stateful_scenes_revisited import async_setup_entry, async_unload_entry
    initial = await setup_scenes(hass)
    initial.stop()
    entry = ConfigEntry(domain=DOMAIN, title="Stateful Scenes Revisited", data={}, options={}, source="user", unique_id=DOMAIN,
                        version=1, minor_version=1, subentries_data=[], discovery_keys=MappingProxyType({}),
                        state=ConfigEntryState.LOADED)
    hass.config_entries._entries[entry.entry_id] = entry
    hass.data[DOMAIN] = {}
    hass.config.components.add(DOMAIN)
    with patch("custom_components.stateful_scenes_revisited.panel_custom.async_register_panel", new_callable=AsyncMock) as panel, patch("custom_components.stateful_scenes_revisited.ha_frontend.async_remove_panel"):
        assert await async_setup_entry(hass, entry)
        await hass.async_block_till_done()
        switches = hass.states.async_all("switch")
        generated = [s for s in switches if s.attributes.get("scene_entity_id") == "scene.desk_scene"]
        assert len(generated) == 1
        assert generated[0].state == "on"
        panel.assert_awaited_once()
        hass.states.async_set("light.desk", "off")
        await hass.async_block_till_done()
        assert hass.states.get(generated[0].entity_id).state == "off"
        assert await async_unload_entry(hass, entry)
        assert not hass.data[DOMAIN]


async def test_scene_switch_metadata_uses_registry_and_tracks_renames(hass):
    manager = await setup_scenes(hass)
    try:
        key = next(iter(manager.scenes))
        assert manager.result(key)["switch_entity_id"] is None
        registry = er.async_get(hass)
        switch = registry.async_get_or_create("switch", DOMAIN, f"{DOMAIN}:{key}", suggested_object_id="desk_match")
        assert manager.result(key)["switch_entity_id"] == switch.entity_id
        registry.async_update_entity(switch.entity_id, new_entity_id="switch.renamed_match")
        await asyncio.sleep(.3)
        assert manager.snapshot()["scenes"][0]["switch_entity_id"] == "switch.renamed_match"
        manager.scenes = {}
        assert manager.result(key)["switch_entity_id"] is None
    finally:
        manager.stop()
