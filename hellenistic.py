#!/usr/bin/env python3
"""
李孟浩项目 — 古典占星计算模块 v1.0
=====================================
派系判定 · Demetra评分 · 半球孤军 · 三分主星 · 必然尊贵

用法:
    from hellenistic import analyze
    result = analyze(data)  # data 来自 adapter.get_natal_chart()
    print(result.planet_table)  # 文本表格
    result.save_chart("output.png", system="placidus")  # 生成图表

行星范围: 7传统(日月水金火木土) + 冥王星(仅参与必要尊贵)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Callable
import os

# ═══════════════════════════════════════════════════════════
#  常量
# ═══════════════════════════════════════════════════════════

SIGN_CN = {
    "Ari": "白羊座", "Tau": "金牛座", "Gem": "双子座", "Can": "巨蟹座",
    "Leo": "狮子座", "Vir": "处女座", "Lib": "天秤座", "Sco": "天蝎座",
    "Sag": "射手座", "Cap": "摩羯座", "Aqu": "水瓶座", "Pis": "双鱼座",
}

SIGN_ELEMENT: Dict[str, str] = {
    "Ari": "火", "Leo": "火", "Sag": "火",
    "Tau": "土", "Vir": "土", "Cap": "土",
    "Gem": "风", "Lib": "风", "Aqu": "风",
    "Can": "水", "Sco": "水", "Pis": "水",
}

YANG_SIGNS = {"Ari", "Gem", "Leo", "Lib", "Sag", "Aqu"}

DAY_PLANETS = {"sun": "太阳", "jupiter": "木星", "saturn": "土星"}
NIGHT_PLANETS = {"moon": "月亮", "venus": "金星", "mars": "火星"}
PLANET_KEYS = {**DAY_PLANETS, **NIGHT_PLANETS, "mercury": "水星", "pluto": "冥王星"}
REVERSE_PK = {v: k for k, v in PLANET_KEYS.items()}

# 多罗修斯三分主星表
TRIPLICITY: Dict[str, Dict[str, str]] = {
    "火": {"day": "太阳", "night": "木星", "participating": "土星"},
    "土": {"day": "金星", "night": "月亮", "participating": "火星"},
    "风": {"day": "土星", "night": "水星", "participating": "木星"},
    "水": {"day": "金星", "night": "火星", "participating": "月亮"},
}

# 必然尊贵 (domicile / exaltation / detriment / fall)
DIGNITY: Dict[str, Dict[str, List[str]]] = {
    "domicile": {
        "太阳": ["Leo"], "月亮": ["Can"], "水星": ["Gem", "Vir"],
        "金星": ["Tau", "Lib"], "火星": ["Ari", "Sco"],
        "木星": ["Sag", "Pis"], "土星": ["Cap", "Aqu"],
    },
    "exaltation": {
        "太阳": ["Ari"], "月亮": ["Tau"], "水星": ["Vir"],
        "金星": ["Pis"], "火星": ["Cap"], "木星": ["Can"], "土星": ["Lib"],
    },
    "detriment": {
        "太阳": ["Aqu"], "月亮": ["Cap"], "水星": ["Sag", "Pis"],
        "金星": ["Sco", "Ari"], "火星": ["Lib", "Tau"],
        "木星": ["Gem", "Vir"], "土星": ["Can", "Leo"],
    },
    "fall": {
        "太阳": ["Lib"], "月亮": ["Sco"], "水星": ["Pis"],
        "金星": ["Vir"], "火星": ["Can"], "木星": ["Cap"], "土星": ["Ari"],
    },
}

DIGNITY_CN = {"domicile": "入庙", "exaltation": "入旺", "detriment": "入弱", "fall": "落陷"}

HOUSE_TYPE = {
    1: "强宫", 4: "强宫", 7: "强宫", 10: "强宫",
    5: "吉宫", 11: "吉宫",
    6: "凶宫", 8: "凶宫", 12: "凶宫",
    3: "弱宫", 9: "弱宫",
}

STAGES = ["0-25岁", "25-50岁", "50岁+"]


# ═══════════════════════════════════════════════════════════
#  宫位判定
# ═══════════════════════════════════════════════════════════

def placidus_house(lon: float, cusps: Tuple[float, ...]) -> int:
    """普拉西度制 (cusps[0-11]=1-12宫头)"""
    for i in range(12):
        cs, ce = cusps[i], cusps[(i + 1) % 12]
        if cs <= ce:
            if cs <= lon < ce:
                return i + 1
        else:
            if lon >= cs or lon < ce:
                return i + 1
    return 1


def whole_sign_house(lon: float, asc_lon: float) -> int:
    """整宫制 (ASC星座=1宫)"""
    return (int(lon // 30) - int(asc_lon // 30) + 12) % 12 + 1


# ═══════════════════════════════════════════════════════════
#  分析结果
# ═══════════════════════════════════════════════════════════

# 天然凶星
NATURAL_MALEFICS = {"火星", "土星"}

# 喜乐宫 (Planet Joy) - 每个行星喜乐的宫位
PLANET_JOY = {
    "太阳": 19,   # 第9宫 (荣誉宫)
    "月亮": 3,    # 第3宫 (兄弟宫)
    "水星": 1,    # 第1宫 (命宫)
    "金星": 5,    # 第5宫 (子女宫)
    "火星": 6,    # 第6宫 (奴仆宫)
    "木星": 11,   # 第11宫 (朋友宫)
    "土星": 12,   # 第12宫 (疾厄宫)
}

@dataclass
class PlanetScore:
    planet_cn: str
    sign: str
    house: int
    sect_score: Optional[int]       # ±5, None for 水星
    hemi_score: Optional[int]       # ±3
    sign_score: Optional[int]       # ±1
    total: Optional[int]
    dignity: str                    # "入庙/落陷/—" 等
    hemisphere_isolated: bool       # 半球孤军
    is_malefic: bool = False        # 天然凶星(火/土)
    in_joy: bool = False            # 是否在喜乐宫


@dataclass
class TriplicityLord:
    stage: str                      # "0-25岁"
    planet_cn: str
    sign: str
    house: int
    score: Optional[int]
    dignity: str
    house_type: str                 # "角宫/续宫/果宫"
    in_joy: bool = False           # 是否在喜乐宫


@dataclass
class HellenisticResult:
    name: str
    system: str                     # "placidus" / "whole_sign"
    sect: str                       # "日生人" / "夜生人"
    sun_sign: str
    sun_house: int
    sun_up: bool
    element: str
    luminaries: str                 # "太阳" / "月亮"
    triplicity_seq: List[str]
    day_planets: List[PlanetScore] = field(default_factory=list)
    night_planets: List[PlanetScore] = field(default_factory=list)
    triplicity_lords: List[TriplicityLord] = field(default_factory=list)
    total_score: int = 0

    def all_scores(self) -> List[int]:
        """所有评分的列表"""
        scores = []
        for p in self.day_planets + self.night_planets:
            if p.total is not None:
                scores.append(p.total)
        return scores


# ═══════════════════════════════════════════════════════════
#  核心计算
# ═══════════════════════════════════════════════════════════

def is_diurnal(sun_lon: float, asc_lon: float) -> bool:
    """Return whether the Sun is above the ASC→DSC horizon arc."""
    return (sun_lon - asc_lon) % 360 >= 180


def sect_from_horizon(sun_lon: float, asc_lon: float) -> str:
    """Single source of truth for the chart sect."""
    return "日生人" if is_diurnal(sun_lon, asc_lon) else "夜生人"

def analyze(data: Dict, system: str = "placidus",
            fixed_sect: Optional[str] = None) -> HellenisticResult:
    """
    完整古典占星分析。

    Args:
        data: adapter.get_natal_chart() 返回的 data
        system: "placidus" 或 "whole_sign"
        fixed_sect: 预先计算好的派系（"日生人"/"夜生人"）。
                    由 analyze_both() 传入，保证两宫制使用同一派系。
                    单独调用时不传，函数自行通过黄道经度计算。

    Returns:
        HellenisticResult 包含所有计算结果
    """
    ps = data["planets"]
    cusps = data["houses"]["cusps"]
    asc_lon = cusps[0]
    name = data.get("name", "")
    sun_lon = ps["sun"]["longitude"]

    # 宫位函数
    if system == "whole_sign":
        hfn = lambda lon: whole_sign_house(lon, asc_lon)
    else:
        hfn = lambda lon: placidus_house(lon, cusps)

    sh = hfn(sun_lon)
    # 派系判断与宫制无关，统一使用地平线经度几何。
    if fixed_sect is not None:
        sect = fixed_sect
        sun_up = sect == "日生人"
    else:
        sect = sect_from_horizon(sun_lon, asc_lon)
        sun_up = sect == "日生人"

    # ── 各行星 Demetra 评分 ──
    def calc_score(pk: str, pcn: str) -> PlanetScore:
        pi = ps[pk]
        nh = hfn(pi["longitude"])
        sign = pi["sign"]
        in_joy = PLANET_JOY.get(pcn, 0) == nh

        if pcn == "水星":
            return PlanetScore(pcn, sign, nh, None, None, None, None,
                               _dignity(pcn, sign), False, pcn in NATURAL_MALEFICS, in_joy)

        is_day = pcn in DAY_PLANETS.values()
        up = nh >= 7

        # 派系 ±5
        sc = +5 if (sect == "日生人") == is_day else -5

        # 半球 ±3: 日间行星应在太阳半球，夜间行星应避开太阳
        hc = +3 if (is_day and up == sun_up) or (not is_day and up != sun_up) else -3

        # 阴阳 ±1
        si = +1 if (is_day and sign in YANG_SIGNS) or (not is_day and sign not in YANG_SIGNS) else -1

        total = sc + hc + si
        iso = (is_day and up != sun_up) or (not is_day and up == sun_up)

        return PlanetScore(pcn, sign, nh, sc, hc, si, total,
                           _dignity(pcn, sign), iso, pcn in NATURAL_MALEFICS, in_joy)

    day_scores = [calc_score(pk, PLANET_KEYS[pk]) for pk in DAY_PLANETS]
    night_scores = [calc_score(pk, PLANET_KEYS[pk]) for pk in NIGHT_PLANETS]

    # ── 三分主星 ──
    lum = "太阳" if sect == "日生人" else "月亮"
    lum_sign = ps["sun"]["sign"] if sect == "日生人" else ps["moon"]["sign"]
    elem = SIGN_ELEMENT[lum_sign]
    order = ["day", "night", "participating"] if sect == "日生人" else ["night", "day", "participating"]
    lord_names = [TRIPLICITY[elem][o] for o in order]

    lords = []
    for i, lord in enumerate(lord_names):
        pk = REVERSE_PK[lord]
        pi = ps[pk]
        nh = hfn(pi["longitude"])
        sc = calc_score(pk, lord)
        in_joy = PLANET_JOY.get(lord, 0) == nh
        lords.append(TriplicityLord(
            STAGES[i], lord, pi["sign"], nh,
            sc.total, _dignity(lord, pi["sign"]), HOUSE_TYPE.get(nh, ''), in_joy
        ))

    total = sum(s.total for s in day_scores + night_scores if s.total is not None)

    return HellenisticResult(
        name=name, system=system, sect=sect,
        sun_sign=ps["sun"]["sign"], sun_house=sh, sun_up=sun_up,
        element=elem, luminaries=lum,
        triplicity_seq=lord_names,
        day_planets=day_scores, night_planets=night_scores,
        triplicity_lords=lords, total_score=total,
    )


def _dignity(pcn: str, sign: str) -> str:
    d = []
    for dt, dm in DIGNITY.items():
        if sign in dm.get(pcn, []):
            d.append(DIGNITY_CN[dt])
    return "+".join(d) if d else "—"


# ═══════════════════════════════════════════════════════════
#  文本输出
# ═══════════════════════════════════════════════════════════

def format_table(r: HellenisticResult) -> str:
    """返回格式化的文本表格"""
    def n(x): return f"{x:+d}" if x is not None else "—"
    lines = []
    lines.append(f"{r.name} · {r.system} · {r.sect} · {r.luminaries}{SIGN_CN[r.sun_sign]}{r.sun_house}宫({r.element}象)")
    lines.append("")

    # 日间派
    lines.append(f"  {'行星':<6} {'宫位':<18} {'派±5':>4} {'半±3':>4} {'阴±1':>4} {'总分':>4} {'尊贵':<8} 孤军")
    for p in r.day_planets:
        iso = "半球孤军" if p.hemisphere_isolated else ""
        lines.append(f"  {p.planet_cn:<6} {SIGN_CN[p.sign]} {p.house}宫{'':>8} {n(p.sect_score):>4} {n(p.hemi_score):>4} {n(p.sign_score):>4} {n(p.total):>4} {p.dignity:<8} {iso}")
    lines.append("")

    # 夜间派
    for p in r.night_planets:
        iso = "半球孤军" if p.hemisphere_isolated else ""
        lines.append(f"  {p.planet_cn:<6} {SIGN_CN[p.sign]} {p.house}宫{'':>8} {n(p.sect_score):>4} {n(p.hemi_score):>4} {n(p.sign_score):>4} {n(p.total):>4} {p.dignity:<8} {iso}")
    lines.append("")

    # 三分主星
    seq_str = " → ".join(r.triplicity_seq)
    lines.append(f"  三分主星: {r.luminaries}在{SIGN_CN[r.sun_sign]}({r.element}象) → {seq_str}")
    for t in r.triplicity_lords:
        lines.append(f"  {t.stage}: {t.planet_cn} {SIGN_CN[t.sign]} {t.house}宫({t.house_type}) 评分={n(t.score)}  {t.dignity}")

    scores = [s for s in r.all_scores()]
    lines.append(f"\n  派系总分: {''.join(n(s) for s in scores)} = {r.total_score:+d}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  便捷入口
# ═══════════════════════════════════════════════════════════

def analyze_both(data: Dict, name: str = "") -> Tuple[HellenisticResult, HellenisticResult]:
    """返回 (普拉西度结果, 整宫结果)，派系一次性确定，两宫制共用。"""
    data["name"] = name
    # 派系由黄道经度确定，与宫制无关，在此统一计算后传入两次 analyze()
    sun_lon = data["planets"]["sun"]["longitude"]
    asc_lon = data["houses"]["cusps"][0]
    sect = sect_from_horizon(sun_lon, asc_lon)
    return analyze(data, "placidus", sect), analyze(data, "whole_sign", sect)
