import pytest

from services.jones_pattern import PLANETS, calculate_jones_pattern


def calculate(values):
    return calculate_jones_pattern({p[0]: {"longitude": v} for p, v in zip(PLANETS, values)})


@pytest.mark.parametrize("values, pattern, expected", [
    ([0, 20, 45, 70, 95, 120, 145, 170, 195, 277.5], "Bucket", {"冥王星": (True, 0)}),
    ([i * 100 / 8 for i in range(9)] + [200], "Sling", {"冥王星": (False, 30)}),
    ([0, 10, 20, 30, 40, 50, 60, 70, 80, 220], "Fanhandle", {"冥王星": (True, 0)}),
    ([0, 20, 40, 60, 75, 100, 130, 150, 258, 264], "ConjHandle",
     {"海王星": (True, 3), "冥王星": (False, 9)}),
    ([100.84, 115, 125, 148.865, 160, 170, 185, 196.89, 308, 328.865], "TwoHandle",
     {"海王星": (False, 20.865), "冥王星": (True, 0)}),
])
@pytest.mark.parametrize("rotation", [0, 103])
def test_every_handle_gets_its_own_computed_mark_and_readable_status(values, pattern, expected, rotation):
    dto = calculate([(v + rotation) % 360 for v in values])
    assert dto["pattern_en"] == pattern
    roles = {r["planet_name"]: r for r in dto["key_roles"] if "geometry_marks" in r}
    assert set(roles) == set(expected)
    for name, (matched, deviation) in expected.items():
        role = roles[name]
        axis_marks = [m for m in role["geometry_marks"] if m["code"] == "handle_on_bowl_axis"]
        assert len(axis_marks) == 1  # two descriptions of one axis, not double evidence
        assert axis_marks[0]["matched"] is matched
        assert axis_marks[0]["deviation_deg"] == pytest.approx(deviation)
        assert axis_marks[0]["orb_deg"] == 8
        expected_text = "合虚空中点／对分碗底几何点：" + ("成立" if matched else "不成立")
        assert expected_text in role["description"]
        if len(expected) == 1:
            assert not any(m["code"] in ("handle_pair_conjunction", "handle_group_on_bowl_axis")
                           for m in role["geometry_marks"])


def test_single_handle_geometric_contact_does_not_fabricate_planet_opposition():
    # Bowl midpoint 90, void 270; handle 278 is on-axis within 8 degrees.
    # The nearest main-group planet is 80: actual opposition misses by 18 degrees.
    dto = calculate([0, 20, 40, 60, 80, 110, 130, 155, 180, 278])
    assert dto["pattern_en"] == "Bucket"
    role = next(r for r in dto["key_roles"] if r["role_type"] == "handle")
    assert role["geometry_marks"][0]["matched"] is True
    assert "对分碗底附近的火星（实际行星）：不成立" in role["description"]
    assert any(m["code"] == "handle_opposes_centre_planet" and m["deviation_deg"] == 18
               and not m["matched"] for m in role["geometry_marks"])


def test_mcp_projections_keep_axis_and_per_handle_marks_without_prose():
    from services.mcp_natal import _strip_text
    from services.natal_jones_view import project_observation_details, build_jones_view
    dto = calculate([0, 20, 40, 60, 75, 100, 130, 150, 258, 264])
    classical = _strip_text(dto)
    assert classical["bowl_axis"] == dto["bowl_axis"]
    details = project_observation_details(dto)
    view, _ = build_jones_view({"jones": {"observation_details": details}},
                           {"planet_profiles": {}, "selection_audit": [], "method": {"config": {"orb_view": 6}}})
    assert view["geometry"]["bowl_axis"] == dto["bowl_axis"]
    expected = {r["planet_name"]: r["geometry_marks"] for r in dto["key_roles"] if "geometry_marks" in r}
    actual = {r["raw_planet"]: r["geometry_marks"] for r in view["observation_roles"] if "geometry_marks" in r}
    assert actual == expected
    assert all("description" not in r for r in classical["key_roles"] + details["roles"])
    view["geometry"]["bowl_axis"]["handles"].clear()
    assert len(dto["bowl_axis"]["handles"]) == 2
