"""法达（Firdaria）与年小限（Annual Profections）计算服务。

生产实现只包含传统周期常数、日期算术和项目已有的本命计算链，不依赖
Stellium/Astrologica。第三方库只在测试中作为开发期对拍基准。

口径：
- 法达默认 Abu Ma'shar / Al-Biruni：昼夜序列、交点置末，行星主限七等分，
  交点不分次限，回归年 365.2425 日，75 年后循环。
- 年小限以出生地当地生日日期切换，0 岁为本命第一宫，逐年推进一宫；
  整宫制取对应整宫星座守护星，普拉西度取本命同序号宫头星座守护星；
  2 月 29 日出生者在平年按 2 月 28 日切换。

内部区间一律半开 ``start <= t < end``；面向表格的 ``end_date`` 是下一段
开始日期减一天，避免同一日期显示在相邻两行。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.8 compatibility
    from backports.zoneinfo import ZoneInfo  # type: ignore


ENGINE_VERSION = "time-lords-2"
FIRDARIA_YEAR_DAYS = 365.2425

PLANETS: Dict[str, Dict[str, str]] = {
    "sun": {"key": "sun", "name": "Sun", "name_zh": "太阳", "glyph": "☉"},
    "moon": {"key": "moon", "name": "Moon", "name_zh": "月亮", "glyph": "☽"},
    "mercury": {"key": "mercury", "name": "Mercury", "name_zh": "水星", "glyph": "☿"},
    "venus": {"key": "venus", "name": "Venus", "name_zh": "金星", "glyph": "♀"},
    "mars": {"key": "mars", "name": "Mars", "name_zh": "火星", "glyph": "♂"},
    "jupiter": {"key": "jupiter", "name": "Jupiter", "name_zh": "木星", "glyph": "♃"},
    "saturn": {"key": "saturn", "name": "Saturn", "name_zh": "土星", "glyph": "♄"},
    "north_node": {"key": "north_node", "name": "North Node", "name_zh": "北交点", "glyph": "☊"},
    "south_node": {"key": "south_node", "name": "South Node", "name_zh": "南交点", "glyph": "☋"},
}

SIGNS: Tuple[Dict[str, str], ...] = (
    {"key": "aries", "name": "Aries", "name_zh": "白羊座", "glyph": "♈"},
    {"key": "taurus", "name": "Taurus", "name_zh": "金牛座", "glyph": "♉"},
    {"key": "gemini", "name": "Gemini", "name_zh": "双子座", "glyph": "♊"},
    {"key": "cancer", "name": "Cancer", "name_zh": "巨蟹座", "glyph": "♋"},
    {"key": "leo", "name": "Leo", "name_zh": "狮子座", "glyph": "♌"},
    {"key": "virgo", "name": "Virgo", "name_zh": "处女座", "glyph": "♍"},
    {"key": "libra", "name": "Libra", "name_zh": "天秤座", "glyph": "♎"},
    {"key": "scorpio", "name": "Scorpio", "name_zh": "天蝎座", "glyph": "♏"},
    {"key": "sagittarius", "name": "Sagittarius", "name_zh": "射手座", "glyph": "♐"},
    {"key": "capricorn", "name": "Capricorn", "name_zh": "摩羯座", "glyph": "♑"},
    {"key": "aquarius", "name": "Aquarius", "name_zh": "水瓶座", "glyph": "♒"},
    {"key": "pisces", "name": "Pisces", "name_zh": "双鱼座", "glyph": "♓"},
)

TRADITIONAL_RULERS: Tuple[str, ...] = (
    "mars", "venus", "mercury", "moon", "sun", "mercury",
    "venus", "mars", "jupiter", "saturn", "saturn", "jupiter",
)

FIRDARIA_YEARS: Dict[str, int] = {
    "sun": 10,
    "venus": 8,
    "mercury": 13,
    "moon": 9,
    "saturn": 11,
    "jupiter": 12,
    "mars": 7,
    "north_node": 3,
    "south_node": 2,
}

DAY_SEQUENCE: Tuple[str, ...] = (
    "sun", "venus", "mercury", "moon", "saturn", "jupiter", "mars",
    "north_node", "south_node",
)
NIGHT_SEQUENCE: Tuple[str, ...] = (
    "moon", "saturn", "jupiter", "mars", "sun", "venus", "mercury",
    "north_node", "south_node",
)
BONATTI_NIGHT_SEQUENCE: Tuple[str, ...] = (
    "moon", "saturn", "jupiter", "mars", "north_node", "south_node",
    "sun", "venus", "mercury",
)
CHALDEAN_ORDER: Tuple[str, ...] = (
    "saturn", "jupiter", "mars", "sun", "venus", "mercury", "moon",
)
NODES = frozenset(("north_node", "south_node"))


@dataclass(frozen=True)
class TimeLordBirthContext:
    name: str
    birth_local: datetime
    birth_utc: datetime
    timezone_name: str
    sect: str
    is_diurnal: bool
    asc_lon: float
    placidus_cusps: Tuple[float, ...]


def _planet(key: str) -> Dict[str, str]:
    return dict(PLANETS[key])


def _sign(index: int) -> Dict[str, str]:
    return dict(SIGNS[index % 12])


def _local_iso(value_utc: datetime, zone: ZoneInfo) -> str:
    return value_utc.astimezone(zone).isoformat(timespec="seconds")


def _display_end_date(exclusive_end_local: datetime) -> str:
    return (exclusive_end_local.date() - timedelta(days=1)).isoformat()


def _utc_date(value: datetime) -> str:
    return value.astimezone(timezone.utc).date().isoformat()


def _utc_display_end_date(exclusive_end: datetime) -> str:
    return (exclusive_end.astimezone(timezone.utc).date() - timedelta(days=1)).isoformat()


def _firdaria_sequence(is_diurnal: bool, tradition: str) -> Sequence[str]:
    normalized = str(tradition or "abu_mashar").strip().lower()
    if normalized not in ("abu_mashar", "al_biruni", "bonatti"):
        raise ValueError("tradition must be abu_mashar, al_biruni, or bonatti")
    if is_diurnal:
        return DAY_SEQUENCE
    if normalized == "bonatti":
        return BONATTI_NIGHT_SEQUENCE
    return NIGHT_SEQUENCE


def _subperiod_order(major_ruler: str) -> Tuple[str, ...]:
    start = CHALDEAN_ORDER.index(major_ruler)
    return tuple(CHALDEAN_ORDER[(start + offset) % 7] for offset in range(7))


def calculate_firdaria(
    birth_utc: datetime,
    timezone_name: str,
    is_diurnal: bool,
    *,
    max_age: float = 100.0,
    tradition: str = "abu_mashar",
    year_length_days: float = FIRDARIA_YEAR_DAYS,
    now: Optional[datetime] = None,
) -> Dict[str, object]:
    """Return Firdaria major periods and flattened table rows."""
    if birth_utc.tzinfo is None:
        raise ValueError("birth_utc must be timezone-aware")
    if max_age <= 0 or max_age > 150:
        raise ValueError("max_age must be between 0 and 150")
    if year_length_days <= 0:
        raise ValueError("year_length_days must be positive")

    birth_utc = birth_utc.astimezone(timezone.utc)
    zone = ZoneInfo(timezone_name)
    now_utc = (now or datetime.now(timezone.utc))
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)

    normalized_tradition = str(tradition or "abu_mashar").strip().lower()
    sequence = _firdaria_sequence(is_diurnal, normalized_tradition)
    major_periods: List[Dict[str, object]] = []
    rows: List[Dict[str, object]] = []
    age = 0.0
    cursor = 0

    while age < max_age:
        ruler = sequence[cursor % len(sequence)]
        years = float(FIRDARIA_YEARS[ruler])
        start_age = age
        end_age = age + years
        start_utc = birth_utc + timedelta(days=start_age * year_length_days)
        end_utc = birth_utc + timedelta(days=end_age * year_length_days)
        start_local = start_utc.astimezone(zone)
        end_local = end_utc.astimezone(zone)
        major_current = start_utc <= now_utc < end_utc
        major_periods.append({
            "ruler": _planet(ruler),
            "start_age": round(start_age, 9),
            "end_age": round(end_age, 9),
            "start_at": _local_iso(start_utc, zone),
            "end_at": _local_iso(end_utc, zone),
            "start_date": start_local.date().isoformat(),
            "end_date": _display_end_date(end_local),
            "start_date_utc": _utc_date(start_utc),
            "end_date_utc": _utc_display_end_date(end_utc),
            "is_current": major_current,
        })

        if ruler in NODES:
            rows.append({
                "major_lord": _planet(ruler),
                "minor_lord": None,
                "start_age": round(start_age, 9),
                "end_age": round(end_age, 9),
                "start_at": _local_iso(start_utc, zone),
                "end_at": _local_iso(end_utc, zone),
                "start_date": start_local.date().isoformat(),
                "end_date": _display_end_date(end_local),
                "start_date_utc": _utc_date(start_utc),
                "end_date_utc": _utc_display_end_date(end_utc),
                "is_current": major_current,
            })
        else:
            sub_length = years / 7.0
            for sub_index, sub_ruler in enumerate(_subperiod_order(ruler)):
                sub_start_age = start_age + sub_index * sub_length
                sub_end_age = (
                    end_age
                    if sub_index == 6
                    else start_age + (sub_index + 1) * sub_length
                )
                sub_start_utc = birth_utc + timedelta(days=sub_start_age * year_length_days)
                sub_end_utc = birth_utc + timedelta(days=sub_end_age * year_length_days)
                sub_start_local = sub_start_utc.astimezone(zone)
                sub_end_local = sub_end_utc.astimezone(zone)
                rows.append({
                    "major_lord": _planet(ruler),
                    "minor_lord": _planet(sub_ruler),
                    "start_age": round(sub_start_age, 9),
                    "end_age": round(sub_end_age, 9),
                    "start_at": _local_iso(sub_start_utc, zone),
                    "end_at": _local_iso(sub_end_utc, zone),
                    "start_date": sub_start_local.date().isoformat(),
                    "end_date": _display_end_date(sub_end_local),
                    "start_date_utc": _utc_date(sub_start_utc),
                    "end_date_utc": _utc_display_end_date(sub_end_utc),
                    "is_current": sub_start_utc <= now_utc < sub_end_utc,
                })

        age = end_age
        cursor += 1

    current_row = next((row for row in rows if row["is_current"]), None)
    return {
        "tradition": "bonatti" if normalized_tradition == "bonatti" else "abu_mashar",
        "sect": "day" if is_diurnal else "night",
        "year_length_days": year_length_days,
        "repeat_after_years": 75,
        "display_timezone": timezone_name,
        "interval_semantics": "start_inclusive_end_exclusive",
        "major_periods": major_periods,
        "rows": rows,
        "current": current_row,
    }


def _anniversary_date(birth_date: date, target_year: int) -> date:
    try:
        return birth_date.replace(year=target_year)
    except ValueError:
        # 2 月 29 日出生者：与 dateutil.relativedelta 的常用行为一致，平年落 2 月 28 日。
        return date(target_year, 2, 28)


def calculate_annual_profections(
    asc_lon: float,
    birth_local: datetime,
    *,
    placidus_cusps: Optional[Sequence[float]] = None,
    max_age: int = 100,
    now: Optional[datetime] = None,
) -> Dict[str, object]:
    """Return annual profections under Whole Sign and Placidus rulerships.

    The activated house number is age-based in both systems. Whole Sign uses the
    sign counted from the Ascendant; Placidus uses the sign on the natal cusp of
    that same numbered house. This preserves intercepted/duplicated signs in the
    Placidus result instead of projecting the profected degree into a house.
    """
    if birth_local.tzinfo is None:
        raise ValueError("birth_local must be timezone-aware")
    if max_age < 1 or max_age > 150:
        raise ValueError("max_age must be between 1 and 150")

    zone = birth_local.tzinfo
    local_now = now or datetime.now(timezone.utc)
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=zone)
    local_now = local_now.astimezone(zone)
    today = local_now.date()
    birth_date = birth_local.date()
    natal_sign_index = int(float(asc_lon) % 360 // 30)
    normalized_cusps = tuple(float(value) % 360 for value in (placidus_cusps or ()))
    if normalized_cusps and len(normalized_cusps) != 12:
        raise ValueError("placidus_cusps must contain 12 house cusps")
    rows: List[Dict[str, object]] = []

    for age in range(max_age):
        start_date = _anniversary_date(birth_date, birth_date.year + age)
        next_date = _anniversary_date(birth_date, birth_date.year + age + 1)
        sign_index = (natal_sign_index + age) % 12
        profected_longitude = (float(asc_lon) + age * 30.0) % 360.0
        activated_house = age % 12 + 1
        whole_sign_ruler = TRADITIONAL_RULERS[sign_index]
        placidus_sign_index = (
            int(normalized_cusps[activated_house - 1] // 30)
            if normalized_cusps else sign_index
        )
        placidus_ruler = TRADITIONAL_RULERS[placidus_sign_index]
        whole_sign_result = {
            "house": activated_house,
            "sign": _sign(sign_index),
            "lord": _planet(whole_sign_ruler),
        }
        placidus_result = {
            "house": activated_house,
            "sign": _sign(placidus_sign_index),
            "lord": _planet(placidus_ruler),
        }
        start_at = datetime.combine(start_date, time.min, tzinfo=zone)
        end_at = datetime.combine(next_date, time.min, tzinfo=zone)
        rows.append({
            "age": age,
            "activated_house": activated_house,
            "profected_longitude": round(profected_longitude, 6),
            "houses": {
                "placidus": activated_house,
                "whole_sign": activated_house,
            },
            "systems": {
                "placidus": placidus_result,
                "whole_sign": whole_sign_result,
            },
            # Legacy Whole Sign fields remain for older API consumers.
            "profected_sign": _sign(sign_index),
            "lord_of_year": _planet(whole_sign_ruler),
            "start_at": start_at.isoformat(timespec="seconds"),
            "end_at": end_at.isoformat(timespec="seconds"),
            "start_date": start_date.isoformat(),
            "end_date": (next_date - timedelta(days=1)).isoformat(),
            "is_current": start_date <= today < next_date,
        })

    return {
        "natal_ascendant": {
            "longitude": round(float(asc_lon) % 360, 6),
            "sign": _sign(natal_sign_index),
        },
        "boundary": "local_birthday_date",
        "leap_day_policy": "february_28_in_non_leap_years",
        "interval_semantics": "start_inclusive_end_exclusive",
        "rows": rows,
        "current": next((row for row in rows if row["is_current"]), None),
    }


def resolve_time_lord_birth_context(user_data: Dict[str, object]) -> TimeLordBirthContext:
    """Resolve one authoritative birth instant and derive sect/Ascendant from it."""
    from hellenistic import is_diurnal
    from services.calculator import BirthContextError
    from services.civil_time_resolver import CivilTimeResolver, ResolutionStatus
    from services.engine_adapter import calc_from_context
    from services.location_resolver import LocationResolver

    name = str(user_data.get("name") or "")
    year = int(user_data["year"])
    month = int(user_data["month"])
    day = int(user_data["day"])
    hour = int(user_data["hour"])
    minute = int(user_data["minute"])
    city = str(user_data.get("city") or "").strip()
    location_id = str(user_data.get("location_id") or "").strip() or None
    lat = user_data.get("lat")
    lng = user_data.get("lng")

    snapshot = LocationResolver().resolve(
        location_id=location_id,
        lat=float(lat) if lat is not None else None,
        lng=float(lng) if lng is not None else None,
        query=city,
    )
    if snapshot is None:
        raise ValueError(
            f"无法解析地点「{city or location_id or ''}」的坐标/时区，请从下拉列表选择城市后重试。"
        )

    resolution = CivilTimeResolver().resolve(
        snapshot, year, month, day, hour, minute, fold=user_data.get("fold")
    )
    if resolution.context is None or resolution.status not in (
        ResolutionStatus.NORMAL, ResolutionStatus.AMBIGUOUS
    ):
        raise BirthContextError(
            resolution.status.value, resolution.message, resolution.candidates
        )
    ctx = resolution.context
    chart = calc_from_context(
        ctx,
        name=name,
        city=city,
        country_code=snapshot.country_code or "CN",
    )
    asc_lon = float(chart["houses"]["cusps"][0])
    placidus_cusps = tuple(float(value) for value in chart["houses"]["cusps"][:12])
    sun_lon = float(chart["planets"]["sun"]["longitude"])
    day_chart = is_diurnal(sun_lon, asc_lon)
    zone = ZoneInfo(snapshot.tz_iana)
    birth_utc = datetime.fromisoformat(ctx.utc_datetime.replace("Z", "+00:00"))
    birth_local = birth_utc.astimezone(zone)
    return TimeLordBirthContext(
        name=name,
        birth_local=birth_local,
        birth_utc=birth_utc,
        timezone_name=snapshot.tz_iana,
        sect="日生人" if day_chart else "夜生人",
        is_diurnal=day_chart,
        asc_lon=asc_lon,
        placidus_cusps=placidus_cusps,
    )


def calculate_firdaria_report(
    user_data: Dict[str, object],
    *,
    max_age: float = 100.0,
    tradition: str = "abu_mashar",
    now: Optional[datetime] = None,
) -> Dict[str, object]:
    context = resolve_time_lord_birth_context(user_data)
    return {
        "success": True,
        "engine_version": ENGINE_VERSION,
        "name": context.name,
        "birth": _birth_payload(context),
        "firdaria": calculate_firdaria(
            context.birth_utc,
            context.timezone_name,
            context.is_diurnal,
            max_age=max_age,
            tradition=tradition,
            now=now,
        ),
    }


def calculate_annual_profections_report(
    user_data: Dict[str, object],
    *,
    max_age: int = 100,
    now: Optional[datetime] = None,
) -> Dict[str, object]:
    context = resolve_time_lord_birth_context(user_data)
    return {
        "success": True,
        "engine_version": ENGINE_VERSION,
        "name": context.name,
        "birth": _birth_payload(context),
        "annual_profections": calculate_annual_profections(
            context.asc_lon,
            context.birth_local,
            placidus_cusps=context.placidus_cusps,
            max_age=max_age,
            now=now,
        ),
    }


def _birth_payload(context: TimeLordBirthContext) -> Dict[str, object]:
    return {
        "local_datetime": context.birth_local.isoformat(timespec="seconds"),
        "utc_datetime": context.birth_utc.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "timezone": context.timezone_name,
        "sect": context.sect,
        "asc_lon": round(context.asc_lon % 360, 6),
    }
