# -*- coding: utf-8 -*-
"""0—84岁流年检索与土木进入本命普拉西度十二宫。

年龄只用于切片与展示。行运行星位置、精确相位和宫头穿越全部在 UTC/JD 上求解；
出生地已经固化在本命快照的点位、四轴和 Placidus 宫头中，本模块不接收现居地。
"""
from calendar import monthrange
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from zoneinfo import ZoneInfo

import swisseph as swe

from services import transit_natal, transit_utils


COMPUTE_VERSION = "transit-lifetime-1"
HOUSE_SYSTEM = "placidus"
MAX_AGE_INCLUSIVE = 84
END_AGE_EXCLUSIVE = 85
CHAPTER_AGE_STARTS = tuple(range(0, 78, 7))  # 0, 7, ... 77
HOUSE_BODIES = {"jupiter": swe.JUPITER, "saturn": swe.SATURN}
HOUSE_ZH = {index: f"第{index}宫" for index in range(1, 13)}
# 单次区间查询的最大跨度。生产实测（2核）全六星×全部点位 20 年约 8 秒，
# 距离 nginx 60 秒读超时仍有大量余量；不再一次性预算 0—84 岁全量。
MAX_RANGE_YEARS = 20
# 用儒略年换算会把「整 20 个日历年」判成超限：含闰日的 20 年是 7305 天，
# 比 365.2425×20 多约 0.15 天。放宽两天余量，让整年选择稳定通过。
MAX_RANGE_DAYS = 365.2425 * MAX_RANGE_YEARS + 2.0
_SUMMARY_CACHE_MAX = 24
_SUMMARY_CACHE = OrderedDict()
_SUMMARY_LOCK = Lock()


def _context(snapshot):
    ctx = getattr(snapshot, "context", None)
    if ctx is None or not getattr(ctx, "civil_dt", None):
        raise ValueError("终身流年需要完整出生民用时间上下文")
    try:
        zone = ZoneInfo(str(ctx.snapshot.tz_iana))
        local = datetime.fromisoformat(str(ctx.civil_dt)).replace(tzinfo=zone)
    except Exception as exc:
        raise ValueError("出生时区上下文无效，无法建立周岁边界") from exc
    return ctx, local, zone


def _anniversary(local_birth: datetime, age: int) -> datetime:
    """当地生日边界；2月29日在非闰年按该月最后一日建立年龄切片。"""
    year = local_birth.year + int(age)
    day = min(local_birth.day, monthrange(year, local_birth.month)[1])
    return local_birth.replace(year=year, day=day)


def _datetime_to_jd(value: datetime) -> float:
    utc = value.astimezone(timezone.utc)
    return swe.julday(
        utc.year, utc.month, utc.day,
        utc.hour + utc.minute / 60.0 + utc.second / 3600.0
        + utc.microsecond / 86400000000.0,
        swe.GREG_CAL,
    )


