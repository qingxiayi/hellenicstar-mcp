# -*- coding: utf-8 -*-
"""services/aspect_windows.py —— 行星·相位：每条生效相位的入相/出相/周期/进度。

与既有两套相位数据的分工（三者互补，不重复口径）：
  - sky_now.planet_aspects_today   今天几点有事发生（精确时刻）
  - sky_now.planet_aspects_active  此刻天上正挂着什么（容许度内，只给当前角距）
  - 本模块                          此刻这条相位走到哪了（容许度进出边界 + 周期 + 进度）

求根口径与 services/transit_utils.py 一致，但解的方程不同：transit_utils 解
dev(t)=0（精确成相），这里解 |dev(t)|=orb（进出容许度边界），同一套二分。

容许度沿用 sky_now._ACTIVE_ORB_BY_ANGLE，不另立一套，避免「同一时刻这边说在相位
内、那边说不在」的口径分裂（AGENTS.md 记过三次同类事故）。
"""
from functools import lru_cache

import swisseph as swe

from services import transit_utils as tu
from services.sky_now import _ACTIVE_ORB_BY_ANGLE, _CHIRON_ORB

# ── 点位集合（姐姐 2026-08-18 定）：十大行星 + 凯龙 + 南北交点 + 福点 + 精神点。
# 不含四轴：上升/天顶一天转一圈，跟行星相位放同一个尺度上没有可比性。
SWE_BODIES = {
    "sun": swe.SUN, "moon": swe.MOON, "mercury": swe.MERCURY, "venus": swe.VENUS,
    "mars": swe.MARS, "jupiter": swe.JUPITER, "saturn": swe.SATURN,
    "uranus": swe.URANUS, "neptune": swe.NEPTUNE, "pluto": swe.PLUTO,
    "chiron": swe.CHIRON,
}
DERIVED_POINTS = ("north_node", "south_node", "pars_fortuna", "pars_spiritus")
ALL_POINTS = tuple(SWE_BODIES) + DERIVED_POINTS

POINT_CN = {
    "sun": "太阳", "moon": "月亮", "mercury": "水星", "venus": "金星", "mars": "火星",
    "jupiter": "木星", "saturn": "土星", "uranus": "天王星", "neptune": "海王星",
    "pluto": "冥王星", "chiron": "凯龙星", "north_node": "北交点",
    "south_node": "南交点", "pars_fortuna": "福点", "pars_spiritus": "精神点",
}
ASPECT_CN = {0.0: "合相", 60.0: "六合相", 90.0: "四分相", 120.0: "三分相",
             150.0: "梅花相位", 180.0: "对分相"}

# 平均日行速度（度/天），只用来推搜索窗宽，不参与任何天文结果。
# 福点/精神点跟上升同速（约 360°/天），它们的相位窗口是分钟级。
_MEAN_SPEED = {
    "moon": 13.2, "sun": 0.986, "mercury": 1.4, "venus": 1.2, "mars": 0.52,
    "jupiter": 0.083, "saturn": 0.034, "uranus": 0.012, "neptune": 0.006,
    "pluto": 0.004, "chiron": 0.02, "north_node": 0.053, "south_node": 0.053,
    "pars_fortuna": 360.0, "pars_spiritus": 360.0,
}

# 日行速度**上限**（度/天，含逆行时的绝对值）。步长必须按这个推，不能按上面的
# 平均速度之差：外行星对子的平均速度差极小（海王-冥王 0.002°/天），但各自逆行时
# 瞬时速度可达 0.03~0.04°/天，相对速度是平均差的几十倍。按平均差定步长会得到
# 40 天的粗步，足以跨过一次短暂的出容许度往返，把窗口报长。
_MAX_SPEED = {
    "moon": 15.4, "sun": 1.02, "mercury": 2.2, "venus": 1.26, "mars": 0.80,
    "jupiter": 0.25, "saturn": 0.14, "uranus": 0.065, "neptune": 0.040,
    "pluto": 0.040, "chiron": 0.065, "north_node": 0.06, "south_node": 0.06,
    "pars_fortuna": 375.0, "pars_spiritus": 375.0,
}
# 单步允许的最大角距变化：取容许度的 1/12，保证任何进出往返都不会被整步跨过。
_STEP_DEV_FRACTION = 12.0
_FAST_LOTS = frozenset(("pars_fortuna", "pars_spiritus"))

_MAX_SEARCH_DAYS = 40000.0   # 约 110 年：海王/冥王的慢相位窗口可长达数十年
_BISECT_ITERS = 42           # 二分到秒级以下


