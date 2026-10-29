99.9% Vibe coded...But it seems to work

# Stateful Scenes Revisited

A custom Home Assistant integration that gives scenes observable on/off state, native switch entities, and a live comparison panel.  It's based on the same idea as the Stateful Scenes added on, but shares no code.  I created this because I ran into problems with Stateful Scenes not correctly reflecting the state of the scene and laking any practical way to see why.  I also didn't like that each scene had multiple entities for config.  Helpful to be able to tweak everything via a script or automation, but adds a lot when trying to sift through entities.

This is installed under `custom_components`, rather than in the Supervisor add-on store. An integration runs inside Home Assistant and can access scene target definitions and create native entities without a separate container, MQTT broker, or access token. No cloud service or frontend build is required.

## Install

Requires **Home Assistant Core 2026.10**. Other versions have not been verified.

1. Copy `custom_components/stateful_scenes_revisited` into `/config/custom_components/stateful_scenes_revisited` on your Home Assistant installation. Keep all files and the `frontend` and `translations` folders.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration**, search for **Stateful Scenes Revisited**, and complete setup.
4. Open **Stateful Scenes Revisited** in the sidebar to inspect differences and save settings. This panel is available to administrators.

By default, each scene gets a switch with a name such as **Evening Stateful Scenes Revisited**. Home Assistant assigns the entity ID; it can be renamed through its entity settings. Only one instance of this integration is allowed.

## Scene scope

Open the sidebar panel’s **Global Config → Scene monitoring** section to choose **All scenes** or **Scenes with a label**, then click **Save scene scope**. In label mode, select an existing label or choose **Add a new label…** and enter its name. The same settings are also available during setup and through **Settings → Devices & services → Stateful Scenes Revisited → Configure**. Existing installations continue to use all scenes until changed.

Select an existing Home Assistant label from the label dropdown, or choose **Add a new label…** to create one. The dropdown loads the Home Assistant label registry directly and refreshes when opened. To label a generated switch, open **Scene Config**, select a monitored scene, open **Configuration → Switch labels**, use the searchable **Labels** tag picker, and click **Save labels**. The picker loads all labels defined in Home Assistant and displays the switch's current assignments as removable chips. Type to filter, select multiple labels, remove a chip with its × button, or use **Clear all**. Arrow keys highlight options, Enter toggles a label, Escape closes the list, and Backspace removes the last chip when the search is empty. Changes remain unsaved until **Save labels**; saving updates the generated switch's complete label assignment. The help text identifies the target switch entity ID, including renamed switches. Scenes without a generated switch have a disabled picker. Labels are refreshed asynchronously when the configuration tab or picker opens. Scene monitoring scope continues to use labels assigned to the original scene; switch labels do not change that scope. You can also manage labels in Home Assistant entity settings. Creating a label does not automatically assign it to scenes. Only scenes with that label receive switches and appear by default in the comparison panel. Scenes without an entity registry entry cannot have labels and are excluded in label mode. Label assignments and removals are detected automatically; switching back to all scenes includes every scene again. Per-scene comparison settings are retained when a scene leaves the selected scope.

## Behavior

- A switch is on only when every entity state and every non-ignored attribute in the scene definition matches. Extra attributes on the current entity are irrelevant.
- Turning on the switch calls `scene.turn_on` with the underlying scene entity ID. It does not optimistically mark the scene as matched: actual device updates determine the switch state.
- Turning off the switch performs no scene or device action. If the scene still matches, the switch stays on.
- Missing, unknown, and unavailable member entities prevent a match and appear in the differences table.
- Scene additions, replacements, deletion, and `scene.reload` are discovered automatically, with a short debounce to coalesce reload events. YAML edits take effect after the normal Home Assistant scene reload.
- Settings persist in Home Assistant's `.storage/stateful_scenes_revisited` file. Use the UI to change them. Registered scene identities keep settings and switch identities across scene renames. Scenes without a registry identity use their entity ID; renaming these creates a new identity.

## Brightness tolerance

The global default is **3 percentage points** of the full brightness range. Each scene can override this, or leave its override blank to inherit the global default. Values from 0 through 100 are accepted; 0 requires an exact brightness match.

Home Assistant stores light brightness on a 0–255 scale. The inclusive comparison is:

```text
abs(current_brightness - scene_brightness) <= tolerance_percent * 255 / 100
```

For a target of 100 and tolerance of 3, values from 93 through 107 match. The tolerance applies only to the `brightness` attribute of `light` entities. Other attributes compare exactly, including list/tuple values by their contents.

## Attribute exclusions and differences

The sidebar panel has two page-level tabs: **Scene Config** and **Global Config**. Scene Config opens first and contains a left navigation listing available scenes with compact search and filter controls. Selecting a scene shows its details on the right, including its **Compare/Debug** (selected first) and **Configuration** tabs for settings, live differences, and scene activation. Global Config contains the default brightness tolerance. Each tab group supports arrow keys, Home, and End independently. Switching page or scene-feature tabs preserves the selected scene, active scene-feature tab, and in-progress form edits. The differences table shows the entity, field, target value, and observed value, and updates as relevant entities change.

