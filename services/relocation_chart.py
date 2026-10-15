#!/usr/bin/env python3
"""Relocation Chart (空间重置盘) 引擎 —— 纯新增服务模块。

设计边界：
  - 核心计算复用 Swiss Ephemeris 与仓库既有本命排盘工具。
  - 保持本命时刻 (UT) 与行星黄道经度完全恒定，仅将地理坐标替换为目标迁居地坐标。
  - 重新计算迁居地重置上升点 (ASC)、天顶 (MC) 四轴及十二宫宫头分布。
  - 重新判定各行星在迁居地重置盘中的落宫与对四轴新相位，并输出四轴偏移量 (Angular Shifts)。
"""

from datetime import datetime
import swisseph as swe

from services.ephemeris_guard import apply_ephe_path
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
    "mean_north_node": "北交点", "south_node": "南交点",
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

ORBS_MAP = {0: 8.0, 60: 4.0, 90: 8.0, 120: 8.0, 150: 3.0, 180: 8.0}


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


def compute_relocation_chart_full(
    natal_data: dict,
    reloc_lat: float,
    reloc_lng: float,
    reloc_location_id: str,
    reloc_name: str = "",
    reloc_tz: str = "",
    house_system: str = "placidus",
) -> dict:
    """计算完整的 Relocation 空间重置盘。"""
    # 提取本命基础信息
    bc = natal_data.get("birth_context", {})
    jd_ut = bc.get("jd_utc")
    if jd_ut is None:
        # 从 civil_dt 和 utc_offset 还原
        civil_dt = bc.get("civil_dt")
        utc_offset = bc.get("utc_offset", 0.0)
        if civil_dt:
            dt = datetime.fromisoformat(civil_dt)
            # 简化：通过 swe.julday 计算
            hour_ut = dt.hour + dt.minute / 60.0 - utc_offset
            jd_ut = swe.julday(dt.year, dt.month, dt.day, hour_ut)
        else:
            raise ValueError("natal_data 缺少有效的 birth_context 时间信息")

    natal_axes = natal_data.get("axes", {})
    natal_asc = natal_axes.get("asc", {}).get("lon")
    if natal_asc is None:
        natal_asc = natal_axes.get("ascendant", {}).get("longitude")
    if natal_asc is None:
        natal_asc = natal_data.get("asc_lon")
    natal_mc = natal_axes.get("mc", {}).get("lon")
    if natal_mc is None:
        natal_mc = natal_axes.get("midheaven", {}).get("longitude")

    # 1. 迁居地四轴与宫位重算
    hsys = b'W' if house_system == "whole_sign" else b'P'
    raw_cusps, ascmc = swe.houses_ex(jd_ut, reloc_lat, reloc_lng, hsys)
    cusps = [_norm(c) for c in raw_cusps[:12]]

    reloc_asc = _norm(ascmc[0])
    reloc_mc = _norm(ascmc[1])
    reloc_dsc = _norm(reloc_asc + 180.0)
    reloc_ic = _norm(reloc_mc + 180.0)

    axes = {
        "ascendant": {"longitude": round(reloc_asc, 4), "sign": _sign_info(reloc_asc)[1], "name": "上升点"},
        "midheaven": {"longitude": round(reloc_mc, 4), "sign": _sign_info(reloc_mc)[1], "name": "天顶"},
        "descendant": {"longitude": round(reloc_dsc, 4), "sign": _sign_info(reloc_dsc)[1], "name": "下降点"},
        "imum_coeli": {"longitude": round(reloc_ic, 4), "sign": _sign_info(reloc_ic)[1], "name": "天底"},
    }

    # 四轴角偏移量 (ΔASC, ΔMC)
    delta_asc = (reloc_asc - natal_asc + 180.0) % 360.0 - 180.0 if natal_asc is not None else 0.0
    delta_mc = (reloc_mc - natal_mc + 180.0) % 360.0 - 180.0 if natal_mc is not None else 0.0

    angular_shifts = {
        "natal_ascendant": round(natal_asc, 4) if natal_asc is not None else None,
        "relocated_ascendant": round(reloc_asc, 4),
        "delta_asc_deg": round(delta_asc, 4),
        "natal_midheaven": round(natal_mc, 4) if natal_mc is not None else None,
        "relocated_midheaven": round(reloc_mc, 4),
        "delta_mc_deg": round(delta_mc, 4),
    }

    # 2. 行星黄道经度完全恒定，但落宫在迁居地重新映射
    planets = []
    points_for_aspects = {}
    natal_planets_src = natal_data.get("natal_planets_full") or natal_data.get("planets") or []
    house_key = "house_w" if house_system == "whole_sign" else "house_p"
    if isinstance(natal_planets_src, dict):
        natal_planets_list = [
            {"key": k, "name": v.get("name_zh") or PLANET_ZH.get(k, k),
             "longitude": v.get("longitude") if v.get("longitude") is not None else v.get("lon"),
             "house": v.get(house_key) if v.get(house_key) is not None else v.get("house"),
             "retrograde": v.get("retrograde", False)}
            for k, v in natal_planets_src.items()
        ]
    else:
        natal_planets_list = natal_planets_src

    natal_house_map = {}
    for p in natal_planets_list:
        k = p.get("key") or p.get("name_en", "").lower()
        natal_house = p.get(house_key)
        if natal_house is None:
            natal_house = p.get("house")
        natal_house_map[k] = natal_house

    for key, p_id in PLANET_DEFS:
        pos, _ = swe.calc_ut(jd_ut, p_id, _FLAGS)
        lon = _norm(pos[0])
        speed = pos[3]
        is_rx = speed < 0.0
        new_house = _house_of(lon, cusps) if house_system == "placidus" else whole_sign_house(lon, reloc_asc)
        nat_house = natal_house_map.get(key)

        planet_entry = {
            "key": key,
            "name": PLANET_ZH[key],
            "longitude": round(lon, 4),
            "sign": _sign_info(lon)[1],
            "natal_house": nat_house,
            "relocated_house": new_house,
            "house_changed": nat_house != new_house if nat_house is not None else None,
            "retrograde": is_rx,
        }
        planets.append(planet_entry)
        points_for_aspects[key] = lon

    # 凯龙星与交点
    pos_chiron, _ = swe.calc_ut(jd_ut, swe.CHIRON, _FLAGS)
    chiron_lon = _norm(pos_chiron[0])
    h_chiron_new = _house_of(chiron_lon, cusps) if house_system == "placidus" else whole_sign_house(chiron_lon, reloc_asc)
    h_chiron_nat = natal_house_map.get("chiron")
    planets.append({
        "key": "chiron",
        "name": PLANET_ZH["chiron"],
        "longitude": round(chiron_lon, 4),
        "sign": _sign_info(chiron_lon)[1],
        "natal_house": h_chiron_nat,
        "relocated_house": h_chiron_new,
        "house_changed": h_chiron_nat != h_chiron_new if h_chiron_nat is not None else None,
        "retrograde": pos_chiron[3] < 0.0,
    })
    points_for_aspects["chiron"] = chiron_lon

    pos_node, _ = swe.calc_ut(jd_ut, swe.MEAN_NODE, _FLAGS)
    node_lon = _norm(pos_node[0])
    h_node_new = _house_of(node_lon, cusps) if house_system == "placidus" else whole_sign_house(node_lon, reloc_asc)
    natal_cusps = natal_data.get("cusps")
    if house_system == "whole_sign" and natal_asc is not None:
        h_node_nat = whole_sign_house(node_lon, natal_asc)
    elif natal_cusps:
        h_node_nat = _house_of(node_lon, natal_cusps)
    else:
        h_node_nat = None
    planets.append({
        "key": "mean_north_node",
        "name": PLANET_ZH["mean_north_node"],
        "longitude": round(node_lon, 4),
        "sign": _sign_info(node_lon)[1],
        "natal_house": h_node_nat,
        "relocated_house": h_node_new,
        "house_changed": h_node_nat != h_node_new if h_node_nat is not None else None,
        "retrograde": True,
    })
    points_for_aspects["mean_north_node"] = node_lon

    # 四轴参与相位重算
    points_for_aspects["ascendant"] = reloc_asc
    points_for_aspects["midheaven"] = reloc_mc

    # 3. 相位重算 (包含行星间相位与对重置四轴的新相位)
    aspects_list = []
    keys_sorted = list(points_for_aspects.keys())
    for i in range(len(keys_sorted)):
        for j in range(i + 1, len(keys_sorted)):
            p1 = keys_sorted[i]
            p2 = keys_sorted[j]
            if p1 in ("ascendant", "midheaven") and p2 in ("ascendant", "midheaven"):
                continue
            lon1 = points_for_aspects[p1]
            lon2 = points_for_aspects[p2]
            sep = abs((lon1 - lon2 + 180.0) % 360.0 - 180.0)
            for angle, name_zh, target_deg in ASPECT_DEFS:
                orb = abs(sep - target_deg)
                max_orb = ORBS_MAP.get(angle, 6.0)
                if orb <= max_orb:
                    aspects_list.append({
                        "point1": p1,
                        "point2": p2,
                        "angle": angle,
                        "aspect": name_zh,
                        "orb": round(orb, 4),
                        "tight": orb <= 1.5,
                        "relocated_axis_contact": p1 in ("ascendant", "midheaven") or p2 in ("ascendant", "midheaven"),
                    })

    aspects_list.sort(key=lambda a: (a["orb"], a["angle"]))

    return {
        "relocation_location": {
            "location_id": reloc_location_id,
            "name": reloc_name,
            "lat": round(reloc_lat, 5),
            "lng": round(reloc_lng, 5),
            "timezone": reloc_tz,
        },
        "angular_shifts": angular_shifts,
        "axes": axes,
        "house_cusps": [round(c, 4) for c in cusps],
        "planets": planets,
        "aspects": aspects_list,
    }

