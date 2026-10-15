"""Solar arc events in the two course-defined directions, plus the full
bidirectional conjunction/square/opposition matrix between the solar-arc
wheel (10 planets + Chiron + nodes + Part of Fortune + four angles) and the
same set of natal points, and a bi-wheel payload for double-wheel rendering.

Type 1 advances natal planets/midpoints to their quadrant's natal axis.
Type 2 advances each natal axis to natal planets/midpoints.
The matrix keeps both types untouched; it is purely additive.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import TYPE_CHECKING, Mapping

from services.solar_arc_engine import (
    circular_midpoint,
    forward_arc,
    solve_age,
    sun_longitude,
)

if TYPE_CHECKING:
    from services.forecast_natal import ForecastNatalSnapshot, ForecastPoint

COMPUTE_VERSION = "solar-arc-compute-5"

_ZH: dict[str, str] = {
    "sun": "太阳", "moon": "月亮", "mercury": "水星", "venus": "金星",
    "mars": "火星", "jupiter": "木星", "saturn": "土星", "uranus": "天王星",
    "neptune": "海王星", "pluto": "冥王星", "chiron": "凯龙星",
    "north_node": "北交点", "south_node": "南交点",
    "fortuna": "福点",
}
_AXIS_ZH: dict[str, str] = {
    "asc": "上升点", "mc": "中天", "dsc": "下降点", "ic": "天底",
}

# 课程四轴算法（type1 / type2）的行星集合，显式白名单。
#
# snapshot.planets 来自 forecast_natal._SPECIAL_POINTS，那份点集由多个模块共用
# （流年双盘等）。往共享点集里加点时，不应该悄悄改变太阳弧课程表的内容——曾经
# 加入 part_of_spirit 就让四轴页多出几行 spiritus，并且因为这里没有中文标签而
# 直接把英文键渲染给了用户。要收录新的点必须在这里显式加，并同步 _ZH。
_COURSE_POINTS: frozenset[str] = frozenset({
    "sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn",
    "uranus", "neptune", "pluto", "chiron", "north_node", "south_node",
    "fortuna",
})

# Full point set shared by the matrix and the bi-wheel payload.
_POINT_ORDER: tuple[str, ...] = (
    "sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn",
    "uranus", "neptune", "pluto", "chiron", "north_node", "south_node",
    "fortuna", "asc", "mc", "dsc", "ic",
)

# Aspect angles (degrees) included in the matrix: conjunction / square /
# opposition, matching the product wording.
_MATRIX_ASPECTS: tuple[float, ...] = (0.0, 90.0, 180.0)

# Aspect label + display order; opposition is a 180-degree contact so it is
# the same geometric event as a conjunction at the same wheel position — a
# lone pair appears once with its strongest aspect.
_ASPECT_ZH: dict[float, str] = {0.0: "合", 90.0: "刑", 180.0: "冲"}
_ASPECT_ORDER: dict[float, int] = {0.0: 0, 180.0: 1, 90.0: 2}
# 比较盘中心相位网沿用日返跨盘的紧容许度；太阳弧产品范围只画合/刑/冲。
_WHEEL_ASPECT_ORB: float = 3.0
# 入相/出相前瞻步长：太阳弧约每年推进 1°，0.01° 约合三四天，
# 足以分辨容许度在收窄还是拉开，又不会跨过精确点导致方向判反。
_ARC_PROBE_DEG: float = 0.01
# 与 engine/natal_chart.py 同名阈值一致：变化小于此值视为方向不明。
_ORB_EPSILON: float = 1e-6

# Quadrant rule: which natal axis does an SA planet in each house first reach?
_HOUSE_AXIS: dict[int, str] = {
    **{h: "ic"  for h in (1, 2, 3)},
    **{h: "dsc" for h in (4, 5, 6)},
    **{h: "mc"  for h in (7, 8, 9)},
    **{h: "asc" for h in (10, 11, 12)},
}

# The axis a planet passes through entering each quadrant (zodiacally forward).
# Used to sort planets within a quadrant by forward distance from entry,
# which correctly handles planet groups that span the 0° boundary.
_QUADRANT_ENTRY: dict[str, str] = {
    "ic":  "asc",   # H1-3 enter at ASC, advance toward IC
    "dsc": "ic",    # H4-6 enter at IC,  advance toward DSC
    "mc":  "dsc",   # H7-9 enter at DSC, advance toward MC
    "asc": "mc",    # H10-12 enter at MC, advance toward ASC
}


def _quadrant_for_house(house: int) -> int:
    """Return the course quadrant for a natal Placidus house (1..12)."""
    if not 1 <= int(house) <= 12:
        raise ValueError(f"宫位必须在 1..12，当前为 {house}")
    return (int(house) - 1) // 3 + 1


def _age_to_date(birth_dt: datetime, age: float) -> str:
    return (birth_dt + timedelta(days=age * 365.2422)).strftime("%Y-%m-%d")


def _point_lon(snapshot: "ForecastNatalSnapshot", key: str) -> float:
    """Return the natal longitude of a planet or angle point."""
    if key in snapshot.axes:
        return snapshot.axes[key]
    return snapshot.planets[key].longitude


def _aspect_label(angle: float) -> str:
    return _ASPECT_ZH.get(angle, f"{angle:.0f}°")


def _course_planets(snapshot: "ForecastNatalSnapshot") -> dict[str, "ForecastPoint"]:
    """课程算法只认 _COURSE_POINTS 里的行星，忽略共享点集后来新增的点。"""
    return {
        name: point
        for name, point in snapshot.planets.items()
        if name in _COURSE_POINTS
    }


def _full_point_set(snapshot: "ForecastNatalSnapshot") -> dict[str, float]:
    """Longitudes of the full 18-point set (10 planets + Chiron + nodes +
    Part of Fortune + four angles).  Missing special points fall back to
    ``None`` and are skipped by callers that tolerate partial input."""
    out: dict[str, float] = {}
    for key in _POINT_ORDER:
        try:
            out[key] = _point_lon(snapshot, key)
        except KeyError:
            continue
    return out


def _matrix_events(
    snapshot: "ForecastNatalSnapshot",
    birth_dt: datetime,
    age_from: float,
    age_to: float,
) -> list[dict]:
    """Bidirectional conjunction/square/opposition between the solar-arc
    wheel and the natal wheel over the same 18-point set.

    Solar-arc points rotate uniformly:  SA(lon) = natal(lon) + arc(age).
    The contact SA(a) ⊕ natal(b) at angle θ holds when
        arc = (natal_b + θ - natal_a) mod 360.
    Each aspect therefore maps to a single required arc; one solve per
    (solar-arc point, natal point, aspect) covers both directions — the
    mirrored pair is the same geometric contact, labelled from the natal
    point's perspective when the solar-arc point does the triggering.
    """
    natal = _full_point_set(snapshot)
    if not natal:
        return []
    arcs = {key: natal[key] for key in natal}
    events: list[dict] = []
    seen: set[tuple[str, str, float]] = set()

    for sa_key, sa_lon in arcs.items():
        for natal_key, natal_lon in arcs.items():
            for angle in _MATRIX_ASPECTS:
                required = (natal_lon + angle - sa_lon) % 360.0
                age = solve_age(
                    snapshot.birth_jd_ut, natal["sun"], required,
                    age_from, age_to,
                )
                if age is None:
                    continue
                key = tuple(sorted((sa_key, natal_key))) + (angle,)
                if key in seen:
                    continue
                seen.add(key)
                events.append({
                    "sa_point": sa_key,
                    "natal_point": natal_key,
                    "aspect": _aspect_label(angle),
                    "angle": angle,
                    "age": round(age, 2),
                    "date": _age_to_date(birth_dt, age),
                })

    events.sort(key=lambda item: (item["age"], item["sa_point"], item["natal_point"]))
    return events


def _angular_sep(lon_a: float, lon_b: float) -> float:
    return abs((lon_a - lon_b + 180.0) % 360.0 - 180.0)


def _mark_opposite_axis_pairs(items: list[dict]) -> None:
    """标记同一几何时点的一体两面，供前端合成一张卡。

    判定不依赖展示层的 0.1 岁四舍五入：两个移动点必须精确相对、两个目标轴必须
    精确相对，而且解算得到的未舍入年龄一致。典型例子是北交点→下降点与
    南交点→上升点。普通“同龄”事件不会被合并。
    """
    paired = set()
    for left_index, left in enumerate(items):
        if left_index in paired:
            continue
        for right_index in range(left_index + 1, len(items)):
            if right_index in paired:
                continue
            right = items[right_index]
            if abs(_angular_sep(left["_point_lon"], right["_point_lon"]) - 180.0) > 1e-7:
                continue
            if abs(_angular_sep(left["_axis_lon"], right["_axis_lon"]) - 180.0) > 1e-7:
                continue
            if abs(left["_exact_age"] - right["_exact_age"]) > 1e-7:
                continue
            pair_id = f"opposite-{left_index}-{right_index}"
            left["opposite_pair_id"] = pair_id
            right["opposite_pair_id"] = pair_id
            paired.update((left_index, right_index))
            break

    for item in items:
        item.pop("_point_lon", None)
        item.pop("_axis_lon", None)
        item.pop("_exact_age", None)


def _wheel_cross_aspects(
    natal: Mapping[str, float],
    arc: float,
) -> tuple[list[dict], list[dict]]:
    """Current SA ↔ natal aspect lines for the comparison-wheel renderer.

    Unlike ``_matrix_events`` (exact dates across an age range), this is a
    snapshot at one selected age.  It uses the same tight 3° cross-wheel orb
    as the solar-return comparison wheel, but only the product-defined
    conjunction/square/opposition set.  Angles and Part of Fortune remain in
    the same 18-point set as the event matrix.
    """
    cross_aspects: list[dict] = []
    contacts: list[dict] = []
    for sa_key, natal_sa_lon in natal.items():
        sa_lon = (natal_sa_lon + arc) % 360.0
        for natal_key, natal_lon in natal.items():
            sep = _angular_sep(sa_lon, natal_lon)
            for angle in _MATRIX_ASPECTS:
                orb = abs(sep - angle)
                if orb > _WHEEL_ASPECT_ORB:
                    continue
                # 入相/出相：与本命盘同一口径——前瞻一小步，看容许度是变小
                # 还是变大。太阳弧的运动比本命简单得多：整张盘以同一个弧
                # 匀速前推，本命盘不动，所以这里不需要每个天体的速度，只要
                # 把弧推进一个增量重算距离即可。弧速约每年 1°（太阳周年
                # 运动），取 0.01° 相当于前瞻三四天，足够分辨方向。
                probe_lon = (natal_sa_lon + arc + _ARC_PROBE_DEG) % 360.0
                probe_orb = abs(_angular_sep(probe_lon, natal_lon) - angle)
                applying: bool | None = None
                if abs(probe_orb - orb) >= _ORB_EPSILON:
                    applying = probe_orb < orb
                cross_aspects.append({
                    # Keep the solar-return renderer field names so both
                    # panels consume one comparison-wheel contract.
                    "sr_planet": sa_key,
                    "natal_planet": natal_key,
                    "angle": angle,
                    "aspect": _aspect_label(angle),
                    "orb": round(orb, 4),
                    "applying": applying,
                })
                if angle == 0.0:
                    contacts.append({
                        "sr_planet": sa_key,
                        "natal_point": natal_key,
                        "orb": round(orb, 4),
                        "applying": applying,
                    })
                break
    return cross_aspects, contacts


def _bi_wheel_payload(
    snapshot: "ForecastNatalSnapshot",
    age: float,
) -> dict:
    """Payload for the double-wheel renderer.

    The natal wheel (inner ring) keeps its own cusps/angles.  The solar-arc
    wheel (outer ring) rotates planets, angles, and all twelve natal cusps by
    the same arc, allowing the shared renderer to draw two independent house
    frames without treating the selected date as a transit chart.
    """
    natal = _full_point_set(snapshot)
    if not natal:
        return {}
    arc = forward_arc(
        natal["sun"],
        sun_longitude(snapshot.birth_jd_ut + age),
    )
    cross_aspects, contacts = _wheel_cross_aspects(natal, arc)
    natal_cusps = [float(cusp) % 360.0 for cusp in snapshot.cusps[:12]]
    sa_planets: dict[str, dict] = {}
    for key, lon in natal.items():
        if key in snapshot.axes:
            continue
        sa_planets[key] = {
            "lon": (lon + arc) % 360.0,
            "retrograde": False,
        }
    return {
        "natal": {
            "planets": {
                key: {"lon": lon, "retrograde": False}
                for key, lon in natal.items()
                if key not in snapshot.axes
            },
            "angles": {key: lon for key, lon in natal.items() if key in snapshot.axes},
            "cusps": natal_cusps,
            "asc_lon": snapshot.axes.get("asc", 0.0),
            "mc_lon": snapshot.axes.get("mc", 0.0),
        },
        "solar_arc": {
            "planets": sa_planets,
            "angles": {
                key: (lon + arc) % 360.0
                for key, lon in natal.items()
                if key in snapshot.axes
            },
            "cusps": [
                (cusp + arc) % 360.0
                for cusp in natal_cusps
            ],
            "arc": round(arc, 4),
            "age": round(age, 2),
        },
        "cross_aspects": cross_aspects,
        "degree_contacts": contacts,
        "birth_jd_ut": snapshot.birth_jd_ut,
    }


def compute_solar_arc_wheel(
    snapshot: "ForecastNatalSnapshot",
    age: float,
) -> dict:
    """Return only the bi-wheel payload at an exact selected age.

    Time stepping in the mini-program calls this lightweight path instead of
    recomputing the full Type 1 / Type 2 / matrix event table on every tap.
    The supported range intentionally matches the event endpoint (0–80).
    """
    try:
        selected_age = float(age)
    except (TypeError, ValueError) as exc:
        raise ValueError("wheel_age 必须是数字") from exc
    if not math.isfinite(selected_age) or not 0.0 <= selected_age <= 80.0:
        raise ValueError("wheel_age 必须在 0..80")
    return _bi_wheel_payload(snapshot, selected_age)


def _sorted_in_quadrant(
    names: list[str], planets: "Mapping", entry_lon: float
) -> list[str]:
    """Sort planets by forward zodiacal distance from the quadrant entry axis.

    Sorting by raw longitude breaks when the group spans 0°. Measuring forward
    distance from a fixed entry point (which is always < any planet in the
    quadrant, modulo 360) gives a monotonic key that survives 0° crossings.
    """
    return sorted(names, key=lambda n: (planets[n].longitude - entry_lon) % 360.0)


def compute_solar_arc_events(
    snapshot: "ForecastNatalSnapshot",
    birth_year: int,
    birth_month: int,
    birth_day: int,
    birth_hour: int,
    birth_minute: int,
    age_from: float = 0.0,
    age_to: float = 80.0,
    wheel_age: float | None = None,
    event_limit: int | None = 50,
) -> dict:
    birth_jd = snapshot.birth_jd_ut
    natal_sun = snapshot.planets["sun"].longitude
    birth_dt = datetime(birth_year, birth_month, birth_day, birth_hour, birth_minute)
    age_cap = min(age_to, 80.0)

    course_planets = _course_planets(snapshot)

    # Group planets by their target axis (quadrant rule)
    by_axis: dict[str, list[str]] = {"ic": [], "dsc": [], "mc": [], "asc": []}
    for name, point in course_planets.items():
        axis = _HOUSE_AXIS.get(point.house)
        if axis:
            by_axis[axis].append(name)

    def _solve(required_arc: float) -> float | None:
        return solve_age(birth_jd, natal_sun, required_arc % 360.0, age_from, age_cap)

    # Same-quadrant adjacent midpoints, sorted by forward distance from entry axis
    # to correctly handle groups that span the 0° boundary.
    midpoints: list[tuple[str, float, int]] = []  # (label, longitude, natal house)
    for axis_key, names in by_axis.items():
        entry_lon = snapshot.axes[_QUADRANT_ENTRY[axis_key]]
        ordered = _sorted_in_quadrant(names, snapshot.planets, entry_lon)
        for i in range(len(ordered) - 1):
            p1, p2 = ordered[i], ordered[i + 1]
            mp_lon = circular_midpoint(
                snapshot.planets[p1].longitude, snapshot.planets[p2].longitude
            )
            label = f"{_ZH.get(p1, p1)}·{_ZH.get(p2, p2)}"
            midpoint_house = min(snapshot.planets[p1].house, snapshot.planets[p2].house)
            midpoints.append((label, mp_lon, midpoint_house))

    # === Type 1: SA planet/midpoint → conjunct natal axis (quadrant rule) ===
    type1: list[dict] = []
    for axis_key, names in by_axis.items():
        ax_lon = snapshot.axes.get(axis_key)
        if ax_lon is None:
            continue
        ax_zh = _AXIS_ZH[axis_key]
        entry_lon = snapshot.axes[_QUADRANT_ENTRY[axis_key]]
        ordered = _sorted_in_quadrant(names, snapshot.planets, entry_lon)

        for name in ordered:
            arc = (ax_lon - snapshot.planets[name].longitude) % 360.0
            age = _solve(arc)
            if age is not None:
                type1.append({
                    "point": _ZH.get(name, name),
                    "axis": ax_zh,
                    "house": snapshot.planets[name].house,
                    "quadrant": _quadrant_for_house(snapshot.planets[name].house),
                    "age": round(age, 1),
                    "date": _age_to_date(birth_dt, age),
                    "_point_lon": snapshot.planets[name].longitude,
                    "_axis_lon": ax_lon,
                    "_exact_age": age,
                })

        for i in range(len(ordered) - 1):
            p1, p2 = ordered[i], ordered[i + 1]
            mp_lon = circular_midpoint(
                snapshot.planets[p1].longitude, snapshot.planets[p2].longitude
            )
            arc = (ax_lon - mp_lon) % 360.0
            age = _solve(arc)
            if age is not None:
                zh1, zh2 = _ZH.get(p1, p1), _ZH.get(p2, p2)
                h1, h2 = snapshot.planets[p1].house, snapshot.planets[p2].house
                type1.append({
                    "point": f"{zh1}·{zh2}",
                    "axis": ax_zh,
                    "house": min(h1, h2),
                    "quadrant": _quadrant_for_house(min(h1, h2)),
                    "age": round(age, 1),
                    "date": _age_to_date(birth_dt, age),
                    "_point_lon": mp_lon,
                    "_axis_lon": ax_lon,
                    "_exact_age": age,
                })

    type1.sort(key=lambda x: x["age"])
    _mark_opposite_axis_pairs(type1)

    # === Type 2: SA axis → conjunct natal planet/midpoint ===
    # (natal_axis + solar_arc) % 360 == natal_point, therefore the required
    # forward arc is (natal_point - natal_axis) % 360.  Reversing this
    # subtraction would incorrectly calculate SA planet/midpoint → natal axis,
    # duplicating Type 1's direction.
    type2: list[dict] = []
    for axis_key, ax_lon in snapshot.axes.items():
        ax_zh = _AXIS_ZH.get(axis_key, axis_key)

        for name, point in course_planets.items():
            arc = (point.longitude - ax_lon) % 360.0
            age = _solve(arc)
            if age is not None:
                type2.append({
                    "axis": ax_zh,
                    "point": _ZH.get(name, name),
                    "house": point.house,
                    "quadrant": _quadrant_for_house(point.house),
                    "age": round(age, 1),
                    "date": _age_to_date(birth_dt, age),
                    "_point_lon": point.longitude,
                    "_axis_lon": ax_lon,
                    "_exact_age": age,
                })

        for label, mp_lon, midpoint_house in midpoints:
            arc = (mp_lon - ax_lon) % 360.0
            age = _solve(arc)
            if age is not None:
                type2.append({
                    "axis": ax_zh,
                    "point": label,
                    "house": midpoint_house,
                    "quadrant": _quadrant_for_house(midpoint_house),
                    "age": round(age, 1),
                    "date": _age_to_date(birth_dt, age),
                    "_point_lon": mp_lon,
                    "_axis_lon": ax_lon,
                    "_exact_age": age,
                })

    type2.sort(key=lambda x: x["age"])
    _mark_opposite_axis_pairs(type2)

    # Additive matrix + bi-wheel payload (new board); type1/type2 untouched.
    matrix = _matrix_events(snapshot, birth_dt, age_from, age_to)
    bi_wheel = _bi_wheel_payload(
        snapshot,
        (age_from + age_to) / 2.0 if wheel_age is None else wheel_age,
    )

    exported_type1 = type1 if event_limit is None else type1[:max(0, int(event_limit))]
    exported_type2 = type2 if event_limit is None else type2[:max(0, int(event_limit))]
    return {
        "type1": exported_type1,
        "type2": exported_type2,
        "matrix": matrix,
        "bi_wheel": bi_wheel,
        "engine_version": COMPUTE_VERSION,
    }
