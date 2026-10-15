from types import MappingProxyType

import pytest
import swisseph as swe

from services.forecast_natal import ForecastNatalSnapshot, ForecastPoint, snapshot_from_engine_data
from services import transit_natal


def _snapshot():
    names = (
        "sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn",
        "uranus", "neptune", "pluto", "chiron", "north_node", "south_node",
        "fortuna", "spiritus",
    )
    return ForecastNatalSnapshot(
        context=None,
        birth_jd_ut=2451545.0,
        planets=MappingProxyType({
            name: ForecastPoint(index * 20.0, index % 12 + 1)
            for index, name in enumerate(names)
        }),
        axes=MappingProxyType({"asc": 5.0, "mc": 95.0, "dsc": 185.0, "ic": 275.0}),
        natal_engine_version="test",
        cusps=tuple(5.0 + index * 30.0 for index in range(12)),
    )


def test_transit_groups_are_complete_and_exclusive():
    flattened = [planet for group in transit_natal.TRANSIT_GROUPS.values() for planet in group]
    assert set(flattened) == set(transit_natal.BODY_IDS)
    assert len(flattened) == len(set(flattened)) == 6


def test_snapshot_includes_fortune_and_spirit():
    class Ctx:
        julian_day_ut = 2451545.0

    snapshot = snapshot_from_engine_data(Ctx(), {
        "planets": {"sun": {"longitude": 10, "house": 1}},
        "special_points": {
            "part_of_fortune": {"longitude": 20, "house": 2},
            "part_of_spirit": {"longitude": 30, "house": 3},
        },
        "axes": {
            "ascendant": {"longitude": 0}, "midheaven": {"longitude": 90},
            "descendant": {"longitude": 180}, "imum_coeli": {"longitude": 270},
        },
        "houses": {"cusps": list(range(0, 360, 30))},
    })
    assert snapshot.planets["fortuna"].longitude == 20
    assert snapshot.planets["spiritus"].longitude == 30


def test_active_aspects_use_group_orbs_and_axes_only_conjunction(monkeypatch):
    snapshot = _snapshot()
    monkeypatch.setattr(transit_natal, "BODY_IDS", {"saturn": swe.SATURN, "mars": swe.MARS})
    monkeypatch.setattr(transit_natal.transit_utils, "body_position", lambda body, jd: ((5.9 if body == swe.SATURN else 6.4), 0.1))
    monkeypatch.setattr(transit_natal.transit_utils, "body_lon", lambda body, jd: (5.8 if body == swe.SATURN else 6.3))
    rows, _ = transit_natal.active_aspects(snapshot, 2451545.0)
    axis_rows = [row for row in rows if row["natal_point"] in transit_natal.AXES]
    assert axis_rows
    assert {row["angle"] for row in axis_rows} == {0.0}
    assert any(row["transit_planet"] == "saturn" and row["natal_point"] == "asc" for row in rows)
    assert any(row["transit_planet"] == "mars" and row["natal_point"] == "asc" for row in rows)


def test_wheel_contains_fixed_natal_lots_and_full_transit_display_ring(monkeypatch):
    monkeypatch.setattr(
        transit_natal.transit_utils, "body_position",
        lambda body, jd: (float(body % 360), -0.1 if body == swe.SATURN else 0.1),
    )
    monkeypatch.setattr(transit_natal.transit_utils, "body_lon", lambda body, jd: float(body % 360))
    wheel = transit_natal.compute_wheel(_snapshot(), 2451545.0)
    assert {"fortuna", "spiritus"} <= set(wheel["natal"]["planets"])
    assert set(wheel["transit"]["planets"]) == set(transit_natal.DISPLAY_POINT_ORDER)
    assert {"sun", "moon", "mercury", "venus", "chiron", "north_node", "south_node"} <= set(wheel["transit"]["planets"])
    assert "angles" not in wheel["transit"]
    assert wheel["transit"]["planets"]["saturn"]["retrograde"] is True


def test_display_ring_is_full_but_calculation_groups_stay_on_six_planets():
    assert len(transit_natal.DISPLAY_POINT_ORDER) == 13
    assert set(transit_natal.BODY_IDS) == {
        "mars", "jupiter", "saturn", "uranus", "neptune", "pluto",
    }


