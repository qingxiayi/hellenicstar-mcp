#!/usr/bin/env python3
"""Davison Relationship Chart (时空中点关系盘) 引擎 —— 纯新增服务模块。

设计边界：
  - 核心计算复用 Swiss Ephemeris 与仓库既有行星/格局计算工具。
  - 计算两人真实世界时出生时刻与地理经纬度的时空中点 (Space-Time Midpoint)。
  - 在该物理时空点排出一张具备独立真实四轴与宫位的完整星盘 (支持 Placidus 与 Whole Sign)。
  - 遵循无冷读、纯计算事实架构。
"""

import swisseph as swe

from services.ephemeris_guard import apply_ephe_path
from services.jones_pattern import calculate_jones_pattern
from fortuna_projection import whole_sign_house

apply_ephe_path()

SIGNS_ZH = [
    "白羊座", "金牛座", "双子座", "巨蟹座", "狮子座", "处女座",
    "天秤座", "天蝎座", "射手座", "摩羯座", "水瓶座", "双鱼座"
]

PLANET_DEFS = [
    ("sun", swe.SUN), ("moon", swe.MOON), ("mercury", swe.MERCURY),
    ("venus", swe.VENUS), ("mars", swe.MARS), ("jupiter", swe.JUPITER),
    ("saturn", swe.SATURN), ("uranus", swe.URANUS), ("neptune", swe.NEPTUNE),
    ("pluto", swe.PLUTO),
]

PLANET_ZH = {
    "sun": "太阳", "moon": "月亮", "mercury": "水星", "venus": "金星",
    "mars": "火星", "jupiter": "木星", "saturn": "土星", "uranus": "天王星",
    "neptune": "海王星", "pluto": "冥王星", "chiron": "凯龙星",
    "mean_north_node": "北交点", "true_north_node": "真北交点",
    "south_node": "南交点",
}

_FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED

ASPECT_DEFS = [
    (0, "合", 0.0),
    (60, "六分", 60.0),
    (90, "刑", 90.0),
    (120, "三分", 120.0),
    (150, "梅花", 150.0),
    (180, "冲", 180.0),
]

ORB_PROFILES = {
    "greene": {0: 10.0, 60: 6.0, 90: 10.0, 120: 10.0, 150: 3.0, 180: 10.0},
    "tight": {0: 3.0, 60: 3.0, 90: 3.0, 120: 3.0, 150: 2.0, 180: 3.0},
}

PHASES_ZH = [
    "新月", "娥眉月", "上弦月", "盈凸月", "满月", "亏凸月", "下弦月", "残月"
]


def _norm(deg: float) -> float:
    return float(deg) % 360.0


