# -*- coding: utf-8 -*-
"""tests/test_progressed_phase.py —— 次限月相(Rudhyar 8阶段) × 行运土星落宫单元测试。

覆盖：age=0 退化为本命相位、公式是次限日月夹角(不是次限-本命月亮)、周期~29.5年、
落宫复用 get_planet_house 一致性、轴点±3°边界。全程本地引擎不打网络。
"""
import os
import sys
from datetime import date
from zoneinfo import ZoneInfo

import pytest
import swisseph as swe

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import progressed_phase as pp  # noqa: E402
from engine.natal_chart import NatalChartCalculator  # noqa: E402

# 固定案例：1989-07-11 12:30 CST（武汉）→ 04:30 UT，跟 test_saturn_jupiter_transits.py 同一案例。
BIRTH_JD = swe.julday(1989, 7, 11, 4.5)
NATAL_AXES = {"Asc": 198.06, "MC": 109.28, "Dsc": 18.06, "IC": 289.28}
# 12 个宫头，从 Asc 起等分（不追求天文精确，只为测「落宫」这条纯函数管线）。
NATAL_CUSPS = [(NATAL_AXES["Asc"] + 30 * i) % 360 for i in range(12)]

# Astro-Seek 公共对拍样例：1990-04-15 18:00 Paris（当日 CEST，16:00 UT）。
# 来源：https://horoscopes.astro-seek.com/the-progressed-lunation-cycle-astrology-calculator
# 记录的是该页 8-fold Lunation + Transit Saturn 表中的阶段日期、次限月亮精确黄经
# （结果图 URL 的 chart_deg）和转换时刻行运土星精确黄经（trans_saturn）。
ASTROSEEK_BIRTH_JD = swe.julday(1990, 4, 15, 16.0)
ASTROSEEK_PHASE_DATES = (
    "1992-11-30", "1996-07-24", "1999-10-22", "2002-12-27",
    "2006-06-20", "2010-05-06", "2014-06-08", "2018-07-16",
)
ASTROSEEK_MOON_LONGITUDES = (
    297.9891667, 346.5502778, 34.7150000, 82.8119444,
    131.1913889, 179.9508333, 228.9066667, 277.8711111,
)
ASTROSEEK_SATURN_LONGITUDES = (
    313.50469919034, 7.3763417229831, 44.873058135648, 84.77411734692,
    128.98481037859, 178.3124688912, 228.01299584186, 274.46955335275,
)


def test_age_zero_matches_natal_phase():
    """age=0 → 次限儒略日=birth_jd → 次限日月经度退化为本命值，相位应等于本命 calculate_moon_phase()。"""
    calc = NatalChartCalculator()
    natal_sun = pp._body_longitude(swe.SUN, BIRTH_JD)
    natal_moon = pp._body_longitude(swe.MOON, BIRTH_JD)
    expected = calc.calculate_moon_phase(natal_sun, natal_moon)

    got = pp.phase_snapshot(BIRTH_JD, 0.0)
    assert got["phase_name"] == expected["phase_name"]
    assert got["phase_num"] == expected["phase_num"]
    assert got["angle_diff"] == pytest.approx(expected["angle_diff"])


def test_formula_is_progressed_moon_minus_progressed_sun_not_natal_moon():
    """公式必须是次限日月夹角，不是「次限月亮-本命月亮」（那是次限月亮返照周期，~27.3年周期，不是Rudhyar的8阶段）。"""
    age = 20.0
    sun20 = pp._body_longitude(swe.SUN, BIRTH_JD + age)
    moon20 = pp._body_longitude(swe.MOON, BIRTH_JD + age)
    natal_moon0 = pp._body_longitude(swe.MOON, BIRTH_JD)

    correct_diff = (moon20 - sun20) % 360.0
    wrong_diff = (moon20 - natal_moon0) % 360.0  # 任务文档原文的错公式

    got = pp.phase_snapshot(BIRTH_JD, age)
    assert got["angle_diff"] == pytest.approx(correct_diff)
    # 两个公式在这个年龄上应该明显不同，否则这条测试不足以区分两种实现。
    assert abs(correct_diff - wrong_diff) > 1.0


