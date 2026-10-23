"""Jones pattern pure-compute adapter for the mini-program.

The vendored engine contains historical presentation text for the website.  This
module exposes geometry, classification state, stable planet identities, and a
short pattern-scoped reading; no AI or whole-chart prediction crosses the API.
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List

from engine.jones import (
    PLANET_NAMES_ZH,
    SELLAR_OPPOSITION_ORB,
    _build_key_roles,
    detect_with_variants,
    result_to_dict,
)
from services.jones_pattern_guide import pattern_guide, role_guide


ENGINE_VERSION = "jones-miniapp-5"

PLANETS = (
    ("sun", "太阳", "☉"),
    ("moon", "月亮", "☽"),
    ("mercury", "水星", "☿"),
    ("venus", "金星", "♀"),
    ("mars", "火星", "♂"),
    ("jupiter", "木星", "♃"),
    ("saturn", "土星", "♄"),
    ("uranus", "天王星", "♅"),
    ("neptune", "海王星", "♆"),
    ("pluto", "冥王星", "♇"),
)

FAMILY_BY_PATTERN = {
    "Bundle": "Bundle",
    "Bowl": "Bowl",
    "Bucket": "Bucket",
    "Locomotive": "Locomotive",
    "Splay": "Splay",
    "See-Saw": "See-Saw",
    "Splash": "Splash",
    "Fanhandle": "Bundle",
    "Sling": "Bucket",
    "ConjHandle": "Bucket",
    "TwoHandle": "Bucket",
    "Hourglass": "See-Saw",
    "Butterfly": "Splay",
    "Tripod": "Splay",
}

FAMILY_ZH = {
    "Bundle": "丛聚型",
    "Bowl": "碗型",
    "Bucket": "提桶型",
    "Locomotive": "火车头型",
    "Splay": "展开型",
    "See-Saw": "跷跷板型",
    "Splash": "散落型",
}

VARIANTS = {
    "Fanhandle", "Sling", "ConjHandle", "TwoHandle",
    "Hourglass", "Butterfly", "Tripod",
}

STATE_LABELS = {
    "standard": "标准格局",
    "variant": "变形格局",
    "borderline": "交界待观察",
}


def _finite_longitude(value, planet_id: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{planet_id} 黄经必须是有限数字")
    try:
        longitude = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{planet_id} 黄经必须是有限数字")
    if not math.isfinite(longitude):
        raise ValueError(f"{planet_id} 黄经必须是有限数字")
    return longitude % 360.0


def _longitudes(planets: Dict[str, Dict]) -> List[float]:
    if not isinstance(planets, dict):
        raise ValueError("缺少十大行星数据")
    values = []
    for planet_id, _name, _glyph in PLANETS:
        item = planets.get(planet_id)
        if not isinstance(item, dict) or "longitude" not in item:
            raise ValueError(f"缺少行星数据：{planet_id}")
        values.append(_finite_longitude(item["longitude"], planet_id))
    return values


def _gaps(longitudes: Iterable[float]) -> List[float]:
    ordered = sorted(longitudes)
    return [
        round((ordered[(idx + 1) % len(ordered)] - value) % 360.0, 4)
        for idx, value in enumerate(ordered)
    ]


def _clean_planet_name(name):
    value = str(name or "")
    for glyph in "☉☽☿♀♂♃♄♅♆♇":
        value = value.replace(glyph, "")
    return value.strip() or None


def calculate_jones_pattern(planets: Dict[str, Dict]) -> Dict:
    """Return the mini-program's stable, pattern-scoped Jones DTO."""
    longitudes = _longitudes(planets)
    result = detect_with_variants(longitudes, planet_names=PLANET_NAMES_ZH)
    pattern = result.pattern_en
    family = FAMILY_BY_PATTERN.get(pattern, pattern)
    is_variant = pattern in VARIANTS
    borderline = bool(result.extra.get("borderline")) or result.confidence == "ambiguous"
    state = "borderline" if borderline else ("variant" if is_variant else "standard")
    gaps = _gaps(longitudes)
    distribution = []
    for (planet_id, name, glyph), longitude in zip(PLANETS, longitudes):
        distribution.append({
            "id": planet_id,
            "name": name,
            "glyph": glyph,
            "longitude": round(longitude, 4),
        })
    # planet_meta 除经度外透传宫位（调用方 calculator 的 planets 自带 house；
    # 纯几何输入没有则静默跳过）——双把手「同宫=同一生活领域两种表达」判定要用，
    # 此前只取经度把宫位丢了，_build_key_roles 里的宫位附加路径从未生效。
    planet_meta = {}
    for (planet_id, _name, _glyph), item in zip(PLANETS, distribution):
        meta = {"abs_pos": item["longitude"]}
        house = (planets.get(planet_id) or {}).get("house")
        if isinstance(house, int) and 1 <= house <= 12:
            meta["house"] = house
        planet_meta[item["name"]] = meta
    # Reuse the migrated engine's own geometry contract. In particular, a
    # Bucket midpoint is derived from the nine-planet bowl boundaries rather
    # than from the largest gap after the handle is put back into the wheel.
    engine_geometry = result_to_dict(result, planet_meta=planet_meta)
    sellar = engine_geometry.get('sellar_focus')
    core_opposition = None
    if sellar and sellar.get('opp_name'):
        separation = abs((sellar['lon'] - sellar['opp_lon'] + 180) % 360 - 180)
        core_opposition = dict(planet_name=_clean_planet_name(sellar['name']),
            opposite_planet_name=_clean_planet_name(sellar['opp_name']),
            longitude=sellar['lon'], opposite_longitude=sellar['opp_lon'],
            orb=abs(180-separation), upstream_orb_limit=SELLAR_OPPOSITION_ORB,
            policy='upstream Sellar supplement; opposite signs and fixed speed-rank ordering')
    midpoint_bowl = engine_geometry.get("midpoint_bowl")
    midpoint_loco = engine_geometry.get("midpoint_loco")
    midpoint_bundle = engine_geometry.get("midpoint_bundle")
    cog_bowl = engine_geometry.get("cog_bowl")
    cog_partners = [
        {"planet_name": _clean_planet_name(item.get("planet_name")),
         "longitude": round(float(item.get("planet_long", 0)) % 360.0, 4),
         "orb_deg": round(float(item.get("orb", 0)), 2)}
        for item in ((cog_bowl or {}).get("partners") or [])
        if _clean_planet_name(item.get("planet_name"))
    ]
    crossing_point = engine_geometry.get("crossing_point")
    group_axis = engine_geometry.get("group_axis")
    key_roles = []
    seen_roles = set()
    for role in _build_key_roles(result, planet_meta):
        public_guide = role_guide(role.get("role_type"))
        name = _clean_planet_name(role.get("name_cn"))
        if not public_guide or not name:
            continue
        identity = (name, role.get("role_type"))
        if identity in seen_roles:
            continue
        seen_roles.add(identity)
        label, description = public_guide
        note = role.get("note") or ""
        entry = {
            "planet_name": name,
            "role_type": role["role_type"],
            "role_label": label,
            "longitude": round(float(role.get("abs_pos", 0)) % 360.0, 4),
            "description": f"{description}{note}" if note else description,
        }
        # 碗中心复合合相：承重墙卡片带上合相伙伴，前端据此显示两颗星并在盘面标亮。
        if role["role_type"] == "cog_bowl" and cog_partners:
            entry["partners"] = cog_partners
        key_roles.append(entry)
    return {
        "engine_version": ENGINE_VERSION,
        "pattern_en": pattern,
        "pattern_zh": result.pattern_zh,
        "family_en": family,
        "family_zh": FAMILY_ZH.get(family, result.pattern_zh),
        "variant_en": pattern if is_variant else None,
        "is_variant": is_variant,
        "confidence": result.confidence,
        "state": state,
        "state_label": STATE_LABELS[state],
        "borderline": borderline,
        "borderline_reasons": list(result.extra.get("borderline_reasons", [])),
        # 交界时的「另一种读法」：越过阈值后本盘会落到的形态 + 当前距阈值的度数差。
        # 前端据此渲染一行短句，替代原先只说「建议自行核对」的空提示。
        "borderline_alternates": [
            {
                "reason": item.get("reason"),
                "pattern_en": item.get("pattern_en"),
                "pattern_zh": item.get("pattern_zh"),
                "delta_deg": item.get("delta_deg"),
                "measure_zh": item.get("measure_zh"),
            }
            for item in result.extra.get("borderline_alternates", [])
            if item.get("pattern_zh")
        ],
        "max_gap_deg": round(result.max_gap, 2),
        "span_deg": round(result.span, 2),
        "sorted_gaps_deg": sorted(gaps, reverse=True),
        "occupied_signs": len({int(value // 30) for value in longitudes}),
        "high_focus_planet": _clean_planet_name(result.high_focus_planet),
        "high_focus_longitude": (
            round(result.high_focus_long % 360.0, 4)
            if result.high_focus_long is not None else None
        ),
        "guide": pattern_guide(pattern),
        "key_roles": key_roles,
        "core_opposition": core_opposition,
        "distribution": distribution,
        "midpoint_bowl": (
            {"long": round(float(midpoint_bowl["long"]) % 360.0, 4)}
            if midpoint_bowl else None
        ),
        # 火车头型虚空中点：空白扇区几何中点，仅 Locomotive 有值
        "midpoint_loco": (
            {"long": round(float(midpoint_loco["long"]) % 360.0, 4)}
            if midpoint_loco else None
        ),
        # 丛聚型虚空中点：星群跨度几何中点，仅 Bundle 有值
        "midpoint_bundle": (
            {"long": round(float(midpoint_bundle["long"]) % 360.0, 4)}
            if midpoint_bundle else None
        ),
        # 占据半球重心/碗底点（Bowl 直算、Bucket 补算）：若 10° 内有行星锚定，
        # 附上行星名与距离；≤3° 视为「碗底锚点」而非泛泛「承重墙」。
        "cog_bowl": (
            {
                "long": round(float(cog_bowl["long"]) % 360.0, 4),
                "planet_name": _clean_planet_name(cog_bowl.get("planet_name")),
                "is_anchor": bool(cog_bowl.get("is_anchor")),
                **({"partners": cog_partners} if cog_partners else {}),
            }
            if cog_bowl and cog_bowl.get("planet_name") else
            ({"long": round(float(cog_bowl["long"]) % 360.0, 4)} if cog_bowl else None)
        ),
        # 蝴蝶型顶点星与较近一翼的交叉点，近似真中点，仅 Butterfly 有值
        "crossing_point": (
            {
                "long": round(float(crossing_point["long"]) % 360.0, 4),
                "near_name": _clean_planet_name(crossing_point.get("near_name")),
            }
            if crossing_point else None
        ),
        # 跷跷板/沙漏两组各自重心：没有其他焦点星时份量偏向哪一组，仅 See-Saw/Hourglass 有值
        "group_axis": (
            {
                "center_a": round(float(group_axis["center_a"]) % 360.0, 4),
                "center_b": round(float(group_axis["center_b"]) % 360.0, 4),
                "heavier": group_axis.get("heavier"),
            }
            if group_axis else None
        ),
    }
