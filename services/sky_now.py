# -*- coding: utf-8 -*-
"""services/sky_now.py —— 今日月相日历（轻量只读）。

供首页「今日日历」卡片使用：不需要任何出生数据，只按当前 UTC 时刻计算日月夹角、
八阶段月相与近似照明比例、月亮星座/换座时刻/月空亡窗口、月亮日行速度与到最近
月球交点的黄经距离，以及水星至冥王星的逆行状态、精确转向和今日非月亮行星主相位。
接口只返回日历所需的紧凑事件，不返回完整十大行星黄经表。

精确位置查询与相位/换座的求根算法都委托给 services/transit_utils.py（跟未来的
「今日精准相位表」共用同一套底层引擎，见该模块文档）。

实时天象：每次请求都按服务器当前时刻重新计算月亮与行星运行状态；只有完全由
北京时间自然日决定的事件求根结果按日缓存，不缓存当前天空快照。
"""
import math
import time
from datetime import datetime, timezone
from functools import lru_cache

import swisseph as swe

from services import transit_patterns
from services import transit_utils as transit_engine
from services.solar_return import _jd_to_utc_str
from services.transit_utils import (
    MAJOR_ASPECTS_WITH_MIRRORS,
    all_exact_in_window,
    body_position,
    last_exact_before,
)

# 全站统一丹露雅尔八分法：阶段从精确相位那一刻起算，每 45° 换一段
# （新月 0°–45°、满月 180°–225°，以此类推）。engine/natal_chart.py 的本命
# 月相与 services/progressed_phase.py 的次限月相用的是同一条边界，首页不能
# 自带一套中心分区（满月 157.5°–202.5°），否则同一天首页说“亏凸月”、本命页
# 说“满月”。精确满月过后仍在满月段内会不会误导，用 exact_at 派生的“已过精确
# 点多久”和真实照明率去消解，不靠改边界。
PHASE_NAMES = [
    "新月", "娥眉月", "上弦月", "盈凸月",
    "满月", "亏凸月", "下弦月", "残月",
]

# 与 services/progressed_phase.py 的星座名/字形表同口径（各自独立小表，本仓库惯例）。
_ZODIAC_ZH = (
    "白羊座", "金牛座", "双子座", "巨蟹座", "狮子座", "处女座",
    "天秤座", "天蝎座", "射手座", "摩羯座", "水瓶座", "双鱼座",
)
_ZODIAC_GLYPHS = ("♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓")

# 月亮平均恒星日行速度（360° / 27.321661 天）。传统判断「月行快/慢」以平均
# 日行为分界；接口同时返回原始速度与基准，前端不自行复制算法口径。
_MEAN_MOON_SPEED_DEG_PER_DAY = 360.0 / 27.321661

# 月空亡（VOC）判定范围：日水金火木土天海冥（不含月亮自身）+ 托勒密五主相位。
# 走主流现代占星软件口径，不是古典七星限定——实测对拍过 moontracks.com 连续
# 10 个窗口，只用七大古典星体时其中 1 个窗口的收官相位对不上（真实收官相位是
# 月亮刑天王星），换成日水金火土天海冥全九星后 10/10 精确匹配（分钟级）。外行星
# 移动虽慢，但月亮本身移动快，仍能在数天窗口内规律地跟外行星形成主相位，并不会
# 让月亮"几乎永远不空亡"。
_VOC_BODIES = (
    swe.SUN, swe.MERCURY, swe.VENUS, swe.MARS, swe.JUPITER, swe.SATURN,
    swe.URANUS, swe.NEPTUNE, swe.PLUTO,
)
# 用 transit_utils 里锁死了「对负号封闭」性质的共享常量，不在这里自己重新枚举
# 一遍镜像角——各调用方各写一份最容易在改动时悄悄改窄、漏掉镜像却没人发现。
_VOC_ASPECTS = MAJOR_ASPECTS_WITH_MIRRORS

# 非月亮行星播报在托勒密五主相位之外，额外收录 150° 梅花相位。150° 的镜像
# 是 210°；两边都要交给求根器，否则会因星体领先方向不同系统性漏掉一半。
# 这张表不能反写进 MAJOR_ASPECTS_WITH_MIRRORS：后者同时用于月空亡判定，VOC
# 只看托勒密五主相位，加入梅花会改变既有业务口径。
_PLANET_ASPECTS_WITH_MIRRORS = MAJOR_ASPECTS_WITH_MIRRORS + (150.0, 210.0)

