# -*- coding: utf-8 -*-
"""tests/test_transit_golden_cases.py —— P5 土木流年黄金案例回归（设计 §15.2）。

22 张固定案例覆盖：中国 1986-1991 夏令时纪元、国际时区、跨 0° 轴、贴轴、顺逆行、
年龄 0/1/6/12/14.75/29.5/79-80 边界、1930 前 + 2008 后、闰日、赤道/高纬/南半球。

黄金结果不要求与香港逐字节一致，要求（§15.2）：
  - 事件计数按引擎/规则版本固定（回归基线，改动即显式暴露）；
  - 精确 JD 由同版本引擎可重复生成（determinism）；
  - 除易变 current 外同输入结果一致。

案例走事件引擎层（本命四轴 + 出生 JD），星历精确、纯计算、不打网络。
时区/夏令时对「事件」不产生影响（只影响 local_date 展示，由出生 JD 已定瞬间）——
民用时间→JD 的 fold/gap 归一由 CivilTimeResolver 及其测试覆盖。
"""
import os
import sys

import pytest
import swisseph as swe

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.saturn_jupiter_transits import (  # noqa: E402
    compute_transit_events, wrap180, _CONJ_DEDUP_YEARS, _DAYS_PER_YEAR,
)
from services.transit_ephemeris import longitude_at  # noqa: E402


def _jd(y, m, d, h):
    return swe.julday(y, m, d, h)


def _axes_fixed(a, mc):
    return lambda _jd: {"Asc": a % 360, "MC": mc % 360,
                        "Dsc": (a + 180) % 360, "IC": (mc + 180) % 360}


def _axes_on_saturn():
    """四轴挂在本命土星经度上 → 贴轴 / 0 岁事件。"""
    def build(_jd):
        s = longitude_at("saturn", _jd)
        return {"Asc": s % 360, "MC": (s + 90) % 360,
                "Dsc": (s + 180) % 360, "IC": (s + 270) % 360}
    return build


def _axes_cross0():
    return lambda _jd: {"Asc": 0.5, "MC": 90.5, "Dsc": 180.5, "IC": 270.5}


# (label, birth_jd, axes_builder, max_age)
CASES = [
    ("1900 下界",           _jd(1900, 3, 21, 6.0),   _axes_fixed(10, 100), 30),
    ("1930 战前",           _jd(1930, 7, 1, 12.0),   _axes_fixed(200, 290), 30),
    ("1955 普通",           _jd(1955, 11, 9, 3.0),   _axes_fixed(45, 135), 30),
    ("1971 普通",           _jd(1971, 2, 14, 20.0),  _axes_fixed(320, 50), 30),
    ("1986 中国夏令时元年",  _jd(1986, 6, 15, 4.0),   _axes_fixed(150, 240), 30),
    ("1988 中国夏令时",      _jd(1988, 8, 1, 5.0),    _axes_fixed(88, 178), 30),
    ("1991 中国夏令时末年",  _jd(1991, 9, 10, 7.0),   _axes_fixed(270, 0), 30),
    ("1989 武汉基准",       _jd(1989, 7, 11, 4.5),   _axes_fixed(198.06, 109.28), 30),
    ("2000 千禧",           _jd(2000, 1, 1, 12.0),   _axes_fixed(280, 10), 30),
    ("2008 后",             _jd(2008, 5, 20, 15.0),  _axes_fixed(120, 210), 30),
    ("2010 近代",           _jd(2010, 12, 31, 23.0), _axes_fixed(15, 105), 30),
    ("跨0°轴 1975",         _jd(1975, 4, 4, 8.0),    _axes_cross0(), 30),
    ("跨0°轴 1995",         _jd(1995, 10, 20, 18.0), _axes_cross0(), 30),
    ("贴土星轴 1965",       _jd(1965, 6, 6, 6.0),    _axes_on_saturn(), 30),
    ("贴土星轴 1993",       _jd(1993, 3, 15, 10.0),  _axes_on_saturn(), 30),
    ("国际 NY 1980",        _jd(1980, 11, 3, 6.0),   _axes_fixed(60, 150), 30),
    ("国际 London 1999",    _jd(1999, 12, 25, 0.0),  _axes_fixed(175, 265), 30),
    ("南半球 Sydney 1983",  _jd(1983, 9, 1, 14.0),   _axes_fixed(240, 330), 30),
    ("年龄边界全程 1950",    _jd(1950, 1, 15, 9.0),   _axes_fixed(30, 120), 80),
    ("赤道 Quito 2005",     _jd(2005, 6, 21, 17.0),  _axes_fixed(100, 190), 30),
    ("高纬 Oslo 1968",      _jd(1968, 2, 29, 11.0),  _axes_fixed(210, 300), 30),
    ("闰日 2000",           _jd(2000, 2, 29, 12.0),  _axes_fixed(5, 95), 30),
]

