# -*- coding: utf-8 -*-
"""天象盘行星运行状态：逆行前阴影、正式逆行、逆行后阴影。

这里只报告可由星历复算的运动事实，不解释“影响”。阴影区间按逆行弧的三次经过定义：

1. 前阴影开始：行星转逆前最后一次顺行经过未来的转顺点黄经；
2. 正式逆行：转逆驻留（黄经速度过零）到转顺驻留；
3. 后阴影结束：转顺后再次经过先前的转逆点黄经。

星体范围沿用 ``services.sky_now._MOTION_BODIES`` 的既有口径：水星至冥王星，
不含从不逆行的太阳/月亮，也不把交点和凯龙顺手扩进来。
"""
from datetime import datetime, timezone
from functools import lru_cache

import swisseph as swe

from services import transit_utils as tu


MOTION_BODIES = (
    swe.MERCURY, swe.VENUS, swe.MARS, swe.JUPITER, swe.SATURN,
    swe.URANUS, swe.NEPTUNE, swe.PLUTO,
)

PLANET_KEY = {
    swe.MERCURY: "mercury", swe.VENUS: "venus", swe.MARS: "mars",
    swe.JUPITER: "jupiter", swe.SATURN: "saturn", swe.URANUS: "uranus",
    swe.NEPTUNE: "neptune", swe.PLUTO: "pluto",
}
PLANET_CN = {
    swe.MERCURY: "水星", swe.VENUS: "金星", swe.MARS: "火星",
    swe.JUPITER: "木星", swe.SATURN: "土星", swe.URANUS: "天王星",
    swe.NEPTUNE: "海王星", swe.PLUTO: "冥王星",
}
SIGN_CN = ("白羊座", "金牛座", "双子座", "巨蟹座", "狮子座", "处女座",
           "天秤座", "天蝎座", "射手座", "摩羯座", "水瓶座", "双鱼座")

PHASE_CN = {
    "pre_shadow": "逆行前阴影",
    "retrograde": "逆行",
    "post_shadow": "逆行后阴影",
}

# 只影响驻留事件的粗采样；根仍由 transit_utils 二分到秒级以下。
_SAMPLE_DAYS = {
    swe.MERCURY: 1.0, swe.VENUS: 2.0, swe.MARS: 2.0,
    swe.JUPITER: 3.0, swe.SATURN: 3.0, swe.URANUS: 3.0,
    swe.NEPTUNE: 3.0, swe.PLUTO: 3.0,
}
_BISECT_ITERS = 42


def _jd_year(jd: float) -> int:
    return int(swe.revjul(jd, swe.GREG_CAL)[0])


