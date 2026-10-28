"""Authenticated live comparisons and administrator-only settings."""

import math

import probatio as vol

from homeassistant.components import websocket_api
from homeassistant.core import callback
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import CONF_SCENE_SCOPE, CONF_SCENE_TAG, DOMAIN, SCOPE_ALL, SCOPE_TAG


def tolerance(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise vol.Invalid("Expected a number of percentage points")
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise vol.Invalid("Tolerance must be between 0 and 100")
    return float(value)


def _manager(hass, connection, msg):
    manager = next(iter(hass.data.get(DOMAIN, {}).values()), None)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Stateful Scenes Revisited is not loaded")
    return manager


@websocket_api.websocket_command({"type": f"{DOMAIN}/subscribe"})
@websocket_api.require_admin
@callback
def subscribe(hass, connection, msg):
    if (manager := _manager(hass, connection, msg)) is None:
        return

    @callback
    def send():
        current = next(iter(hass.data.get(DOMAIN, {}).values()), None)
        connection.send_event(msg["id"], current.snapshot() if current else {
            "brightness_tolerance": 3, "scenes": [],
        })

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(hass, f"{DOMAIN}_updated", send)
    connection.send_result(msg["id"])
    send()


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/settings",
    vol.Required("brightness_tolerance"): tolerance,
})
@websocket_api.require_admin
@websocket_api.async_response
async def settings(hass, connection, msg):
    if (manager := _manager(hass, connection, msg)) is None:
        return
    await manager.async_save(msg)
    connection.send_result(msg["id"])


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/scope",
    vol.Required(CONF_SCENE_SCOPE): vol.In([SCOPE_ALL, SCOPE_TAG]),
    vol.Optional(CONF_SCENE_TAG): str,
    vol.Optional("new_tag"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def scope(hass, connection, msg):
    if (manager := _manager(hass, connection, msg)) is None:
        return
    entry_id = next(key for key, value in hass.data[DOMAIN].items() if value is manager)
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None:
        connection.send_error(msg["id"], "not_loaded", "Integration configuration is unavailable")
        return
    options = {**entry.data, **entry.options, CONF_SCENE_SCOPE: msg[CONF_SCENE_SCOPE]}
    options.pop(CONF_SCENE_TAG, None)
    if msg[CONF_SCENE_SCOPE] == SCOPE_TAG:
        registry = lr.async_get(hass)
        if "new_tag" in msg:
            name = msg["new_tag"].strip()
            if not name:
                connection.send_error(msg["id"], "invalid_tag", "Enter a label name")
                return
            label = registry.async_get_label_by_name(name) or registry.async_create(name)
        else:
            label = registry.async_get_label(msg.get(CONF_SCENE_TAG, ""))
        if label is None:
            connection.send_error(msg["id"], "invalid_tag", "Select an existing label or add a new one")
            return
        options[CONF_SCENE_TAG] = label.label_id
    hass.config_entries.async_update_entry(entry, options=options)
    manager.config = dict(options)
    manager.discover()
    connection.send_result(msg["id"])


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/scene_settings",
    vol.Required("scene_key"): str,
    vol.Required("brightness_tolerance"): vol.Any(None, tolerance),
    vol.Required("ignore_attributes"): bool,
    vol.Required("ignored_attributes"): [str],
})
@websocket_api.require_admin
@websocket_api.async_response
async def scene_settings(hass, connection, msg):
    if (manager := _manager(hass, connection, msg)) is None:
        return
    try:
        await manager.async_save(msg)
    except ValueError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    connection.send_result(msg["id"])


@callback
def async_register_commands(hass):
    for command in (subscribe, settings, scope, scene_settings):
        websocket_api.async_register_command(hass, command)
