# -*- coding: utf-8 -*-
"""行运对本命：内圈本命、外圈六颗行运星的双盘与精确事件。

本模块只定义产品口径并组装既有能力：本命点位来自 ``forecast_natal``，行运位置
与精确时刻来自 ``transit_utils``（strict SWIEPH）。不计算行运四轴、宫头、福点或
精神点；双盘始终以本命宫位框架为准。
"""
from datetime import datetime, timezone
from typing import Iterable, Mapping

import swisseph as swe

from services import transit_utils

COMPUTE_VERSION = "transit-natal-2"

TRANSIT_GROUPS = {
    "slow": ("saturn", "uranus", "neptune", "pluto"),
    "fast": ("jupiter", "mars"),
}
GROUP_ZH = {"slow": "天海冥土", "fast": "木火"}
# 主流相位/全年事件的触发星：产品分组只计算这六颗。
BODY_IDS = {
    "mars": swe.MARS,
    "jupiter": swe.JUPITER,
    "saturn": swe.SATURN,
    "uranus": swe.URANUS,
    "neptune": swe.NEPTUNE,
    "pluto": swe.PLUTO,
}
DISPLAY_BODY_IDS = {
    "sun": swe.SUN, "moon": swe.MOON, "mercury": swe.MERCURY,
    "venus": swe.VENUS, "mars": swe.MARS, "jupiter": swe.JUPITER,
    "saturn": swe.SATURN, "uranus": swe.URANUS, "neptune": swe.NEPTUNE,
    "pluto": swe.PLUTO, "chiron": swe.CHIRON, "north_node": swe.MEAN_NODE,
}
DISPLAY_POINT_ORDER = tuple(DISPLAY_BODY_IDS) + ("south_node",)
POINT_ZH = {
    "sun": "太阳", "moon": "月亮", "mercury": "水星", "venus": "金星",
    "mars": "火星", "jupiter": "木星", "saturn": "土星", "uranus": "天王星",
    "neptune": "海王星", "pluto": "冥王星", "chiron": "凯龙星",
    "north_node": "北交点", "south_node": "南交点", "fortuna": "福点",
    "spiritus": "精神点", "asc": "上升点", "mc": "中天",
    "dsc": "下降点", "ic": "天底",
}
PLANET_ZH = {key: POINT_ZH[key] for key in DISPLAY_POINT_ORDER}
NATAL_POINT_ORDER = (
    "sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn",
    "uranus", "neptune", "pluto", "chiron", "north_node", "south_node",
    "fortuna", "spiritus", "asc", "mc", "dsc", "ic",
)
AXES = frozenset(("asc", "mc", "dsc", "ic"))
ASPECT_ANGLES = (0.0, 60.0, 90.0, 120.0, 180.0)
ASPECT_WITH_MIRRORS = transit_utils.MAJOR_ASPECTS_WITH_MIRRORS
ASPECT_ZH = {0.0: "合", 60.0: "六合", 90.0: "刑", 120.0: "三合", 180.0: "冲"}

# 同一次逆行接触环必须在一年内完成。扫描区间按同样长度向两端外扩，保证落在
# 请求边界附近的第 2/3 次接触仍能拿到完整序号；分组以首个接触为锚，避免相邻
# 间隔链式把两个周期串在一起。
SERIES_WINDOW_DAYS = 365.0

# 用户确认的流年容许度。四轴只有合相，单列 orb。
ORBS = {
    "slow": {0.0: 1.5, 60.0: 1.0, 90.0: 1.5, 120.0: 1.0, 180.0: 1.5, "axis": 1.0},
    "fast": {0.0: 2.0, 60.0: 1.5, 90.0: 2.0, 120.0: 1.5, 180.0: 2.0, "axis": 1.5},
}

# 与本命盘入相/出相算法保持同一探测口径。使用一小时会在非常接近精确点时
# 跨过精确点，进而把仍在入相的接触误判为出相。
_APPLYING_DT = 0.001
_ORB_EPSILON = 1e-6


def _group_for(planet: str) -> str:
    for group, planets in TRANSIT_GROUPS.items():
        if planet in planets:
            return group
    raise KeyError(planet)


def _natal_longitudes(snapshot) -> dict[str, float]:
    result = {}
    for key in NATAL_POINT_ORDER:
        if key in snapshot.axes:
            result[key] = float(snapshot.axes[key]) % 360.0
        elif key in snapshot.planets:
            result[key] = float(snapshot.planets[key].longitude) % 360.0
    return result