def test_diff_is_monotonic_increasing_over_age():
    """次限日月夹角在人类寿命窗口内单调递增（月亮黄经速度恒正，从不逆行）。"""
    ages = [i * 0.25 for i in range(0, 400)]  # 0..99.75 岁
    diffs_unwrapped = []
    prev = None
    offset = 0.0
    for age in ages:
        d = pp._raw_diff(BIRTH_JD, age)
        if prev is not None and d < prev - 180:
            offset += 360.0
        diffs_unwrapped.append(d + offset)
        prev = d
    assert all(b >= a - 1e-9 for a, b in zip(diffs_unwrapped, diffs_unwrapped[1:]))


def test_cycle_length_is_about_29_5_years():
    """一圈完整周期（回到同一次限日月夹角）应接近朔望月周期长度 29.5 年，不是 27.3 年（次限月亮返照周期）。"""
    target = pp._raw_diff(BIRTH_JD, 0.0)
    cycle_age = pp.solve_phase_age(BIRTH_JD, target, 1.0, 100.0)
    assert cycle_age is not None
    assert cycle_age == pytest.approx(29.5, abs=1.0)


def test_phase_timeline_boundaries_are_spaced_about_3_69_years_apart():
    result = pp.phase_timeline(BIRTH_JD, BIRTH_JD + 40 * pp.TROPICAL_YEAR_DAYS, max_age=40)
    ages = [b["age"] for b in result["timeline"]]
    assert ages == sorted(ages)
    gaps = [b - a for a, b in zip(ages, ages[1:])]
    assert all(gap == pytest.approx(29.5 / 8, abs=0.5) for gap in gaps)


def test_astroseek_public_case_numerical_regression():
    """外部对拍锁住计算核心；民用日期容许不同次限年钥带来的最多一天差异。"""
    result = pp.phase_timeline(
        ASTROSEEK_BIRTH_JD,
        swe.julday(2026, 7, 18, 12.0),
        max_age=30,
        tz=ZoneInfo("Europe/Paris"),
    )
    timeline = result["timeline"]
    assert len(timeline) == 8

    exact_date_matches = 0
    for boundary, expected_date, expected_moon, expected_saturn in zip(
        timeline,
        ASTROSEEK_PHASE_DATES,
        ASTROSEEK_MOON_LONGITUDES,
        ASTROSEEK_SATURN_LONGITUDES,
    ):
        actual_date = date.fromisoformat(boundary["date"])
        reference_date = date.fromisoformat(expected_date)
        day_error = abs((actual_date - reference_date).days)
        assert day_error <= 1
        exact_date_matches += day_error == 0

        age = (boundary["civil_jd"] - ASTROSEEK_BIRTH_JD) / pp.TROPICAL_YEAR_DAYS
        moon_lon = pp.progressed_positions(ASTROSEEK_BIRTH_JD, age).moon_lon
        # 当前最大误差约 0.011 角分；0.02 角分阈值可发现求根/星历口径退化。
        assert abs(pp._wrap180(moon_lon - expected_moon)) * 60.0 <= 0.02

        saturn_lon = pp._transit_longitude_at("saturn", boundary["civil_jd"])
        # Astro-Seek 的转换时刻口径略有差异，当前最大误差约 2.45 角分。
        assert abs(pp._wrap180(saturn_lon - expected_saturn)) * 60.0 <= 3.0

    # 当地日期转换后 8 个节点有 7 个同日；唯一差异为 1996 年的一日年钥差异。
    assert exact_date_matches >= 7


def test_civil_date_uses_event_location_timezone_near_midnight():
    event_jd = swe.julday(2014, 6, 7, 22.5)
    assert pp._civil_jd_to_date_str(event_jd) == "2014-06-07"
    assert pp._civil_jd_to_date_str(event_jd, ZoneInfo("Europe/Paris")) == "2014-06-08"