# 与 services/calculator.py::PLANET_CN 同口径，但那边是字符串键、这里是 swisseph
# 常量键，两套表不共用——各自独立小表是本仓库处理"同名不同键"表的惯例。
_PLANET_CN = {
    swe.SUN: "太阳", swe.MOON: "月亮", swe.MERCURY: "水星", swe.VENUS: "金星", swe.MARS: "火星",
    swe.JUPITER: "木星", swe.SATURN: "土星",
    swe.URANUS: "天王星", swe.NEPTUNE: "海王星", swe.PLUTO: "冥王星",
    swe.CHIRON: "凯龙星",
}
_PLANET_KEY = {
    swe.SUN: "sun", swe.MOON: "moon", swe.MERCURY: "mercury", swe.VENUS: "venus",
    swe.MARS: "mars", swe.JUPITER: "jupiter", swe.SATURN: "saturn",
    swe.URANUS: "uranus", swe.NEPTUNE: "neptune", swe.PLUTO: "pluto",
    swe.CHIRON: "chiron",
}
_MOTION_BODIES = (
    swe.MERCURY, swe.VENUS, swe.MARS, swe.JUPITER, swe.SATURN,
    swe.URANUS, swe.NEPTUNE, swe.PLUTO,
)
# 相位表含凯龙，逆行/转向表（_MOTION_BODIES）与月空亡表（_VOC_BODIES）不含：
# 本命盘一直算凯龙相位，天象板块此前漏了，这里补齐口径；月空亡是九大行星的
# 主流口径（对拍过 moontracks，有测试锁死），不因为补相位就动它。
_PLANET_ASPECT_BODIES = (swe.SUN,) + _MOTION_BODIES + (swe.CHIRON,)
# 「此刻生效相位」也要包含月亮；否则像月木 150° 这种当前非常紧密的配置只会
# 在精确根恰好落入今天时出现在下方列表，无法回答「此刻天上正挂着什么」。
_ACTIVE_ASPECT_BODIES = (swe.MOON,) + _PLANET_ASPECT_BODIES
# 凯龙体量小、走得慢，用行星那套 6–8° 会让它长期挂在列表上刷屏；一律收到 3°，
# 与梅花相位同一个「严格」档。判定时取 min(角度容许度, 这个值)。
_CHIRON_ORB = 3.0
_STATION_SAMPLE_DAYS = {
    swe.MERCURY: 1.0, swe.VENUS: 2.0, swe.MARS: 2.0,
    swe.JUPITER: 3.0, swe.SATURN: 3.0, swe.URANUS: 3.0,
    swe.NEPTUNE: 3.0, swe.PLUTO: 3.0,
}
# 镜像角折叠回同一个相位名——0°/60°和300°/90°和270°/120°和240°分别是同一种
# 相位的两个方向，今日相位列表只关心"发生了什么相位"，不区分方向。
_ASPECT_CN = {
    0.0: "合相", 180.0: "对分相",
    60.0: "六合相", 300.0: "六合相",
    90.0: "四分相", 270.0: "四分相",
    120.0: "三分相", 240.0: "三分相",
    150.0: "梅花相位", 210.0: "梅花相位",
}
_BEIJING_OFFSET_DAYS = 8.0 / 24.0

# ── 月亮栏专用常量 ────────────────────────────────────────────────────────
# 天文单位换算：swisseph 返回的月地距离单位是 AU，展示需要公里。
_AU_KM = 149597870.7
# 朔望月平均长度（天）。只用来给「回看多久能罩住上一次新月」定安全窗口，
# 不参与任何取整或日期推算——月龄的真值一律来自求根得到的精确朔时刻。
_SYNODIC_MONTH_DAYS = 29.53058867
# 回看/前瞻窗口：朔望月最长约 29.8 天，取 32 天必然罩住相邻的朔与望。
_LUNATION_SEARCH_DAYS = 32.0
# 朔望求根的采样步长。日月相对速度最慢约 10.8°/天，60 分钟≈0.45°，
# 远在折叠假象阈值内，二分仍能把时刻收敛到秒级（与 _PHASE_SAMPLE_MINUTES 同口径）。
_LUNATION_SAMPLE_MINUTES = 60.0

# ── 日月食 ────────────────────────────────────────────────────────────────
# 食是朔望的特例：日月合相或对分刚好落在交点附近。它属于月亮自身的周期读数，
# 所以归月相栏，不进行星事件区。这里只报客观事实——食别、精确时刻、太阳当时
# 所在黄道位置——不解释影响，也不判断吉凶。
#
# swisseph 的求根器一次返回一个食：backward=True 给最近一次已发生的，
# backward=False 给下一次。日食、月食各查两次即可罩住当前所处的整个食窗。
#
# ⚠️ 类型表顺序敏感：全环食（ECL_ANNULAR_TOTAL）的 retflag 同时带 ANNULAR 与
# TOTAL 位，复合类型必须排在单一类型前面，否则会被先命中的 ANNULAR 吃掉。
_ECLIPSE_SOLAR_TYPES = (
    (swe.ECL_ANNULAR_TOTAL, "全环食"),
    (swe.ECL_ANNULAR, "日环食"),
    (swe.ECL_TOTAL, "日全食"),
    (swe.ECL_PARTIAL, "日偏食"),
)
_ECLIPSE_LUNAR_TYPES = (
    (swe.ECL_TOTAL, "月全食"),
    (swe.ECL_PARTIAL, "月偏食"),
    (swe.ECL_PENUMBRAL, "半影月食"),
)