Opening Compare/Debug requests fresh comparison details from the server. Missing details and request failures show an explicit message. The panel asset URL includes a fingerprint of its contents so updates request the current JavaScript.

Compare/Debug displays the selected scene entity ID and every compared member state and attribute, including matching values. Matching rows are green and nonmatching rows are red. The Result column identifies mismatches that keep the switch off. Ignored rows keep a neutral background. Ignored restorable attributes are shown with an explanatory result and do not block matching. Attributes that activation does not restore are omitted. Missing or unavailable entities retain their target attribute rows. Targets come from Home Assistant's loaded scene definition; if membership differs from the scene editor, reload scenes after saving the definition.

The scene navigation supports case-insensitive name search, **Only monitored scenes** (enabled by default, using the configured all-scenes or label scope), and an **Area** filter. Turn off **Only monitored scenes** to browse other discovered scenes without adding them to monitoring. Combine the filters to narrow the list; the count shows how many scenes remain. Areas use the scene entity's assigned Home Assistant area, falling back to its device's area. Choose **No area** for unassigned scenes. Filters affect only the scene list and do not change scene scope or switch creation.

For each scene you can:

- Ignore **all attributes**, comparing entity state strings only.
- Uncheck attributes in the **Attributes to compare** list to ignore them, then save the scene settings. Checked attributes are compared; unchecked attributes are ignored for all members of that scene. Saved exclusions remain unchecked when you return to the scene. **Ignore all attributes** disables the list while preserving the individual choices.
- Save a brightness tolerance override.

In **Global Config → Global attribute ignore list**, edit attributes to ignore for every scene. The initial list includes `supported_color_modes`, `effect_list`, and `supported_features`, including on existing installations. Enter one name per line or separate names with commas, then save. Clear the field and save to remove all global exclusions. Global and per-scene exclusions apply together; checking a scene attribute cannot override a global exclusion. Ignored restorable fields remain visible in Compare/Debug. Home Assistant snapshot metadata and non-restorable fields are omitted even when included in the ignore list.

Snapshot metadata (`friendly_name`, `supported_features`, `icon`, and group `entity_id`) does not determine a match. For lights, comparison follows the values Home Assistant restores: off targets compare state only; null values and capability metadata are informational; on targets compare brightness, effect, color mode, and the color representation selected by that mode. Other entity attributes continue to compare literally unless excluded. Compare/Debug omits these informational values.

## Supported scenes and limits

Scenes created through Home Assistant's scene editor, YAML scenes, and runtime `scene.create` snapshots expose target definitions and are supported. Scenes exposed by third-party integrations may be opaque: Home Assistant knows how to activate them but cannot inspect their targets. These scenes still get a switch, but it is unavailable, and the panel explains why comparison is unavailable. When membership is exposed, the panel lists those entities and their current states with **Target unavailable** instead of inventing target states. They can still be activated from the panel. Empty definitions are also unavailable rather than treated as a match.

The scene definition adapter in `manager.py` uses Home Assistant's internal `homeassistant_scene` platform and `scene_config.states`, because the scene entity state only exposes membership, not the desired member states. This API may require updates after Home Assistant upgrades. No scene files are parsed or modified.

The comparison/settings panel and its WebSocket commands require administrator access. Native switches use Home Assistant's ordinary entity and service permissions. Scene activation uses the user's normal `scene.turn_on` service path. The panel loads only the bundled JavaScript, and scene names and values are rendered as text.

## Development

Python 3.14.2+ and `uv`:

```sh
uv sync --group dev
uv run pytest -q
node --check custom_components/stateful_scenes_revisited/frontend/panel.js
```

Tests exercise comparison boundaries, attribute exclusions, missing entities, persistence, real Home Assistant scene services, definition reloads, switch activation and deletion, native switch platform setup/unload, and administrator checks. Home Assistant is pinned to 2026.10.0 for reproducibility.

To preview just the UI with synthetic data:

```sh
python3 -m http.server 8765 --bind 127.0.0.1
```

Visit `http://127.0.0.1:8765/tests/frontend-preview.html`. The preview uses a mock Home Assistant connection and does not control devices.

Package for manual installation:

```sh
python3 scripts/package.py
```

Extract `dist/stateful-scenes-revisited-0.1.1.zip` into `/config` so that the resulting directory is `/config/custom_components/stateful_scenes_revisited`.

Architecture reference: [Home Assistant integrations](https://contributors.home-assistant.io/core/integrations/), [scene implementation in Core 2026.10.0](https://github.com/home-assistant/core/blob/2026.10.0/homeassistant/components/homeassistant/scene.py), and [custom frontend panels](https://www.home-assistant.io/integrations/panel_custom/).
