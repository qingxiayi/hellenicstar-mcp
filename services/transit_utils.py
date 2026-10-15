# -*- coding: utf-8 -*-
"""services/transit_utils.py —— 通用相位精确时刻引擎。

单一职责：给定两个星体、一个时间窗口、一个目标相位角，求窗口内两者黄经差精确
等于目标角的儒略日 UT。供月空亡判定（services/sky_now.py）与未来的"今日精确
相位表"共用同一套底层算法，避免各算各的、以后改一处忘一处。

背景：天象播报技能的 transit_calc.py v3.1（阳光设计）提出用"raw 差值 + 目标
拉同圈直接二分"，不折叠角度、从根上避免 0°/360° 回绕震荡假象，思路是对的。
但那个写法要求两个星体各自的黄经在整个窗口内都不跨越 0°/360° 边界才成立——
对月亮这种快速星体（约 27.3 天绕行一周）不能默认满足，任意 2-3 天窗口都有
不低的概率正好卡在白羊 0° 附近。本模块改用"折叠到 (-180,180] + 显式识别并
剔除折叠自身产生的跳变假象"，效果等价但不依赖"窗口内不过零"这个前提，对
任意星体、任意窗口长度都成立。

跟仓库其它星历模块同一条纪律：显式请求 FLG_SWIEPH，校验返回旗标，静默降级
到 Moshier 就 fail loud（ephemeris_guard.py 之所以存在的原因，这里不能省）。
"""
import math

import swisseph as swe

from services.ephemeris_guard import EphemerisModeError, apply_ephe_path, _mode_of

# 与引擎/自检共用同一星历路径入口，重复调用无副作用。
apply_ephe_path()

_FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED
_IDX_LON = 0
_IDX_LON_SPEED = 3

DEFAULT_SAMPLE_MINUTES = 10.0
DEFAULT_BISECT_ITERS = 20
# 月亮近地点最快约 15.4°/天，是太阳系里两两黄经相对速度的实际上限（其余星体
# 之间的相对速度只会更慢）。真过零两侧的偏差不会超过"这一步理论上最多能走
# 多远"；折叠算法在 diff=target+180 处产生的跳变假象两侧则恒定接近 ±180，
# 不随采样步长变化。取真实上限的若干倍做阈值，两者量级差距足够大，任何调用方
# 传入的 sample_minutes（哪怕远大于默认的 10 分钟）都不会把假象误当真过零，
# 也不会因为步长变粗而把真过零误杀成假象。
_MAX_RELATIVE_DEG_PER_DAY = 15.4
_GENUINE_CROSSING_SAFETY_FACTOR = 10.0
# 阈值随 sample_minutes 线性增长，折叠假象两侧恒定接近 180°——阈值一旦逼近
# 180°，两者就分不清了，防护形同虚设。90°留了一半安全边际，同时对应
# sample_minutes 上限约 841 分钟（~14 小时），任何真实场景的采样步长都远小于
# 这个值；超过时 fail loud 拒绝，而不是悄悄放行一个已经失效的防护。
_MAX_GENUINE_CROSSING_THRESHOLD_DEG = 90.0

# 相位看的是两点间的角距离，不分方向：60/90/120 各自有两个镜像点（领先 60° 和
# 落后 60°，即 diff=300°，是同一种六合的两个方向）；0°/180° 自镜像不重复。
# 这个集合对「取负 mod 360」封闭，任何调用方要「找两星体间某个主相位，不管
# 谁领先谁」时，必须传这整个集合而不是随手挑一半，否则会系统性漏掉约 3/8 的
# 真实相位时刻——`test_major_aspects_with_mirrors_closed_under_negation` 锁死
# 这条封闭性质，谁不小心改窄了这个集合，测试就会炸。
MAJOR_ASPECTS_WITH_MIRRORS = (0.0, 60.0, 90.0, 120.0, 180.0, 240.0, 270.0, 300.0)


def _genuine_crossing_threshold_deg(sample_minutes: float) -> float:
    step_days = sample_minutes / 1440.0
    threshold = _MAX_RELATIVE_DEG_PER_DAY * step_days * _GENUINE_CROSSING_SAFETY_FACTOR
    if threshold >= _MAX_GENUINE_CROSSING_THRESHOLD_DEG:
        raise ValueError(
            "sample_minutes=%.1f 太粗，折叠假象防护阈值 (%.1f°) 逼近 180° 已经失效，"
            "无法可靠区分真过零和折叠假象；请调小 sample_minutes"
            % (sample_minutes, threshold)
        )
    return threshold