def _lunation_exact(jd_ut: float, angle: float, backward: bool):
    """最近一次日月成 ``angle`` 的精确 JD（0=朔，180=望）；找不到返回 None。"""
    if backward:
        window = (jd_ut - _LUNATION_SEARCH_DAYS, jd_ut)
    else:
        window = (jd_ut, jd_ut + _LUNATION_SEARCH_DAYS)
    hits = all_exact_in_window(
        swe.SUN, (swe.MOON,), (angle,), window[0], window[1],
        sample_minutes=_LUNATION_SAMPLE_MINUTES,
    )
    if not hits:
        return None
    return hits[-1][0] if backward else hits[0][0]


def _lunation_context(jd_ut: float) -> dict:
    """月龄 + 上次新月 + 下次新月/满月。

    月龄按「距上一次精确朔的实际天数」算，不用平均朔望月估算——朔望月长度在
    29.27–29.83 天之间摆动，用平均值推月龄会有半天以上的误差。
    """
    last_new_jd = _lunation_exact(jd_ut, 0.0, backward=True)
    next_new_jd = _lunation_exact(jd_ut, 0.0, backward=False)
    next_full_jd = _lunation_exact(jd_ut, 180.0, backward=False)
    # 上一次满月：刚过满月时「下次满月」在 29 天后，光报未来会让人以为
    # 满月很遥远，其实它昨天刚发生。两侧都给，展示层挑更近的那个说。
    last_full_jd = _lunation_exact(jd_ut, 180.0, backward=True)

    def at(jd):
        return _jd_to_utc_str(jd) if jd else None

    def days_from_now(jd):
        return round(jd - jd_ut, 3) if jd else None

    return {
        # 月龄：本轮朔望月已经走过的天数
        "moon_age_days": round(jd_ut - last_new_jd, 3) if last_new_jd else None,
        "last_new_moon_at": at(last_new_jd),
        "last_full_moon_at": at(last_full_jd),
        "days_since_last_full_moon": (
            round(jd_ut - last_full_jd, 3) if last_full_jd else None
        ),
        "next_new_moon_at": at(next_new_jd),
        "days_to_next_new_moon": days_from_now(next_new_jd),
        "next_full_moon_at": at(next_full_jd),
        "days_to_next_full_moon": days_from_now(next_full_jd),
        # 本轮朔望月的实际长度（上次朔 → 下次朔），供展示层说明周期不是恒定 29.53 天
        "lunation_length_days": (
            round(next_new_jd - last_new_jd, 3)
            if (last_new_jd and next_new_jd) else None
        ),
        "mean_synodic_month_days": _SYNODIC_MONTH_DAYS,
    }


def _moon_distance(jd_ut: float, illuminated_fraction: float) -> dict:
    """地月距离与月面视直径。

    两项都是 swisseph 的直接读数，不需要求根：``calc_ut`` 的第三个分量是距离
    （AU），``pheno_ut`` 的第四项是视直径（度）。距离在近地点约 356,500 km、
    远地点约 406,700 km 之间变化，视直径随之差约 12%。
    """
    values, _flags = swe.calc_ut(jd_ut, swe.MOON, swe.FLG_SWIEPH)
    distance_km = values[2] * _AU_KM
    # pheno_ut：[0]=相位角 [1]=照明比例 [2]=日月距角 [3]=视直径(度)
    pheno = swe.pheno_ut(jd_ut, swe.MOON, swe.FLG_SWIEPH)
    return {
        "distance_km": round(distance_km),
        "apparent_diameter_arcmin": round(pheno[3] * 60.0, 2),
        "phase_angle_deg": round(pheno[0], 2),
        "illuminated_fraction": round(illuminated_fraction, 6),
    }


def _eclipse_type_cn(retflag: int, table) -> str:
    """swisseph 的 retflag 位掩码 → 中文食别。"""
    for bit, name in table:
        if retflag & bit:
            return name
    return "食"


@lru_cache(maxsize=16)
def _eclipse_neighbours(day_start: float) -> tuple:
    """当天前后各一次日食与月食（按北京自然日缓存；求根开销大且当日不变）。

    返回 ``(jd, kind, type_cn)`` 三元组，位置等派生字段留给调用方，
    避免把随时刻变化的量混进按日缓存里。
    """
    pivot = day_start + 0.5
    found = []
    for kind, finder in (
        ("solar", swe.sol_eclipse_when_glob),
        ("lunar", swe.lun_eclipse_when),
    ):
        table = _ECLIPSE_SOLAR_TYPES if kind == "solar" else _ECLIPSE_LUNAR_TYPES
        for backward in (True, False):
            try:
                retflag, tret = finder(pivot, swe.FLG_SWIEPH, 0, backward)
            except Exception:
                # 星历边界外或求根失败：食是附加信息，不能拖垮整个天象快照
                continue
            if retflag <= 0:
                continue
            found.append((tret[0], kind, _eclipse_type_cn(retflag, table)))
    return tuple(found)


