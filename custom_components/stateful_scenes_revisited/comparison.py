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
) -> list[dict[str, Any]]:
    """Compare only attributes present in the definition.

    Brightness tolerance is an inclusive number of percentage points of the
    full 0..255 range. Missing/unknown/unavailable members never match.
    """
    differences = []
    for entity_id, target in expected.items():
        actual = current.get(entity_id)
        if actual is None or actual.state in ("unknown", "unavailable"):
            differences.append({
                "entity_id": entity_id, "field": "state", "expected": target.state,
                "actual": actual.state if actual else None,
                "reason": "missing" if actual is None else actual.state,
            })
            continue
        if actual.state != target.state:
            differences.append({
                "entity_id": entity_id, "field": "state", "expected": target.state,
                "actual": actual.state, "reason": "different",
            })
        if ignore_attributes:
            continue
        for attribute, value in target.attributes.items():
            if attribute in ignored_attributes:
                continue
            present = attribute in actual.attributes
            observed = actual.attributes.get(attribute)
            matches = present and _equal(value, observed)
            if (
                present and entity_id.startswith("light.") and attribute == "brightness"
                and _number(value) and _number(observed)
            ):
                matches = abs(value - observed) <= tolerance * 255 / 100 + 1e-9
            if not matches:
                differences.append({
                    "entity_id": entity_id, "field": attribute, "expected": value,
                    "actual": observed, "reason": "different" if present else "missing_attribute",
                })
    return differences


def _number(value: Any) -> bool:
    return isinstance(value, (float, int)) and not isinstance(value, bool) and isfinite(value)


def _equal(left: Any, right: Any) -> bool:
    """HA freezes lists into tuples in state objects; compare them by value."""
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return left.keys() == right.keys() and all(_equal(v, right[k]) for k, v in left.items())
    return left == right
