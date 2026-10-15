# -*- coding: utf-8 -*-
"""services/progressed_phase.py —— 次限月相、换相日月定位与行运土星落宫。

单一职责：次限太阳/月亮经度（一日一年）→ Rudhyar 8 阶段月相 + 阶段时间轴，
以及每个月相阶段转换时刻的次限日月星座/本命落宫、行运土星落宫与四轴
（Asc/MC/Dsc/IC）触发检测。不含 Flask/DB 依赖。

阶段公式是次限太阳与次限月亮的夹角（跟本命月相 calculate_moon_phase() 同一条公式，
只是喂次限值），不是次限月亮与本命月亮的距离——那是另一个概念（次限月亮返照周期，
~27.3 年），跟 Rudhyar 的 Progressed Lunation Cycle（~29.5 年，跟朔望月同周期）不是一回事。

一日一年换算沿用 services/solar_arc_engine.py 的惯例：次限儒略日 = birth_jd + age，
真实对应的民用日期 = birth_jd + age * TROPICAL_YEAR_DAYS。
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import swisseph as swe

from services.ephemeris_guard import EphemerisModeError, apply_ephe_path, _mode_of
from services.solar_arc_engine import TROPICAL_YEAR_DAYS, MAX_SUPPORTED_AGE
from services.transit_ephemeris import longitude_at as _transit_longitude_at
from engine.natal_chart import NatalChartCalculator

ENGINE_VERSION = "progressed-lunation-4"
PHASE_STEP_DEG = 45.0
AXIS_ORB_DEG = 3.0
_AGE_TOLERANCE = 1e-6
_POS_FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED
_ZODIAC_ZH = (
    "白羊座", "金牛座", "双子座", "巨蟹座", "狮子座", "处女座",
    "天秤座", "天蝎座", "射手座", "摩羯座", "水瓶座", "双鱼座",
)
_ZODIAC_GLYPHS = ("♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓")


@dataclass(frozen=True)
class ProgressedPositions:
    sun_lon: float
    moon_lon: float


def _body_longitude(planet_const, jd):
    """次限太阳/月亮经度，strict swieph（回退 Moshier 直接抛错，不冒充精确结果）。"""
    xx, rflag = swe.calc_ut(jd, planet_const, _POS_FLAGS)
    mode = _mode_of(rflag)
    if mode != "swieph":
        apply_ephe_path()
        xx, rflag = swe.calc_ut(jd, planet_const, _POS_FLAGS)
        mode = _mode_of(rflag)
    if mode != "swieph":
        raise EphemerisModeError(
            "progressed_phase 要求 swieph 文件模式，planet=%d JD=%.5f 返回 %s（旗标 %d）"
            % (planet_const, jd, mode, rflag)
        )
    return xx[0] % 360.0


def progressed_positions(birth_jd, age):
    """次限太阳/月亮经度：jd = birth_jd + age（一日一年）。"""
    jd = birth_jd + age
    return ProgressedPositions(
        sun_lon=_body_longitude(swe.SUN, jd),
        moon_lon=_body_longitude(swe.MOON, jd),
    )


def phase_snapshot(birth_jd, age):
    """次限月相快照：复用本命版 calculate_moon_phase()，只是喂次限日月经度。"""
    pos = progressed_positions(birth_jd, age)
    calc = NatalChartCalculator()
    phase = calc.calculate_moon_phase(pos.sun_lon, pos.moon_lon)
    within_phase = phase["angle_diff"] % PHASE_STEP_DEG
    phase["progress_pct"] = round(within_phase / PHASE_STEP_DEG * 100, 1)
    phase["sun_lon"] = pos.sun_lon
    phase["moon_lon"] = pos.moon_lon
    return phase


def _raw_diff(birth_jd, age):
    pos = progressed_positions(birth_jd, age)
    return (pos.moon_lon - pos.sun_lon) % 360.0


def solve_phase_age(birth_jd, target_diff, min_age, max_age):
    """找次限日月夹角首次等于 target_diff（0-360）的年龄，逐年 bracket + 二分。

    月亮黄经速度恒为正（几何上从不逆行），次限日月夹角在人类寿命窗口内单调递增，
    结构照抄 solar_arc_engine.solve_age()；这里一个 max_age=100 的窗口会经过
    多个 ~29.5 年周期，bracket 循环天然处理多圈（不像太阳弧只需扫一圈）。
    """
    target = target_diff % 360.0

    def residual(age):
        # wrap180（而非直接相减取 %360）：target 本身可能是 0/360，跟 _raw_diff()
        # 的取模断点重合，直接相减会在真正想找的那个交叉点上失去符号翻转。
        # wrap180 把断点挪到 target+180 这个不相干的对跖点上，交叉点本身保持连续。
        return _wrap180(_raw_diff(birth_jd, age) - target)

    left = min_age
    left_value = residual(left)
    if abs(left_value) <= 1e-9:
        return left

    while left < max_age:
        right = min(left + 1.0, max_age)
        right_value = residual(right)
        if abs(right_value) <= 1e-9:
            return right
        if left_value < 0 < right_value:
            while right - left > _AGE_TOLERANCE:
                midpoint = (left + right) / 2.0
                midpoint_value = residual(midpoint)
                if midpoint_value < 0:
                    left = midpoint
                else:
                    right = midpoint
            return (left + right) / 2.0
        left, left_value = right, right_value
    return None


def phase_timeline(birth_jd, as_of_jd, max_age=100, tz=None):
    """0/45/.../315 八个阶段边界在 [0, max_age] 内的全部切换年龄 + 对应民用日期。

    额外算出下一次切换（相对 as_of_jd 的真实剩余天数）。
    """
    max_age = min(max_age, MAX_SUPPORTED_AGE)
    calc = NatalChartCalculator()
    boundaries = []
    for phase_num in range(8):
        target = phase_num * PHASE_STEP_DEG
        age = 0.0
        while age is not None and age < max_age:
            age = solve_phase_age(birth_jd, target, age, max_age)
            if age is None:
                break
            civil_jd = birth_jd + age * TROPICAL_YEAR_DAYS
            boundaries.append({
                "phase_num": phase_num + 1,
                "phase_name": calc.PHASE_NAMES[phase_num],
                "age": round(age, 1),
                "civil_jd": civil_jd,
                "date": _civil_jd_to_date_str(civil_jd, tz=tz),
            })
            age += 1.0  # 跳过本次命中，继续找下一圈同一边界

    boundaries.sort(key=lambda b: b["age"])

    next_boundary = None
    for b in boundaries:
        if b["civil_jd"] > as_of_jd:
            next_boundary = b
            break

    days_to_next = (next_boundary["civil_jd"] - as_of_jd) if next_boundary else None
    return {
        "timeline": boundaries,
        "next_phase": next_boundary,
        "days_to_next_phase": round(days_to_next, 1) if days_to_next is not None else None,
    }


def _civil_jd_to_date_str(jd, tz=None):
    """把 UT 儒略日显示为事件地点的当地民用日期。

    Swiss Ephemeris 的事件 JD 是 UT。直接 ``revjul`` 后截日期会在当地午夜附近
    提前一天；页面时间轴应沿用出生地点的 IANA 时区（含历史 DST）。没有传入时区
    的内部调用仍明确按 UTC 返回，保持向后兼容。
    """
    zone = tz or timezone.utc
    utc_dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
        days=jd - 2440587.5,
    )
    return utc_dt.astimezone(zone).strftime("%Y-%m-%d")


def _wrap180(delta):
    return (delta + 180.0) % 360.0 - 180.0


def _nearest_axis(lon, natal_axes):
    """natal_axes（Asc/MC/Dsc/IC 四值）里离 lon 最近的一个，返回 (轴名, 距离度数)。"""
    nearest_axis, axis_orb = None, None
    for axis_name, axis_lon in natal_axes.items():
        orb = abs(_wrap180(lon - axis_lon))
        if axis_orb is None or orb < axis_orb:
            nearest_axis, axis_orb = axis_name, orb
    return nearest_axis, axis_orb


def saturn_snapshot(event_jd, natal_cusps, natal_axes):
    """指定阶段转换 JD 的行运土星 → 本命落宫、宫头距离与四轴触发。"""
    saturn_lon = _transit_longitude_at("saturn", event_jd)
    calc = NatalChartCalculator()
    house = calc.get_planet_house(saturn_lon, natal_cusps)
    house_cusp = natal_cusps[house - 1]
    degrees_into_house = (saturn_lon - house_cusp) % 360.0

    nearest_axis, axis_orb = _nearest_axis(saturn_lon, natal_axes)

    return {
        "longitude": saturn_lon,
        "house": house,
        "degrees_into_house": round(degrees_into_house, 2),
        "nearest_axis": nearest_axis,
        "axis_orb": round(axis_orb, 2) if axis_orb is not None else None,
        "near_axis": bool(axis_orb is not None and axis_orb <= AXIS_ORB_DEG),
    }


def _light_location(lon, natal_cusps):
    """把次限发光体黄经投影到黄道星座与本命宫位。"""
    longitude = lon % 360.0
    sign_index = int(longitude // 30.0)
    house = NatalChartCalculator().get_planet_house(longitude, natal_cusps)
    return {
        "longitude": longitude,
        "sign_index": sign_index,
        "sign": _ZODIAC_ZH[sign_index],
        "glyph": _ZODIAC_GLYPHS[sign_index],
        "degree_in_sign": longitude % 30.0,
        "natal_house": house,
    }


def progressed_lights_snapshot(birth_jd, event_jd, natal_cusps):
    """指定民用换相时刻对应的次限日月位置，并投影到本命宫位。

    event_jd 是现实时间；需先按一日一年反推精确次限年龄，不能直接把现实 JD
    当成星历时刻，也不能在前端用已四舍五入到 0.1 岁的年龄重新计算。
    """
    age = (event_jd - birth_jd) / TROPICAL_YEAR_DAYS
    positions = progressed_positions(birth_jd, age)
    return {
        "sun": _light_location(positions.sun_lon, natal_cusps),
        "moon": _light_location(positions.moon_lon, natal_cusps),
        "house_reference": "natal_placidus",
    }


def _summary_text(phase, transition):
    text = "次限日月正处%s阶段（已完成%s%%）" % (
        phase["phase_name"], phase["progress_pct"],
    )
    if transition:
        return "%s；本阶段于%s切换，当时行运土星在第%d宫" % (
            text, transition["date"], transition["saturn"]["house"],
        )
    return text


def build_report(birth_jd, as_of_jd, natal_cusps, natal_axes, max_age=100, tz=None):
    """组装次限月相、换相日月定位与行运土星快照为最终响应 dict。"""
    age = (as_of_jd - birth_jd) / TROPICAL_YEAR_DAYS
    phase = phase_snapshot(birth_jd, age)
    timeline = phase_timeline(birth_jd, as_of_jd, max_age=max_age, tz=tz)

    # 土星的参照时刻是“月相阶段切换发生时”，不是查询当天。
    # 每个时间轴节点都绑定它自己 civil_jd 上的行运土星快照；
    # 顶部卡片取 as_of_jd 之前最近的一次切换（即当前阶段起点）。
    for boundary in timeline["timeline"]:
        boundary["progressed_lights"] = progressed_lights_snapshot(
            birth_jd, boundary["civil_jd"], natal_cusps,
        )
        boundary["saturn"] = saturn_snapshot(
            boundary["civil_jd"], natal_cusps, natal_axes,
        )
    current_transition = next(
        (boundary for boundary in reversed(timeline["timeline"])
         if boundary["civil_jd"] <= as_of_jd),
        None,
    )
    saturn = current_transition["saturn"] if current_transition else None
    return {
        "engine_version": ENGINE_VERSION,
        "age": round(age, 1),
        "phase": phase,
        "days_to_next_phase": timeline["days_to_next_phase"],
        "next_phase": timeline["next_phase"],
        "timeline": timeline["timeline"],
        "current_phase_transition": current_transition,
        "saturn": saturn,
        "summary": _summary_text(phase, current_transition),
    }
