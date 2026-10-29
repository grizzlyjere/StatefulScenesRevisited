"""Scene scope configuration and label lifecycle coverage."""

import asyncio
from types import MappingProxyType
from unittest.mock import ANY, MagicMock

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er, label_registry as lr

from custom_components.stateful_scenes_revisited.config_flow import StatefulScenesConfigFlow
from custom_components.stateful_scenes_revisited.const import DOMAIN
from custom_components.stateful_scenes_revisited.manager import SceneManager
from test_runtime import setup_scenes


def entry_for(hass, data=None, options=None):
    entry = ConfigEntry(domain=DOMAIN, title="Stateful Scenes Revisited", data=data or {},
                        options=options or {}, source="user", unique_id=DOMAIN,
                        version=1, minor_version=1, subentries_data=[], discovery_keys=MappingProxyType({}))
    hass.config_entries._entries[entry.entry_id] = entry
    return entry


async def test_setup_scope_and_existing_tag(hass):
    label = lr.async_get(hass).async_create("Evening")
    flow = StatefulScenesConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    form = await flow.async_step_user()
    assert form["data_schema"]({}) == {"scene_scope": "all"}
    form = await flow.async_step_user({"scene_scope": "tag"})
    assert form["step_id"] == "tag"
    selector = next(iter(form["data_schema"].schema.values()))
    assert selector.config["options"] == [{"value": label.label_id, "label": "Evening"}]
    result = await flow.async_step_tag({"scene_tag": label.label_id})
    assert result["data"] == {"scene_scope": "tag", "scene_tag": label.label_id}


async def test_setup_new_tag_blank_and_duplicate(hass):
    flow = StatefulScenesConfigFlow()
    flow.hass = hass
    form = await flow.async_step_tag({"scene_tag": "   "})
    assert form["errors"] == {"scene_tag": "empty_tag"}
    result = await flow.async_step_tag({"scene_tag": "  My scenes  "})
    registry = lr.async_get(hass)
    label = registry.async_get_label_by_name("My scenes")
    assert label is not None
    assert result["data"]["scene_tag"] == label.label_id
    result = await flow.async_step_tag({"scene_tag": "My scenes"})
    assert result["data"]["scene_tag"] == label.label_id
    assert len(list(registry.async_list_labels())) == 1


async def test_options_can_select_tag_and_return_to_all(hass):
    entry = entry_for(hass)
    flow = StatefulScenesConfigFlow.async_get_options_flow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    assert (await flow.async_step_init())["data_schema"]({}) == {"scene_scope": "all"}
    assert (await flow.async_step_init({"scene_scope": "tag"}))["step_id"] == "tag"
    selected = await flow.async_step_tag({"scene_tag": "Tracked"})
    hass.config_entries.async_update_entry(entry, options=selected["data"])
    assert (await flow.async_step_init())["data_schema"]({}) == {"scene_scope": "tag"}
    assert (await flow.async_step_tag())["data_schema"]({}) == {"scene_tag": "tracked"}
    result = await flow.async_step_init({"scene_scope": "all"})
    assert result["data"] == {"scene_scope": "all"}


async def test_tag_assignments_and_deletion_update_scope(hass):
    initial = await setup_scenes(hass)
    initial.stop()
    registry = er.async_get(hass)
    label = lr.async_get(hass).async_create("Tracked")
    manager = SceneManager(hass, {"scene_scope": "tag", "scene_tag": label.label_id})
    await manager.async_start()
    try:
        assert not manager.scenes
        assert len(manager.snapshot()["scenes"]) == 1
        assert manager.snapshot()["scenes"][0]["monitored"] is False
        registry.async_update_entity("scene.desk_scene", labels={label.label_id})
        await asyncio.sleep(.3)
        assert len(manager.scenes) == 1
        assert manager.snapshot()["scenes"][0]["monitored"] is True
        key = next(iter(manager.scenes))
        await manager.async_save({"scene_key": key, "brightness_tolerance": 5,
                                  "ignore_attributes": True, "ignored_attributes": []})
        registry.async_update_entity("scene.desk_scene", labels=set())
        await asyncio.sleep(.3)
        assert not manager.scenes
        assert manager.snapshot()["scenes"][0]["monitored"] is False
        registry.async_update_entity("scene.desk_scene", labels={label.label_id})
        await asyncio.sleep(.3)
        assert manager.options(key)["brightness_tolerance"] == 5
        lr.async_get(hass).async_delete(label.label_id)
        await asyncio.sleep(.3)
        assert not manager.scenes
    finally:
        manager.stop()