def _canonical_angle(directed_angle: float) -> float:
    angle = directed_angle % 360.0
    return min(angle, 360.0 - angle)


def _separation(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _applying(moving_lon: float, speed: float | None, fixed_lon: float, angle: float) -> bool | None:
    """True=入相，False=出相，None=速度不足以可靠判定。"""
    if speed is None or abs(speed) <= 1e-9:
        return None
    orb = abs(_separation(moving_lon, fixed_lon) - angle)
    future_lon = (moving_lon + speed * _APPLYING_DT) % 360.0
    future_orb = abs(_separation(future_lon, fixed_lon) - angle)
    if abs(future_orb - orb) < _ORB_EPSILON:
        return None
    return future_orb < orb


def _jd_to_utc(jd: float) -> str:
    year, month, day, hour = swe.revjul(jd, swe.GREG_CAL)
    whole_hour = int(hour)
    minute_float = (hour - whole_hour) * 60.0
    minute = int(minute_float)
    second = int(round((minute_float - minute) * 60.0))
    if second >= 60:
        second = 59
    return datetime(year, month, day, whole_hour, minute, second, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _node_equivalent(directed_angle: float) -> dict:
    """北交点事件对应的南交点等价表达；只展示一条但不丢语义。"""
    equivalent_directed = (float(directed_angle) + 180.0) % 360.0
    equivalent_angle = _canonical_angle(equivalent_directed)
    return {
        "equivalent_natal_point": "south_node",
        "equivalent_natal_point_zh": POINT_ZH["south_node"],
        "equivalent_angle": equivalent_angle,
        "equivalent_aspect": ASPECT_ZH[equivalent_angle],
    }


def active_aspects(snapshot, jd_ut: float) -> tuple[list[dict], dict[str, dict]]:
    """返回选定时刻的跨盘生效相位及正常行运盘的完整外圈星体。

    外圈显示十大行星、凯龙和南北交点；相位筛选仍只遍历 ``BODY_IDS`` 六颗
    触发星，显示集合与产品计算集合不能再混为一谈。
    """
    natal = _natal_longitudes(snapshot)
    rows = []
    transit_planets = {}
    for planet, body_id in DISPLAY_BODY_IDS.items():
        longitude, speed = transit_utils.body_position(body_id, jd_ut)
        transit_planets[planet] = {
            "lon": round(longitude, 6),
            "speed": round(speed, 6),
            "retrograde": speed < 0,
        }
    north = transit_planets["north_node"]
    transit_planets["south_node"] = {
        "lon": round((north["lon"] + 180.0) % 360.0, 6),
        "speed": north["speed"],
        "retrograde": north["retrograde"],
    }

    for planet, body_id in BODY_IDS.items():
        position = transit_planets[planet]
        longitude, speed = position["lon"], position["speed"]
        group = _group_for(planet)
        for point, natal_lon in natal.items():
            # 南北交恒定对冲；同一几何接触统一以北交点为主行，南交点作为等价
            # 表达随行返回，避免列表、计数和跨盘线重复。
            if point == "south_node":
                continue
            angles = (0.0,) if point in AXES else ASPECT_ANGLES
            sep = _separation(longitude, natal_lon)
            for angle in angles:
                orb = abs(sep - angle)
                limit = ORBS[group]["axis"] if point in AXES else ORBS[group][angle]
                if orb > limit:
                    continue
                applying = _applying(longitude, speed, natal_lon, angle)
                row = {
                    "group": group,
                    "group_zh": GROUP_ZH[group],
                    "transit_planet": planet,
                    "transit_planet_zh": PLANET_ZH[planet],
                    "natal_point": point,
                    "natal_point_zh": POINT_ZH[point],
                    "angle": angle,
                    "aspect": ASPECT_ZH[angle],
                    "orb": round(orb, 4),
                    "orb_limit": limit,
                    "applying": applying,
                    "phase": "applying" if applying is True else "separating" if applying is False else None,
                    "phase_zh": "入相" if applying is True else "出相" if applying is False else "",
                    "retrograde": speed < 0,
                }
                if point == "north_node":
                    row.update(_node_equivalent(angle))
                rows.append(row)
                break
    rows.sort(key=lambda row: (0 if row["group"] == "slow" else 1, row["orb"], row["transit_planet"], row["natal_point"]))
    return rows, transit_planets


def compute_wheel(snapshot, jd_ut: float, selected_datetime: str | None = None) -> dict:
    natal = _natal_longitudes(snapshot)
    aspects, transit_planets = active_aspects(snapshot, jd_ut)
    return {
        "selected_datetime": selected_datetime or _jd_to_utc(jd_ut),
        "natal": {
            "planets": {
                key: {"lon": lon, "retrograde": False}
                for key, lon in natal.items() if key not in AXES
            },
            "angles": {key: natal[key] for key in AXES if key in natal},
            "cusps": [float(value) % 360.0 for value in snapshot.cusps[:12]],
            "asc_lon": natal.get("asc", 0.0),
            "mc_lon": natal.get("mc", 0.0),
        },
        "transit": {"planets": transit_planets},
        "cross_aspects": [
            {
                "sr_planet": row["transit_planet"],
                "natal_planet": row["natal_point"],
                "angle": row["angle"],
                "aspect": row["aspect"],
                "orb": row["orb"],
                # active_aspects 早就算了入相/出相，只是组装比较盘时漏传，
                # 导致点击星盘出的卡片没有这个标记。
                "applying": row["applying"],
            }
            for row in aspects
        ],
        "active_aspects": aspects,
        "groups": {
            group: [row for row in aspects if row["group"] == group]
            for group in TRANSIT_GROUPS
        },
        "engine_version": COMPUTE_VERSION,
    }


def _directed_aspects(aspects: Iterable[float]) -> tuple[float, ...]:
    """把无方向的五大相位展开成求根引擎需要的黄道两侧目标角。"""
    result = []
    for raw in aspects:
        angle = _canonical_angle(float(raw))
        if angle not in ASPECT_ANGLES:
            raise ValueError(f"不支持的流年相位角: {raw}")
        for directed in (angle, (-angle) % 360.0):
            if directed not in result:
                result.append(directed)
    return tuple(result)


def _assign_contact_series(rows: list[dict]) -> None:
    """原地补齐稳定的逆行接触环 id、序号与总次数。"""
    buckets = {}
    for row in rows:
        # 六合/刑/三合各有黄道两侧；只有同一个有向目标角的多次命中才是同一
        # 逆行接触序列，不能把 +60° 与 -60° 两个不同位置合成“第 1/2 次”。
        key = (row["transit_planet"], row["natal_point"], row["directed_angle"])
        buckets.setdefault(key, []).append(row)
    for key, contacts in buckets.items():
        contacts.sort(key=lambda row: row["exact_jd"])
        clusters = []
        cluster = []
        for row in contacts:
            if cluster and row["exact_jd"] - cluster[0]["exact_jd"] > SERIES_WINDOW_DAYS:
                clusters.append(cluster)
                cluster = []
            cluster.append(row)
        if cluster:
            clusters.append(cluster)
        for cluster in clusters:
            first_jd = cluster[0]["exact_jd"]
            series_id = "%s:%s:%g:%.6f" % (*key, first_jd)
            total = len(cluster)
            for index, row in enumerate(cluster, 1):
                row["series_id"] = series_id
                row["contact_index"] = index
                row["contact_total"] = total


def collapse_contact_rings(rows: list[dict]) -> list[dict]:
    """逆行接触环只保留第一次与最后一次，丢弃中间的反复拉扯。

    这是本模块（流年双盘 / 终身相位 / 土木过宫）的统一产品口径：一个逆行环
    真正要记录的是它何时开始、何时结束，中间那些来回接触不单独成行。
    调用方必须在 ``_assign_contact_series`` 之后、裁切请求时间窗之前调用，
    否则窗口边界会把真正的末次截掉，把中间接触误当成环的终点。

    ``entry_role`` 取 ``only`` / ``first`` / ``final``；``contact_index`` 与
    ``contact_total`` 保持环内真实序号不变，便于回溯原始次数。

    注意：原有土木流年板块（services/saturn_jupiter_transits.py）是另一条
    独立管线，不适用这条规则，也不会经过这里。
    """
    rings: dict[str, list[dict]] = {}
    for row in rows:
        rings.setdefault(row["series_id"], []).append(row)
    kept = []
    for members in rings.values():
        members.sort(key=lambda row: row["exact_jd"])
        first, last = members[0], members[-1]
        if first is last:
            first["entry_role"] = "only"
            first["entry_role_zh"] = "单次"
            kept.append(first)
            continue
        first["entry_role"] = "first"
        first["entry_role_zh"] = "首次"
        last["entry_role"] = "final"
        last["entry_role_zh"] = "末次"
        kept.extend((first, last))
    # 过宫行没有 natal_point，用 series_id 兜底保证排序稳定且不依赖具体字段。
    kept.sort(key=lambda row: (row["exact_jd"], row["transit_planet"], row["series_id"]))
    return kept


def compute_filtered_events(
    snapshot,
    lo_jd: float,
    hi_jd: float,
    *,
    planets: Iterable[str] | None = None,
    natal_points: Iterable[str] | None = None,
    aspects: Iterable[float] | None = None,
    max_days: float | None = 1098.0,
    collapse_series: bool = True,
) -> dict:
    """按触发星、本命目标和相位筛选精确事件。

    终身接口只把一个年龄章节交给本函数；摘要允许 ``max_days=None`` 扫描完整
    生命框架。扫描仍向两端各扩一年，以保证章节边缘接触的第几次/共几次正确。
    ``collapse_series=False`` 仅供需要逐次精确触点的调用方使用；默认保持
    逆行接触环首末两次的既有展示口径。
    """
    if hi_jd <= lo_jd:
        raise ValueError("结束时间必须晚于开始时间")
    if max_days is not None and hi_jd - lo_jd > max_days:
        raise ValueError("单次流年事件范围不能超过三年")
    natal = _natal_longitudes(snapshot)
    selected_planets = tuple(planets or BODY_IDS.keys())
    unknown_planets = set(selected_planets) - set(BODY_IDS)
    if unknown_planets:
        raise ValueError(f"不支持的行运星: {sorted(unknown_planets)}")
    selected_points = set(natal_points or natal.keys())
    unknown_points = selected_points - set(natal)
    if unknown_points:
        raise ValueError(f"不支持的本命点: {sorted(unknown_points)}")
    selected_points.discard("south_node")
    selected_aspects = tuple(aspects or ASPECT_ANGLES)
    directed_aspects = _directed_aspects(selected_aspects)
    scan_lo = lo_jd - SERIES_WINDOW_DAYS
    scan_hi = hi_jd + SERIES_WINDOW_DAYS
    rows = []
    for planet in selected_planets:
        body_id = BODY_IDS[planet]
        group = _group_for(planet)
        non_axes = {
            key: lon for key, lon in natal.items()
            if key in selected_points and key not in AXES
        }
        axes = {key: lon for key, lon in natal.items() if key in selected_points and key in AXES}
        hits = transit_utils.all_exact_to_fixed_in_window(
            body_id, non_axes, directed_aspects, scan_lo, scan_hi,
        )
        hits += transit_utils.all_exact_to_fixed_in_window(
            body_id, axes, (0.0,), scan_lo, scan_hi,
        )
        for exact_jd, point, directed_angle in hits:
            angle = _canonical_angle(directed_angle)
            _longitude, speed = transit_utils.body_position(body_id, exact_jd)
            row = {
                "group": group,
                "group_zh": GROUP_ZH[group],
                "transit_planet": planet,
                "transit_planet_zh": PLANET_ZH[planet],
                "natal_point": point,
                "natal_point_zh": POINT_ZH[point],
                "angle": angle,
                "directed_angle": float(directed_angle) % 360.0,
                "aspect": ASPECT_ZH[angle],
                "exact_jd": exact_jd,
                "exact_utc": _jd_to_utc(exact_jd),
                "direction": "retrograde" if speed < 0 else "direct",
                "direction_zh": "逆行" if speed < 0 else "顺行",
            }
            if point == "north_node":
                row.update(_node_equivalent(directed_angle))
            rows.append(row)
    rows.sort(key=lambda row: (row["exact_jd"], row["transit_planet"], row["natal_point"], row["angle"]))
    _assign_contact_series(rows)
    # 环内只留首末两端；必须先建环、后裁窗，边界事件才不会被误标。
    if collapse_series:
        rows = collapse_contact_rings(rows)

    # API 时间窗按 [from, to) 返回，避免相邻年度都包含元旦零点同一事件。
    rows = [row for row in rows if lo_jd <= row["exact_jd"] < hi_jd]
    for row in rows:
        row["exact_jd"] = round(row["exact_jd"], 6)
    return {
        "from_jd": round(lo_jd, 6),
        "to_jd": round(hi_jd, 6),
        "event_count": len(rows),
        "events": rows,
        "groups": {
            group: [row for row in rows if row["group"] == group]
            for group in TRANSIT_GROUPS
        },
        "engine_version": COMPUTE_VERSION,
    }


def compute_events(snapshot, lo_jd: float, hi_jd: float) -> dict:
    """旧年度接口：返回时间窗内全部精确过点，继续保持三年上限。"""
    return compute_filtered_events(snapshot, lo_jd, hi_jd)