def _jd_iso(jd: float) -> str:
    seconds = (jd - 2440587.5) * 86400.0
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def _position_payload(lon: float) -> dict:
    lon = lon % 360.0
    sign_idx = int(lon // 30.0)
    return {
        "longitude": round(lon, 6),
        "sign_idx": sign_idx,
        "sign_cn": SIGN_CN[sign_idx],
        "deg_in_sign": round(lon % 30.0, 6),
    }


@lru_cache(maxsize=64)
def _station_schedule(planet: int, year: int):
    """返回包住该年的完整驻留序列。

    火星约 26 个月一次逆行，需要比其它行星更宽的窗口，才能保证任意年份附近都
    同时拿到“前一转顺 → 转逆 → 转顺 → 下一转逆”四个边界。结果按行星+年份缓存，
    用户在时间轴上逐日/逐月移动不会重复扫星历。
    """
    pad_years = 2 if planet == swe.MARS else 1
    lo = swe.julday(year - pad_years, 1, 1, 0.0, swe.GREG_CAL)
    hi = swe.julday(year + pad_years + 1, 1, 1, 0.0, swe.GREG_CAL)
    return tuple(tu.all_stations_in_window(
        (planet,), lo, hi,
        sample_hours=_SAMPLE_DAYS[planet] * 24.0,
        bisect_iters=32,
    ))


def _crossing_in_direct_interval(planet: int, target_lon: float,
                                 lo_jd: float, hi_jd: float):
    """在一段足够短的单调顺行区间内求固定黄经交点。"""
    if hi_jd <= lo_jd:
        return None
    lo_lon = tu.body_lon(planet, lo_jd)
    hi_lon = tu.body_lon(planet, hi_jd)
    travel = (hi_lon - lo_lon) % 360.0
    target_travel = (target_lon - lo_lon) % 360.0
    if target_travel > travel + 1e-7:
        return None
    if target_travel <= 1e-10:
        return lo_jd
    if travel - target_travel <= 1e-10:
        return hi_jd

    lo, hi = lo_jd, hi_jd
    for _ in range(_BISECT_ITERS):
        mid = (lo + hi) / 2.0
        progress = (tu.body_lon(planet, mid) - lo_lon) % 360.0
        if progress < target_travel:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _direct_longitude_crossing(planet: int, target_lon: float,
                               lo_jd: float, hi_jd: float,
                               prefer_last: bool = False):
    """在两个相邻驻留点之间的顺行段求固定黄经交点。

    金星/火星的相邻驻留之间可能顺行超过一整圈，同一黄经因此可能出现多次：
    前阴影要取转逆前**最后一次**经过未来转顺点；后阴影要取转顺后**第一次**
    经过先前转逆点。这里按小步扫描找到目标区间后再二分，既处理 0° 回绕，也不
    会把多圈运动压扁到一圈而选错交点。
    """
    if hi_jd <= lo_jd:
        return None
    step = _SAMPLE_DAYS.get(planet, 1.0)
    if prefer_last:
        right = hi_jd
        while right > lo_jd:
            left = max(lo_jd, right - step)
            hit = _crossing_in_direct_interval(planet, target_lon, left, right)
            if hit is not None:
                return hit
            right = left
        return None

    left = lo_jd
    while left < hi_jd:
        right = min(hi_jd, left + step)
        hit = _crossing_in_direct_interval(planet, target_lon, left, right)
        if hit is not None:
            return hit
        left = right
    return None


@lru_cache(maxsize=64)
def _cycles_for_year(planet: int, year: int):
    """构造该年份附近可完整定义的逆行阴影周期。"""
    stations = _station_schedule(planet, year)
    cycles = []
    for idx in range(1, len(stations) - 2):
        prev_direct, station_retro, station_direct, next_retro = stations[idx - 1:idx + 3]
        if not (
            prev_direct[2] == "direct"
            and station_retro[2] == "retrograde"
            and station_direct[2] == "direct"
            and next_retro[2] == "retrograde"
        ):
            continue
        retro_jd, direct_jd = station_retro[0], station_direct[0]
        retro_lon = tu.body_lon(planet, retro_jd)
        direct_lon = tu.body_lon(planet, direct_jd)
        shadow_start = _direct_longitude_crossing(
            planet, direct_lon, prev_direct[0], retro_jd, prefer_last=True,
        )
        shadow_end = _direct_longitude_crossing(
            planet, retro_lon, direct_jd, next_retro[0],
        )
        if shadow_start is None or shadow_end is None:
            continue
        cycles.append((shadow_start, retro_jd, direct_jd, shadow_end, direct_lon, retro_lon))
    return tuple(cycles)


def motion_status_at(jd: float, bodies=MOTION_BODIES) -> list:
    """返回 ``jd`` 时处于逆行弧三阶段之一的行星，顺行空档不返回。"""
    year = _jd_year(jd)
    rows = []
    for planet in bodies:
        active = None
        for cycle in _cycles_for_year(planet, year):
            shadow_start, retro_jd, direct_jd, shadow_end, direct_lon, retro_lon = cycle
            if shadow_start <= jd <= shadow_end:
                active = cycle
                break
        if active is None:
            continue

        shadow_start, retro_jd, direct_jd, shadow_end, direct_lon, retro_lon = active
        if jd < retro_jd:
            phase = "pre_shadow"
            phase_end = retro_jd
        elif jd < direct_jd:
            phase = "retrograde"
            phase_end = direct_jd
        else:
            phase = "post_shadow"
            phase_end = shadow_end

        lon, speed = tu.body_position(planet, jd)
        rows.append({
            "planet": PLANET_KEY[planet],
            "planet_cn": PLANET_CN[planet],
            "phase": phase,
            "phase_cn": PHASE_CN[phase],
            "retrograde": phase == "retrograde",
            "speed": round(speed, 8),
            **_position_payload(lon),
            "phase_end": _jd_iso(phase_end),
            "shadow_start": _jd_iso(shadow_start),
            "station_retrograde": {
                "at": _jd_iso(retro_jd),
                **_position_payload(retro_lon),
            },
            "station_direct": {
                "at": _jd_iso(direct_jd),
                **_position_payload(direct_lon),
            },
            "shadow_end": _jd_iso(shadow_end),
        })
    return rows


def clear_cache():
    """测试/运维用：清空驻留与周期缓存。"""
    _station_schedule.cache_clear()
    _cycles_for_year.cache_clear()