def test_saturn_snapshot_house_matches_get_planet_house_directly():
    calc = NatalChartCalculator()
    now_jd = BIRTH_JD + 30.0 * pp.TROPICAL_YEAR_DAYS
    saturn_lon = pp._transit_longitude_at("saturn", now_jd)
    expected_house = calc.get_planet_house(saturn_lon, NATAL_CUSPS)

    snap = pp.saturn_snapshot(now_jd, NATAL_CUSPS, NATAL_AXES)
    assert snap["house"] == expected_house
    assert 0 <= snap["degrees_into_house"] < 360


def test_progressed_lights_snapshot_uses_exact_transition_and_natal_houses():
    event_jd = BIRTH_JD + 25.4321 * pp.TROPICAL_YEAR_DAYS
    snap = pp.progressed_lights_snapshot(BIRTH_JD, event_jd, NATAL_CUSPS)
    exact = pp.progressed_positions(BIRTH_JD, 25.4321)

    assert snap["house_reference"] == "natal_placidus"
    assert snap["sun"]["longitude"] == pytest.approx(exact.sun_lon)
    assert snap["moon"]["longitude"] == pytest.approx(exact.moon_lon)
    for key in ("sun", "moon"):
        light = snap[key]
        assert light["sign"] in pp._ZODIAC_ZH
        assert 0 <= light["degree_in_sign"] < 30
        assert 1 <= light["natal_house"] <= 12
        assert light["natal_house"] == NatalChartCalculator().get_planet_house(
            light["longitude"], NATAL_CUSPS,
        )


@pytest.mark.parametrize("orb,expected", [(2.9, True), (3.1, False)])
def test_axis_orb_boundary(orb, expected):
    """±3° 触发边界：2.9° 内算触发，3.1° 不算。直接测生产用的 _nearest_axis()，
    不复制它的算法——否则实现里 abs()/wrap180()/<= 任何一处改错，测试都发现不了。"""
    axis_lon = NATAL_AXES["MC"]
    saturn_lon = (axis_lon + orb) % 360.0
    natal_axes = dict(NATAL_AXES)
    # 把 MC 以外三轴推得很远，确保「最近轴点」测的就是 MC。
    natal_axes["Asc"] = (axis_lon + 90) % 360.0
    natal_axes["Dsc"] = (axis_lon + 180) % 360.0
    natal_axes["IC"] = (axis_lon + 270) % 360.0

    nearest_axis, axis_orb = pp._nearest_axis(saturn_lon, natal_axes)
    assert nearest_axis == "MC"
    assert (axis_orb <= pp.AXIS_ORB_DEG) == expected


def test_build_report_shape_and_compliance_wording():
    now_jd = BIRTH_JD + 25.0 * pp.TROPICAL_YEAR_DAYS
    report = pp.build_report(BIRTH_JD, now_jd, NATAL_CUSPS, NATAL_AXES, max_age=40)

    assert report["engine_version"] == pp.ENGINE_VERSION
    assert 24.9 < report["age"] < 25.1
    assert report["phase"]["phase_name"]
    assert 1 <= report["saturn"]["house"] <= 12
    assert isinstance(report["timeline"], list) and report["timeline"]
    assert report["age"] == round(report["age"], 1)
    assert all(item["age"] == round(item["age"], 1) for item in report["timeline"])
    assert all(1 <= item["saturn"]["house"] <= 12 for item in report["timeline"])
    assert all(item["progressed_lights"]["house_reference"] == "natal_placidus"
               for item in report["timeline"])
    assert all(1 <= item["progressed_lights"][body]["natal_house"] <= 12
               for item in report["timeline"] for body in ("sun", "moon"))
    transition = report["current_phase_transition"]
    assert transition["civil_jd"] <= now_jd
    assert transition["saturn"] == report["saturn"]
    assert report["saturn"] == pp.saturn_snapshot(
        transition["civil_jd"], NATAL_CUSPS, NATAL_AXES,
    )
    # 不能偷换成查询当天的土星位置。
    assert report["saturn"]["longitude"] != pytest.approx(
        pp.saturn_snapshot(now_jd, NATAL_CUSPS, NATAL_AXES)["longitude"],
        abs=1e-6,
    )
    for banned in ("运势", "预测", "命运", "吉凶", "算命"):
        assert banned not in report["summary"]
    assert report["summary"].startswith("次限日月正处")
