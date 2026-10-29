"""Authenticated live comparisons and administrator-only settings."""

import math

import probatio as vol

from homeassistant.components import websocket_api
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, label_registry as lr
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
    "type": f"{DOMAIN}/comparison",
    vol.Required("scene_key"): str,
})
@websocket_api.require_admin
@callback
def comparison(hass, connection, msg):
    """Return fresh details independently of the live scene list subscription."""
    if (manager := _manager(hass, connection, msg)) is None:
        return
    if msg["scene_key"] not in manager.available_scenes:
        connection.send_error(msg["id"], "not_found", "Scene no longer exists")
        return
    connection.send_result(msg["id"], manager.result(msg["scene_key"]))


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/settings",
    vol.Optional("brightness_tolerance"): tolerance,
    vol.Optional("ignored_attributes"): [str],
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


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/scene_labels",
    vol.Required("scene_key"): str,
    vol.Required("label_ids"): [str],
})
@websocket_api.require_admin
@callback
def scene_labels(hass, connection, msg):
    """Save labels on the generated switch after validating every label."""
    if (manager := _manager(hass, connection, msg)) is None:
        return
    scene = manager.available_scenes.get(msg["scene_key"])
    if scene is None:
        connection.send_error(msg["id"], "not_found", "Scene no longer exists")
        return
    registry = er.async_get(hass)
    entry = manager.switch_entry(msg["scene_key"])
    if entry is None:
        connection.send_error(msg["id"], "not_registered", "The generated switch is unavailable. Monitor this scene before assigning switch labels.")
        return
    labels = set(msg["label_ids"])
    label_registry = lr.async_get(hass)
    if any(label_registry.async_get_label(label_id) is None for label_id in labels):
        connection.send_error(msg["id"], "invalid_label", "A selected label no longer exists. Refresh the labels and try again.")
        return
    registry.async_update_entity(entry.entity_id, labels=labels)
    manager.discover()
    connection.send_result(msg["id"])


@callback
def async_register_commands(hass):
    for command in (subscribe, comparison, settings, scope, scene_settings, scene_labels):
        websocket_api.async_register_command(hass, command)