def test_events_include_lots_and_keep_multiple_contacts(monkeypatch):
    requested_lo = 2451545.0
    monkeypatch.setattr(
        transit_natal.transit_utils,
        "all_exact_to_fixed_in_window",
        lambda body, fixed, aspects, lo, hi: (
            [(requested_lo + 1, "fortuna", 0.0), (requested_lo + 2, "spiritus", 60.0), (requested_lo + 3, "fortuna", 0.0)]
            if "fortuna" in fixed else []
        ),
    )
    monkeypatch.setattr(transit_natal.transit_utils, "body_position", lambda body, jd: (0.0, -0.1 if int(jd) % 2 else 0.1))
    result = transit_natal.compute_events(_snapshot(), 2451545.0, 2451550.0)
    assert {row["natal_point"] for row in result["events"]} >= {"fortuna", "spiritus"}
    series = [row for row in result["events"] if row["transit_planet"] == "saturn" and row["natal_point"] == "fortuna"]
    assert len(series) == 2
    assert [row["contact_index"] for row in series] == [1, 2]
    assert all(row["contact_total"] == 2 for row in series)


def test_event_series_uses_expanded_window_for_contact_numbers(monkeypatch):
    requested_lo = 2451545.0
    requested_hi = requested_lo + 20.0

    def fake_hits(body, fixed, aspects, lo, hi):
        assert lo == requested_lo - transit_natal.SERIES_WINDOW_DAYS
        assert hi == requested_hi + transit_natal.SERIES_WINDOW_DAYS
        if "sun" not in fixed:
            return []
        return [
            (requested_lo - 10.0, "sun", 0.0),
            (requested_lo + 5.0, "sun", 0.0),
            (requested_hi + 10.0, "sun", 0.0),
        ]

    monkeypatch.setattr(transit_natal, "BODY_IDS", {"saturn": swe.SATURN})
    monkeypatch.setattr(transit_natal.transit_utils, "all_exact_to_fixed_in_window", fake_hits)
    monkeypatch.setattr(transit_natal.transit_utils, "body_position", lambda body, jd: (0.0, 0.1))
    result = transit_natal.compute_events(_snapshot(), requested_lo, requested_hi)
    # 窗口外的首末两次才是这个环的两端，窗口内那次是中间接触。
    # 折叠后中间接触不再单独成行，因此窗口内没有事件可返回。
    assert result["events"] == []


def test_contact_rings_keep_only_first_and_last_contact(monkeypatch):
    requested_lo = 2451545.0
    requested_hi = requested_lo + 400.0

    def fake_hits(body, fixed, aspects, lo, hi):
        if "sun" not in fixed:
            return []
        return [
            (requested_lo + 10.0, "sun", 0.0),
            (requested_lo + 100.0, "sun", 0.0),
            (requested_lo + 200.0, "sun", 0.0),
        ]

    monkeypatch.setattr(transit_natal, "BODY_IDS", {"saturn": swe.SATURN})
    monkeypatch.setattr(transit_natal.transit_utils, "all_exact_to_fixed_in_window", fake_hits)
    monkeypatch.setattr(transit_natal.transit_utils, "body_position", lambda body, jd: (0.0, 0.1))
    events = transit_natal.compute_events(_snapshot(), requested_lo, requested_hi)["events"]
    assert [row["entry_role"] for row in events] == ["first", "final"]
    assert [row["contact_index"] for row in events] == [1, 3]
    assert all(row["contact_total"] == 3 for row in events)


def test_single_contact_ring_is_marked_only(monkeypatch):
    requested_lo = 2451545.0
    requested_hi = requested_lo + 100.0

    def fake_hits(body, fixed, aspects, lo, hi):
        return [(requested_lo + 10.0, "sun", 0.0)] if "sun" in fixed else []

    monkeypatch.setattr(transit_natal, "BODY_IDS", {"saturn": swe.SATURN})
    monkeypatch.setattr(transit_natal.transit_utils, "all_exact_to_fixed_in_window", fake_hits)
    monkeypatch.setattr(transit_natal.transit_utils, "body_position", lambda body, jd: (0.0, 0.1))
    events = transit_natal.compute_events(_snapshot(), requested_lo, requested_hi)["events"]
    assert len(events) == 1
    assert events[0]["entry_role"] == "only"
    assert events[0]["contact_total"] == 1


