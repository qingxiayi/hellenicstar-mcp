"""法达与年小限纯引擎测试；第三方库存在时追加开发期对拍。"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from services import time_lords as tl


SCREENSHOT_START_DATES_UTC = [
    "1987-08-09", "1988-11-20", "1990-03-05", "1991-06-18",
    "1992-09-29", "1994-01-12", "1995-04-26", "1996-08-08",
    "1998-03-05", "1999-09-30", "2001-04-26", "2002-11-21",
    "2004-06-17", "2006-01-12", "2007-08-09", "2009-04-26",
    "2011-01-12", "2012-09-29", "2014-06-17", "2016-03-04",
    "2017-11-20", "2019-08-09", "2020-08-08", "2021-08-08",
    "2022-08-08", "2023-08-08", "2024-08-08", "2025-08-08",
    "2026-08-08", "2028-01-12", "2029-06-17", "2030-11-21",
    "2032-04-25", "2033-09-29",
]


def _golden_firdaria(**kwargs):
    return tl.calculate_firdaria(
        datetime(1987, 8, 9, 6, 0, tzinfo=timezone.utc),
        "Asia/Shanghai",
        False,
        max_age=47,
        **kwargs,
    )


def test_firdaria_golden_dates_match_reference_table():
    result = _golden_firdaria()
    assert [row["start_date_utc"] for row in result["rows"][:34]] == SCREENSHOT_START_DATES_UTC
    # 日期列可能因时区跨日；精确时刻和两套日期都必须保留，不能静默混为一列。
    assert result["rows"][1]["start_date"] == "1988-11-21"
    assert result["rows"][1]["start_date_utc"] == "1988-11-20"


def test_firdaria_rules_nodes_subperiods_and_repeat():
    result = tl.calculate_firdaria(
        datetime(2000, 1, 1, tzinfo=timezone.utc), "UTC", True, max_age=80
    )
    majors = result["major_periods"]
    assert [p["ruler"]["name"] for p in majors[:9]] == [
        "Sun", "Venus", "Mercury", "Moon", "Saturn", "Jupiter", "Mars",
        "North Node", "South Node",
    ]
    assert majors[8]["end_age"] == pytest.approx(75.0)
    assert majors[9]["ruler"]["name"] == "Sun"
    assert [r["minor_lord"]["name"] for r in result["rows"][:7]] == [
        "Sun", "Venus", "Mercury", "Moon", "Saturn", "Jupiter", "Mars",
    ]
    node_rows = [r for r in result["rows"] if r["major_lord"]["key"] in tl.NODES]
    assert node_rows
    assert all(row["minor_lord"] is None for row in node_rows)
    for previous, following in zip(result["rows"], result["rows"][1:]):
        previous_end = datetime.fromisoformat(previous["end_at"]).astimezone(timezone.utc)
        following_start = datetime.fromisoformat(following["start_at"]).astimezone(timezone.utc)
        assert previous_end == following_start


def test_firdaria_bonatti_only_moves_night_nodes():
    birth = datetime(2000, 1, 1, tzinfo=timezone.utc)
    night = tl.calculate_firdaria(birth, "UTC", False, max_age=75, tradition="bonatti")
    day = tl.calculate_firdaria(birth, "UTC", True, max_age=75, tradition="bonatti")
    assert [p["ruler"]["name"] for p in night["major_periods"][:9]] == [
        "Moon", "Saturn", "Jupiter", "Mars", "North Node", "South Node",
        "Sun", "Venus", "Mercury",
    ]
    assert [p["ruler"]["name"] for p in day["major_periods"][:9]][-2:] == [
        "North Node", "South Node",
    ]


def test_firdaria_current_interval_is_half_open():
    birth = datetime(2000, 1, 1, tzinfo=timezone.utc)
    boundary = birth + timedelta(days=10 * tl.FIRDARIA_YEAR_DAYS)
    before = tl.calculate_firdaria(
        birth, "UTC", True, max_age=20,
        now=boundary - timedelta(microseconds=1),
    )
    at = tl.calculate_firdaria(birth, "UTC", True, max_age=20, now=boundary)
    assert before["current"]["major_lord"]["name"] == "Sun"
    assert at["current"]["major_lord"]["name"] == "Venus"


def test_annual_profection_switches_on_local_birthday_date():
    zone = ZoneInfo("Asia/Shanghai")
    birth = datetime(1987, 8, 9, 14, 0, tzinfo=zone)
    before = tl.calculate_annual_profections(
        10.0, birth, max_age=50, now=datetime(2026, 8, 8, 23, 59, tzinfo=zone)
    )
    birthday = tl.calculate_annual_profections(
        10.0, birth, max_age=50, now=datetime(2026, 8, 9, 0, 0, tzinfo=zone)
    )
    assert before["current"]["age"] == 38
    assert birthday["current"]["age"] == 39
    assert before["current"]["activated_house"] == 3
    assert birthday["current"]["activated_house"] == 4


def test_annual_profection_leap_day_policy_is_explicit():
    birth = datetime(2000, 2, 29, 8, 30, tzinfo=timezone.utc)
    result = tl.calculate_annual_profections(
        0.0, birth, max_age=3, now=datetime(2001, 2, 28, tzinfo=timezone.utc)
    )
    assert result["leap_day_policy"] == "february_28_in_non_leap_years"
    assert result["rows"][1]["start_date"] == "2001-02-28"
    assert result["current"]["age"] == 1


def test_annual_profection_returns_system_specific_signs_and_lords():
    birth = datetime(2000, 1, 1, 8, 30, tzinfo=timezone.utc)
    # Age 1 activates house 2 in both systems. Whole Sign counts Taurus from
    # the Aries Ascendant; this Placidus house 2 cusp is also Taurus.
    cusps = (10, 50, 80, 110, 140, 170, 190, 220, 250, 280, 310, 340)
    row = tl.calculate_annual_profections(
        10.0,
        birth,
        placidus_cusps=cusps,
        max_age=2,
        now=datetime(2001, 6, 1, tzinfo=timezone.utc),
    )["current"]
    assert row["age"] == 1
    assert row["profected_longitude"] == 40.0
    assert row["houses"] == {"placidus": 2, "whole_sign": 2}
    assert row["activated_house"] == 2
    assert row["systems"]["placidus"]["sign"]["key"] == "taurus"
    assert row["systems"]["placidus"]["lord"]["key"] == "venus"
    assert row["systems"]["whole_sign"]["sign"]["key"] == "taurus"
    assert row["systems"]["whole_sign"]["lord"]["key"] == "venus"


def test_annual_profection_placidus_uses_same_numbered_cusp_ruler():
    birth = datetime(2000, 1, 1, 8, 30, tzinfo=timezone.utc)
    # Aries rises, so Whole Sign house 2 is Taurus/Venus. The Placidus second
    # cusp is deliberately Gemini, so its result must be Gemini/Mercury.
    cusps = (10, 61, 80, 110, 140, 170, 190, 220, 250, 280, 310, 340)
    row = tl.calculate_annual_profections(
        10.0,
        birth,
        placidus_cusps=cusps,
        max_age=2,
        now=datetime(2001, 6, 1, tzinfo=timezone.utc),
    )["current"]
    assert row["systems"]["whole_sign"]["sign"]["key"] == "taurus"
    assert row["systems"]["whole_sign"]["lord"]["key"] == "venus"
    assert row["systems"]["placidus"]["sign"]["key"] == "gemini"
    assert row["systems"]["placidus"]["lord"]["key"] == "mercury"


def test_annual_profection_matches_aixingpan_1976_visible_differences():
    birth = datetime(1976, 2, 1, 9, 50, tzinfo=ZoneInfo("Asia/Shanghai"))
    asc_lon = 7.362927332859617
    cusps = (
        7.362927332859617, 46.516659, 72.466410, 93.959457,
        116.095190, 144.344757, 187.362927, 226.516659,
        252.466410, 273.959457, 296.095190, 324.344757,
    )
    result = tl.calculate_annual_profections(
        asc_lon, birth, placidus_cusps=cusps, max_age=61,
        now=datetime(2028, 2, 1, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    by_age = {row["age"]: row for row in result["rows"]}
    expected = {
        52: (5, "moon", "sun"),
        53: (6, "sun", "mercury"),
        59: (12, "saturn", "jupiter"),
    }
    for age, (house, placidus_lord, whole_lord) in expected.items():
        row = by_age[age]
        assert row["start_date"] == f"{1976 + age}-02-01"
        assert row["systems"]["placidus"]["house"] == house
        assert row["systems"]["whole_sign"]["house"] == house
        assert row["systems"]["placidus"]["lord"]["key"] == placidus_lord
        assert row["systems"]["whole_sign"]["lord"]["key"] == whole_lord


def test_against_astrologica_when_available():
    astrologica = pytest.importorskip("astrologica")
    from astrologica import firdaria, profection

    chart = SimpleNamespace(is_diurnal=False, ascendant=10.0)
    reference = firdaria.compute_firdaria(chart, max_age_years=82.0)
    ours = tl.calculate_firdaria(
        datetime(2000, 1, 1, tzinfo=timezone.utc), "UTC", False, max_age=82
    )
    planet_map = {
        "MOON": "moon", "SATURN": "saturn", "JUPITER": "jupiter",
        "MARS": "mars", "SUN": "sun", "VENUS": "venus", "MERCURY": "mercury",
        "TRUE_NODE": "north_node", "SOUTH_TRUE_NODE": "south_node",
        "NORTH_NODE": "north_node", "SOUTH_NODE": "south_node",
    }
    assert len(reference) == len(ours["major_periods"])
    for ref, actual in zip(reference, ours["major_periods"]):
        assert planet_map[ref.ruler.name] == actual["ruler"]["key"]
        assert ref.start_age == pytest.approx(actual["start_age"])
        assert ref.end_age == pytest.approx(actual["end_age"])
        actual_subs = [
            row for row in ours["rows"]
            if row["major_lord"]["key"] == actual["ruler"]["key"]
            and actual["start_age"] <= row["start_age"] < actual["end_age"]
            and row["minor_lord"] is not None
        ]
        assert [planet_map[sub.ruler.name] for sub in ref.sub_periods] == [
            sub["minor_lord"]["key"] for sub in actual_subs
        ]

    prof_ref = profection.compute_annual_profection(chart, age_years=39)
    prof_ours = tl.calculate_annual_profections(
        10.0,
        datetime(2000, 1, 1, tzinfo=timezone.utc),
        max_age=40,
        now=datetime(2039, 6, 1, tzinfo=timezone.utc),
    )["current"]
    assert prof_ref.profected_house == prof_ours["activated_house"]
    assert prof_ref.profected_sign.name.lower() == prof_ours["profected_sign"]["key"]
    assert planet_map[prof_ref.lord_of_year.name] == prof_ours["lord_of_year"]["key"]


def test_against_stellium_dates_when_available():
    pytest.importorskip("stellium")
    from stellium.engines.firdaria import FirdariaEngine

    birth = datetime(1987, 8, 9, 6, tzinfo=timezone.utc)
    chart = SimpleNamespace(
        is_time_unknown=False,
        sect="night",
        datetime=SimpleNamespace(utc_datetime=birth),
    )
    reference = FirdariaEngine(chart, max_age=47).calculate()
    ours = _golden_firdaria()
    for ref, actual in zip(reference.majors(), ours["major_periods"]):
        assert ref.ruler == actual["ruler"]["name"]
        assert ref.start == datetime.fromisoformat(actual["start_at"]).astimezone(timezone.utc)
        assert ref.end == datetime.fromisoformat(actual["end_at"]).astimezone(timezone.utc)