def _jd_to_datetime(jd: float) -> datetime:
    year, month, day, hour = swe.revjul(jd, swe.GREG_CAL)
    whole_hour = int(hour)
    minute_float = (hour - whole_hour) * 60.0
    minute = int(minute_float)
    second = min(59, int(round((minute_float - minute) * 60.0)))
    return datetime(year, month, day, whole_hour, minute, second, tzinfo=timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def lifetime_chapters(snapshot) -> list[dict]:
    """十二个展示章节；末章77—84岁实际结束于85岁生日。"""
    _ctx, birth, _zone = _context(snapshot)
    chapters = []
    for index, age_start in enumerate(CHAPTER_AGE_STARTS):
        age_end_exclusive = END_AGE_EXCLUSIVE if index == len(CHAPTER_AGE_STARTS) - 1 else age_start + 7
        start = _anniversary(birth, age_start)
        end = _anniversary(birth, age_end_exclusive)
        chapters.append({
            "index": index,
            "age_start": age_start,
            "age_end_inclusive": age_end_exclusive - 1,
            "label": f"{age_start}—{age_end_exclusive - 1}岁",
            "from_jd": _datetime_to_jd(start),
            "to_jd": _datetime_to_jd(end),
            "from_utc": _utc_text(start),
            "to_utc": _utc_text(end),
        })
    return chapters


def _age_fields(snapshot, jd: float) -> dict:
    _ctx, birth, zone = _context(snapshot)
    local = _jd_to_datetime(jd).astimezone(zone)
    age = local.year - birth.year
    if local < _anniversary(birth, age):
        age -= 1
    age = max(0, age)
    birthday = _anniversary(birth, age)
    next_birthday = _anniversary(birth, age + 1)
    fraction = (local - birthday).total_seconds() / max(
        1.0, (next_birthday - birthday).total_seconds()
    )
    return {
        "age": age,
        "age_decimal": round(age + max(0.0, min(1.0, fraction)), 3),
        "birth_timezone": zone.key,
    }


def _chapter_for_jd(chapters: list[dict], jd: float) -> int | None:
    for chapter in chapters:
        if chapter["from_jd"] <= jd < chapter["to_jd"]:
            return chapter["index"]
    return None


def lifetime_bounds(snapshot) -> dict:
    """0—84岁可查询区间的两端，供前端夹取用户输入的起止时间。"""
    chapters = lifetime_chapters(snapshot)
    _ctx, birth, zone = _context(snapshot)
    # 小程序 picker 的 start/end 只认 YYYY-MM-DD；带 T/Z 的 ISO 串会被忽略，
    # 约束就形同虚设。这里直接给出可用的日期串，前端不必再解析。
    start_local = _jd_to_datetime(chapters[0]["from_jd"]).astimezone(zone)
    end_local = _jd_to_datetime(chapters[-1]["to_jd"]).astimezone(zone)
    return {
        "from_jd": chapters[0]["from_jd"],
        "to_jd": chapters[-1]["to_jd"],
        "from_utc": chapters[0]["from_utc"],
        "to_utc": chapters[-1]["to_utc"],
        "from_date": start_local.date().isoformat(),
        "to_date": end_local.date().isoformat(),
        "birth_timezone": zone.key,
        "birth_local": birth.isoformat(),
        "max_range_years": MAX_RANGE_YEARS,
    }


def compute_range_events(
    snapshot,
    from_jd: float,
    to_jd: float,
    *,
    group: str | None = None,
    planet: str | None = None,
    target_scope: str = "all",
    natal_point: str | None = None,
    aspects=None,
) -> dict:
    """按用户指定的起止时间查询精确相位，不预算整个生命框架。

    这是终身板块的主查询入口：默认只算最近一年，老师可以自行输入任意区间。
    单次跨度上限 ``MAX_RANGE_YEARS`` 年，避免一次请求拖垮 2 核生产机。
    """
    if to_jd <= from_jd:
        raise ValueError("结束时间必须晚于开始时间")
    if to_jd - from_jd > MAX_RANGE_DAYS:
        raise ValueError(f"单次查询范围不能超过{MAX_RANGE_YEARS}年，请缩小时间段")
    if group is not None and group not in transit_natal.TRANSIT_GROUPS:
        raise ValueError("group 必须是 slow 或 fast")
    if planet:
        if planet not in transit_natal.BODY_IDS:
            raise ValueError("不支持的行运星")
        if group and planet not in transit_natal.TRANSIT_GROUPS[group]:
            raise ValueError("行运星不属于所选分组")
    if target_scope not in ("all", "axes", "points"):
        raise ValueError("target_scope 必须是 all、axes 或 points")
    all_points = [key for key in transit_natal.NATAL_POINT_ORDER if key != "south_node"]
    if target_scope == "axes":
        allowed_points = [key for key in all_points if key in transit_natal.AXES]
    elif target_scope == "points":
        allowed_points = [key for key in all_points if key not in transit_natal.AXES]
    else:
        allowed_points = all_points
    if natal_point and natal_point not in allowed_points:
        raise ValueError("本命目标不属于所选目标组")

    if planet:
        planets = (planet,)
    elif group:
        planets = transit_natal.TRANSIT_GROUPS[group]
    else:
        planets = tuple(transit_natal.BODY_IDS)
    selected_points = (natal_point,) if natal_point else allowed_points
    selected_aspects = tuple(aspects or transit_natal.ASPECT_ANGLES)
    if target_scope == "axes" and aspects and tuple(float(angle) for angle in aspects) != (0.0,):
        selected_aspects = (0.0,)
    axis_points = tuple(point for point in selected_points if point in transit_natal.AXES)
    ordinary_points = tuple(point for point in selected_points if point not in transit_natal.AXES)
    event_rows = []
    if axis_points:
        axis_result = transit_natal.compute_filtered_events(
            snapshot, from_jd, to_jd,
            planets=planets, natal_points=axis_points, aspects=(0.0,), max_days=None,
        )
        event_rows.extend(axis_result["events"])
    if ordinary_points:
        point_result = transit_natal.compute_filtered_events(
            snapshot, from_jd, to_jd,
            planets=planets, natal_points=ordinary_points,
            aspects=selected_aspects, max_days=None,
        )
        event_rows.extend(point_result["events"])
    event_rows.sort(key=lambda row: (
        row["exact_jd"], row["transit_planet"], row["natal_point"], row["angle"],
    ))
    chapters = lifetime_chapters(snapshot)
    for row in event_rows:
        row.update(_age_fields(snapshot, row["exact_jd"]))
        row["chapter_index"] = _chapter_for_jd(chapters, row["exact_jd"])
    return {
        "from_jd": round(from_jd, 6),
        "to_jd": round(to_jd, 6),
        "from_utc": _utc_text(_jd_to_datetime(from_jd)),
        "to_utc": _utc_text(_jd_to_datetime(to_jd)),
        "range_days": round(to_jd - from_jd, 3),
        "filters": {
            "group": group, "planet": planet, "target_scope": target_scope,
            "natal_point": natal_point, "aspects": list(selected_aspects),
        },
        "event_count": len(event_rows),
        "events": event_rows,
        "engine_version": COMPUTE_VERSION,
    }


def _summary_key(snapshot) -> tuple:
    natal = transit_natal._natal_longitudes(snapshot)
    ctx, _birth, zone = _context(snapshot)
    return (
        round(float(snapshot.birth_jd_ut), 6),
        str(ctx.civil_dt),
        zone.key,
        tuple((key, round(natal[key], 6)) for key in sorted(natal)),
        COMPUTE_VERSION,
    )


def compute_lifetime_summary(snapshot) -> dict:
    key = _summary_key(snapshot)
    with _SUMMARY_LOCK:
        cached = _SUMMARY_CACHE.get(key)
        if cached is not None:
            _SUMMARY_CACHE.move_to_end(key)
            result = deepcopy(cached)
            result["cache_hit"] = True
            return result

    chapters = lifetime_chapters(snapshot)
    result = transit_natal.compute_filtered_events(
        snapshot, chapters[0]["from_jd"], chapters[-1]["to_jd"], max_days=None,
    )
    rows = result["events"]
    summaries = []
    for chapter in chapters:
        chapter_rows = [
            row for row in rows
            if chapter["from_jd"] <= row["exact_jd"] < chapter["to_jd"]
        ]
        counts = {
            "total": len(chapter_rows),
            "slow": sum(row["group"] == "slow" for row in chapter_rows),
            "fast": sum(row["group"] == "fast" for row in chapter_rows),
            "axes": sum(row["natal_point"] in transit_natal.AXES for row in chapter_rows),
            "points": sum(row["natal_point"] not in transit_natal.AXES for row in chapter_rows),
        }
        counts["planets"] = {
            planet: sum(row["transit_planet"] == planet for row in chapter_rows)
            for planet in transit_natal.BODY_IDS
        }
        item = {key: value for key, value in chapter.items() if not key.endswith("_jd")}
        item["counts"] = counts
        summaries.append(item)
    payload = {
        "age_range": {"from": 0, "to_inclusive": MAX_AGE_INCLUSIVE, "ends_before_age": 85},
        "birth_timezone": _context(snapshot)[2].key,
        "chapter_count": len(summaries),
        "event_count": len(rows),
        "chapters": summaries,
        "groups": {
            key: {"label": transit_natal.GROUP_ZH[key], "planets": list(planets)}
            for key, planets in transit_natal.TRANSIT_GROUPS.items()
        },
        "targets": {
            "axes": [key for key in transit_natal.NATAL_POINT_ORDER if key in transit_natal.AXES],
            "points": [
                key for key in transit_natal.NATAL_POINT_ORDER
                if key not in transit_natal.AXES and key != "south_node"
            ],
        },
        "aspects": list(transit_natal.ASPECT_ANGLES),
        "engine_version": COMPUTE_VERSION,
        "cache_hit": False,
    }
    with _SUMMARY_LOCK:
        _SUMMARY_CACHE[key] = deepcopy(payload)
        _SUMMARY_CACHE.move_to_end(key)
        while len(_SUMMARY_CACHE) > _SUMMARY_CACHE_MAX:
            _SUMMARY_CACHE.popitem(last=False)
    return payload


def compute_lifetime_events(
    snapshot,
    chapter_index: int,
    *,
    group: str,
    planet: str | None = None,
    target_scope: str = "axes",
    natal_point: str | None = None,
    aspects=None,
) -> dict:
    chapters = lifetime_chapters(snapshot)
    if not 0 <= int(chapter_index) < len(chapters):
        raise ValueError("chapter_index 必须在 0..11")
    if group not in transit_natal.TRANSIT_GROUPS:
        raise ValueError("group 必须是 slow 或 fast")
    if planet and planet not in transit_natal.TRANSIT_GROUPS[group]:
        raise ValueError("行运星不属于所选分组")
    if group == "fast" and not planet:
        raise ValueError("木火明细必须先选择木星或火星")
    if target_scope not in ("axes", "points"):
        raise ValueError("target_scope 必须是 axes 或 points")
    allowed_points = [
        key for key in transit_natal.NATAL_POINT_ORDER
        if (key in transit_natal.AXES) == (target_scope == "axes") and key != "south_node"
    ]
    if natal_point and natal_point not in allowed_points:
        raise ValueError("本命目标不属于所选目标组")
    if group == "fast" and not natal_point:
        raise ValueError("木火明细必须先选择本命目标")

    chapter = chapters[int(chapter_index)]
    selected_aspects = (0.0,) if target_scope == "axes" else tuple(aspects or transit_natal.ASPECT_ANGLES)
    result = transit_natal.compute_filtered_events(
        snapshot,
        chapter["from_jd"], chapter["to_jd"],
        planets=(planet,) if planet else transit_natal.TRANSIT_GROUPS[group],
        natal_points=(natal_point,) if natal_point else allowed_points,
        aspects=selected_aspects,
        max_days=None,
    )
    for row in result["events"]:
        row.update(_age_fields(snapshot, row["exact_jd"]))
        row["chapter_index"] = int(chapter_index)
    return {
        "chapter": {key: value for key, value in chapter.items() if not key.endswith("_jd")},
        "filters": {
            "group": group, "planet": planet, "target_scope": target_scope,
            "natal_point": natal_point, "aspects": list(selected_aspects),
        },
        "event_count": len(result["events"]),
        "events": result["events"],
        "engine_version": COMPUTE_VERSION,
    }


def _house_for_longitude(longitude: float, cusps) -> int:
    lon = float(longitude) % 360.0
    normalized = [float(value) % 360.0 for value in cusps[:12]]
    if len(normalized) != 12:
        raise ValueError("普拉西度宫头必须恰好有12个")
    for index, start in enumerate(normalized):
        end = normalized[(index + 1) % 12]
        span = (end - start) % 360.0
        offset = (lon - start) % 360.0
        if offset < span or abs(offset - span) < 1e-9 and index == 11:
            return index + 1
    raise ValueError("普拉西度宫头顺序无效，无法定位宫位")


def _assign_ingress_series(rows: list[dict]) -> None:
    buckets = {}
    for row in rows:
        buckets.setdefault((row["transit_planet"], row["cusp"]), []).append(row)
    for key, contacts in buckets.items():
        contacts.sort(key=lambda row: row["exact_jd"])
        cluster = []
        clusters = []
        for row in contacts:
            if cluster and row["exact_jd"] - cluster[0]["exact_jd"] > transit_natal.SERIES_WINDOW_DAYS:
                clusters.append(cluster)
                cluster = []
            cluster.append(row)
        if cluster:
            clusters.append(cluster)
        for group in clusters:
            series_id = "%s:cusp%d:%.6f" % (key[0], key[1], group[0]["exact_jd"])
            for index, row in enumerate(group, 1):
                row["series_id"] = series_id
                row["contact_index"] = index
                row["contact_total"] = len(group)


def _collapse_ingress_rings(rows: list[dict]) -> list[dict]:
    """过宫沿用统一的接触环折叠口径，只把角色文案换成进入语义。"""
    kept = transit_natal.collapse_contact_rings(rows)
    for row in kept:
        row["entry_role_zh"] = {
            "only": "单次进入", "first": "首次进入", "final": "最终进入",
        }[row["entry_role"]]
    return kept


def compute_house_ingresses(snapshot, *, planet: str | None = None, house: int | None = None) -> dict:
    """土星/木星跨越固定本命宫头后的进入区间，仅使用 Placidus 宫头。"""
    if planet and planet not in HOUSE_BODIES:
        raise ValueError("过宫时间表只支持土星或木星")
    if house is not None and not 1 <= int(house) <= 12:
        raise ValueError("house 必须在 1..12")
    chapters = lifetime_chapters(snapshot)
    lo_jd, hi_jd = chapters[0]["from_jd"], chapters[-1]["to_jd"]
    cusps = tuple(float(value) % 360.0 for value in snapshot.cusps[:12])
    if len(cusps) != 12:
        raise ValueError("本命快照缺少十二个普拉西度宫头")
    fixed = {f"cusp_{index}": value for index, value in enumerate(cusps, 1)}
    bodies = (planet,) if planet else tuple(HOUSE_BODIES)
    all_rows = []
    # 多扫十二年只用于给寿限末端最后一次进入补齐离开时刻。高纬度 Placidus
    # 宫距可能远大于30°，土星跨到下一宫头不应假定只需常见的约2.5年。
    # 输出仍严格止于85岁生日。
    scan_lo = lo_jd - transit_natal.SERIES_WINDOW_DAYS
    scan_hi = hi_jd + 4384.0
    for body_name in bodies:
        hits = transit_utils.all_exact_to_fixed_in_window(
            HOUSE_BODIES[body_name], fixed, (0.0,), scan_lo, scan_hi,
        )
        body_rows = []
        for exact_jd, cusp_key, _angle in hits:
            cusp_number = int(str(cusp_key).split("_")[1])
            _lon, speed = transit_utils.body_position(HOUSE_BODIES[body_name], exact_jd)
            direct = speed >= 0.0
            entered_house = cusp_number if direct else (12 if cusp_number == 1 else cusp_number - 1)
            left_house = (12 if cusp_number == 1 else cusp_number - 1) if direct else cusp_number
            body_rows.append({
                "transit_planet": body_name,
                "transit_planet_zh": transit_natal.PLANET_ZH[body_name],
                "cusp": cusp_number,
                "entered_house": entered_house,
                "entered_house_zh": HOUSE_ZH[entered_house],
                "left_house": left_house,
                "left_house_zh": HOUSE_ZH[left_house],
                "exact_jd": exact_jd,
                "exact_utc": transit_natal._jd_to_utc(exact_jd),
                "direction": "direct" if direct else "retrograde",
                "direction_zh": "顺行" if direct else "逆行",
                "entry_type_zh": "顺行进入" if direct else "逆行返回",
            })
        body_rows.sort(key=lambda row: row["exact_jd"])
        for index, row in enumerate(body_rows):
            next_row = body_rows[index + 1] if index + 1 < len(body_rows) else None
            leave_jd = next_row["exact_jd"] if next_row else None
            row["leave_jd"] = leave_jd
            row["leave_utc"] = transit_natal._jd_to_utc(leave_jd) if leave_jd else None
            row["duration_days"] = round(leave_jd - row["exact_jd"], 3) if leave_jd else None
        all_rows.extend(body_rows)

    all_rows.sort(key=lambda row: (row["exact_jd"], row["transit_planet"]))
    # 与相位事件相同：先在扩展窗内建立完整逆行接触环，再裁寿限输出，避免出生
    # 或85岁边界把“第2/3次”错误显示成“第1/1次”。
    _assign_ingress_series(all_rows)
    all_rows = _collapse_ingress_rings(all_rows)
    filtered = []
    for row in all_rows:
        if not lo_jd <= row["exact_jd"] < hi_jd:
            continue
        if house is not None and row["entered_house"] != int(house):
            continue
        row.update(_age_fields(snapshot, row["exact_jd"]))
        row["chapter_index"] = _chapter_for_jd(chapters, row["exact_jd"])
        row["exact_jd"] = round(row["exact_jd"], 6)
        if row["leave_jd"] is not None:
            row["leave_jd"] = round(row["leave_jd"], 6)
        filtered.append(row)
    return {
        "house_system": HOUSE_SYSTEM,
        "age_range": {"from": 0, "to_inclusive": MAX_AGE_INCLUSIVE, "ends_before_age": 85},
        "filters": {"planet": planet, "house": int(house) if house is not None else None},
        "event_count": len(filtered),
        "events": filtered,
        "engine_version": COMPUTE_VERSION,
    }
