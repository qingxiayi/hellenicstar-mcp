#!/usr/bin/env python3
"""
李孟浩项目 — 福点盘宫位投影 v4.0
===================================
核心原理：
  福点落在本命的哪个宫位 → 该宫位 = 福点盘第1宫
  福点盘照顾宫位: 1 / 4 / 7 / 10 / 11
  映射回本命宫位，找对应行星

两制并行:
  普拉西度制 — 本命普拉西度宫位
  整宫制     — ASC星座=1宫，依次12星座

行星范围: 7传统(日月水金火木土) + 冥王星
附加分析:
  ① 凶宫赦免 — 被照顾行生是否在本命6/8/12宫
  ② 凶星检查 — 被照顾行生中的火星/土星/冥王星
"""

import sys
import os
import time
from typing import Dict, List, Tuple, Set, Optional, Callable

# ── 常量 ──────────────────────────────────────────

SIGNS = [
    "白羊座", "金牛座", "双子座", "巨蟹座",
    "狮子座", "处女座", "天秤座", "天蝎座",
    "射手座", "摩羯座", "水瓶座", "双鱼座",
]

PLANETS: Dict[str, str] = {
    "sun": "太阳", "moon": "月亮", "mercury": "水星", "venus": "金星",
    "mars": "火星", "jupiter": "木星", "saturn": "土星", "pluto": "冥王星",
}

CARE_HOUSES: List[int] = [1, 4, 7, 10, 11]
MALEFIC_HOUSES: Dict[int, str] = {6: "", 8: "", 12: ""}
MALEFIC_PLANETS: Set[str] = {"火星", "土星", "冥王星"}

# 行星条目: (中文名, 本命宫位, 星座名, 星座内度数)
PlanetEntry = Tuple[str, int, str, float]
# 照顾结果: {福点盘宫号: [(行星, 本命宫位, 星座, 度数), ...]}
CareResult = Dict[int, List[PlanetEntry]]


# ── 工具函数 ──────────────────────────────────────

