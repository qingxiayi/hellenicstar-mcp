from collections import OrderedDict
from datetime import datetime
from types import MappingProxyType, SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from services.forecast_natal import ForecastNatalSnapshot, ForecastPoint
from services import transit_lifetime


def _snapshot(civil_dt="2000-02-29T12:00:00", tz="Asia/Shanghai"):
    context = SimpleNamespace(civil_dt=civil_dt, snapshot=SimpleNamespace(tz_iana=tz))
    planets = {
        key: ForecastPoint(index * 20.0 % 360.0, index % 12 + 1)
        for index, key in enumerate((
            "sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn",
            "uranus", "neptune", "pluto", "chiron", "north_node", "fortuna", "spiritus",
        ))
    }
    axes = {"asc": 0.0, "mc": 90.0, "dsc": 180.0, "ic": 270.0}
    return ForecastNatalSnapshot(
        context=context, birth_jd_ut=2451604.666667,
        planets=MappingProxyType(planets), axes=MappingProxyType(axes),
        natal_engine_version="test",
        cusps=tuple(index * 30.0 for index in range(12)),
    )


def test_lifetime_has_twelve_chapters_and_keeps_the_complete_age_84_band():
    chapters = transit_lifetime.lifetime_chapters(_snapshot())
    assert len(chapters) == 12
    assert chapters[0]["label"] == "0—6岁"
    assert chapters[-1]["label"] == "77—84岁"
    assert chapters[-1]["to_utc"].startswith("2085-02-28T")
    assert chapters[-1]["to_jd"] - chapters[-1]["from_jd"] > 7.9 * 365


def test_lifetime_fast_details_require_planet_and_natal_target():
    snapshot = _snapshot()
    with pytest.raises(ValueError, match="木星或火星"):
        transit_lifetime.compute_lifetime_events(snapshot, 0, group="fast")
    with pytest.raises(ValueError, match="本命目标"):
        transit_lifetime.compute_lifetime_events(
            snapshot, 0, group="fast", planet="mars", target_scope="points",
        )


def test_axes_force_conjunction_and_rows_receive_age(monkeypatch):
    snapshot = _snapshot(civil_dt="2000-01-01T12:00:00")
    captured = {}

    def fake_compute(_snapshot, lo, hi, **kwargs):
        captured.update(kwargs)
        return {"events": [{
            "exact_jd": lo + 30.0, "exact_utc": "2007-01-31T04:00:00Z",
            "transit_planet": "saturn", "natal_point": "asc",
        }]}

    monkeypatch.setattr(transit_lifetime.transit_natal, "compute_filtered_events", fake_compute)
    result = transit_lifetime.compute_lifetime_events(
        snapshot, 1, group="slow", target_scope="axes", aspects=[90.0],
    )
    assert captured["aspects"] == (0.0,)
    assert result["events"][0]["age"] == 7
    assert result["events"][0]["chapter_index"] == 1
    assert result["chapter"]["label"] == "7—13岁"


def test_summary_returns_counts_only_not_lifetime_event_rows(monkeypatch):
    snapshot = _snapshot(civil_dt="2000-01-01T12:00:00")
    chapters = transit_lifetime.lifetime_chapters(snapshot)
    rows = [
        {"exact_jd": chapters[0]["from_jd"] + 1, "group": "slow", "natal_point": "asc", "transit_planet": "saturn"},
        {"exact_jd": chapters[1]["from_jd"] + 1, "group": "fast", "natal_point": "sun", "transit_planet": "mars"},
    ]
    monkeypatch.setattr(transit_lifetime, "_SUMMARY_CACHE", OrderedDict())
    monkeypatch.setattr(
        transit_lifetime.transit_natal, "compute_filtered_events",
        lambda *args, **kwargs: {"events": rows},
    )
    result = transit_lifetime.compute_lifetime_summary(snapshot)
    assert "events" not in result
    assert result["event_count"] == 2
    assert result["chapters"][0]["counts"]["axes"] == 1
    assert result["chapters"][1]["counts"]["fast"] == 1


