"""Single-instance setup and scene scope options."""

import probatio as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import label_registry as lr, selector

from .const import CONF_SCENE_SCOPE, CONF_SCENE_TAG, DOMAIN, SCOPE_ALL, SCOPE_TAG


async def scope_step(flow, step_id, user_input, current):
    """Share the scope form between initial setup and options."""
    if user_input is not None:
        if user_input[CONF_SCENE_SCOPE] == SCOPE_TAG:
            return await flow.async_step_tag()
        return flow.async_create_entry(title="Stateful Scenes Revisited", data={CONF_SCENE_SCOPE: SCOPE_ALL})
    return flow.async_show_form(step_id=step_id, data_schema=vol.Schema({
        vol.Required(CONF_SCENE_SCOPE, default=current.get(CONF_SCENE_SCOPE, SCOPE_ALL)):
            selector.SelectSelector(selector.SelectSelectorConfig(options=[
                {"value": SCOPE_ALL, "label": "All scenes"},
                {"value": SCOPE_TAG, "label": "Scenes with a label"},
            ], mode=selector.SelectSelectorMode.LIST)),
    }))


async def tag_step(flow, user_input, current):
    """Resolve an existing label or create one from the entered name."""
    registry = lr.async_get(flow.hass)
    errors = {}
    if user_input is not None:
        value = user_input[CONF_SCENE_TAG].strip()
        if value:
            label = registry.async_get_label(value) or registry.async_get_label_by_name(value)
            if label is None:
                label = registry.async_create(value)
            return flow.async_create_entry(title="Stateful Scenes Revisited", data={
                CONF_SCENE_SCOPE: SCOPE_TAG, CONF_SCENE_TAG: label.label_id,
            })
        errors[CONF_SCENE_TAG] = "empty_tag"
    field = vol.Required(CONF_SCENE_TAG)
    if tag := current.get(CONF_SCENE_TAG):
        if registry.async_get_label(tag):
            field = vol.Required(CONF_SCENE_TAG, default=tag)
    return flow.async_show_form(step_id="tag", errors=errors, data_schema=vol.Schema({
        field: selector.SelectSelector(selector.SelectSelectorConfig(
            options=[{"value": label.label_id, "label": label.name} for label in
                     sorted(registry.async_list_labels(), key=lambda label: label.name.casefold())],
            custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN,
        )),
    }))


class StatefulScenesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return await scope_step(self, "user", user_input, {})

    async def async_step_tag(self, user_input=None):
        return await tag_step(self, user_input, {})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return StatefulScenesOptionsFlow()


class StatefulScenesOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        return await scope_step(self, "init", user_input, self.config_entry.options or self.config_entry.data)

    async def async_step_tag(self, user_input=None):
        return await tag_step(self, user_input, self.config_entry.options or self.config_entry.data)
