# -*- coding: utf-8 -*-
"""services/transit_ephemeris.py —— 土木流年精确星历封装（设计 §4.1 / §6.2）。

单一职责：按儒略日 UT 返回土星或木星的精确黄经、黄经速度与**实际返回**星历旗标。
不含事件语义、不依赖 Flask/DB/DOM——事件引擎（saturn_jupiter_transits.py）在其上构建。

精度前提复用第 0 步地基（services/ephemeris_guard.py）：请求 FLG_SWIEPH，并校验
**返回**旗标确实是 swieph 文件模式；一旦静默回退 Moshier 即抛错（fail loud），
绝不拿降级数据冒充精确结果。

背景见 docs/superpowers/specs/2026-07-03-saturn-jupiter-transit-precise-design.md。
"""
from dataclasses import dataclass

import swisseph as swe

from services.ephemeris_guard import (
    EphemerisModeError,
    apply_ephe_path,
    _mode_of,
)

# 进程内确定性星历路径就位一次；与引擎/自检共用同一入口，重复调用无副作用。
apply_ephe_path()

# 本模块只关心土星与木星。名字全小写，与 API/事件契约一致。
_PLANETS = {
    "saturn": swe.SATURN,
    "jupiter": swe.JUPITER,
}

_PLANET_ZH = {
    "saturn": "土星",
    "jupiter": "木星",
}

# swe.calc_ut(..., FLG_SPEED) 返回 xx = (lon, lat, dist, lon_speed, lat_speed, dist_speed)
_IDX_LON = 0
_IDX_LON_SPEED = 3


@dataclass(frozen=True)
class BodyPosition:
    """某一瞬间(JD UT)土/木的精确位置快照。"""
    body: str            # "saturn" / "jupiter"
    jd_ut: float
    longitude: float     # 黄经 [0, 360)
    speed: float         # 黄经速度 度/日；>0 顺行，<0 逆行
    ephemeris_mode: str  # 实际返回模式，应为 "swieph"
    returned_flags: int  # swe.calc_ut 返回旗标原值

    @property
    def direction(self) -> str:
        """顺行 direct / 逆行 retrograde；速度精确为 0（停滞）归入 direct。"""
        return "direct" if self.speed >= 0 else "retrograde"

    @property
    def body_zh(self) -> str:
        return _PLANET_ZH.get(self.body, self.body)


def _planet_const(body: str) -> int:
    try:
        return _PLANETS[body]
    except KeyError:
        raise ValueError(
            "transit_ephemeris 只支持 %s，收到 %r" % (list(_PLANETS), body)
        )


def body_at(body: str, jd_ut: float, strict: bool = True) -> BodyPosition:
    """返回 body 在 jd_ut 的精确位置。

    strict=True（默认）：返回旗标非 swieph 文件模式即抛 EphemerisModeError，
    杜绝静默 Moshier 回退。事件引擎全程用 strict，保证「精确」名副其实。
    """
    pl = _planet_const(body)
    xx, rflag = swe.calc_ut(jd_ut, pl, swe.FLG_SWIEPH | swe.FLG_SPEED)
    mode = _mode_of(rflag)
    if mode != "swieph":
        # 引擎/kerykeion 可能改过 swe 全局星历路径导致回退。重钉路径重算一次自愈；
        # 只在真正降级时触发（正常扫描不付这份开销）。
        apply_ephe_path()
        xx, rflag = swe.calc_ut(jd_ut, pl, swe.FLG_SWIEPH | swe.FLG_SPEED)
        mode = _mode_of(rflag)
    if strict and mode != "swieph":
        raise EphemerisModeError(
            "土木流年要求 swieph 文件模式，%s 在 JD=%.5f 返回 %s（旗标 %d）；"
            "请核对 ephe/ 星历文件（见 ephe/PROVENANCE.md）"
            % (body, jd_ut, mode, rflag)
        )
    return BodyPosition(
        body=body,
        jd_ut=jd_ut,
        longitude=xx[_IDX_LON] % 360.0,
        speed=xx[_IDX_LON_SPEED],
        ephemeris_mode=mode,
        returned_flags=rflag,
    )


def longitude_at(body: str, jd_ut: float, strict: bool = True) -> float:
    """便捷入口：只要黄经。"""
    return body_at(body, jd_ut, strict=strict).longitude