class PointResolver:
    """按 (jd, 地点) 求任一点位黄经。同一 jd 上的 swe 调用做缓存。

    福点/精神点依赖上升点，因而依赖地点；其余点位与地点无关。
    """

    def __init__(self, lat: float, lng: float):
        self.lat = lat
        self.lng = lng
        self._cache = {}

    def _asc(self, jd: float) -> float:
        key = ("asc", jd)
        if key not in self._cache:
            _cusps, ascmc = swe.houses(jd, self.lat, self.lng, b"P")
            self._cache[key] = ascmc[0] % 360.0
        return self._cache[key]

    def is_diurnal(self, jd: float) -> bool:
        """日生盘判定：太阳在地平线上。与 hellenistic.is_diurnal 同一口径。"""
        key = ("diurnal", jd)
        if key not in self._cache:
            from hellenistic import is_diurnal
            self._cache[key] = bool(is_diurnal(self.lon("sun", jd), self._asc(jd)))
        return self._cache[key]

    def lon(self, key: str, jd: float) -> float:
        cache_key = (key, jd)
        if cache_key in self._cache:
            return self._cache[cache_key]
        if key in SWE_BODIES:
            val = tu.body_lon(SWE_BODIES[key], jd)
        elif key == "north_node":
            val = tu.body_lon(swe.MEAN_NODE, jd)      # AGENTS.md：交点用平均交点
        elif key == "south_node":
            val = (tu.body_lon(swe.MEAN_NODE, jd) + 180.0) % 360.0
        elif key in _FAST_LOTS:
            asc = self._asc(jd)
            sun = self.lon("sun", jd)
            moon = self.lon("moon", jd)
            day = self.is_diurnal(jd)
            # 日生：福点=ASC+月-日，精神点=ASC+日-月；夜生两者互换。
            # 与 engine/natal_chart.py:3900 同一份公式，改一处必须两处同步。
            if (key == "pars_fortuna") == day:
                val = (asc + moon - sun) % 360.0
            else:
                val = (asc + sun - moon) % 360.0
        else:
            raise ValueError(f"未知点位：{key}")
        self._cache[cache_key] = val
        return val

    def speed(self, key: str, jd: float):
        """日行速度（度/天，逆行为负）；福点/精神点无解析速度，返回 None。"""
        if key in SWE_BODIES:
            return tu.body_position(SWE_BODIES[key], jd)[1]
        if key == "north_node":
            return tu.body_position(swe.MEAN_NODE, jd)[1]
        if key == "south_node":
            return tu.body_position(swe.MEAN_NODE, jd)[1]   # 南交点与北交点同速
        return None

    def is_applying(self, k1: str, k2: str, angle: float, jd: float) -> bool:
        """入相＝此刻角距正在缩小（古典定义：按当下的实际运动，含逆行）。

        用**解析速度**判，不用有限差分：海王六合冥王这种对子，14 分钟前瞻内角距
        只变 0.043 角秒，是两个大数相减的结果，离浮点噪声太近。swisseph 直接给
        黄经速度，一步到位且无噪声。

        福点/精神点没有解析速度（由上升点推出），退回极短前瞻的差分——它们每天
        走一圈，任何前瞻内的变化量都远大于噪声，差分在这里是安全的。
        """
        s1, s2 = self.speed(k1, jd), self.speed(k2, jd)
        if s1 is None or s2 is None:
            look = 1.0 / 86400.0          # 1 秒
            return self.abs_dev(k1, k2, angle, jd + look) < self.abs_dev(k1, k2, angle, jd)
        # 取当前匹配上的那个镜像角，dev 对时间的导数 = (s2 - s1) * sign(dev)
        l1, l2 = self.lon(k1, jd), self.lon(k2, jd)
        angles = (angle,) if angle in (0.0, 180.0) else (angle, 360.0 - angle)
        dev = min((tu._rel_diff(l2, l1, a) for a in angles), key=abs)
        d_dev = s2 - s1
        if dev == 0.0:
            return False                   # 恰好精确：既不入也不出，按出相处理
        return (dev > 0 and d_dev < 0) or (dev < 0 and d_dev > 0)

    def abs_dev(self, k1: str, k2: str, angle: float, jd: float) -> float:
        """到该相位的角距（0=精确）。

        ⚠️ 必须连镜像角一起取最小：60°/300°、90°/270°、120°/240°、150°/210°
        是同一种相位的两个方向，只算一半会系统性漏掉约 3/8 的情形
        （transit_utils.MAJOR_ASPECTS_WITH_MIRRORS 的注释专门警告过，
        sky_now 初版就栽在这上面）。
        """
        l1 = self.lon(k1, jd)
        l2 = self.lon(k2, jd)
        angles = (angle,) if angle in (0.0, 180.0) else (angle, 360.0 - angle)
        return min(abs(tu._rel_diff(l2, l1, a)) for a in angles)


