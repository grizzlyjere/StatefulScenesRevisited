import pytest

from custom_components.stateful_scenes_revisited.comparison import EntityState, compare_scene


def compare(target, actual, tolerance=0, **kwargs):
    return compare_scene({"light.desk": target}, {"light.desk": actual}, tolerance, **kwargs)


def test_only_defined_attributes_and_list_normalization():
    assert not compare(EntityState("on", {"rgb_color": [1, 2, 3]}), EntityState("on", {"rgb_color": (1, 2, 3), "friendly_name": "Desk"}))


@pytest.mark.parametrize(("brightness", "matches"), [(107, True), (108, False), (93, True), (92, False)])
def test_brightness_tolerance(brightness, matches):
    assert (not compare(EntityState("on", {"brightness": 100}), EntityState("on", {"brightness": brightness}), 3)) == matches


def test_brightness_exact_and_boundary():
    target = {"light.desk": EntityState("on", {"brightness": 100})}
    actual = {"light.desk": EntityState("on", {"brightness": 151})}
    assert not compare_scene(target, actual, 20)
    assert compare_scene(target, actual, 0)


def test_tolerance_only_applies_to_light_brightness():
    target = {"sensor.desk": EntityState("on", {"brightness": 100})}
    actual = {"sensor.desk": EntityState("on", {"brightness": 101})}
    assert compare_scene(target, actual, 100)


def test_ignore_all_attributes_still_requires_state():
    assert not compare(EntityState("on", {"brightness": 100}), EntityState("on", {}), ignore_attributes=True)
    assert compare(EntityState("on", {}), EntityState("off", {}), ignore_attributes=True)


def test_selected_ignored_attributes():
    assert not compare(EntityState("on", {"effect": "rainbow", "brightness": 100}), EntityState("on", {"brightness": 100}), ignored_attributes=("effect",))


@pytest.mark.parametrize("state", ["unknown", "unavailable"])
def test_unhealthy_entity_never_matches(state):
    assert compare(EntityState(state, {}), EntityState(state, {}), ignore_attributes=True)[0]["reason"] == state


def test_missing_entity_and_attribute():
    assert compare_scene({"light.desk": EntityState("off", {})}, {}, 0)[0]["reason"] == "missing"
    assert compare(EntityState("on", {"brightness": 0}), EntityState("on", {}))[0]["reason"] == "missing_attribute"


def test_zero_brightness_not_missing():
    assert not compare(EntityState("off", {"brightness": 0}), EntityState("off", {"brightness": 0}))