def test_placidus_house_lookup_handles_zero_degree_wrap():
    cusps = (350, 20, 50, 80, 110, 140, 170, 200, 230, 260, 290, 320)
    assert transit_lifetime._house_for_longitude(355, cusps) == 1
    assert transit_lifetime._house_for_longitude(5, cusps) == 1
    assert transit_lifetime._house_for_longitude(25, cusps) == 2


def test_range_query_rejects_spans_that_would_stall_production(monkeypatch):
    snapshot = _snapshot(civil_dt="2000-01-01T12:00:00")
    lo = transit_lifetime.lifetime_chapters(snapshot)[0]["from_jd"]
    monkeypatch.setattr(
        transit_lifetime.transit_natal, "compute_filtered_events",
        lambda *args, **kwargs: {"events": []},
    )
    over = lo + transit_lifetime.MAX_RANGE_DAYS + 1.0
    with pytest.raises(ValueError, match="不能超过"):
        transit_lifetime.compute_range_events(snapshot, lo, over)
    with pytest.raises(ValueError, match="结束时间"):
        transit_lifetime.compute_range_events(snapshot, lo, lo)
    ok = transit_lifetime.compute_range_events(snapshot, lo, lo + 365.0)
    assert ok["event_count"] == 0
    assert ok["range_days"] == 365.0


def test_exactly_twenty_calendar_years_is_accepted(monkeypatch):
    """整 20 个日历年含闰日约 7305 天，不能被儒略年换算误判成超限。"""
    snapshot = _snapshot(civil_dt="2000-01-01T12:00:00")
    monkeypatch.setattr(
        transit_lifetime.transit_natal, "compute_filtered_events",
        lambda *args, **kwargs: {"events": []},
    )
    start = datetime(2026, 1, 1, tzinfo=ZoneInfo("Asia/Shanghai"))
    end = datetime(2046, 1, 1, tzinfo=ZoneInfo("Asia/Shanghai"))
    lo = transit_lifetime._datetime_to_jd(start)
    hi = transit_lifetime._datetime_to_jd(end)
    assert hi - lo > 365.2425 * 20  # 确认这正是此前被误拒的场景
    result = transit_lifetime.compute_range_events(snapshot, lo, hi)
    assert result["event_count"] == 0


def test_range_query_defaults_to_all_six_trigger_planets(monkeypatch):
    snapshot = _snapshot(civil_dt="2000-01-01T12:00:00")
    lo = transit_lifetime.lifetime_chapters(snapshot)[0]["from_jd"]
    captured = []

    def fake(_s, _lo, _hi, **kwargs):
        captured.append(kwargs)
        return {"events": []}

    monkeypatch.setattr(transit_lifetime.transit_natal, "compute_filtered_events", fake)
    transit_lifetime.compute_range_events(snapshot, lo, lo + 365.0)
    assert all(set(call["planets"]) == set(transit_lifetime.transit_natal.BODY_IDS) for call in captured)
    # 默认混合目标时，轴与普通点分别执行各自的相位规则。
    assert any(call["aspects"] == (0.0,) for call in captured)
    assert any(set(call["aspects"]) == set(transit_lifetime.transit_natal.ASPECT_ANGLES) for call in captured)


def test_range_query_mixes_axes_and_points_with_their_own_aspect_rules(monkeypatch):
    snapshot = _snapshot(civil_dt="2000-01-01T12:00:00")
    lo = transit_lifetime.lifetime_chapters(snapshot)[0]["from_jd"]
    captured = []

    def fake(_snapshot, _lo, _hi, **kwargs):
        captured.append(kwargs)
        return {"events": []}

    monkeypatch.setattr(transit_lifetime.transit_natal, "compute_filtered_events", fake)
    result = transit_lifetime.compute_range_events(snapshot, lo, lo + 365.0)
    assert result["event_count"] == 0
    assert len(captured) == 2
    axis_call = next(call for call in captured if "asc" in call["natal_points"])
    point_call = next(call for call in captured if "sun" in call["natal_points"])
    assert axis_call["aspects"] == (0.0,)
    assert set(point_call["aspects"]) == set(transit_lifetime.transit_natal.ASPECT_ANGLES)