def orb_for(k1: str, k2: str, angle: float) -> float:
    """该对子该角度的容许度。凯龙用更紧的 3°，与 sky_now 一致。"""
    orb = _ACTIVE_ORB_BY_ANGLE[angle]
    if "chiron" in (k1, k2):
        orb = min(orb, _CHIRON_ORB)
    return orb


def _search_profile(k1: str, k2: str, orb: float):
    """(搜索上限天数, 采样步长天数)。

    窗宽按**平均**相对速度推（估个数量级，够宽就行）；
    步长按**速度上限之和**推（保证不漏，见 _MAX_SPEED 的注释）。两者用不同的
    速度表是有意的，不是笔误。
    """
    rel_mean = abs(_MEAN_SPEED.get(k1, 1.0) - _MEAN_SPEED.get(k2, 1.0))
    if rel_mean < 1e-4:
        rel_mean = 1e-4
    span = min((2 * orb / rel_mean) * 4.0, _MAX_SEARCH_DAYS)
    rel_max = _MAX_SPEED.get(k1, 1.0) + _MAX_SPEED.get(k2, 1.0)
    step = max((orb / _STEP_DEV_FRACTION) / rel_max, 1.0 / 1440.0)  # 下限 1 分钟
    return span, step


def _boundary(res: PointResolver, k1: str, k2: str, angle: float, orb: float,
              jd0: float, direction: int):
    """从 jd0 朝 direction(+1 未来 / -1 过去) 找 |dev| 首次达到 orb 的时刻。

    返回 (jd, reason)：reason=None 表示找到真实出入相边界；
      "search_limit"  搜索上限内没越界（极慢对子），jd 是搜索边界不是真实时刻；
      "sect_change"   扫到日夜交界（只可能发生在福点/精神点上，见下）。
    两种情况 jd 都不是真实出入相时刻，前端必须据此标注，不能当结果展示。

    ⚠️ 日夜交界：福点/精神点的公式在日生盘与夜生盘互换
    （engine/natal_chart.py:3900），太阳过地平线的瞬间两点直接对调位置——
    这是数学上的真实不连续点，不是数值噪声。跨过它继续二分算出来的「窗口」
    没有意义（相当于把两个不同的点当成同一个点在追踪），所以扫到就停。
    """
    span, step = _search_profile(k1, k2, orb)
    watch_sect = bool(_FAST_LOTS & {k1, k2})
    sect0 = res.is_diurnal(jd0) if watch_sect else None
    prev_jd = jd0
    t = 0.0
    while t < span:
        t += step
        jd = jd0 + direction * t
        if watch_sect and res.is_diurnal(jd) != sect0:
            # 二分定位交界本身，把窗口截到这里
            lo, hi = (prev_jd, jd) if direction > 0 else (jd, prev_jd)
            for _ in range(_BISECT_ITERS):
                mid = (lo + hi) / 2.0
                same = res.is_diurnal(mid) == sect0
                if direction > 0:
                    lo, hi = (mid, hi) if same else (lo, mid)
                else:
                    lo, hi = (lo, mid) if same else (mid, hi)
            return (lo + hi) / 2.0, "sect_change"
        if res.abs_dev(k1, k2, angle, jd) >= orb:
            lo, hi = (prev_jd, jd) if direction > 0 else (jd, prev_jd)
            for _ in range(_BISECT_ITERS):
                mid = (lo + hi) / 2.0
                inside = res.abs_dev(k1, k2, angle, mid) < orb
                if direction > 0:
                    lo, hi = (mid, hi) if inside else (lo, mid)
                else:
                    lo, hi = (lo, mid) if inside else (mid, hi)
            return (lo + hi) / 2.0, None
        prev_jd = jd
    return jd0 + direction * span, "search_limit"


