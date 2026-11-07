"""The bowl centre must follow the occupied arc, including across 0 degrees."""

import pytest

from engine.jones import detect_with_variants, result_to_dict
from services.jones_pattern import PLANETS, calculate_jones_pattern


@pytest.mark.parametrize("rotation", [0, 45, 90, 180, 220, 300])
@pytest.mark.parametrize("longitudes, parent, centre", [
    ([100.84, 115, 125, 140, 155, 170, 185, 196.89, 300, 320], "See-Saw", 148.865),
    ([0, 20, 150, 168, 174, 184, 211, 229, 234, 289], "See-Saw", 219.5),
    ([100.84, 115, 125, 140, 155, 170, 185, 196.89, 280, 20], "Bucket", 148.865),
    ([0, 20, 40, 60, 80, 100, 120, 140, 240, 300], "Locomotive", 70),
])
def test_two_handle_bowl_direction_across_detection_paths(longitudes, parent, centre, rotation):
    values = [(value + rotation) % 360 for value in longitudes]
    result = detect_with_variants(values)
    assert result.pattern_en == "TwoHandle"
    assert result.extra["parent_pattern"] == parent
    handle = result.extra["two_handle"]
    # The directed boundary arc is the void, not the occupied bowl.
    assert (handle["right_edge"] - handle["left_edge"]) % 360 == pytest.approx(
        360 - handle["bowl_span"])
    expected = (centre + rotation) % 360
    engine = result_to_dict(result)
    planets = {planet_id: {"longitude": longitude}
               for (planet_id, _, _), longitude in zip(PLANETS, values)}
    dto = calculate_jones_pattern(planets)
    for actual in (engine["cog_bowl"]["long"], dto["cog_bowl"]["long"]):
        assert abs((actual - expected + 180) % 360 - 180) <= 0.006
    axis = dto["bowl_axis"]
    assert axis["bowl_bottom"]["longitude"] == pytest.approx(expected)
    assert axis["void_midpoint"]["longitude"] == pytest.approx((expected + 180) % 360)
    assert axis["handle_pair_conjunction"]["within_orb"] is False
    assert axis["handle_group_midpoint"] is None


def test_two_handle_bowl_anchor_and_role_use_main_group_not_handle():
    values = [100.84, 115, 125, 148.865, 160, 170, 185, 196.89, 308, 328.865]
    dto = calculate_jones_pattern({planet_id: {"longitude": longitude}
        for (planet_id, _, _), longitude in zip(PLANETS, values)})
    assert dto["pattern_en"] == "TwoHandle"
    assert dto["cog_bowl"] == {"long": 148.87, "planet_name": "金星", "is_anchor": True}
    role = next(role for role in dto["key_roles"] if role["role_type"] == "cog_bowl")
    assert role["planet_name"] == "金星"
    assert role["longitude"] == pytest.approx(148.865)


def dto_for(values):
    return calculate_jones_pattern({planet_id: {"longitude": longitude}
        for (planet_id, _, _), longitude in zip(PLANETS, values)})


@pytest.mark.parametrize("rotation", [0, 103, 220])
@pytest.mark.parametrize("handles, individual, group", [
    ([252, 258], [True, True], True),
    ([258, 264], [True, False], True),
    ([264, 270], [False, False], False),
    ([263, 269], [True, False], False),  # inclusive 8-degree threshold
    ([263.0001, 269.0001], [False, False], False),
])
def test_conj_handles_mutual_conjunction_and_axis_contacts_are_independent(rotation, handles, individual, group):
    values = [(v + rotation) % 360 for v in [0, 20, 40, 60, 75, 100, 130, 150] + handles]
    dto = dto_for(values)
    assert dto["pattern_en"] == "ConjHandle"
    axis = dto["bowl_axis"]
    assert axis["bowl_bottom"]["longitude"] == (75 + rotation) % 360
    assert axis["void_midpoint"]["longitude"] == (255 + rotation) % 360
    assert axis["handle_pair_conjunction"]["within_orb"] is True
    by_name = {h["planet_name"]: h for h in axis["handles"]}
    for name, expected in zip(("海王星", "冥王星"), individual):
        handle = by_name[name]
        assert handle["void_midpoint_conjunction"]["within_orb"] is expected
        assert handle["bowl_bottom_opposition"] ["within_orb"] is expected
    mid = axis["handle_group_midpoint"]
    assert mid["kind"] == "geometric_midpoint"
    assert mid["longitude"] == pytest.approx(((handles[0] + handles[1]) / 2 + rotation) % 360)
    assert mid["void_midpoint_conjunction"]["within_orb"] is group


def test_centered_conj_handles_do_not_imply_real_planet_oppositions():
    dto = dto_for([0, 20, 40, 60, 65, 100, 130, 150, 252, 258])
    axis = dto["bowl_axis"]
    assert axis["handle_group_midpoint"]["void_midpoint_conjunction"]["within_orb"]
    handles = {h["planet_name"]: h for h in axis["handles"]}
    for handle in handles.values():
        assert handle["bowl_bottom_opposition"]["within_orb"]
    assert handles["海王星"]["centre_planet_oppositions"] == [
        {"planet_name": "火星", "label": "对分碗底附近行星", "deviation_deg": 7.0, "within_orb": True}]
    assert handles["冥王星"]["centre_planet_oppositions"] == [
        {"planet_name": "火星", "label": "对分碗底附近行星", "deviation_deg": 13.0, "within_orb": False}]


@pytest.mark.parametrize("values, pattern, bottom, void", [
    (list(range(0, 181, 20)), "Bowl", 90, 270),
    ([0, 20, 45, 70, 95, 120, 145, 170, 195, 277.5], "Bucket", 97.5, 277.5),
    ([i * 100 / 8 for i in range(9)] + [200], "Sling", 50, 230),
    ([0, 10, 20, 30, 40, 50, 60, 70, 80, 220], "Fanhandle", 40, 220),
])
def test_bowl_axis_preserves_pure_bowl_void_and_other_handle_families(values, pattern, bottom, void):
    dto = dto_for(values)
    assert dto["pattern_en"] == pattern
    axis = dto["bowl_axis"]
    assert axis["bowl_bottom"]["longitude"] == bottom
    assert axis["void_midpoint"]["longitude"] == void
    if pattern in ("Bowl", "Bucket"):
        assert dto["midpoint_bowl"]["long"] == void
    assert dto["cog_bowl"]["long"] == bottom
    assert len(axis["handles"]) == (0 if pattern == "Bowl" else 1)


def test_non_bowl_pattern_has_no_bowl_axis():
    assert dto_for([10, 18, 28, 40, 50, 58, 65, 72, 80, 88])["bowl_axis"] is None