def body_position(planet: int, jd_ut: float):
    """单次精确黄经+黄经速度；返回旗标非 swieph 时重钉星历路径自愈一次，仍
    降级则 fail loud 抛错，不冒充精确结果。"""
    xx, rflag = swe.calc_ut(jd_ut, planet, _FLAGS)
    if _mode_of(rflag) != "swieph":
        apply_ephe_path()
        xx, rflag = swe.calc_ut(jd_ut, planet, _FLAGS)
    if _mode_of(rflag) != "swieph":
        raise EphemerisModeError(
            "transit_utils 要求 swieph 文件模式，planet=%d JD=%.5f 返回 %s（旗标 %d）；"
            "请核对 ephe/ 星历文件（见 ephe/PROVENANCE.md）"
            % (planet, jd_ut, _mode_of(rflag), rflag)
        )
    return xx[_IDX_LON] % 360.0, xx[_IDX_LON_SPEED]


def body_lon(planet: int, jd_ut: float) -> float:
    """只要经度时的便捷包装。"""
    return body_position(planet, jd_ut)[0]


def _rel_diff(lon2: float, lon1: float, target_deg: float) -> float:
    """(lon2-lon1) 与目标角的有符号偏差，折叠到 (-180,180]，0 即精确相位。"""
    return (lon2 - lon1 - target_deg + 180.0) % 360.0 - 180.0


def _sample_times(lo_jd: float, hi_jd: float, sample_minutes: float):
    step = sample_minutes / 1440.0
    n = max(1, int(math.ceil((hi_jd - lo_jd) / step)))
    times = [lo_jd + i * step for i in range(n + 1)]
    times[-1] = hi_jd
    return times


def _all_crossings(times, lon1s, lon2s, p1_id: int, p2_id: int, target_deg: float,
                    bisect_iters: int, genuine_threshold: float):
    """在预采样好的 lon1s/lon2s 上找窗口内*全部*精确等于 target_deg 的 JD，
    按时间升序返回（可能是空列表）。二分细化阶段仍要现查 body_lon，粗采样
    阶段的重复查询才是真正的开销所在。

    对同一个 (p1,p2) 只调一次这个函数就能拿到窗口内的所有交点——不必再靠
    "分段调用、每段只要第一个"这种笨办法拼凑，也不再要求 p1 是全局移动最快
    的那个天体：无论两者相对运动是否单调，这里一次扫描就把该出现的交点全
    找出来。
    """
    diffs = [_rel_diff(b, a, target_deg) for a, b in zip(lon1s, lon2s)]
    hits = []

    for i in range(len(diffs) - 1):
        d0, d1 = diffs[i], diffs[i + 1]
        if d0 == 0.0:
            hits.append(times[i])
            continue
        # 精确命中恰好落在窗口最后一个采样点（times[-1]，通常就是 hi_jd 本身）
        # 时，本轮循环没有下一个 i 能把它当 d0 == 0.0 抓到，必须在这里单独收尾。
        if i == len(diffs) - 2 and d1 == 0.0:
            hits.append(times[i + 1])
            continue
        if (
            (d0 > 0) != (d1 > 0)
            and abs(d0) < genuine_threshold
            and abs(d1) < genuine_threshold
        ):
            lo, hi, lo_positive = times[i], times[i + 1], d0 > 0
            for _ in range(bisect_iters):
                mid = (lo + hi) / 2.0
                mid_diff = _rel_diff(body_lon(p2_id, mid), body_lon(p1_id, mid), target_deg)
                if (mid_diff > 0) == lo_positive:
                    lo = mid
                else:
                    hi = mid
            hits.append((lo + hi) / 2.0)
    return hits


def find_exact(lo_jd: float, hi_jd: float, p1_id: int, p2_id: int, target_deg: float,
                sample_minutes: float = DEFAULT_SAMPLE_MINUTES,
                bisect_iters: int = DEFAULT_BISECT_ITERS):
    """[lo_jd, hi_jd] 内 (p2 经度 - p1 经度) 首次精确等于 target_deg 的 JD；无则 None。

    只匹配这一个具体角度，不自动匹配镜像——60° 和 300° 是同一种六合相位的两个
    方向，都关心时调用方自己分别传 60.0 和 300.0（`last_exact_before` 已经这样
    枚举好了完整的八角度集合）。
    """
    if hi_jd <= lo_jd:
        return None
    times = _sample_times(lo_jd, hi_jd, sample_minutes)
    lon1s = [body_lon(p1_id, t) for t in times]
    lon2s = [body_lon(p2_id, t) for t in times]
    genuine_threshold = _genuine_crossing_threshold_deg(sample_minutes)
    hits = _all_crossings(times, lon1s, lon2s, p1_id, p2_id, target_deg,
                           bisect_iters, genuine_threshold)
    return hits[0] if hits else None