def aspect_window(res: PointResolver, k1: str, k2: str, angle: float, jd0: float):
    """一条生效相位的完整窗口。不在容许度内返回 None。"""
    orb = orb_for(k1, k2, angle)
    dev_now = res.abs_dev(k1, k2, angle, jd0)
    if dev_now > orb:
        return None
    entry, entry_reason = _boundary(res, k1, k2, angle, orb, jd0, -1)
    exit_, exit_reason = _boundary(res, k1, k2, angle, orb, jd0, +1)
    total = exit_ - entry
    elapsed = jd0 - entry
    applying = res.is_applying(k1, k2, angle, jd0)
    return {
        "p1": k1, "p2": k2,
        "p1_cn": POINT_CN[k1], "p2_cn": POINT_CN[k2],
        "angle": angle, "aspect_cn": ASPECT_CN[angle],
        "orb_limit": orb,
        "orb_deg": round(dev_now, 4),
        "applying": applying,
        "phase_cn": "入相" if applying else "出相",
        "enter_jd": entry, "exit_jd": exit_,
        "total_days": round(total, 2),
        "elapsed_days": round(elapsed, 2),
        "remaining_days": round(exit_ - jd0, 2),
        "progress_pct": round(max(0.0, min(1.0, elapsed / total)) * 100.0, 1) if total > 0 else 0.0,
        # 截断原因：非 None 时该侧不是真实出入相时刻，前端必须显示为
        # 「超出搜索范围」/「跨日夜交界」，不能把边界当结果展示。
        "enter_truncated": entry_reason,
        "exit_truncated": exit_reason,
    }


def _sort_key(row):
    """先按是否精确（角距小的在前），同样紧时入相排在出相前。"""
    return (row["orb_deg"], not row["applying"])


_CACHE_MAXSIZE = 256


@lru_cache(maxsize=_CACHE_MAXSIZE)
def _aspect_groups_cached(jd_min: float, lat_r: float, lng_r: float, points: tuple):
    return _aspect_groups_impl(jd_min, lat_r, lng_r, points)


def aspect_groups(jd0: float, lat: float, lng: float, points=ALL_POINTS):
    """按点位分组的生效相位，供「行星·相位」那一屏直接渲染。

    返回 [{key, cn, lon, sign_idx, deg_in_sign, count, aspects:[...]}, ...]，
    点位顺序固定按 ALL_POINTS（太阳月亮在前），不按数量排，保证界面顺序稳定。

    带 LRU 缓存：全盘一次 130ms 上下，用户在时间轴上来回拖会反复请求同一时刻。
    键把 jd 归整到**分钟**、经纬度归整到 4 位小数（约 11 米）——后端 compute()
    本来就只吃到分，秒是被忽略的，所以归整不损失任何精度。
    返回的是共享的只读结构，调用方不要就地修改。
    """
    jd_min = round(jd0 * 1440.0) / 1440.0
    return _aspect_groups_cached(jd_min, round(lat, 4), round(lng, 4), tuple(points))


def unique_aspects(groups) -> list:
    """Return each physical aspect once, ignoring mirrored group presentation.

    The UI intentionally lists one aspect under both participating points.  A
    Sun-Chiron aspect therefore produces two grouped presentation rows, but the
    flat primary list must contain only one physical aspect.
    """
    by_identity = {}
    for group in groups:
        for row in group.get("aspects", ()):
            pair = tuple(sorted((str(row["p1"]), str(row["p2"]))))
            identity = (pair, float(row["angle"]))
            if identity not in by_identity:
                item = dict(row)
                item.pop("other", None)
                item.pop("other_cn", None)
                by_identity[identity] = item
    return sorted(by_identity.values(), key=_sort_key)


def unique_aspect_count(groups) -> int:
    """Return the physical aspect count used by the primary list headline."""
    return len(unique_aspects(groups))


def _aspect_groups_impl(jd0, lat, lng, points):
    res = PointResolver(lat, lng)
    keys = list(points)
    by_point = {k: [] for k in keys}
    for i, k1 in enumerate(keys):
        for k2 in keys[i + 1:]:
            # 南北交点恒定对冲，它俩之间的「对分相」是定义性的恒真，不是天象
            if {k1, k2} == {"north_node", "south_node"}:
                continue
            for angle in _ACTIVE_ORB_BY_ANGLE:
                row = aspect_window(res, k1, k2, angle, jd0)
                if row is None:
                    continue
                by_point[k1].append(dict(row, other=k2, other_cn=POINT_CN[k2]))
                by_point[k2].append(dict(row, other=k1, other_cn=POINT_CN[k1]))
    groups = []
    for k in keys:
        lon = res.lon(k, jd0)
        rows = sorted(by_point[k], key=_sort_key)
        groups.append({
            "key": k,
            "cn": POINT_CN[k],
            "lon": round(lon, 4),
            "sign_idx": int(lon // 30),
            "deg_in_sign": round(lon % 30.0, 4),
            "count": len(rows),
            "aspects": rows,
        })
    return groups
