"""Deterministic classical astrology engine: essential dignities, solar states, receptions, and lots.

Provenances:
- Egyptian Bounds (Terms): Standard Hellenistic / Medieval Egyptian table (Ptolemy Tetrabiblos, Delphic Oracle 8).
- Chaldean Faces (Decans): Standard Chaldean planetary sequence starting from Mars at Aries 0°.
- Dorothean Triplicities: Dorotheus of Sidon (Carmen Astrologicum), Day/Night/Participating triplicity lords.
- Essential Dignity Scoring: Classical 5-fold scoring (Domicile +5, Exaltation +4, Triplicity +3, Term +2, Face +1, Detriment -5, Fall -4).
- Solar States: Cazimi (<17'), Combust (<8°30'), Under the Beams (<17°), Free (>=17°).
- Orientality: Oriental (rises before Sun; (sun_lon - planet_lon + 360) % 360 < 180°), Occidental otherwise.
- Reception & Mutual Reception: Bonatti / Masha'allah criteria (reception threshold: strong >= 1 or weak >= 2 dignities;
  mutual reception without aspect, reception requires Ptolemaic aspect).
- Arabic Lots: Hermetic 7 (Schmidt / Delphic Oracle 8) plus classical parental, marriage, and topical lots.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Any

# ═══════════════════════════════════════════════════════════
#  CONSTANTS & SIGN DEFINITIONS
# ═══════════════════════════════════════════════════════════

SIGN_NAMES_ZH = [
    "白羊座", "金牛座", "双子座", "巨蟹座",
    "狮子座", "处女座", "天秤座", "天蝎座",
    "射手座", "摩羯座", "水瓶座", "双鱼座",
]

SIGN_NAMES_EN = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

PLANET_ZH = {
    "sun": "太阳", "moon": "月亮", "mercury": "水星",
    "venus": "金星", "mars": "火星", "jupiter": "木星", "saturn": "土星",
    "uranus": "天王星", "neptune": "海王星", "pluto": "冥王星",
    "north_node": "北交点", "south_node": "南交点", "chiron": "凯龙星",
}

TRADITIONAL_PLANETS = ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn")

# Domicile rulers for signs 0..11
DOMICILE_RULERS = {
    0: "mars", 1: "venus", 2: "mercury", 3: "moon", 4: "sun", 5: "mercury",
    6: "venus", 7: "mars", 8: "jupiter", 9: "saturn", 10: "saturn", 11: "jupiter",
}

# Exaltation rulers for signs 0..11 (None if none)
EXALTATION_RULERS = {
    0: "sun", 1: "moon", 2: None, 3: "jupiter", 4: None, 5: "mercury",
    6: "saturn", 7: None, 8: None, 9: "mars", 10: None, 11: "venus",
}

# Detriment rulers (opposite domicile)
DETRIMENT_RULERS = {
    0: "venus", 1: "mars", 2: "jupiter", 3: "saturn", 4: "saturn", 5: "jupiter",
    6: "mars", 7: "venus", 8: "mercury", 9: "moon", 10: "sun", 11: "mercury",
}

# Fall rulers (opposite exaltation)
FALL_RULERS = {
    0: "saturn", 1: None, 2: None, 3: "mars", 4: None, 5: "venus",
    6: "sun", 7: "moon", 8: None, 9: "jupiter", 10: None, 11: "mercury",
}

# Dorothean triplicity rulers (day_lord, night_lord, participating_lord)
# Signs: 0,4,8 = Fire; 1,5,9 = Earth; 2,6,10 = Air; 3,7,11 = Water
DOROTHEAN_TRIPLICITY = {
    # Fire: Sun, Jupiter, Saturn
    0: ("sun", "jupiter", "saturn"),
    4: ("sun", "jupiter", "saturn"),
    8: ("sun", "jupiter", "saturn"),
    # Earth: Venus, Moon, Mars
    1: ("venus", "moon", "mars"),
    5: ("venus", "moon", "mars"),
    9: ("venus", "moon", "mars"),
    # Air: Saturn, Mercury, Jupiter
    2: ("saturn", "mercury", "jupiter"),
    6: ("saturn", "mercury", "jupiter"),
    10: ("saturn", "mercury", "jupiter"),
    # Water: Venus, Mars, Moon
    3: ("venus", "mars", "moon"),
    7: ("venus", "mars", "moon"),
    11: ("venus", "mars", "moon"),
}

# Egyptian Bounds (Terms) - 12 signs, 5 segments each: (planet_key, upper_degree_limit)
EGYPTIAN_BOUNDS = [
    # 0 Aries
    [("jupiter", 6), ("venus", 12), ("mercury", 20), ("mars", 25), ("saturn", 30)],
    # 1 Taurus
    [("venus", 8), ("mercury", 14), ("jupiter", 22), ("saturn", 27), ("mars", 30)],
    # 2 Gemini
    [("mercury", 6), ("jupiter", 12), ("venus", 17), ("mars", 24), ("saturn", 30)],
    # 3 Cancer
    [("mars", 7), ("venus", 13), ("mercury", 19), ("jupiter", 26), ("saturn", 30)],
    # 4 Leo
    [("jupiter", 6), ("venus", 11), ("saturn", 18), ("mercury", 24), ("mars", 30)],
    # 5 Virgo
    [("mercury", 7), ("venus", 17), ("jupiter", 21), ("mars", 28), ("saturn", 30)],
    # 6 Libra
    [("saturn", 6), ("mercury", 14), ("jupiter", 21), ("venus", 28), ("mars", 30)],
    # 7 Scorpio
    [("mars", 7), ("venus", 11), ("mercury", 19), ("jupiter", 24), ("saturn", 30)],
    # 8 Sagittarius
    [("jupiter", 12), ("venus", 17), ("mercury", 21), ("saturn", 26), ("mars", 30)],
    # 9 Capricorn
    [("mercury", 7), ("jupiter", 14), ("venus", 22), ("saturn", 26), ("mars", 30)],
    # 10 Aquarius
    [("mercury", 7), ("venus", 13), ("jupiter", 20), ("mars", 25), ("saturn", 30)],
    # 11 Pisces
    [("venus", 12), ("jupiter", 16), ("mercury", 19), ("mars", 28), ("saturn", 30)],
]

# Chaldean Faces (Decans) - 36 decans, repeating descending order Saturn to Moon, starting with Mars in Aries 0-10°
CHALDEAN_ORDER = ["mars", "sun", "venus", "mercury", "moon", "saturn", "jupiter"]
CHALDEAN_FACES = [CHALDEAN_ORDER[i % 7] for i in range(36)]

# Essential dignity weights (Classical Ptolemaic / Lilly)
ESSENTIAL_WEIGHTS = {
    "domicile": 5,
    "exaltation": 4,
    "triplicity": 3,
    "term": 2,
    "face": 1,
    "detriment": -5,
    "fall": -4,
}

# Solar state threshold constants
SOLAR_THRESHOLDS = {
    "cazimi_deg": 17.0 / 60.0,   # 17 arcminutes = 0.2833°
    "combust_deg": 8.5,          # 8°30' = 8.5°
    "under_beams_deg": 17.0,     # 17°00' = 17.0°
}


# ═══════════════════════════════════════════════════════════
#  CORE DIGNITY & SOLAR LOOKUPS
# ═══════════════════════════════════════════════════════════

def get_bound_lord(sign_idx: int, deg_in_sign: float) -> str:
    """Return the Egyptian term lord for a degree in a sign."""
    bounds = EGYPTIAN_BOUNDS[sign_idx % 12]
    for lord, limit in bounds:
        if deg_in_sign < limit:
            return lord
    return bounds[-1][0]


def get_face_lord(sign_idx: int, deg_in_sign: float) -> str:
    """Return the Chaldean face (decan) lord for a degree in a sign."""
    decan_idx = min(2, int(deg_in_sign // 10))
    return CHALDEAN_FACES[(sign_idx % 12) * 3 + decan_idx]


def compute_essential_dignities(planet_key: str, longitude: float, is_diurnal: bool) -> Dict[str, Any]:
    """Calculate the 5 essential dignities plus detriment/fall and net essential score."""
    sign_idx = int(longitude // 30) % 12
    deg_in_sign = longitude % 30.0

    domicile_lord = DOMICILE_RULERS[sign_idx]
    exalt_lord = EXALTATION_RULERS[sign_idx]
    detriment_lord = DETRIMENT_RULERS[sign_idx]
    fall_lord = FALL_RULERS[sign_idx]

    tri_lords = DOROTHEAN_TRIPLICITY[sign_idx]
    active_tri_lord = tri_lords[0] if is_diurnal else tri_lords[1]

    term_lord = get_bound_lord(sign_idx, deg_in_sign)
    face_lord = get_face_lord(sign_idx, deg_in_sign)

    is_domicile = (planet_key == domicile_lord)
    is_exaltation = (planet_key == exalt_lord)
    is_triplicity = (planet_key == active_tri_lord)
    is_term = (planet_key == term_lord)
    is_face = (planet_key == face_lord)
    is_detriment = (planet_key == detriment_lord)
    is_fall = (planet_key == fall_lord)

    score = 0
    if is_domicile:
        score += ESSENTIAL_WEIGHTS["domicile"]
    if is_exaltation:
        score += ESSENTIAL_WEIGHTS["exaltation"]
    if is_triplicity:
        score += ESSENTIAL_WEIGHTS["triplicity"]
    if is_term:
        score += ESSENTIAL_WEIGHTS["term"]
    if is_face:
        score += ESSENTIAL_WEIGHTS["face"]
    if is_detriment:
        score += ESSENTIAL_WEIGHTS["detriment"]
    if is_fall:
        score += ESSENTIAL_WEIGHTS["fall"]

    return {
        "sign": SIGN_NAMES_ZH[sign_idx],
        "degree_in_sign": round(deg_in_sign, 4),
        "domicile": is_domicile,
        "exaltation": is_exaltation,
        "triplicity": is_triplicity,
        "term": is_term,
        "face": is_face,
        "detriment": is_detriment,
        "fall": is_fall,
        "essential_score": score,
        "term_lord": term_lord,
        "face_lord": face_lord,
        "active_triplicity_lord": active_tri_lord,
        "domicile_ruler": domicile_lord,
    }


def compute_solar_state(planet_lon: float, sun_lon: float) -> Dict[str, Any]:
    """Calculate whether a planet is cazimi, combust, under the beams, or free."""
    diff = abs(planet_lon - sun_lon)
    if diff > 180.0:
        diff = 360.0 - diff

    if diff < SOLAR_THRESHOLDS["cazimi_deg"]:
        state = "cazimi"
        state_zh = "日核内(核心)"
    elif diff < SOLAR_THRESHOLDS["combust_deg"]:
        state = "combust"
        state_zh = "燃烧(焦伤)"
    elif diff < SOLAR_THRESHOLDS["under_beams_deg"]:
        state = "under_beams"
        state_zh = "在日光束下"
    else:
        state = "free"
        state_zh = "自由"

    return {
        "state": state,
        "state_zh": state_zh,
        "solar_separation_deg": round(diff, 4),
    }


def compute_orientality(planet_lon: float, sun_lon: float) -> Dict[str, str]:
    """Calculate whether a planet rises before the Sun (Oriental) or after (Occidental)."""
    # (sun_lon - planet_lon + 360) % 360 < 180 means planet has smaller longitude,
    # so it rises earlier in the diurnal rotation: Oriental (东出 / 晨星).
    diff = (sun_lon - planet_lon + 360.0) % 360.0
    is_oriental = (0.0 < diff < 180.0)
    return {
        "orientality": "oriental" if is_oriental else "occidental",
        "orientality_zh": "东出" if is_oriental else "西入",
    }


# ═══════════════════════════════════════════════════════════
#  RECEPTIONS & MUTUAL RECEPTIONS
# ═══════════════════════════════════════════════════════════

def _dignities_given_by(dignitor: str, lon: float, is_diurnal: bool) -> List[Tuple[str, bool]]:
    """Return dignities provided by dignitor to a point at lon: list of (dignity_name, is_strong)."""
    sign_idx = int(lon // 30) % 12
    deg = lon % 30.0
    d = []
    if DOMICILE_RULERS[sign_idx] == dignitor:
        d.append(("庙", True))
    if EXALTATION_RULERS[sign_idx] == dignitor:
        d.append(("旺", True))

    tri = DOROTHEAN_TRIPLICITY[sign_idx]
    active_tri = tri[0] if is_diurnal else tri[1]
    if active_tri == dignitor:
        d.append(("三分", False))

    if get_bound_lord(sign_idx, deg) == dignitor:
        d.append(("界", False))
    if get_face_lord(sign_idx, deg) == dignitor:
        d.append(("面", False))
    return d


def _reception_strength(dignitor: str, lon: float, is_diurnal: bool) -> Tuple[bool, List[str]]:
    """Check if dignities provided by dignitor meet the classical reception threshold (strong >= 1 or weak >= 2)."""
    d = _dignities_given_by(dignitor, lon, is_diurnal)
    strong = sum(1 for _, s in d if s)
    weak = sum(1 for _, s in d if not s)
    meets = (strong >= 1 or weak >= 2)
    return meets, [name for name, _ in d]


def _get_lon(p_dict: Any) -> float:
    if isinstance(p_dict, (int, float)):
        return float(p_dict)
    if 'lon' in p_dict:
        return float(p_dict['lon'])
    return float(p_dict['longitude'])

def compute_receptions(
    planets_map: Dict[str, Dict[str, Any]],
    aspects_list: List[Dict[str, Any]],
    is_diurnal: bool,
) -> Dict[str, Any]:
    """Calculate mutual receptions (no aspect required) and one-way receptions (Ptolemaic aspect required)."""
    target_planets = [k for k in TRADITIONAL_PLANETS if k in planets_map]

    # Map Ptolemaic aspects between traditional planets
    ptolemaic_aspects = {"合相", "六分相", "四分相", "三分相", "对分相"}
    aspect_lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for a in aspects_list:
        if a.get("aspect") in ptolemaic_aspects:
            p1 = a.get("point1")
            p2 = a.get("point2")
            if p1 and p2:
                aspect_lookup[(p1, p2)] = a
                aspect_lookup[(p2, p1)] = a

    mutual_receptions = []
    mutual_pairs = set()

    for i in range(len(target_planets)):
        for j in range(i + 1, len(target_planets)):
            p1, p2 = target_planets[i], target_planets[j]
            lon1 = _get_lon(planets_map[p1])
            lon2 = _get_lon(planets_map[p2])

            m1, parts1 = _reception_strength(p1, lon2, is_diurnal)
            m2, parts2 = _reception_strength(p2, lon1, is_diurnal)

            if m1 and m2:
                mutual_pairs.add(tuple(sorted([p1, p2])))
                mutual_receptions.append({
                    "planet1": p1,
                    "planet1_zh": PLANET_ZH.get(p1, p1),
                    "dignities_of_planet1": parts1,
                    "planet2": p2,
                    "planet2_zh": PLANET_ZH.get(p2, p2),
                    "dignities_of_planet2": parts2,
                    "has_aspect": (p1, p2) in aspect_lookup,
                    "aspect": aspect_lookup[(p1, p2)]["aspect"] if (p1, p2) in aspect_lookup else None,
                })

    receptions = []
    for p_dignitor in target_planets:
        for p_received in target_planets:
            if p_dignitor == p_received:
                continue
            if tuple(sorted([p_dignitor, p_received])) in mutual_pairs:
                continue
            if (p_dignitor, p_received) not in aspect_lookup:
                continue

            lon_received = _get_lon(planets_map[p_received])
            meets, parts = _reception_strength(p_dignitor, lon_received, is_diurnal)
            if meets:
                asp = aspect_lookup[(p_dignitor, p_received)]
                receptions.append({
                    "received_planet": p_received,
                    "received_planet_zh": PLANET_ZH.get(p_received, p_received),
                    "dignitor_planet": p_dignitor,
                    "dignitor_planet_zh": PLANET_ZH.get(p_dignitor, p_dignitor),
                    "dignities_granted": parts,
                    "aspect": asp["aspect"],
                    "orb": asp.get("orb"),
                })

    return {
        "threshold": "strong >= 1 or weak >= 2 dignities (strong=庙/旺, weak=三分/界/面)",
        "mutual_receptions": mutual_receptions,
        "receptions": receptions,
    }


# ═══════════════════════════════════════════════════════════
#  ARABIC & HELLENISTIC LOTS CATALOG
# ═══════════════════════════════════════════════════════════

def _norm_deg(x: float) -> float:
    return (x % 360.0 + 360.0) % 360.0


def compute_lots(
    asc_lon: float,
    sun_lon: float,
    moon_lon: float,
    planets_map: Dict[str, float],
    cusps: List[float],
    is_diurnal: bool,
    requested_lots: Optional[List[str]] = None,
    house_system: str = "whole_sign",
) -> List[Dict[str, Any]]:
    """Compute Arabic and Hellenistic lots with formulas and day/night reversal info."""
    ven = planets_map.get("venus", 0.0)
    mar = planets_map.get("mars", 0.0)
    jup = planets_map.get("jupiter", 0.0)
    sat = planets_map.get("saturn", 0.0)
    merc = planets_map.get("mercury", 0.0)

    fof = _norm_deg(asc_lon + moon_lon - sun_lon) if is_diurnal else _norm_deg(asc_lon + sun_lon - moon_lon)
    pos = _norm_deg(asc_lon + sun_lon - moon_lon) if is_diurnal else _norm_deg(asc_lon + moon_lon - sun_lon)

    # Condition for Father 3: Saturn within 15° of Sun
    sat_sun_diff = abs(sat - sun_lon)
    if sat_sun_diff > 180.0:
        sat_sun_diff = 360.0 - sat_sun_diff
    sat_combust_trigger = (sat_sun_diff <= 15.0)

    # Catalog of lots
    # (key, name_zh, formula_day, formula_night, reverses, calc_fn)
    catalog = {
        "fortune": {
            "key": "fortune", "name_zh": "福点",
            "formula_day": "ASC + ☽ − ☉", "formula_night": "ASC + ☉ − ☽",
            "reversed_at_night": True,
            "longitude": fof,
            "provenance": "Hellenistic Hermes / Ptolemy",
        },
        "spirit": {
            "key": "spirit", "name_zh": "精神点",
            "formula_day": "ASC + ☉ − ☽", "formula_night": "ASC + ☽ − ☉",
            "reversed_at_night": True,
            "longitude": pos,
            "provenance": "Hellenistic Hermes / Valens",
        },
        "eros": {
            "key": "eros", "name_zh": "爱神点(Eros)",
            "formula_day": "ASC + ♀ − 精神点", "formula_night": "ASC + 精神点 − ♀",
            "reversed_at_night": True,
            "longitude": _norm_deg(asc_lon + ven - pos) if is_diurnal else _norm_deg(asc_lon + pos - ven),
            "provenance": "Hermetic 7 (Schmidt / Delphic Oracle)",
        },
        "necessity": {
            "key": "necessity", "name_zh": "必然点",
            "formula_day": "ASC + 福点 − ☿", "formula_night": "ASC + ☿ − 福点",
            "reversed_at_night": True,
            "longitude": _norm_deg(asc_lon + fof - merc) if is_diurnal else _norm_deg(asc_lon + merc - fof),
            "provenance": "Hermetic 7 (Schmidt)",
        },
        "courage": {
            "key": "courage", "name_zh": "勇气点",
            "formula_day": "ASC + 福点 − ♂", "formula_night": "ASC + ♂ − 福点",
            "reversed_at_night": True,
            "longitude": _norm_deg(asc_lon + fof - mar) if is_diurnal else _norm_deg(asc_lon + mar - fof),
            "provenance": "Hermetic 7 (Schmidt)",
        },
        "victory": {
            "key": "victory", "name_zh": "胜利点",
            "formula_day": "ASC + ♃ − 精神点", "formula_night": "ASC + 精神点 − ♃",
            "reversed_at_night": True,
            "longitude": _norm_deg(asc_lon + jup - pos) if is_diurnal else _norm_deg(asc_lon + pos - jup),
            "provenance": "Hermetic 7 (Schmidt)",
        },
        "nemesis": {
            "key": "nemesis", "name_zh": "报应点",
            "formula_day": "ASC + 福点 − ♄", "formula_night": "ASC + ♄ − 福点",
            "reversed_at_night": True,
            "longitude": _norm_deg(asc_lon + fof - sat) if is_diurnal else _norm_deg(asc_lon + sat - fof),
            "provenance": "Hermetic 7 (Schmidt)",
        },
        "marriage_male": {
            "key": "marriage_male", "name_zh": "婚姻点(男)",
            "formula_day": "ASC + ♀ − ♄", "formula_night": "ASC + ♀ − ♄",
            "reversed_at_night": False,
            "longitude": _norm_deg(asc_lon + ven - sat),
            "provenance": "Hermes / Valens male marriage lot",
        },
        "marriage_female": {
            "key": "marriage_female", "name_zh": "婚姻点(女)",
            "formula_day": "ASC + ♄ − ♀", "formula_night": "ASC + ♄ − ♀",
            "reversed_at_night": False,
            "longitude": _norm_deg(asc_lon + sat - ven),
            "provenance": "Hermes / Valens female marriage lot",
        },
        "mother": {
            "key": "mother", "name_zh": "母亲点",
            "formula_day": "ASC + ☽ − ♀", "formula_night": "ASC + ♀ − ☽",
            "reversed_at_night": True,
            "longitude": _norm_deg(asc_lon + moon_lon - ven) if is_diurnal else _norm_deg(asc_lon + ven - moon_lon),
            "provenance": "Classical parental lot",
        },
        "father_default": {
            "key": "father_default", "name_zh": "父亲点1(日土反转)",
            "formula_day": "ASC + ♄ − ☉", "formula_night": "ASC + ☉ − ♄",
            "reversed_at_night": True,
            "longitude": _norm_deg(asc_lon + sat - sun_lon) if is_diurnal else _norm_deg(asc_lon + sun_lon - sat),
            "provenance": "Standard Greek / Arabic father lot",
        },
        "father_no_reversal": {
            "key": "father_no_reversal", "name_zh": "父亲点2(昼夜不反转)",
            "formula_day": "ASC + ♄ − ☉", "formula_night": "ASC + ♄ − ☉",
            "reversed_at_night": False,
            "longitude": _norm_deg(asc_lon + sat - sun_lon),
            "provenance": "Alternative tradition without sect reversal",
        },
        "father_saturn_combust": {
            "key": "father_saturn_combust", "name_zh": "父亲点3(日木公式)",
            "formula_day": "ASC + ♃ − ☉", "formula_night": "ASC + ☉ − ♃",
            "reversed_at_night": True,
            "longitude": _norm_deg(asc_lon + jup - sun_lon) if is_diurnal else _norm_deg(asc_lon + sun_lon - jup),
            "trigger_condition": f"土星距太阳15°内适用(当前日土距离: {sat_sun_diff:.2f}°，{'触发' if sat_combust_trigger else '未触发'})",
            "provenance": "Used when Saturn is combust or under the beams",
        },
        "siblings": {
            "key": "siblings", "name_zh": "兄弟点",
            "formula_day": "ASC + ♃ − ♄", "formula_night": "ASC + ♄ − ♃",
            "reversed_at_night": True,
            "longitude": _norm_deg(asc_lon + jup - sat) if is_diurnal else _norm_deg(asc_lon + sat - jup),
            "provenance": "Classical fraternal lot",
        },
        "children": {
            "key": "children", "name_zh": "子女点",
            "formula_day": "ASC + ♄ − ♃", "formula_night": "ASC + ♃ − ♄",
            "reversed_at_night": True,
            "longitude": _norm_deg(asc_lon + sat - jup) if is_diurnal else _norm_deg(asc_lon + jup - sat),
            "provenance": "Classical progeny lot",
        },
        "illness": {
            "key": "illness", "name_zh": "疾病点",
            "formula_day": "ASC + ♂ − ♄", "formula_night": "ASC + ♄ − ♂",
            "reversed_at_night": True,
            "longitude": _norm_deg(asc_lon + mar - sat) if is_diurnal else _norm_deg(asc_lon + sat - mar),
            "provenance": "Classical chronic illness lot",
        },
    }

    if requested_lots:
        req_keys = [k.strip().lower() for k in requested_lots]
        selected = [catalog[k] for k in req_keys if k in catalog]
    else:
        selected = list(catalog.values())

    from hellenistic import whole_sign_house, placidus_house

    results = []
    for entry in selected:
        lon = entry["longitude"]
        sign_idx = int(lon // 30) % 12
        hw = whole_sign_house(lon, asc_lon)
        hp = placidus_house(lon, tuple(cusps)) if cusps and len(cusps) == 12 else hw
        active_house = hp if house_system == "placidus" else hw

        ruler = DOMICILE_RULERS[sign_idx]
        item = {
            "key": entry["key"],
            "name_zh": entry["name_zh"],
            "longitude": round(lon, 4),
            "sign": SIGN_NAMES_ZH[sign_idx],
            "sign_zh": SIGN_NAMES_ZH[sign_idx],
            "degree_in_sign": round(lon % 30.0, 4),
            "house": active_house,
            "house_whole_sign": hw,
            "house_placidus": hp,
            "ruler": ruler,
            "ruler_zh": PLANET_ZH.get(ruler, ruler),
            "formula": entry["formula_day"] if is_diurnal else entry["formula_night"],
            "reversed_at_night": entry["reversed_at_night"],
            "provenance": entry.get("provenance", ""),
        }
        if "trigger_condition" in entry:
            item["trigger_condition"] = entry["trigger_condition"]
        results.append(item)

    return results

