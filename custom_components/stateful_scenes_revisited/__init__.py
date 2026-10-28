"""Stateful scene switches and comparison panel."""

from pathlib import Path

from homeassistant.components import frontend as ha_frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform

from .const import DOMAIN, PANEL_PATH
from .manager import SceneManager
from .websocket import async_register_commands


async def async_setup(hass, config):
    hass.data.setdefault(DOMAIN, {})
    async_register_commands(hass)
    await hass.http.async_register_static_paths([
        StaticPathConfig(
            "/stateful_scenes_revisited/panel.js",
            str(Path(__file__).parent / "frontend" / "panel.js"),
            False,
        )
    ])
    return True


async def async_setup_entry(hass, entry):
    manager = SceneManager(hass, dict(entry.options or entry.data))
    await manager.async_start()
    hass.data[DOMAIN][entry.entry_id] = manager
    try:
        await hass.config_entries.async_forward_entry_setups(entry, [Platform.SWITCH])
        await panel_custom.async_register_panel(
            hass, frontend_url_path=PANEL_PATH, webcomponent_name="stateful-scenes-revisited-panel",
            sidebar_title="Stateful Scenes Revisited", sidebar_icon="mdi:palette",
            module_url="/stateful_scenes_revisited/panel.js?v=0.1.0-scene-sidebar", require_admin=True,
        )
        entry.async_on_unload(entry.add_update_listener(async_update_options))
        manager.notify()
    except Exception:
        manager.stop()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        await hass.config_entries.async_unload_platforms(entry, [Platform.SWITCH])
        raise
    return True


async def async_unload_entry(hass, entry):
    if not await hass.config_entries.async_unload_platforms(entry, [Platform.SWITCH]):
        return False
    manager = hass.data[DOMAIN].pop(entry.entry_id)
    manager.stop()
    ha_frontend.async_remove_panel(hass, PANEL_PATH)
    return True


async def async_update_options(hass, entry):
    """Apply scene scope changes without interrupting the open panel."""
    if manager := hass.data.get(DOMAIN, {}).get(entry.entry_id):
        manager.config = dict(entry.options or entry.data)
        manager.discover()