def test_bounds_expose_picker_ready_dates():
    """小程序 picker 的 start/end 只认 YYYY-MM-DD，带 T/Z 的串会被忽略。"""
    bounds = transit_lifetime.lifetime_bounds(_snapshot(civil_dt="2000-01-01T12:00:00"))
    assert bounds["from_date"] == "2000-01-01"
    assert bounds["to_date"] == "2085-01-01"
    assert "T" not in bounds["from_date"] and "Z" not in bounds["to_date"]
    assert bounds["max_range_years"] == transit_lifetime.MAX_RANGE_YEARS


def test_house_ingress_direct_and_retrograde_have_real_stay_intervals(monkeypatch):
    snapshot = _snapshot(civil_dt="2000-01-01T12:00:00")
    lo = transit_lifetime.lifetime_chapters(snapshot)[0]["from_jd"]
    hits = [
        (lo - 20.0, "cusp_1", 0.0),
        (lo + 10.0, "cusp_1", 0.0), (lo + 40.0, "cusp_1", 0.0),
        (lo + 70.0, "cusp_1", 0.0), (lo + 400.0, "cusp_2", 0.0),
    ]
    monkeypatch.setattr(
        transit_lifetime.transit_utils, "all_exact_to_fixed_in_window",
        lambda *args, **kwargs: hits,
    )
    monkeypatch.setattr(
        transit_lifetime.transit_utils, "body_position",
        lambda _body, jd: (0.0, -0.1 if abs(jd - (lo + 40.0)) < 0.1 else 0.1),
    )
    result = transit_lifetime.compute_house_ingresses(snapshot, planet="jupiter")
    assert result["house_system"] == "placidus"
    # 同一宫头的逆行环只留两端：窗前那次是首次进入，lo+70 那次是最终进入，
    # 中间的逆行返回与再次进入都不进时间表。
    ring = [row for row in result["events"] if row["cusp"] == 1]
    assert len(ring) == 1
    final_entry = ring[0]
    assert final_entry["entry_role"] == "final"
    assert final_entry["entry_type_zh"] == "顺行进入"
    assert final_entry["entered_house"] == 1
    assert final_entry["contact_index"] == 4 and final_entry["contact_total"] == 4
    # 停留区间仍由相邻的真实接触界定，不因折叠而拉长。
    assert final_entry["duration_days"] == 330.0
    # 独立一次的过宫标记为单次进入。
    solo = [row for row in result["events"] if row["cusp"] == 2]
    assert len(solo) == 1 and solo[0]["entry_role"] == "only"


def test_house_ingress_keeps_only_first_and_final_entry_per_ring(monkeypatch):
    snapshot = _snapshot(civil_dt="2000-01-01T12:00:00")
    lo = transit_lifetime.lifetime_chapters(snapshot)[0]["from_jd"]
    hits = [(lo + 10.0, "cusp_5", 0.0), (lo + 40.0, "cusp_5", 0.0), (lo + 70.0, "cusp_5", 0.0)]
    monkeypatch.setattr(
        transit_lifetime.transit_utils, "all_exact_to_fixed_in_window",
        lambda *args, **kwargs: hits,
    )
    monkeypatch.setattr(
        transit_lifetime.transit_utils, "body_position",
        lambda _body, jd: (0.0, -0.1 if abs(jd - (lo + 40.0)) < 0.1 else 0.1),
    )
    events = transit_lifetime.compute_house_ingresses(snapshot, planet="saturn")["events"]
    assert [row["entry_role"] for row in events] == ["first", "final"]
    assert [row["contact_index"] for row in events] == [1, 3]
    assert all(row["contact_total"] == 3 for row in events)
    # 中间那次逆行返回不出现在结果里。
    assert all(row["entry_type_zh"] == "顺行进入" for row in events)