def _eclipse_context(jd_ut: float) -> dict:
    """最近一次已发生的食与下一次食。

    只报「什么食、何时、落在黄道哪个度数、距今多少天」，不判断影响。
    多近才值得播报由展示层决定——跟月相换段一样，门槛留在前端。
    """
    day_start, _day_end = _beijing_day_window(jd_ut)
    entries = _eclipse_neighbours(day_start)

    def payload(item):
        jd, kind, type_cn = item
        # 位置统一取太阳：日食时日月合相、月食时月亮在太阳对面，报一个点即可
        # 定位这次食落在黄道何处，不必两个都报造成读数冗余。
        sun_lon, _ = body_position(swe.SUN, jd)
        return {
            "kind": kind,
            "kind_cn": "日食" if kind == "solar" else "月食",
            "type_cn": type_cn,
            "at": _jd_to_utc_str(jd),
            "days_from_now": round(jd - jd_ut, 3),
            "sun": _sign_of(sun_lon),
        }

    past = [e for e in entries if e[0] <= jd_ut]
    future = [e for e in entries if e[0] > jd_ut]
    return {
        "recent": payload(max(past, key=lambda e: e[0])) if past else None,
        "next": payload(min(future, key=lambda e: e[0])) if future else None,
    }

def moon_phase(
    sun_lon: float,
    moon_lon: float,
    illuminated_fraction: float = None,
) -> dict:
    """日月黄经差 → 丹露雅尔八分法月相（与本命盘、次限月相同口径）。

    阶段从 0° 起每 45° 切换，边界即精确相位时刻。``illuminated_fraction``
    生产由 Swiss Ephemeris ``pheno_ut`` 提供；省略时仅供纯函数测试/旧调用
    兼容，使用黄经差余弦近似。
    """
    diff = (moon_lon - sun_lon) % 360.0
    phase_idx = int(diff // 45.0) % 8
    if illuminated_fraction is None:
        illumination_pct = (1.0 - math.cos(math.radians(diff))) * 50.0
        illumination_source = "longitude_approximation"
    else:
        illumination_pct = max(0.0, min(1.0, illuminated_fraction)) * 100.0
        illumination_source = "swiss_ephemeris_pheno"
    return {
        "phase_num": phase_idx + 1,
        "phase_name": PHASE_NAMES[phase_idx],
        "angle_diff": round(diff, 2),
        "illumination_pct": round(illumination_pct, 2),
        "illumination_source": illumination_source,
        "cycle_progress_pct": round(diff / 360.0 * 100.0, 1),
        "is_waxing": diff < 180.0,
        "phase_progress_deg": round(diff % 45.0, 2),
    }


# 八个阶段边界角（丹露雅尔八分法）。相位查找按 (月亮-太阳) 有方向的黄经差取，
# 所以 135/225/315 这些不在 MAJOR_ASPECTS_WITH_MIRRORS 里的角度要自己列全。
_PHASE_BOUNDARY_ANGLES = tuple(float(i * 45) for i in range(8))
# 日月相对速度最慢约 10.8°/天，走完 45° 一段最多约 4.2 天；回看 5 天必然罩住
# 当前阶段的起点。采样步长放宽到 60 分钟：日月每小时才拉开约 0.5°，边界两侧
# 的样本仍远在折叠假象防护阈值内，二分照样把时刻收敛到秒级。
_PHASE_LOOKBACK_DAYS = 5.0
# 往后同理：45° 一段最多约 4.2 天，前瞻 5 天必然罩住下一次切换。
_PHASE_LOOKAHEAD_DAYS = 5.0
_PHASE_SAMPLE_MINUTES = 60.0


def _phase_exact_before(jd_ut: float):
    """当前月相阶段的起点（最近一次 45° 整数倍的精确日月相位）的 JD；找不到返回 None。"""
    hits = all_exact_in_window(
        swe.SUN, (swe.MOON,), _PHASE_BOUNDARY_ANGLES,
        jd_ut - _PHASE_LOOKBACK_DAYS, jd_ut,
        sample_minutes=_PHASE_SAMPLE_MINUTES,
    )
    return hits[-1][0] if hits else None


def _phase_exact_after(jd_ut: float):
    """下一次月相切换（下一个 45° 整数倍精确相位）的 JD；找不到返回 None。"""
    hits = all_exact_in_window(
        swe.SUN, (swe.MOON,), _PHASE_BOUNDARY_ANGLES,
        jd_ut, jd_ut + _PHASE_LOOKAHEAD_DAYS,
        sample_minutes=_PHASE_SAMPLE_MINUTES,
    )
    return hits[0][0] if hits else None


def _sign_of(lon: float) -> dict:
    idx = int((lon % 360.0) // 30.0)
    return {
        "sign_cn": _ZODIAC_ZH[idx],
        "glyph": _ZODIAC_GLYPHS[idx],
        "deg_in_sign": round(lon % 30.0, 2),
    }


def _moon_motion_and_node_distance(moon_lon: float, moon_speed: float, jd_ut: float) -> tuple:
    """月亮日行速度 + 到最近平均交点的黄经距离。

    交点与本命引擎、太阳返照同用 ``swe.MEAN_NODE``，避免首页与排盘页出现两套
    口径。这里报告黄道经度上的最短角距离，不把它解释成吉凶，也不把黄纬混进来。
    """
    north_node_lon, _ = body_position(swe.MEAN_NODE, jd_ut)
    south_node_lon = (north_node_lon + 180.0) % 360.0

    def angular_distance(a: float, b: float) -> float:
        return abs((a - b + 180.0) % 360.0 - 180.0)

    north_distance = angular_distance(moon_lon, north_node_lon)
    south_distance = angular_distance(moon_lon, south_node_lon)
    if north_distance <= south_distance:
        nearest_key, nearest_cn, nearest_lon, distance = (
            "north", "北交点", north_node_lon, north_distance,
        )
    else:
        nearest_key, nearest_cn, nearest_lon, distance = (
            "south", "南交点", south_node_lon, south_distance,
        )

    motion = {
        "speed_deg_per_day": round(moon_speed, 4),
        "mean_speed_deg_per_day": round(_MEAN_MOON_SPEED_DEG_PER_DAY, 4),
        "state": "fast" if moon_speed >= _MEAN_MOON_SPEED_DEG_PER_DAY else "slow",
        "state_cn": "快" if moon_speed >= _MEAN_MOON_SPEED_DEG_PER_DAY else "慢",
    }
    node = {
        "nearest": nearest_key,
        "nearest_cn": nearest_cn,
        "distance_deg": round(distance, 2),
        "nearest_lon": round(nearest_lon, 2),
    }
    return motion, node


def _find_moon_crossing(jd_guess: float, target_lon: float, max_iter: int = 40) -> float:
    """牛顿法求月亮到达 target_lon 的精确 JD（速度做导数）；jd_guess 可在目标前或后。"""
    target = target_lon % 360.0
    jd = jd_guess
    for _ in range(max_iter):
        lon, speed = body_position(swe.MOON, jd)
        diff = (lon - target + 180) % 360 - 180
        if abs(diff) < 1e-7 or not speed:
            break
        jd -= diff / speed
    return jd


def _voc_window(jd_ut: float, moon_lon: float, moon_speed: float) -> dict:
    """月空亡窗口：月亮离开当前星座前与其余九大行星的最后一个主相位 → 换座时刻。"""
    sign_floor = math.floor(moon_lon / 30.0) * 30.0
    sign_ceil = sign_floor + 30.0

    if moon_speed:
        entry_guess = jd_ut - ((moon_lon - sign_floor) % 360.0) / moon_speed
        ingress_guess = jd_ut + ((sign_ceil - moon_lon) % 360.0) / moon_speed
    else:
        entry_guess = ingress_guess = jd_ut

    entry_jd = _find_moon_crossing(entry_guess, sign_floor)
    ingress_jd = _find_moon_crossing(ingress_guess, sign_ceil % 360.0)

    last_hit = last_exact_before(swe.MOON, _VOC_BODIES, _VOC_ASPECTS, entry_jd, ingress_jd)
    start_jd = entry_jd if last_hit is None else last_hit

    return {
        "ingress_jd": ingress_jd,
        "active": jd_ut >= start_jd,
        "start": _jd_to_utc_str(start_jd),
        "end": _jd_to_utc_str(ingress_jd),
    }


def _moon_aspects_today(jd_ut: float) -> list:
    """自然日（北京时间 00:00-24:00）内月亮与其余九大行星的全部精确主相位，
    按时间升序返回；跟月空亡不是一回事——月空亡只关心"离开当前星座前的最后
    一个"，这里要"今天一整天发生的所有"，用 `all_exact_in_window` 而不是
    `last_exact_before`。

    自然日边界硬编码北京时间（这个仓库的用户群假设），不是从请求方读时区——
    跟仓库其它地方对中国用户的硬编码假设是同一类简化，不是新引入的口径。
    """
    day_start, day_end = _beijing_day_window(jd_ut)

    hits = all_exact_in_window(
        swe.MOON, _VOC_BODIES, _PLANET_ASPECTS_WITH_MIRRORS, day_start, day_end,
    )
    return [
        {
            "planet_cn": _PLANET_CN[body],
            "aspect_cn": _ASPECT_CN[angle],
            "at": _jd_to_utc_str(hit_jd),
        }
        for hit_jd, body, angle in hits
    ]


def _beijing_day_window(jd_ut: float):
    """当前时刻所在北京时间自然日的 [start, end) 儒略日 UT。"""
    local_jd = jd_ut + _BEIJING_OFFSET_DAYS
    year, month, day, _hour = swe.revjul(local_jd, swe.GREG_CAL)
    day_start = swe.julday(year, month, day, 0.0, swe.GREG_CAL) - _BEIJING_OFFSET_DAYS
    return day_start, day_start + 1.0


@lru_cache(maxsize=16)
def _daily_planet_event_hits(day_start: float):
    """缓存只由北京自然日决定的低频事件求根；不缓存当前天空快照。"""
    day_end = day_start + 1.0
    aspects = transit_engine.all_pairwise_exact_in_window(
        _PLANET_ASPECT_BODIES,
        _PLANET_ASPECTS_WITH_MIRRORS,
        day_start,
        day_end,
        sample_minutes=30.0,
    )
    stations = transit_engine.all_stations_in_window(
        _MOTION_BODIES, day_start, day_end, sample_hours=6.0,
    )
    return tuple(aspects), tuple(stations)


@lru_cache(maxsize=128)
def _station_schedule(planet: int, day_start: float):
    """从当天零点起查未来 250 天 station；供当前逆行行星找下一次转顺。"""
    return tuple(transit_engine.all_stations_in_window(
        (planet,),
        day_start,
        day_start + 250.0,
        sample_hours=_STATION_SAMPLE_DAYS[planet] * 24.0,
    ))


def _station_payload(jd: float, planet: int, direction: str) -> dict:
    lon, _speed = transit_engine.body_position(planet, jd)
    return {
        "planet": _PLANET_KEY[planet],
        "planet_cn": _PLANET_CN[planet],
        "direction": direction,
        "at": _jd_to_utc_str(jd),
        "longitude": round(lon, 6),
        **_sign_of(lon),
    }


# 「当前生效相位」的容许度。取值与 services/calculator.py::_phase_defs 同口径
# （合8/六6/四7/三8/梅花3/冲8），刻意不另立一套——同一个相位在本命页和天象页给出不同
# 判断，比取值本身略有出入更糟。
#
# 为什么需要这一层（NLM 核验记录，2026-07-30）：
#   · 本页月亮区用的是八分法「相位带」模型——满月带宽 45°，横跨近 4 天，不要求
#     精确；行星区却只收「精确根落在今天窗口内」的相位。同一个页面两套模型，
#     结果是 0.43° 的日木合相（比月亮区门槛紧一百倍）因为归行星区管而被挡掉。
#     这一层是把行星区的口径与月亮区对齐，不是新发明一套判据。
#   · Robert Hand《Planets in Transit》Rule 2 明确说行运不存在 "orb of influence"，
#     但他 Rule 3 自己用 "average orb approaches zero" 衡量接近程度。Co-Star 的说法
#     最准：orb 是 "a buffer zone for what counts as an aspect"。所以这里的容许度
#     只用于决定**收录什么**，绝不用来断言"影响持续到某日"——文案只讲此刻角距与
#     精确时刻，不讲影响期。
_ACTIVE_ORB_BY_ANGLE = {
    0.0: 8.0, 60.0: 6.0, 90.0: 7.0, 120.0: 8.0, 150.0: 3.0, 180.0: 8.0,
}
# 速度分层：含月亮或内行星（日水金火）的对子几天内走完容许度，属「事件级」；纯外行星
# 对子（木及以外）在容许度内可持续数周至数月，属「背景级」。前端据此路由到
# 背景层还是当日事件层，后端不替前端决定展示位置。
_FAST_BODIES = frozenset((swe.MOON, swe.SUN, swe.MERCURY, swe.VENUS, swe.MARS))
_ACTIVE_EXACT_SEARCH_DAYS = 20.0


def _canonical_separation(lon1: float, lon2: float) -> float:
    """两点黄经差折算成 0-180° 的角距。"""
    diff = abs((lon1 - lon2) % 360.0)
    return min(diff, 360.0 - diff)


@lru_cache(maxsize=256)
def _nearest_exact_jd(p1: int, p2: int, angle: float, day_start: float):
    """该相位最近一次精确成相的时刻（可能在过去或未来），按北京自然日缓存。

    只在「已判定在容许度内」的对子上调用，因此调用次数很少。取样步长 6 小时：
    这批星体里最快的太阳约 1°/天，6 小时≈0.25°，足够粗定位，其余由二分细化。

    ⚠️ 必须连镜像角一起传（60↔300 / 90↔270 / 120↔240 / 150↔210）：
    六分/四分/三分/梅花的精确
    时刻落在哪个方向取决于谁领先谁，只传一半会系统性漏掉约 3/8 的时刻——
    transit_utils.MAJOR_ASPECTS_WITH_MIRRORS 的注释专门警告过这条，初版就是只传
    了 (angle,)，导致海王六合冥王 0.06°（几乎正精确）都报不出精确时刻。
    """
    angles = (angle,) if angle in (0.0, 180.0) else (angle, 360.0 - angle)
    hits = transit_engine.all_pairwise_exact_in_window(
        (p1, p2), angles,
        day_start - _ACTIVE_EXACT_SEARCH_DAYS,
        day_start + 1.0 + _ACTIVE_EXACT_SEARCH_DAYS,
        sample_minutes=360.0,
    )
    if not hits:
        return None
    pivot = day_start + 0.5
    return min((jd for jd, _p1, _p2, _a in hits), key=lambda jd: abs(jd - pivot))


def _active_planet_aspects(jd_ut: float) -> list:
    """此刻仍在容许度内的月亮及行星相位（精确时刻可能不在今天）。

    与 planet_aspects_today（今日精确成相）互补：那边回答「今天几点有事发生」，
    这边回答「此刻天上正挂着什么」。两者都保留，前端各取所需。
    """
    day_start, _day_end = _beijing_day_window(jd_ut)
    positions = {
        body: transit_engine.body_position(body, jd_ut)
        for body in _ACTIVE_ASPECT_BODIES
    }
    # 稍后一点的位置，用来判入相/出相（角距在收窄还是拉开）
    later = jd_ut + 0.02  # ≈29 分钟
    positions_later = {
        body: transit_engine.body_position(body, later)[0]
        for body in _ACTIVE_ASPECT_BODIES
    }

    rows = []
    for i, p1 in enumerate(_ACTIVE_ASPECT_BODIES):
        for p2 in _ACTIVE_ASPECT_BODIES[i + 1:]:
            sep_now = _canonical_separation(positions[p1][0], positions[p2][0])
            sep_later = _canonical_separation(positions_later[p1], positions_later[p2])
            chiron_involved = swe.CHIRON in (p1, p2)
            for angle, orb in _ACTIVE_ORB_BY_ANGLE.items():
                if chiron_involved:
                    orb = min(orb, _CHIRON_ORB)
                delta_now = abs(sep_now - angle)
                if delta_now > orb:
                    continue
                exact_jd = _nearest_exact_jd(p1, p2, angle, day_start)
                rows.append({
                    "p1": _PLANET_KEY[p1],
                    "p1_cn": _PLANET_CN[p1],
                    "p2": _PLANET_KEY[p2],
                    "p2_cn": _PLANET_CN[p2],
                    "angle": angle,
                    "aspect_cn": _ASPECT_CN[angle],
                    "orb_deg": round(delta_now, 2),
                    # applying=正在走向精确，separating=已过精确正在拉开
                    "applying": abs(sep_later - angle) < delta_now,
                    "tier": ("event" if (p1 in _FAST_BODIES or p2 in _FAST_BODIES)
                             else "background"),
                    "exact_at": _jd_to_utc_str(exact_jd) if exact_jd else None,
                })
    # 角距越紧越靠前；同样紧的把事件级排在背景级之前
    rows.sort(key=lambda r: (r["orb_deg"], r["tier"] != "event"))
    return rows


def _planet_aspect_payload(jd: float, p1: int, p2: int, angle: float) -> dict:
    p1_lon, _ = transit_engine.body_position(p1, jd)
    p2_lon, _ = transit_engine.body_position(p2, jd)
    canonical_angle = min(angle % 360.0, (-angle) % 360.0)
    return {
        "p1": _PLANET_KEY[p1],
        "p1_cn": _PLANET_CN[p1],
        "p1_longitude": round(p1_lon, 6),
        "p2": _PLANET_KEY[p2],
        "p2_cn": _PLANET_CN[p2],
        "p2_longitude": round(p2_lon, 6),
        "angle": canonical_angle,
        "aspect_cn": _ASPECT_CN[angle],
        "at": _jd_to_utc_str(jd),
    }


def _planetary_events(jd_ut: float) -> dict:
    """当前逆行状态 + 今日精确转向 + 今日非月亮行星精准主相位。"""
    day_start, day_end = _beijing_day_window(jd_ut)
    aspect_hits, station_hits = _daily_planet_event_hits(day_start)

    retrograde = []
    for planet in _MOTION_BODIES:
        lon, speed = transit_engine.body_position(planet, jd_ut)
        if speed >= 0.0:
            continue
        next_direct = next(
            (
                hit for hit in _station_schedule(planet, day_start)
                if hit[0] > jd_ut and hit[2] == "direct"
            ),
            None,
        )
        row = {
            "planet": _PLANET_KEY[planet],
            "planet_cn": _PLANET_CN[planet],
            "longitude": round(lon, 6),
            "speed": round(speed, 8),
            **_sign_of(lon),
        }
        if next_direct is not None:
            row["next_station"] = _station_payload(*next_direct)
        retrograde.append(row)

    return {
        "retrograde_planets": retrograde,
        "stations_today": [
            _station_payload(jd, planet, direction)
            for jd, planet, direction in station_hits
            if day_start <= jd < day_end
        ],
        "planet_aspects_today": [
            _planet_aspect_payload(jd, p1, p2, angle)
            for jd, p1, p2, angle in aspect_hits
            if day_start <= jd < day_end
        ],
        "planet_aspects_active": _active_planet_aspects(jd_ut),
    }


def sky_at(jd_ut: float, timestamp: str = "") -> dict:
    """指定儒略日 UT 的月相日历快照。测试可传固定 JD，生产用 current_sky()。"""
    sun_lon, _ = body_position(swe.SUN, jd_ut)
    moon_lon, moon_speed = body_position(swe.MOON, jd_ut)
    # pheno_ut 的第 2 项是月面照明比例（0..1），包含真实日地月几何；相比只用
    # 黄经差的余弦式，它不会忽略月球黄纬和距离造成的相位角差异。
    illuminated_fraction = swe.pheno_ut(jd_ut, swe.MOON, swe.FLG_SWIEPH)[1]
    moon_motion, moon_node_distance = _moon_motion_and_node_distance(
        moon_lon, moon_speed, jd_ut,
    )

    voc = _voc_window(jd_ut, moon_lon, moon_speed)
    ingress_jd = voc.pop("ingress_jd")
    sign_ceil_idx = int((math.floor(moon_lon / 30.0) + 1) % 12)

    # 阶段起点即上一次精确相位：满月段里“已经过了精确满月多久”靠这个说清楚，
    # 而不是把阶段边界挪到中点去回避问题。
    phase = moon_phase(sun_lon, moon_lon, illuminated_fraction)
    phase_exact_jd = _phase_exact_before(jd_ut)
    phase["exact_at"] = _jd_to_utc_str(phase_exact_jd) if phase_exact_jd else None
    phase["hours_since_exact"] = (
        round((jd_ut - phase_exact_jd) * 24.0, 2) if phase_exact_jd else None
    )
    # 下一次切换：时刻与目标阶段名都给出，前端据此决定要不要提前播报。
    # 门槛（多久算「即将」）留在前端，后端只报事实，不替展示层做取舍。
    next_exact_jd = _phase_exact_after(jd_ut)
    phase["next_at"] = _jd_to_utc_str(next_exact_jd) if next_exact_jd else None
    phase["hours_to_next"] = (
        round((next_exact_jd - jd_ut) * 24.0, 2) if next_exact_jd else None
    )
    phase["next_phase_name"] = PHASE_NAMES[(phase["phase_num"]) % 8]

    return {
        "timestamp": timestamp,
        "moon_phase": phase,
        "moon": _sign_of(moon_lon),
        "moon_motion": moon_motion,
        "moon_node_distance": moon_node_distance,
        # 月亮栏的三组新读数：本轮朔望月进度、地月距离/视直径、相邻日月食。
        # 都只描述月亮自身的周期，不涉及行星间关系。
        "lunation": _lunation_context(jd_ut),
        "moon_distance": _moon_distance(jd_ut, illuminated_fraction),
        "eclipse": _eclipse_context(jd_ut),
        "sun": {k: v for k, v in _sign_of(sun_lon).items() if k in ("sign_cn", "glyph")},
        "ingress": {
            "next_sign_cn": _ZODIAC_ZH[sign_ceil_idx],
            "at": _jd_to_utc_str(ingress_jd),
        },
        "voc": voc,
        # 相位格局（大三角/风筝/T三角/大十字/Yod）：慢星组成、能持续数周到数月，
        # 判定与容许度口径见 services/transit_patterns.py。
        "patterns": transit_patterns.patterns_at(jd_ut),
        "moon_aspects_today": _moon_aspects_today(jd_ut),
        **_planetary_events(jd_ut),
    }


def current_sky(now: float = None) -> dict:
    """当前时刻天象快照：每次调用都按服务器当前时刻实时计算。

    `now` 仅测试用来注入固定时刻；生产路由一律不传，永远取服务器当前时间。
    按日确定的低频事件根可复用，时间戳、月亮与当前逆行状态不缓存。
    """
    now = time.time() if now is None else now
    dt = datetime.fromtimestamp(now, tz=timezone.utc)
    hour = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    jd_ut = swe.julday(dt.year, dt.month, dt.day, hour)
    return sky_at(jd_ut, timestamp=dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
