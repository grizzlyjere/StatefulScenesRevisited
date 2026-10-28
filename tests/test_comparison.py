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


def test_full_comparison_includes_matching_entities_and_keeps_differences():
    target = {
        "light.reading": EntityState("on", {"brightness": 100}),
        "fan.ceiling": EntityState("on", {"percentage": 50}),
        "switch.desk": EntityState("off", {}),
    }
    current = {**target, "fan.ceiling": EntityState("on", {"percentage": 75})}
    rows = compare_scene(target, current, 3, include_matches=True)
    assert [(row["entity_id"], row["field"], row["reason"]) for row in rows] == [
        ("light.reading", "state", "match"),
        ("light.reading", "brightness", "match"),
        ("fan.ceiling", "state", "match"),
        ("fan.ceiling", "percentage", "different"),
        ("switch.desk", "state", "match"),
    ]
    assert [row for row in rows if row["reason"] != "match"] == compare_scene(target, current, 3)


def test_full_comparison_respects_exclusions_and_missing_members():
    target = {"light.reading": EntityState("on", {"brightness": 100})}
    rows = compare_scene(target, target, 0, ignored_attributes=("brightness",), include_matches=True)
    assert len(rows) == 2
    assert rows[1]["reason"] == "ignored"
    assert rows[0]["field"] == "state"
    assert rows[0]["reason"] == "match"
    assert compare_scene(target, {}, 0, include_matches=True)[0]["reason"] == "missing"


def test_light_snapshot_metadata_nulls_and_off_values_do_not_block_match():
    target = EntityState("off", {"brightness": 100, "color_mode": None, "friendly_name": "Old name"})
    assert not compare(target, EntityState("off", {}))
    rows = compare(target, EntityState("off", {}), include_matches=True)
    assert [(row["field"], row["reason"]) for row in rows] == [("state", "match")]
    assert compare(target, EntityState("on", {}))[0]["field"] == "state"


def test_only_active_light_color_representation_is_compared():
    target = EntityState("on", {"color_mode": "xy", "xy_color": [0.3, 0.4], "rgb_color": [100, 120, 140]})
    actual = EntityState("on", {"color_mode": "xy", "xy_color": [0.3, 0.4], "rgb_color": [99, 119, 139]})
    assert not compare(target, actual)
    assert [row["field"] for row in compare(target, actual, include_matches=True)] == ["state", "color_mode", "xy_color"]
    assert compare(target, EntityState("on", {"color_mode": "xy", "xy_color": [0.5, 0.4]}))


def test_unavailable_member_still_shows_every_defined_attribute():
    rows = compare(EntityState("on", {"brightness": 51}), EntityState("unavailable", {}), include_matches=True)
    assert [(row["field"], row["reason"]) for row in rows] == [("state", "unavailable"), ("brightness", "unavailable")]


@pytest.mark.parametrize("options", [{}, {"ignore_attributes": True}, {"ignored_attributes": ("friendly_name", "effect", "supported_features")}])
def test_non_restored_fields_are_omitted_even_when_ignored(options):
    target = EntityState("on", {"brightness": 51, "effect": None, "friendly_name": "Desk", "supported_features": 44})
    rows = compare(target, EntityState("on", {"brightness": 51}), include_matches=True, **options)
    assert [row["field"] for row in rows] == ["state", "brightness"]