def _sign_info(lon: float) -> tuple[int, str]:
    norm = _norm(lon)
    idx = int(norm // 30.0) % 12
    return idx, SIGNS_ZH[idx]


def _house_of(lon: float, cusps: list[float]) -> int:
    norm = _norm(lon)
    for i in range(12):
        c1 = cusps[i]
        c2 = cusps[(i + 1) % 12]
        if c1 <= c2:
            if c1 <= norm < c2:
                return i + 1
        else:
            if norm >= c1 or norm < c2:
                return i + 1
    return 1


def _rudhyar_phase(sun_lon: float, moon_lon: float) -> dict:
    elongation = _norm(moon_lon - sun_lon)
    phase_idx = int(elongation // 45.0) % 8
    return {
        "phase_num": phase_idx + 1,
        "phase_name": PHASES_ZH[phase_idx],
        "elongation": round(elongation, 4),
    }


def compute_davison_space_time_midpoint(
    jd_a: float, lat_a: float, lon_a: float,
    jd_b: float, lat_b: float, lon_b: float,
) -> dict:
    """按未校正 Davison 口径，分别取 UTC 时间、纬度和经度的算术平均。"""
    jd_mid = (jd_a + jd_b) / 2.0
    year, month, day, hour = swe.revjul(jd_mid)
    minute_val = (hour % 1.0) * 60.0
    second_val = (minute_val % 1.0) * 60.0
    hour_int = int(hour)
    minute_int = int(minute_val)
    sec_float = round(second_val, 2)
    if sec_float >= 60.0:
        sec_float = 0.0
        minute_int += 1
    if minute_int >= 60:
        minute_int = 0
        hour_int += 1

    utc_iso = f"{int(year):04d}-{int(month):02d}-{int(day):02d}T{hour_int:02d}:{minute_int:02d}:{sec_float:05.2f}Z"

    lat_mid = (lat_a + lat_b) / 2.0
    lon_mid = (lon_a + lon_b) / 2.0

    return {
        "jd": jd_mid,
        "utc": utc_iso,
        "year": int(year),
        "month": int(month),
        "day": int(day),
        "hour": hour_int,
        "minute": minute_int,
        "second": sec_float,
        "lat": round(lat_mid, 5),
        "lng": round(lon_mid, 5),
        "time_span_days": round(abs(jd_b - jd_a), 4),
    }


def compute_davison_chart_full(
    jd_a: float, lat_a: float, lon_a: float,
    jd_b: float, lat_b: float, lon_b: float,
    house_system: str = "placidus",
    orb_profile: str = "greene",
) -> dict:
    """计算完整的 Davison 时空中点盘。"""
    st_mid = compute_davison_space_time_midpoint(
        jd_a, lat_a, lon_a, jd_b, lat_b, lon_b
    )
    jd_mid = st_mid["jd"]
    lat_mid = st_mid["lat"]
    lon_mid = st_mid["lng"]

    # 1. 四轴与宫位 (调用 Swiss Ephemeris)
    hsys = b'W' if house_system == "whole_sign" else b'P'
    raw_cusps, ascmc = swe.houses_ex(jd_mid, lat_mid, lon_mid, hsys)
    cusps = [_norm(c) for c in raw_cusps[:12]]

    asc = _norm(ascmc[0])
    mc = _norm(ascmc[1])
    dsc = _norm(asc + 180.0)
    ic = _norm(mc + 180.0)

    axes = {
        "ascendant": {"longitude": round(asc, 4), "sign": _sign_info(asc)[1], "name": "上升点"},
        "midheaven": {"longitude": round(mc, 4), "sign": _sign_info(mc)[1], "name": "天顶"},
        "descendant": {"longitude": round(dsc, 4), "sign": _sign_info(dsc)[1], "name": "下降点"},
        "imum_coeli": {"longitude": round(ic, 4), "sign": _sign_info(ic)[1], "name": "天底"},
    }

    # 2. 行星位置 (调用 Swiss Ephemeris)
    planets = {}
    points_for_aspects = {}
    for key, p_id in PLANET_DEFS:
        pos, _ = swe.calc_ut(jd_mid, p_id, _FLAGS)
        lon = _norm(pos[0])
        speed = pos[3]
        is_rx = speed < 0.0
        h_num = _house_of(lon, cusps) if house_system == "placidus" else whole_sign_house(lon, asc)
        planets[key] = {
            "key": key,
            "name": PLANET_ZH[key],
            "longitude": round(lon, 4),
            "sign": _sign_info(lon)[1],
            "house": h_num,
            "retrograde": is_rx,
            "speed": round(speed, 5),
        }
        points_for_aspects[key] = lon

    # 凯龙星与交点
    pos_chiron, _ = swe.calc_ut(jd_mid, swe.CHIRON, _FLAGS)
    chiron_lon = _norm(pos_chiron[0])
    h_chiron = _house_of(chiron_lon, cusps) if house_system == "placidus" else whole_sign_house(chiron_lon, asc)
    chiron_dict = {
        "key": "chiron",
        "name": PLANET_ZH["chiron"],
        "longitude": round(chiron_lon, 4),
        "sign": _sign_info(chiron_lon)[1],
        "house": h_chiron,
        "retrograde": pos_chiron[3] < 0.0,
    }
    points_for_aspects["chiron"] = chiron_lon

    pos_node, _ = swe.calc_ut(jd_mid, swe.MEAN_NODE, _FLAGS)
    node_lon = _norm(pos_node[0])
    south_node_lon = _norm(node_lon + 180.0)
    special_points = {
        "chiron": chiron_dict,
        "mean_north_node": {
            "key": "mean_north_node",
            "name": PLANET_ZH["mean_north_node"],
            "longitude": round(node_lon, 4),
            "sign": _sign_info(node_lon)[1],
            "house": _house_of(node_lon, cusps) if house_system == "placidus" else whole_sign_house(node_lon, asc),
            "retrograde": True,
        },
        "south_node": {
            "key": "south_node",
            "name": PLANET_ZH["south_node"],
            "longitude": round(south_node_lon, 4),
            "sign": _sign_info(south_node_lon)[1],
            "house": _house_of(south_node_lon, cusps) if house_system == "placidus" else whole_sign_house(south_node_lon, asc),
            "retrograde": True,
        },
    }
    points_for_aspects["mean_north_node"] = node_lon

    # 四轴参与相位判定
    points_for_aspects["ascendant"] = asc
    points_for_aspects["midheaven"] = mc

    # 3. 相位判定
    orbs_map = ORB_PROFILES.get(orb_profile, ORB_PROFILES["greene"])
    aspects_list = []
    keys_sorted = list(points_for_aspects.keys())
    for i in range(len(keys_sorted)):
        for j in range(i + 1, len(keys_sorted)):
            p1 = keys_sorted[i]
            p2 = keys_sorted[j]
            # 四轴之间不形成独立相位
            if p1 in ("ascendant", "midheaven") and p2 in ("ascendant", "midheaven"):
                continue
            lon1 = points_for_aspects[p1]
            lon2 = points_for_aspects[p2]
            sep = abs((lon1 - lon2 + 180.0) % 360.0 - 180.0)
            for angle, name_zh, target_deg in ASPECT_DEFS:
                orb = abs(sep - target_deg)
                max_orb = orbs_map.get(angle, 6.0)
                if orb <= max_orb:
                    aspects_list.append({
                        "point1": p1,
                        "point2": p2,
                        "angle": angle,
                        "aspect": name_zh,
                        "orb": round(orb, 4),
                        "max_orb": max_orb,
                        "tight": orb <= 1.5,
                    })

    aspects_list.sort(key=lambda a: (a["orb"], a["angle"]))

    # 4. 月相
    lunation = _rudhyar_phase(planets["sun"]["longitude"], planets["moon"]["longitude"])

    # 5. 琼斯格局
    jones = calculate_jones_pattern(planets)

    return {
        "midpoint_space_time": st_mid,
        "chart": {
            "planets": planets,
            "special_points": special_points,
            "axes": axes,
            "house_cusps": [round(c, 4) for c in cusps],
            "lunation_phase": lunation,
            "jones_pattern": jones,
        },
        "aspects": aspects_list,
    }