def all_exact_in_window(p1_id: int, bodies, aspects, lo_jd: float, hi_jd: float,
                         sample_minutes: float = DEFAULT_SAMPLE_MINUTES,
                         bisect_iters: int = DEFAULT_BISECT_ITERS):
    """[lo_jd, hi_jd] 内 p1 与 bodies 中每个星体、aspects 中每个角度的*全部*
    精确相位事件，按时间升序返回 `[(jd, body_id, angle), ...]`（可能是空列表）。

    今日相位列表这类"把窗口内所有命中都列出来"的场景用这个；月空亡只要
    "最后一个"用 `last_exact_before`（内部就是调这个再取最后一条，见下）。

    p1 在整个窗口只采样一次，每个 body 的黄经也只采样一次、复用到它对应的
    全部 aspects——不必对每个 (body, angle) 组合重新重采样一遍星历。
    """
    if hi_jd <= lo_jd:
        return []
    times = _sample_times(lo_jd, hi_jd, sample_minutes)
    lon1s = [body_lon(p1_id, t) for t in times]
    genuine_threshold = _genuine_crossing_threshold_deg(sample_minutes)

    results = []
    for body in bodies:
        lon2s = [body_lon(body, t) for t in times]
        for angle in aspects:
            for jd in _all_crossings(times, lon1s, lon2s, p1_id, body, angle,
                                      bisect_iters, genuine_threshold):
                results.append((jd, body, angle))
    results.sort(key=lambda row: row[0])
    return results


def all_exact_to_fixed_in_window(
    moving_body: int,
    fixed_longitudes,
    aspects,
    lo_jd: float,
    hi_jd: float,
    sample_minutes: float = 720.0,
    bisect_iters: int = DEFAULT_BISECT_ITERS,
):
    """求一颗行运星与多个固定本命黄经在窗口内的全部精确相位。

    ``all_exact_in_window`` 面向两个都由 Swiss Ephemeris 提供的移动星体；
    本命盘的行星、派生点和四轴在出生后是固定黄经，不能伪装成 swe body id。
    本函数沿用同一套采样、角度折叠、折叠假象防护和二分精化，只把第二端替换为
    ``{point_key: longitude}``。返回 ``[(jd, point_key, directed_angle), ...]``。

    默认 12 小时粗采样适用于本项目的行运火星及更慢星体；它仍低于通用折叠防护
    允许的上限。调用方若扩展到月亮/内行星，应显式使用更细采样。
    """
    if hi_jd <= lo_jd:
        return []
    times = _sample_times(lo_jd, hi_jd, sample_minutes)
    moving_lons = [body_lon(moving_body, t) for t in times]
    genuine_threshold = _genuine_crossing_threshold_deg(sample_minutes)
    results = []

    for point_key, raw_lon in fixed_longitudes.items():
        fixed_lon = float(raw_lon) % 360.0
        for angle in aspects:
            diffs = [_rel_diff(fixed_lon, moving_lon, angle) for moving_lon in moving_lons]
            hits = []
            for i in range(len(diffs) - 1):
                d0, d1 = diffs[i], diffs[i + 1]
                if d0 == 0.0:
                    hits.append(times[i])
                    continue
                if i == len(diffs) - 2 and d1 == 0.0:
                    hits.append(times[i + 1])
                    continue
                if not (
                    (d0 > 0) != (d1 > 0)
                    and abs(d0) < genuine_threshold
                    and abs(d1) < genuine_threshold
                ):
                    continue
                lo, hi, lo_positive = times[i], times[i + 1], d0 > 0
                for _ in range(bisect_iters):
                    mid = (lo + hi) / 2.0
                    mid_diff = _rel_diff(fixed_lon, body_lon(moving_body, mid), angle)
                    if (mid_diff > 0) == lo_positive:
                        lo = mid
                    else:
                        hi = mid
                hits.append((lo + hi) / 2.0)
            results.extend((jd, point_key, float(angle)) for jd in hits)

    results.sort(key=lambda item: item[0])
    return results