def sign_of(lon: float) -> Tuple[str, float]:
    """经度 → (星座名, 星座内度数)"""
    si = int(lon // 30) % 12
    return SIGNS[si], lon % 30


def _ensure_path() -> None:
    """确保项目路径在 sys.path 中（本地开发路径，生产环境无效果）"""
    skill_dir = '/Users/lijianling/.hermes/skills/menghao-natal-chart'
    # 注意：不再 pop sys.modules，否则会清除已注入的 CITY_COORDINATES
    if skill_dir not in sys.path:
        sys.path.insert(0, skill_dir)


# ── 宫位判定函数 ──────────────────────────────────

def placidus_house(lon: float, cusps: Tuple[float, ...]) -> int:
    """普拉西度制: cusps[0-11]=1-12宫头"""
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
    """整宫制: ASC星座=1宫, 依次"""
    asc_si = int(asc_lon // 30) % 12
    si = int(lon // 30) % 12
    return (si - asc_si + 12) % 12 + 1


# ── 核心投影 ──────────────────────────────────────

def project(
    data: Dict,
    house_fn: Callable,
    house_arg,
) -> Tuple[int, Dict[int, int], CareResult]:
    """
    福点盘投影核心函数。

    Args:
        data: 本命盘数据 (adapter.get_natal_chart 返回的 data)
        house_fn: 宫位判定函数 (lon, *house_args) → 本命宫位号
        house_args: 传给 house_fn 的额外参数

    Returns:
        (福点在本命的宫位, {福点盘宫→本命宫}, {福点盘宫→[(行星,本命宫,星座,度数)]})
    """
    fof_lon = data["special_points"]["part_of_fortune"]["longitude"]
    fof_natal = house_fn(fof_lon, house_arg)

    # 福点盘照顾宫位 → 本命宫位映射
    mapping: Dict[int, int] = {}
    for fc in CARE_HOUSES:
        mapping[fc] = ((fof_natal - 1 + fc - 1) % 12) + 1

    # 收集本命行星并按宫位分组
    by_natal: Dict[int, List[PlanetEntry]] = {}
    for k, v in data["planets"].items():
        if k not in PLANETS:
            continue
        nh = house_fn(v["longitude"], house_arg)
        pcn = PLANETS[k]
        s, pos = sign_of(v["longitude"])
        by_natal.setdefault(nh, []).append((pcn, nh, s, pos))

    # 找每个福点盘照顾宫位里的行星
    cared: CareResult = {}
    for fc in CARE_HOUSES:
        nh = mapping[fc]
        cared[fc] = by_natal.get(nh, [])

    return fof_natal, mapping, cared


# ── 数据获取 ──────────────────────────────────────

def get_natal_data(name: str, y: int, mo: int, d: int,
                   h: int, mi: int, city: str, cc: str = "CN") -> Dict:
    """获取本命盘数据，自动处理城市坐标缺失"""
    from adapter import get_natal_chart

    # 注入补充城市坐标（幂等）
    try:
        from services.city_data import inject_extra_cities
        inject_extra_cities()
    except Exception:
        pass

    # Nominatim geocoding 兜底
    try:
        from engine.natal_chart import NatalChartCalculator as _NCC
        import re as _re2
        _lc2 = city.strip()
        def _local_has2(c, ks=_NCC.CITY_COORDINATES):
            if c in ks: return True
            for s in ['市','县','区','省','自治州','自治县']:
                if c.endswith(s) and c[:-len(s)] in ks: return True
            st = _re2.sub(r'[族回壮苗彝满蒙藏维哈侗布依土家瑶白傣黎傈僳]+自治[州县旗]$', '', c)
            if st and st in ks: return True
            if len(c) >= 3 and c[:2] in ks: return True
            return False
        if not _local_has2(_lc2):
            from services.geocoding import resolve_city
            resolve_city(_lc2)
    except Exception:
        pass

    _ensure_path()
    r = get_natal_chart(y, mo, d, h, mi, city, cc)
    if not r["success"]:
        raise RuntimeError(f"星盘计算失败: {r.get('error')}")
    return r["data"]


# ── 完整报告 ──────────────────────────────────────

def print_full_report(
    name: str,
    data: Dict,
    fof_lon: float,
    fof_natal: int,
    mapping: Dict[int, int],
    cared: CareResult,
    label: str,
) -> None:
    """输出福点盘完整分析报告"""
    fof_sign, fof_pos = sign_of(fof_lon)
    sep = "═" * 55
    line = "─" * 55

    print(f"\n{sep}")
    print(f"  {name}  福点盘投影 [{label}]")
    print(f"  福点: {fof_sign} {fof_pos:.2f}° → 本命第{fof_natal}宫")
    print(f"  照顾宫位: 福点盘 1 / 4 / 7 / 10 / 11")
    print(sep)

    # 主表
    print(f"\n{'福点盘宫':<10} {'=本命宫':<8} {'落入行星'}")
    print(f"{'─'*10} {'─'*8} {'─'*45}")
    all_cared: Set[str] = set()
    for fc in CARE_HOUSES:
        nh = mapping[fc]
        entries = cared[fc]
        if entries:
            parts = [f"{pcn}({s} {pos:.1f}°)" for pcn, _, s, pos in entries]
            row = ", ".join(parts)
        else:
            row = "(空)"
        print(f"第{fc}宫{'':>6} 第{nh}宫{'':>4}  {row}")
        for pcn, _, _, _ in entries:
            all_cared.add(pcn)

    # ① 凶宫赦免
    print(f"\n{line}")
    print(f"【分析①：凶宫赦免】被照顾行星是否在本命6/8/12宫")
    pardon = False
    for fc in CARE_HOUSES:
        for pcn, nh, s, pos in cared[fc]:
            if nh in MALEFIC_HOUSES:
                label_mh = MALEFIC_HOUSES[nh]
                print(f"  ✅ {pcn} 本命第{nh}宫({label_mh}) 被福点盘第{fc}宫赦免")
                pardon = True
    if not pardon:
        print(f"  无——所有被照顾行星均不在本命6/8/12宫")

    # ② 凶星检查
    print(f"\n【分析②：凶星检查】被照顾行星中的火星/土星/冥王星")
    mal = False
    for fc in CARE_HOUSES:
        for pcn, nh, s, pos in cared[fc]:
            if pcn in MALEFIC_PLANETS:
                print(f"  🔥 {pcn} 本命第{nh}宫 被福点盘第{fc}宫照顾 → 凶性赦免")
                mal = True
    if not mal:
        print(f"  无——被照顾行星中无火星/土星/冥王星")

    # 未被照顾
    print(f"\n{line}")
    print(f"【未被福点盘五宫照顾的行星】")
    uncared = []
    for k, v in data["planets"].items():
        if k not in PLANETS:
            continue
        pcn = PLANETS[k]
        if pcn in all_cared:
            continue
        nh = v["house"]
        fc = ((nh - fof_natal + 12) % 12) + 1
        tag = f" ⚠️{MALEFIC_HOUSES.get(nh, '')}" if nh in MALEFIC_HOUSES else ""
        uncared.append((pcn, nh, fc, tag))
    if uncared:
        for pcn, nh, fc, tag in uncared:
            print(f"  {pcn}: 本命第{nh}宫 (福点盘第{fc}宫){tag}")
    else:
        print(f"  (全部被照顾)")


# ════════════════════════════════════════════════════════════
#  入口
# ════════════════════════════════════════════════════════════

def run(name: str, y: int, mo: int, d: int,
        h: int, mi: int, city: str, cc: str = "CN") -> None:
    """运行一个人的完整福点盘分析（双制）"""
    t0 = time.time()
    data = get_natal_data(name, y, mo, d, h, mi, city, cc)
    fof_lon = data["special_points"]["part_of_fortune"]["longitude"]
    cusps = data["houses"]["cusps"]
    asc_lon = cusps[0]

    # ── 普拉西度制 ──
    fof_np, mapping_p, cared_p = project(data, placidus_house, cusps)
    print_full_report(name, data, fof_lon, fof_np, mapping_p, cared_p, "普拉西度制")

    # ── 整宫制 ──
    fof_nw, mapping_w, cared_w = project(data, whole_sign_house, asc_lon)
    print_full_report(name, data, fof_lon, fof_nw, mapping_w, cared_w, "整宫制")

    # ── 两制对比 ──
    sep = "═" * 55
    print(f"\n{sep}")
    print(f"  【两制对比】")
    print(f"  {'宫位':<8} {'普拉西度制':<24} {'整宫制':<24}")
    print(f"  {'─'*8} {'─'*24} {'─'*24}")
    for fc in CARE_HOUSES:
        pp = ", ".join(pcn for pcn, _, _, _ in cared_p[fc]) or "(空)"
        wp = ", ".join(pcn for pcn, _, _, _ in cared_w[fc]) or "(空)"
        mark = " ⚠️" if pp != wp else ""
        print(f"  第{fc}宫{'':>4} {pp:<20}    {wp}{mark}")

    elapsed = time.time() - t0
    print(f"\n  ⏱ 用时 {elapsed:.1f}s")


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 7:
        run(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), sys.argv[7])
    else:
        print("用法: python fortuna_projection.py <姓名> <年> <月> <日> <时> <分> <城市>")
