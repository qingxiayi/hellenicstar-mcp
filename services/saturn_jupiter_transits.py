# -*- coding: utf-8 -*-
"""services/saturn_jupiter_transits.py —— 土木流年事件引擎（设计 §6.2 / §7）。

纯计算：输入本命四轴经度 + 出生儒略日，输出土星/木星合四轴事件、土木相位事件。
不依赖 Flask / DOM / 数据库 / 进程缓存。星历数据一律走 transit_ephemeris（strict swieph）。

保留香港页面的事件语义（事件类别、去重、周期号、0 岁归零），但数值以精确星历为准：
1 日步长扫描候选窗口，符号变号处用二分求根精化到分钟级（§6.2），不停留在逐日峰值。

事件规则见设计 §7；事件身份键见 §7.3。
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from services.transit_ephemeris import body_at

RULE_VERSION = "hk-visible-rules-precise-1"

# —— 轴点：本命四轴，固定不动，行星过境来合 —— #
AXES_ORDER = ("Asc", "MC", "Dsc", "IC")

# 同一轴点合相去重最小间隔（年）：香港显示语义。逆行三次擦轴收敛为一次。
_CONJ_DEDUP_YEARS = {"saturn": 14.75, "jupiter": 6.0}
# 周期号除数：土星 floor(age/29.5)+1，木星 floor(age/12)+1。
_CYCLE_DIVISOR = {"saturn": 29.5, "jupiter": 12.0}

# 相位目标（有向角 Jupiter - Saturn）与中文名。
ASPECT_TARGETS = (
    (0, "合相"),
    (90, "上刑"),
    (180, "冲相"),
    (270, "下刑"),
)
_ASPECT_DEDUP_YEARS = 2.0

# 出生时距离目标不大于此度数记为 0 岁事件。
_BIRTH_ZERO_ORB = 10.0
# 1 岁以内的事件归为 0 岁。
_AGE_ZERO_CUTOFF = 1.0

_DAYS_PER_YEAR = 365.25
_SCAN_STEP_DAYS = 1.0
# 二分求根终止：窗口收敛到 <1 分钟（1/1440 日）。
_REFINE_EPS_DAYS = 1.0 / 1440.0
_REFINE_MAX_ITER = 80
# 变号连续性阈值：相邻样本角差跳变 >90° 视为 ±180 环绕，非真实过零。
_CONTINUITY_LIMIT = 90.0


def _make_pos():
    """调用内 (body, jd) 位置记忆化。合四轴 4 个轴与相位扫描共用同一日网格，
    同一 (body, jd) 会被重复问询多次；缓存收敛为一次 swe 计算，显著提速。
    call-local（每次 compute_transit_events 新建），无跨请求/跨线程共享。"""
    memo = {}

    def pos(body, jd):
        key = (body, jd)
        v = memo.get(key)
        if v is None:
            v = body_at(body, jd)
            memo[key] = v
        return v
    return pos


def norm360(x: float) -> float:
    return x % 360.0


def wrap180(x: float) -> float:
    """把角度折到 [-180, 180)（180 与 -180 同为对冲点）。"""
    return (x + 180.0) % 360.0 - 180.0


@dataclass(frozen=True)
class TransitEvent:
    event_id: str
    event_type: str          # "conjunction" / "aspect"
    planet: Optional[str]    # 合轴事件的过境行星；相位事件为 None
    planet_zh: Optional[str]
    axis: Optional[str]      # 合轴事件的轴名；相位事件为 None
    aspect: Optional[int]    # 相位目标角度；合轴事件为 None
    aspect_zh: Optional[str]
    exact_jd: float
    utc_datetime: str
    local_date: Optional[str]
    age_years: float
    cycle: Optional[int]
    direction: str           # "direct" / "retrograde"
    crossing_index: int
    # 相位事件附当时土木精确经度（§7.2）；合轴事件放过境行星经度/速度。
    longitude: Optional[float] = None
    speed: Optional[float] = None
    saturn_longitude: Optional[float] = None
    jupiter_longitude: Optional[float] = None

    def as_dict(self) -> Dict:
        d = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "exact_jd": round(self.exact_jd, 6),
            "utc_datetime": self.utc_datetime,
            "local_date": self.local_date,
            "age_years": round(self.age_years, 3),
            "cycle": self.cycle,
            "direction": self.direction,
            "crossing_index": self.crossing_index,
            "rule_version": RULE_VERSION,
        }
        if self.event_type == "conjunction":
            d.update(planet=self.planet, planet_zh=self.planet_zh, axis=self.axis,
                     longitude=_r(self.longitude), speed=_r(self.speed, 4))
        else:
            d.update(aspect=self.aspect, aspect_zh=self.aspect_zh,
                     saturn_longitude=_r(self.saturn_longitude),
                     jupiter_longitude=_r(self.jupiter_longitude))
        return d


def _r(v, n=3):
    return None if v is None else round(v, n)


# —————————————————————— 时间换算 —————————————————————— #

def _jd_to_utc_dt(jd: float) -> datetime:
    """儒略日 UT → UTC datetime（分钟级）。"""
    import swisseph as swe
    y, m, d, h = swe.revjul(jd, swe.GREG_CAL)
    base = datetime(int(y), int(m), int(d), tzinfo=timezone.utc)
    return base + timedelta(hours=h)


def _jd_to_utc_iso(jd: float) -> str:
    return _jd_to_utc_dt(jd).strftime("%Y-%m-%dT%H:%MZ")


def _jd_to_local_date(jd: float, tz) -> Optional[str]:
    if tz is None:
        return None
    return _jd_to_utc_dt(jd).astimezone(tz).strftime("%Y-%m-%d")


def _age_at(jd: float, birth_jd: float) -> float:
    return (jd - birth_jd) / _DAYS_PER_YEAR


def _cycle_of(planet: str, age: float) -> int:
    return int(age // _CYCLE_DIVISOR[planet]) + 1


# —————————————————————— 求根 —————————————————————— #

def _bisect(f, lo: float, hi: float) -> float:
    """f 在 [lo,hi] 连续且端点异号，二分到 <1 分钟。返回根 JD。"""
    flo = f(lo)
    for _ in range(_REFINE_MAX_ITER):
        mid = 0.5 * (lo + hi)
        fmid = f(mid)
        if hi - lo < _REFINE_EPS_DAYS or fmid == 0.0:
            return mid
        if (flo < 0) != (fmid < 0):
            hi = mid
        else:
            lo, flo = mid, fmid
    return 0.5 * (lo + hi)


def _scan_zeros(f, t0: float, t1: float):
    """在 [t0,t1] 上 1 日步长扫描 f 的过零点，返回精化后的根 JD 列表。

    只接受相邻样本连续（跳变 <90°）的变号，滤掉 ±180 环绕假过零。
    """
    roots = []
    prev_t = t0
    prev = f(t0)
    t = t0 + _SCAN_STEP_DAYS
    while t <= t1 + 1e-9:
        cur = f(t)
        if prev == 0.0:
            roots.append(prev_t)
        elif (prev < 0) != (cur < 0) and abs(cur - prev) < _CONTINUITY_LIMIT:
            roots.append(_bisect(f, prev_t, t))
        prev_t, prev = t, cur
        t += _SCAN_STEP_DAYS
    return roots


# —————————————————————— 合四轴（§7.1）—————————————————————— #

def _scan_conjunctions(planet: str, natal_axes: Dict[str, float],
                       birth_jd: float, max_age: float, tz, pos_fn) -> List[TransitEvent]:
    end_jd = birth_jd + max_age * _DAYS_PER_YEAR
    events: List[TransitEvent] = []

    for axis in AXES_ORDER:
        if axis not in natal_axes:
            continue
        axis_lon = natal_axes[axis]

        def sep(jd, _axis_lon=axis_lon):
            return wrap180(pos_fn(planet, jd).longitude - _axis_lon)

        raw = []  # (jd, direction, speed, planet_lon)

        # 0 岁：出生时本命行星距最近该轴 <=10° → 记 0 岁起始事件。
        natal_pos = pos_fn(planet, birth_jd)
        if abs(wrap180(natal_pos.longitude - axis_lon)) <= _BIRTH_ZERO_ORB:
            raw.append((birth_jd, natal_pos.direction, natal_pos.speed, natal_pos.longitude))

        # 过境合相：只记录顺行时的合轴（§7.1）。
        for jd in _scan_zeros(sep, birth_jd, end_jd):
            pos = pos_fn(planet, jd)
            if pos.direction != "direct":
                continue
            raw.append((jd, pos.direction, pos.speed, pos.longitude))

        # 按 JD 排序、同轴去重（间隔 < dedup_years 视为同一次擦轴，保留最早）。
        raw.sort(key=lambda r: r[0])
        dedup_days = _CONJ_DEDUP_YEARS[planet] * _DAYS_PER_YEAR
        kept = []
        for r in raw:
            if kept and (r[0] - kept[-1][0]) < dedup_days:
                continue
            kept.append(r)

        # 1 岁以内归 0 岁；同轴只保留一个 0 岁事件。
        seen_zero = False
        idx = 0
        for jd, direction, speed, plon in kept:
            age = _age_at(jd, birth_jd)
            if age < _AGE_ZERO_CUTOFF:
                if seen_zero:
                    continue
                seen_zero = True
                age = 0.0  # 分桶到 0 岁；exact_jd 仍保留真实时刻/位置
            idx += 1
            events.append(_mk_conjunction(planet, axis, jd, age, direction,
                                          speed, plon, idx, tz))
    events.sort(key=lambda e: e.age_years)
    return events


def _mk_conjunction(planet, axis, jd, age, direction, speed, plon, idx, tz):
    cycle = _cycle_of(planet, age)
    utc = _jd_to_utc_iso(jd)
    # 稳定身份（§7.3）：rule_version+event_type+planet+axis+crossing_index+direction，
    # 不含日期——星历升级/求根精度变化不改同一 crossing 的身份，保缓存/前端 key 稳定。
    eid = "%s:conjunction:%s:%s:%d:%s" % (RULE_VERSION, planet, axis.lower(), idx, direction)
    return TransitEvent(
        event_id=eid, event_type="conjunction", planet=planet,
        planet_zh={"saturn": "土星", "jupiter": "木星"}[planet], axis=axis,
        aspect=None, aspect_zh=None, exact_jd=jd, utc_datetime=utc,
        local_date=_jd_to_local_date(jd, tz), age_years=age, cycle=cycle,
        direction=direction, crossing_index=idx, longitude=plon, speed=speed,
    )


# —————————————————————— 土木相位（§7.2）—————————————————————— #

def _scan_aspects(birth_jd: float, max_age: float, tz, pos_fn) -> List[TransitEvent]:
    end_jd = birth_jd + max_age * _DAYS_PER_YEAR
    events: List[TransitEvent] = []

    for target, target_zh in ASPECT_TARGETS:
        def g(jd, _t=target):
            sat = pos_fn("saturn", jd).longitude
            jup = pos_fn("jupiter", jd).longitude
            return wrap180((jup - sat) - _t)

        raw = []  # (jd,)

        # 0 岁：出生时有向角距目标 <=10° → 记 0 岁。
        if abs(g(birth_jd)) <= _BIRTH_ZERO_ORB:
            raw.append(birth_jd)
        for jd in _scan_zeros(g, birth_jd, end_jd):
            raw.append(jd)

        raw.sort()
        dedup_days = _ASPECT_DEDUP_YEARS * _DAYS_PER_YEAR
        kept = []
        for jd in raw:
            if kept and (jd - kept[-1]) < dedup_days:
                continue
            kept.append(jd)

        seen_zero = False
        idx = 0
        for jd in kept:
            age = _age_at(jd, birth_jd)
            if age < _AGE_ZERO_CUTOFF:
                if seen_zero:
                    continue
                seen_zero = True
                age = 0.0  # 分桶到 0 岁；exact_jd 仍保留真实时刻/位置
            eff_jd = jd
            idx += 1
            sat = pos_fn("saturn", eff_jd)
            jup = pos_fn("jupiter", eff_jd)
            direction = "direct" if (jup.speed - sat.speed) >= 0 else "retrograde"
            utc = _jd_to_utc_iso(eff_jd)
            # 稳定身份（§7.3）：不含日期，rule_version+event_type+aspect+crossing_index+direction
            eid = "%s:aspect:%d:%d:%s" % (RULE_VERSION, target, idx, direction)
            events.append(TransitEvent(
                event_id=eid, event_type="aspect", planet=None, planet_zh=None,
                axis=None, aspect=target, aspect_zh=target_zh, exact_jd=eff_jd,
                utc_datetime=utc, local_date=_jd_to_local_date(eff_jd, tz),
                age_years=age, cycle=None, direction=direction, crossing_index=idx,
                saturn_longitude=sat.longitude, jupiter_longitude=jup.longitude,
            ))
    events.sort(key=lambda e: e.age_years)
    return events


# —————————————————————— 主入口 —————————————————————— #

def compute_transit_events(natal_axes: Dict[str, float], birth_jd: float,
                           max_age: float = 80.0, tz=None) -> Dict[str, List[TransitEvent]]:
    """算出土星/木星合四轴事件与土木相位事件。

    natal_axes: {"Asc":lon,"MC":lon,"Dsc":lon,"IC":lon}（度，本命固定轴点）。
    birth_jd:   出生瞬间儒略日 UT（唯一真相，来自 CivilTimeResolver）。
    max_age:    扫描年龄上界（默认 0–80）。
    tz:         可选 tzinfo，用于填充事件 local_date；None 则 local_date=None。
    """
    # 引擎/kerykeion 可能在本请求早些时候改过 swe 的全局星历路径，
    # 扫描前重新钉回确定性 ephe/，杜绝静默回退 Moshier。
    from services.ephemeris_guard import apply_ephe_path
    apply_ephe_path()
    pos = _make_pos()  # 调用内位置记忆化，跨轴/相位共享同一日网格
    return {
        "saturn_events": _scan_conjunctions("saturn", natal_axes, birth_jd, max_age, tz, pos),
        "jupiter_events": _scan_conjunctions("jupiter", natal_axes, birth_jd, max_age, tz, pos),
        "aspects": _scan_aspects(birth_jd, max_age, tz, pos),
    }