def all_pairwise_exact_in_window(bodies, aspects, lo_jd: float, hi_jd: float,
                                 sample_minutes: float = DEFAULT_SAMPLE_MINUTES,
                                 bisect_iters: int = DEFAULT_BISECT_ITERS):
    """窗口内多颗星体两两之间的全部精确相位。

    每个星体在粗采样阶段只查询一次，再枚举无序 pair；返回
    ``[(jd, p1_id, p2_id, angle), ...]``。调用方传入
    ``MAJOR_ASPECTS_WITH_MIRRORS`` 时，60/90/120 的两个方向都会覆盖，但同一对
    星体不会因为交换 p1/p2 再报一遍。
    """
    if hi_jd <= lo_jd:
        return []
    unique_bodies = tuple(dict.fromkeys(bodies))
    times = _sample_times(lo_jd, hi_jd, sample_minutes)
    longitudes = {
        body: [body_lon(body, t) for t in times]
        for body in unique_bodies
    }
    genuine_threshold = _genuine_crossing_threshold_deg(sample_minutes)

    results = []
    for i, p1_id in enumerate(unique_bodies):
        for p2_id in unique_bodies[i + 1:]:
            lon1s = longitudes[p1_id]
            lon2s = longitudes[p2_id]
            for angle in aspects:
                for jd in _all_crossings(
                    times, lon1s, lon2s, p1_id, p2_id, angle,
                    bisect_iters, genuine_threshold,
                ):
                    results.append((jd, p1_id, p2_id, angle))
    results.sort(key=lambda row: row[0])
    return results


def _speed_zero_between(planet: int, lo_jd: float, hi_jd: float,
                        lo_speed: float, bisect_iters: int) -> float:
    """已知速度在 [lo, hi] 变号，二分求黄经速度为零的精确时刻。"""
    lo = lo_jd
    hi = hi_jd
    lo_nonnegative = lo_speed >= 0.0
    for _ in range(bisect_iters):
        mid = (lo + hi) / 2.0
        mid_speed = body_position(planet, mid)[1]
        if (mid_speed >= 0.0) == lo_nonnegative:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def all_stations_in_window(bodies, lo_jd: float, hi_jd: float,
                           sample_hours: float = 6.0,
                           bisect_iters: int = 32):
    """窗口内所有行星黄经速度过零事件。

    返回 ``[(jd, planet_id, direction), ...]``，direction 是转向之后的运动状态：
    ``retrograde`` 或 ``direct``。这里只报告真实过零点，不定义资料无统一阈值的
    “停滞窗口”。
    """
    if hi_jd <= lo_jd:
        return []
    if sample_hours <= 0:
        raise ValueError("sample_hours 必须大于 0")
    times = _sample_times(lo_jd, hi_jd, sample_hours * 60.0)
    results = []

    for planet in tuple(dict.fromkeys(bodies)):
        speeds = [body_position(planet, t)[1] for t in times]
        for i in range(len(times) - 1):
            s0, s1 = speeds[i], speeds[i + 1]
            if s0 == 0.0:
                jd = times[i]
            elif s1 == 0.0:
                jd = times[i + 1]
            elif (s0 > 0.0) == (s1 > 0.0):
                continue
            else:
                jd = _speed_zero_between(
                    planet, times[i], times[i + 1], s0, bisect_iters,
                )

            # 一个精确采样点可能同时作为前一段的 s1 和后一段的 s0，被看见两次。
            if results and results[-1][1] == planet and abs(results[-1][0] - jd) < 1e-7:
                continue
            after_jd = min(hi_jd, jd + 1e-4)
            after_speed = body_position(planet, after_jd)[1]
            if after_jd == jd or after_speed == 0.0:
                after_speed = s1
            direction = "retrograde" if after_speed < 0.0 else "direct"
            results.append((jd, planet, direction))

    results.sort(key=lambda row: row[0])
    return results


def find_next_station(planet: int, after_jd: float, max_days: float = 250.0,
                      sample_days: float = 1.0, bisect_iters: int = 32):
    """查找 after_jd 之后下一次真实速度过零；找不到返回 None。"""
    if max_days <= 0:
        return None
    hits = all_stations_in_window(
        (planet,), after_jd + 1e-7, after_jd + max_days,
        sample_hours=sample_days * 24.0,
        bisect_iters=bisect_iters,
    )
    return hits[0] if hits else None


def last_exact_before(p1_id: int, bodies, aspects, lo_jd: float, hi_jd: float,
                       sample_minutes: float = DEFAULT_SAMPLE_MINUTES,
                       bisect_iters: int = DEFAULT_BISECT_ITERS):
    """[lo_jd, hi_jd] 内 p1 与 bodies 中任一星体、aspects 中任一角度的最后一个
    精确相位 JD；无则 None。月空亡判定用（p1=月亮，bodies=九大行星去掉月亮自身，
    aspects=含镜像的完整角度集合）。

    直接复用 `all_exact_in_window` 枚举窗口内全部交点、取时间最晚的一条——
    不再要求 p1 是全局移动最快的天体、也不再依赖"同一对 (body,angle) 至多
    一个交点"这个假设，任意两个天体、任意窗口长度都成立。
    """
    hits = all_exact_in_window(p1_id, bodies, aspects, lo_jd, hi_jd,
                                sample_minutes=sample_minutes, bisect_iters=bisect_iters)
    return hits[-1][0] if hits else None