async def test_scope_reload_removes_previously_created_switches(hass):
    from custom_components.stateful_scenes_revisited.switch import async_setup_entry
    initial = await setup_scenes(hass)
    key = next(iter(initial.scenes))
    initial.stop()
    entry = entry_for(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create("switch", DOMAIN, f"{DOMAIN}:{key}", config_entry=entry)
    manager = SceneManager(hass, {"scene_scope": "tag", "scene_tag": "not_assigned"})
    await manager.async_start()
    hass.data[DOMAIN] = {entry.entry_id: manager}
    try:
        added = []
        await async_setup_entry(hass, entry, added.extend)
        assert not added
        assert registry.async_get(old.entity_id) is None
    finally:
        manager.stop()


async def test_options_listener_updates_active_manager(hass):
    from custom_components.stateful_scenes_revisited import async_update_options
    entry = entry_for(hass, options={"scene_scope": "tag", "scene_tag": "tracked"})
    manager = MagicMock()
    hass.data[DOMAIN] = {entry.entry_id: manager}
    await async_update_options(hass, entry)
    assert manager.config == dict(entry.options)
    manager.discover.assert_called_once()


async def test_global_panel_scope_saves_options_and_filters_scenes(hass):
    from custom_components.stateful_scenes_revisited.websocket import scope
    manager = await setup_scenes(hass)
    entry = entry_for(hass)
    hass.data[DOMAIN] = {entry.entry_id: manager}
    connection = MagicMock()
    connection.user.is_admin = True
    try:
        scope(hass, connection, {"id": 1, "scene_scope": "tag", "new_tag": "Tracked"})
        await hass.async_block_till_done()
        connection.send_result.assert_called_with(1)
        tag = lr.async_get(hass).async_get_label_by_name("Tracked")
        assert entry.options == {"scene_scope": "tag", "scene_tag": tag.label_id}
        assert not manager.scenes
        assert manager.snapshot()["tags"] == [{"id": tag.label_id, "name": "Tracked"}]
        assert manager.snapshot()["scene_scope"] == "tag"
        er.async_get(hass).async_update_entity("scene.desk_scene", labels={tag.label_id})
        await asyncio.sleep(.3)
        assert len(manager.scenes) == 1
        scope(hass, connection, {"id": 2, "scene_scope": "all"})
        await hass.async_block_till_done()
        assert entry.options == {"scene_scope": "all"}
        assert len(manager.scenes) == 1
        scope(hass, connection, {"id": 3, "scene_scope": "tag", "scene_tag": tag.label_id})
        await hass.async_block_till_done()
        assert entry.options["scene_tag"] == tag.label_id
        assert len(list(lr.async_get(hass).async_list_labels())) == 1
        # Persisted config entry options restore the same scope after startup.
        restored = SceneManager(hass, dict(entry.options))
        await restored.async_start()
        assert len(restored.scenes) == 1
        restored.stop()
    finally:
        manager.stop()


async def test_global_panel_scope_rejects_invalid_tags_and_non_admins(hass):
    import pytest
    from homeassistant.exceptions import Unauthorized
    from custom_components.stateful_scenes_revisited.websocket import scope
    manager = await setup_scenes(hass)
    entry = entry_for(hass)
    hass.data[DOMAIN] = {entry.entry_id: manager}
    connection = MagicMock()
    connection.user.is_admin = False
    try:
        with pytest.raises(Unauthorized):
            scope(hass, connection, {"id": 1, "scene_scope": "all"})
        connection.user.is_admin = True
        for selection in ({"scene_tag": "missing"}, {"new_tag": "   "}, {}):
            scope(hass, connection, {"id": 2, "scene_scope": "tag", **selection})
            await hass.async_block_till_done()
            connection.send_error.assert_called_with(2, "invalid_tag", ANY)
        assert not entry.options
        assert len(manager.scenes) == 1
        assert not list(lr.async_get(hass).async_list_labels())
    finally:
        manager.stop()


async def test_switch_labels_save_remove_and_clear_without_changing_source_scene(hass):
    from custom_components.stateful_scenes_revisited.websocket import scene_labels

    manager = await setup_scenes(hass)
    hass.data[DOMAIN] = {"test": manager}
    registry = er.async_get(hass)
    labels = lr.async_get(hass)
    source = labels.async_create("Source scene")
    existing = labels.async_create("Existing switch label")
    extra = labels.async_create("Extra switch label")
    registry.async_update_entity("scene.desk_scene", labels={source.label_id})
    manager.config = {"scene_scope": "tag", "scene_tag": source.label_id}
    manager.discover()
    key = next(iter(manager.scenes))
    switch = registry.async_get_or_create("switch", DOMAIN, f"{DOMAIN}:{key}", config_entry=entry_for(hass))
    switch = registry.async_update_entity(switch.entity_id, new_entity_id="switch.renamed_scene_match", labels={existing.label_id})
    connection = MagicMock()
    connection.user.is_admin = True
    try:
        result = manager.result(key)
        assert result["can_label"] is True
        assert result["label_ids"] == [existing.label_id]
        assert result["switch_entity_id"] == switch.entity_id
        selections = ([existing.label_id, extra.label_id], [extra.label_id], [])
        for request_id, selected in enumerate(selections, 1):
            scene_labels(hass, connection, {"id": request_id, "scene_key": key, "label_ids": selected})
            connection.send_result.assert_called_with(request_id)
            assert registry.async_get(switch.entity_id).labels == set(selected)
            assert manager.result(key)["label_ids"] == sorted(selected)
            assert registry.async_get("scene.desk_scene").labels == {source.label_id}
            assert key in manager.scenes
        scene_labels(hass, connection, {"id": 4, "scene_key": key, "label_ids": [extra.label_id]})
        labels.async_delete(extra.label_id)
        await asyncio.sleep(.3)
        assert manager.result(key)["label_ids"] == []
        assert registry.async_get("scene.desk_scene").labels == {source.label_id}
        assert key in manager.scenes
        # A stale registry entry must not allow labeling an unmonitored scene.
        manager.config = {"scene_scope": "tag", "scene_tag": existing.label_id}
        manager.discover()
        assert manager.result(key)["can_label"] is False
        scene_labels(hass, connection, {"id": 5, "scene_key": key, "label_ids": [existing.label_id]})
        connection.send_error.assert_called_with(5, "not_registered", ANY)
        assert registry.async_get(switch.entity_id).labels == set()
    finally:
        manager.stop()


async def test_switch_labels_rejects_invalid_requests_and_missing_switch_without_scene_fallback(hass):
    import pytest
    from homeassistant.exceptions import Unauthorized
    from custom_components.stateful_scenes_revisited.websocket import scene_labels

    manager = await setup_scenes(hass)
    hass.data[DOMAIN] = {"test": manager}
    key = next(iter(manager.scenes))
    registry = er.async_get(hass)
    valid = lr.async_get(hass).async_create("Valid")
    registry.async_update_entity("scene.desk_scene", labels={valid.label_id})
    switch = registry.async_get_or_create("switch", DOMAIN, f"{DOMAIN}:{key}", config_entry=entry_for(hass))
    registry.async_update_entity(switch.entity_id, labels={valid.label_id})
    connection = MagicMock()
    connection.user.is_admin = False
    message = {"id": 1, "scene_key": key, "label_ids": ["missing"]}
    try:
        with pytest.raises(Unauthorized):
            scene_labels(hass, connection, message)
        connection.user.is_admin = True
        scene_labels(hass, connection, message)
        connection.send_error.assert_called_with(1, "invalid_label", ANY)
        scene_labels(hass, connection, {**message, "scene_key": "deleted"})
        connection.send_error.assert_called_with(1, "not_found", ANY)
        scene_labels(hass, connection, {**message, "label_ids": [valid.label_id, "missing"]})
        assert registry.async_get(switch.entity_id).labels == {valid.label_id}
        registry.async_remove(switch.entity_id)
        assert manager.result(key)["can_label"] is False
        assert manager.result(key)["label_ids"] == []
        scene_labels(hass, connection, {**message, "label_ids": []})
        connection.send_error.assert_called_with(1, "not_registered", ANY)
        assert registry.async_get("scene.desk_scene").labels == {valid.label_id}
    finally:
        manager.stop()