# 黄金基线：(saturn_count, jupiter_count, aspect_count)，引擎 precise-ephemeris-1 /
# 规则 hk-visible-rules-precise-1。引擎或规则升级时须在此显式对齐，不得偷偷改弱。
GOLDEN = {
    "1900 下界": (5, 10, 6), "1930 战前": (4, 10, 6), "1955 普通": (5, 10, 6),
    "1971 普通": (5, 10, 7), "1986 中国夏令时元年": (5, 10, 6), "1988 中国夏令时": (5, 10, 6),
    "1991 中国夏令时末年": (4, 10, 6), "1989 武汉基准": (5, 10, 6), "2000 千禧": (4, 10, 7),
    "2008 后": (4, 10, 6), "2010 近代": (5, 11, 7), "跨0°轴 1975": (4, 11, 6),
    "跨0°轴 1995": (5, 11, 7), "贴土星轴 1965": (5, 10, 6), "贴土星轴 1993": (5, 10, 6),
    "国际 NY 1980": (4, 10, 7), "国际 London 1999": (4, 10, 7), "南半球 Sydney 1983": (4, 11, 6),
    "年龄边界全程 1950": (11, 28, 17), "赤道 Quito 2005": (4, 11, 7),
    "高纬 Oslo 1968": (4, 10, 6), "闰日 2000": (4, 10, 7),
}


@pytest.fixture(scope="module")
def computed():
    """每案例算一次，全模块复用。"""
    out = {}
    for label, bjd, ab, ma in CASES:
        out[label] = (compute_transit_events(ab(bjd), bjd, max_age=ma), bjd, ma)
    return out


def test_have_at_least_20_cases():
    assert len(CASES) >= 20
    assert set(c[0] for c in CASES) == set(GOLDEN)


@pytest.mark.parametrize("label", [c[0] for c in CASES])
def test_golden_event_counts(computed, label):
    ev, _bjd, _ma = computed[label]
    got = (len(ev["saturn_events"]), len(ev["jupiter_events"]), len(ev["aspects"]))
    assert got == GOLDEN[label], f"{label}: {got} != 基线 {GOLDEN[label]}"


def test_invariants_all_cases(computed):
    """跨全部案例的结构不变量。"""
    for label, (ev, bjd, ma) in computed.items():
        for key in ("saturn_events", "jupiter_events", "aspects"):
            ages = [e.age_years for e in ev[key]]
            assert ages == sorted(ages), f"{label}/{key} 未按年龄升序"
            assert all(a <= ma + 1e-6 for a in ages), f"{label}/{key} 越界"
        # 过境合轴仅顺行（0 岁除外）
        for pk, planet in (("saturn_events", "saturn"), ("jupiter_events", "jupiter")):
            for e in ev[pk]:
                if e.age_years > 0:
                    assert e.direction == "direct", f"{label} {e.event_id} 非顺行"
                    resid = abs(wrap180(
                        longitude_at(planet, e.exact_jd) - _axis_lon(label, e.axis)))
                    assert resid < 0.05, f"{label} 求根残差 {resid}"
        # 同轴去重间隔
        for pk, planet in (("saturn_events", "saturn"), ("jupiter_events", "jupiter")):
            by_axis = {}
            for e in ev[pk]:
                by_axis.setdefault(e.axis, []).append(e.exact_jd)
            mind = _CONJ_DEDUP_YEARS[planet] * _DAYS_PER_YEAR
            for jds in by_axis.values():
                jds.sort()
                for a, b in zip(jds, jds[1:]):
                    assert (b - a) >= mind - 1e-6, f"{label} 同轴去重违规"


def _axis_lon(label, axis):
    for lb, bjd, ab, _ma in CASES:
        if lb == label:
            return ab(bjd)[axis]
    raise KeyError(label)


def test_determinism_reproducible():
    """代表性 4 例重算，序列化事件完全一致（同版本可复现）。"""
    for label in ("1989 武汉基准", "跨0°轴 1995", "贴土星轴 1965", "年龄边界全程 1950"):
        bjd, ab, ma = next((b, a, m) for lb, b, a, m in CASES if lb == label)
        e1 = compute_transit_events(ab(bjd), bjd, max_age=ma)
        e2 = compute_transit_events(ab(bjd), bjd, max_age=ma)
        for key in ("saturn_events", "jupiter_events", "aspects"):
            assert [x.as_dict() for x in e1[key]] == [x.as_dict() for x in e2[key]], \
                f"{label}/{key} 非确定性"