def test_event_series_splits_separate_cycles(monkeypatch):
    requested_lo = 2451545.0
    requested_hi = requested_lo + 900.0

    def fake_hits(body, fixed, aspects, lo, hi):
        if "sun" not in fixed:
            return []
        return [
            (requested_lo + 20.0, "sun", 0.0),
            (requested_lo + 120.0, "sun", 0.0),
            (requested_lo + 650.0, "sun", 0.0),
            (requested_lo + 750.0, "sun", 0.0),
        ]

    monkeypatch.setattr(transit_natal, "BODY_IDS", {"mars": swe.MARS})
    monkeypatch.setattr(transit_natal.transit_utils, "all_exact_to_fixed_in_window", fake_hits)
    monkeypatch.setattr(transit_natal.transit_utils, "body_position", lambda body, jd: (0.0, 0.1))
    result = transit_natal.compute_events(_snapshot(), requested_lo, requested_hi)
    assert [row["contact_total"] for row in result["events"]] == [2, 2, 2, 2]
    assert len({row["series_id"] for row in result["events"]}) == 2


def test_node_axis_is_single_row_with_equivalent_south_node(monkeypatch):
    snapshot = _snapshot()
    north_lon = snapshot.planets["north_node"].longitude

    monkeypatch.setattr(transit_natal, "BODY_IDS", {"jupiter": swe.JUPITER})
    monkeypatch.setattr(transit_natal, "DISPLAY_BODY_IDS", {"jupiter": swe.JUPITER, "north_node": swe.MEAN_NODE})
    monkeypatch.setattr(
        transit_natal.transit_utils,
        "body_position",
        lambda body, jd: (north_lon + 180.0, 0.1) if body == swe.JUPITER else (20.0, -0.1),
    )
    monkeypatch.setattr(transit_natal.transit_utils, "body_lon", lambda body, jd: north_lon + 180.0)
    rows, _ = transit_natal.active_aspects(snapshot, 2451545.0)
    node_rows = [row for row in rows if row["natal_point"] in ("north_node", "south_node")]
    assert len(node_rows) == 1
    assert node_rows[0]["natal_point"] == "north_node"
    assert node_rows[0]["aspect"] == "冲"
    assert node_rows[0]["equivalent_natal_point"] == "south_node"
    assert node_rows[0]["equivalent_aspect"] == "合"


def test_event_range_is_capped_at_three_years():
    with pytest.raises(ValueError, match="三年"):
        transit_natal.compute_events(_snapshot(), 2451545.0, 2451545.0 + 1099)


def test_wheel_cross_aspects_forward_the_applying_flag():
    """行运比较盘必须把入相/出相带给前端。

    active_aspects 一直算了 applying，但 compute_wheel 组装 cross_aspects 时
    漏传，导致点击星盘弹出的相位卡没有这个标记——数据算了却没送到。
    """
    snapshot = _snapshot()
    jd = 2451545.0
    wheel = transit_natal.compute_wheel(snapshot, jd)
    rows = wheel["cross_aspects"]
    assert rows, "样例盘应当有跨盘相位"
    assert all("applying" in row for row in rows)

    # 与 active_aspects 的同一对相位方向必须一致，不能两处各说各话。
    active = {
        (row["transit_planet"], row["natal_point"], row["angle"]): row["applying"]
        for row in wheel["active_aspects"]
    }
    for row in rows:
        key = (row["sr_planet"], row["natal_planet"], row["angle"])
        assert row["applying"] == active[key]


def test_applying_probe_does_not_jump_over_an_imminent_exact_contact(monkeypatch):
    """极接近精确点时仍应标为入相，不能因一小时探测跨点而判反。"""
    snapshot = _snapshot()  # 本命太阳 0°
    monkeypatch.setattr(transit_natal, "BODY_IDS", {"mars": swe.MARS})
    monkeypatch.setattr(
        transit_natal,
        "DISPLAY_BODY_IDS",
        {"mars": swe.MARS, "north_node": swe.MEAN_NODE},
    )

    def position(body, jd):
        if body == swe.MARS:
            # 火星位于 359.99°、顺行 0.5°/日：1.44 分钟后更接近 0°，
            # 但一小时后会越过 0°，旧算法会误判为出相。
            return 359.99, 0.5
        return 180.0, -0.05

    monkeypatch.setattr(transit_natal.transit_utils, "body_position", position)
    rows, _ = transit_natal.active_aspects(snapshot, 2451545.0)
    hit = next(
        row for row in rows
        if row["transit_planet"] == "mars"
        and row["natal_point"] == "sun"
        and row["angle"] == 0.0
    )
    assert hit["applying"] is True
    assert hit["phase_zh"] == "入相"


def test_applying_is_unknown_when_transit_is_stationary():
    assert transit_natal._applying(10.0, 0.0, 100.0, 90.0) is None
