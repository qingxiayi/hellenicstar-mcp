"""Mechanical ruler chains for all twelve natal houses.

The chain topology only uses domicile rulerships:
house cusp sign -> ruler -> ruler's natal sign -> that sign's ruler.
House placement, aspects and retrograde state are node metadata; they do not
change the next edge.  Two deterministic tracks are returned:

* traditional: the seven-planet domicile scheme
* modern: Uranus/Neptune/Pluto replace the traditional rulers of
  Aquarius/Pisces/Scorpio

Identical tracks are de-duplicated.  This keeps the response linear and
auditable while still exposing both co-ruler routes when they differ.

The twelve houses are grouped into the three modal crosses.  Each house also
carries its wheel position (left/top/right/bottom) so the UI can lay a cross
out the way a chart wheel does: 1 on the left, 10 on top, 7 on the right and
4 at the bottom, with the succedent and cadent crosses following the same
geometry.  House 1 is flagged as the chart ruler: its cusp sign is the
ascending sign under both Placidus and whole sign, so the ascendant's domicile
lord needs no separate chain.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional


SIGN_KEYS = ("Ari", "Tau", "Gem", "Can", "Leo", "Vir", "Lib", "Sco", "Sag", "Cap", "Aqu", "Pis")
SIGN_ZH = {
    "Ari": "白羊座", "Tau": "金牛座", "Gem": "双子座", "Can": "巨蟹座",
    "Leo": "狮子座", "Vir": "处女座", "Lib": "天秤座", "Sco": "天蝎座",
    "Sag": "射手座", "Cap": "摩羯座", "Aqu": "水瓶座", "Pis": "双鱼座",
}
PLANET_ZH = {
    "sun": "太阳", "moon": "月亮", "mercury": "水星", "venus": "金星",
    "mars": "火星", "jupiter": "木星", "saturn": "土星",
    "uranus": "天王星", "neptune": "海王星", "pluto": "冥王星",
}
TRADITIONAL_RULERS = {
    "Ari": "mars", "Tau": "venus", "Gem": "mercury", "Can": "moon",
    "Leo": "sun", "Vir": "mercury", "Lib": "venus", "Sco": "mars",
    "Sag": "jupiter", "Cap": "saturn", "Aqu": "saturn", "Pis": "jupiter",
}
MODERN_RULERS = {
    **TRADITIONAL_RULERS,
    "Sco": "pluto", "Aqu": "uranus", "Pis": "neptune",
}
ANGULAR_HOUSES = (1, 4, 7, 10)

# position 是星盘方位，不是阅读顺序：左＝上升侧，上＝中天侧。
# houses 的顺序是逆时针读序（1→4→7→10），跟星盘走向一致。
HOUSE_CROSSES = (
    {
        "id": "angular",
        "name": "基本宫十字",
        "houses": (1, 4, 7, 10),
        "positions": {1: "left", 4: "bottom", 7: "right", 10: "top"},
    },
    {
        "id": "succedent",
        "name": "固定宫十字",
        "houses": (2, 5, 8, 11),
        "positions": {2: "left", 5: "bottom", 8: "right", 11: "top"},
    },
    {
        "id": "cadent",
        "name": "变动宫十字",
        "houses": (3, 6, 9, 12),
        "positions": {3: "left", 6: "bottom", 9: "right", 12: "top"},
    },
)


def _sign_key_from_lon(longitude: float) -> str:
    return SIGN_KEYS[int(float(longitude) % 360 // 30)]


def _planet_node(planet_key: str, planets: Mapping[str, Mapping], asc_lon: float) -> Optional[dict]:
    raw = planets.get(planet_key)
    if not raw:
        return None
    longitude = float(raw.get("longitude", 0.0)) % 360
    sign_key = raw.get("sign") or _sign_key_from_lon(longitude)
    asc_sign_index = int(float(asc_lon) % 360 // 30)
    sign_index = int(longitude // 30)
    return {
        "planet": planet_key,
        "planet_zh": PLANET_ZH[planet_key],
        "longitude": round(longitude, 4),
        "sign": sign_key,
        "sign_zh": SIGN_ZH.get(sign_key, sign_key),
        "house_p": int(raw.get("house", 0) or 0),
        "house_w": (sign_index - asc_sign_index + 12) % 12 + 1,
        "retrograde": bool(raw.get("retrograde", False)),
    }


def trace_ruler_chain(
    start_planet: str,
    planets: Mapping[str, Mapping],
    asc_lon: float,
    rulers: Mapping[str, str],
) -> dict:
    """Trace one deterministic rulership policy until self-rule or a cycle."""
    nodes: List[dict] = []
    seen: Dict[str, int] = {}
    current = start_planet

    # Ten supported planets is the absolute graph size.  The extra iteration
    # is defensive only; normal termination happens through ``seen``.
    for _ in range(len(PLANET_ZH) + 1):
        if current in seen:
            return {
                "nodes": nodes,
                "status": "cycle",
                "cycle_start": seen[current],
                "cycle_planets": [node["planet"] for node in nodes[seen[current]:]],
            }
        seen[current] = len(nodes)
        node = _planet_node(current, planets, asc_lon)
        if not node:
            return {"nodes": nodes, "status": "missing", "missing_planet": current}
        nodes.append(node)
        next_planet = rulers.get(node["sign"])
        if not next_planet:
            return {"nodes": nodes, "status": "missing", "missing_sign": node["sign"]}
        if next_planet == current:
            return {
                "nodes": nodes,
                "status": "self",
                "cycle_start": len(nodes) - 1,
                "cycle_planets": [current],
            }
        current = next_planet

    return {"nodes": nodes, "status": "limit"}


def _track_signature(track: dict) -> tuple:
    return (
        tuple(node["planet"] for node in track.get("nodes", [])),
        track.get("status"),
        tuple(track.get("cycle_planets", [])),
    )


def _house_row(
    house: int,
    cusp_lon: float,
    planets: Mapping[str, Mapping],
    asc_lon: float,
    cross_id: str,
    position: str,
) -> dict:
    sign_key = _sign_key_from_lon(cusp_lon)
    tracks = []
    for key, label, rulers in (
        ("traditional", "传统", TRADITIONAL_RULERS),
        ("modern", "现代", MODERN_RULERS),
    ):
        ruler = rulers[sign_key]
        chain = trace_ruler_chain(ruler, planets, asc_lon, rulers)
        track = {
            "key": key,
            "label": label,
            "house_ruler": ruler,
            "house_ruler_zh": PLANET_ZH[ruler],
            **chain,
        }
        if not tracks or _track_signature(track) != _track_signature(tracks[0]):
            tracks.append(track)
    return {
        "house": house,
        "cusp_lon": round(float(cusp_lon) % 360, 4),
        "sign": sign_key,
        "sign_zh": SIGN_ZH[sign_key],
        "cross": cross_id,
        "position": position,
        # 1 宫宫头星座在两种宫制下都是上升星座，所以 1 宫链就是命主星链。
        "chart_ruler": house == 1,
        "dual_ruler": len(tracks) > 1,
        "tracks": tracks,
    }


def build_house_ruler_chains(
    planets: Mapping[str, Mapping],
    cusps: Iterable[float],
    asc_lon: float,
) -> dict:
    """Return all twelve house ruler chains, grouped by modal cross."""
    cusp_list = list(cusps)
    if len(cusp_list) < 12:
        raise ValueError("twelve house cusps are required")
    asc_sign_index = int(float(asc_lon) % 360 // 30)

    def rows(cusp_of) -> List[dict]:
        out = []
        for cross in HOUSE_CROSSES:
            for house in cross["houses"]:
                out.append(_house_row(
                    house, cusp_of(house), planets, asc_lon,
                    cross["id"], cross["positions"][house],
                ))
        return sorted(out, key=lambda row: row["house"])

    placidus = rows(lambda house: cusp_list[house - 1])
    whole_sign = rows(lambda house: ((asc_sign_index + house - 1) % 12) * 30.0)
    return {
        "crosses": [
            {"id": cross["id"], "name": cross["name"], "houses": list(cross["houses"])}
            for cross in HOUSE_CROSSES
        ],
        "placidus": placidus,
        "whole_sign": whole_sign,
    }


__all__ = [
    "ANGULAR_HOUSES", "HOUSE_CROSSES", "MODERN_RULERS", "TRADITIONAL_RULERS",
    "build_house_ruler_chains", "trace_ruler_chain",
]
