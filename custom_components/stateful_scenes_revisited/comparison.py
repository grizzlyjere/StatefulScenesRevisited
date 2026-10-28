"""Pure scene comparison; no Home Assistant runtime required."""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class EntityState:
    state: str
    attributes: Mapping[str, Any]


def compare_scene(
    expected: Mapping[str, EntityState],
    current: Mapping[str, EntityState],
    tolerance: float,
    ignore_attributes: bool = False,
    ignored_attributes: tuple[str, ...] = (),
    *,
    include_matches: bool = False,
) -> list[dict[str, Any]]:
    """Compare restorable attributes present in the definition.

    Brightness tolerance is an inclusive number of percentage points of the
    full 0..255 range. Missing/unknown/unavailable members never match.
    Full debug output also includes ignored restorable attributes.
    """
    differences = []
    for entity_id, target in expected.items():
        actual = current.get(entity_id)
        unhealthy = actual is None or actual.state in ("unknown", "unavailable")
        reason = (
            "missing" if actual is None else actual.state if unhealthy
            else "match" if actual.state == target.state else "different"
        )
        if include_matches or reason != "match":
            differences.append({
                "entity_id": entity_id, "field": "state", "expected": target.state,
                "actual": actual.state if actual else None, "reason": reason,
            })
        for attribute, value in target.attributes.items():
            if _attribute_is_not_restored(entity_id, target, attribute, value):
                continue
            skipped = (
                "ignored" if ignore_attributes or attribute in ignored_attributes
                else None
            )
            if skipped and not include_matches:
                continue
            present = actual is not None and attribute in actual.attributes
            observed = actual.attributes.get(attribute) if actual else None
            matches = present and _equal(value, observed)
            if (
                present and entity_id.startswith("light.") and attribute == "brightness"
                and _number(value) and _number(observed)
            ):
                matches = abs(value - observed) <= tolerance * 255 / 100 + 1e-9
            if unhealthy and not include_matches:
                continue
            reason = skipped or (
                "missing" if actual is None else actual.state if unhealthy
                else "match" if matches else "different" if present else "missing_attribute"
            )
            if include_matches or reason != "match":
                differences.append({
                    "entity_id": entity_id, "field": attribute, "expected": value,
                    "actual": observed, "reason": reason,
                })
    return differences


def _attribute_is_not_restored(entity_id: str, target: EntityState, attribute: str, value: Any) -> bool:
    """Exclude snapshot metadata and light values activation does not restore."""
    if attribute in {"friendly_name", "supported_features", "icon", "entity_id"}:
        return True
    if not entity_id.startswith("light."):
        return False
    restorable = {
        "brightness", "effect", "color_mode", "color_temp_kelvin", "hs_color",
        "rgb_color", "rgbw_color", "rgbww_color", "xy_color",
    }
    if target.state == "off" or attribute not in restorable or value is None:
        return True
    # HA restores only the color representation selected by color_mode.
    color_attributes = {
        "color_temp": "color_temp_kelvin", "hs": "hs_color", "rgb": "rgb_color",
        "rgbw": "rgbw_color", "rgbww": "rgbww_color", "xy": "xy_color",
    }
    mode = target.attributes.get("color_mode")
    if mode in (*color_attributes, "onoff", "brightness", "white"):
        if attribute in color_attributes.values() and attribute != color_attributes.get(mode):
            return True
    return False


def _number(value: Any) -> bool:
    return isinstance(value, (float, int)) and not isinstance(value, bool) and isfinite(value)


def _equal(left: Any, right: Any) -> bool:
    """HA freezes lists into tuples in state objects; compare them by value."""
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return left.keys() == right.keys() and all(_equal(v, right[k]) for k, v in left.items())
    return left == right
