"""Deterministic, data-only synthesis of existing timing calculations.

The caller supplies the already validated natal result and birth input. This
module does not change any Mini Program route or any existing MCP tool.
Intervals are half-open; all displayed dates use the birth-place time zone.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from zoneinfo import ZoneInfo

import swisseph as swe

from services.ephemeris_guard import apply_ephe_path, EXPECTED_SHA256
from services.solar_arc_engine import MAX_SUPPORTED_AGE, TROPICAL_YEAR_DAYS


ENGINE_VERSION = "timeline-synthesis-2"
MAX_SPAN_YEARS = 3
SECONDARY_SCAN_DAYS = 7  # civil days for planets other than the Moon
SECONDARY_MOON_SCAN_DAYS = 1  # resolves a short exit and re-entry within a week
SECONDARY_ROOT_TOLERANCE_DAYS = 1 / 1440  # one civil minute
RESONANCE_WINDOW_DAYS = 30
TECHNIQUE_PRIORITY = {
    "firdaria": 0,
    "zodiacal_releasing": 1,
    "secondary_progressions": 2,
    "transits": 3,
}
NATURES = frozenset({"period_start", "period_active", "peak_start", "sign_ingress",
                     "exact_aspect", "axis_contact"})
WEIGHTS = frozenset({"context", "marker", "exact"})
_SECONDARY_ASPECTS = (0, 90, 180)  # subset of existing progression aspect angles
_TRANSIT_PLANETS = ("jupiter", "saturn", "uranus", "neptune", "pluto")
_AXES = ("asc", "mc", "dsc", "ic")


def _utc_from_jd(jd: float) -> datetime:
    year, month, day, hour = swe.revjul(jd, swe.GREG_CAL)
    return datetime(year, month, day, tzinfo=timezone.utc) + timedelta(hours=hour)


def _jd_from_utc(moment: datetime) -> float:
    value = moment.astimezone(timezone.utc)
    return swe.julday(value.year, value.month, value.day,
                      value.hour + value.minute / 60 + value.second / 3600
                      + value.microsecond / 3_600_000_000)


def _moment(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("事件时间必须带时区")
    return value


def _event(technique: str, nature: str, weight: str, when: datetime,
           zone: ZoneInfo, focus: str, source: dict) -> dict:
    utc = when.astimezone(timezone.utc)
    local = utc.astimezone(zone)
    return {
        "technique": technique,
        "nature": nature,
        "weight": weight,
        "date": local.date().isoformat(),
        "exact_utc": utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "local_at": local.isoformat(timespec="seconds"),
        "time_precision": "minute" if technique == "secondary_progressions" else "second",
        "focus": focus,
        "source": source,
    }


def _sort_key(row: dict) -> tuple:
    source = row["source"]
    return (row["exact_utc"], TECHNIQUE_PRIORITY[row["technique"]],
            source.get("planet", ""), source.get("target", ""), row["nature"],
            row["focus"], source.get("lot", ""), source.get("level", 0))


def _append_periods(events: list, natal: dict, birth: dict, start: datetime,
                    end: datetime, zone: ZoneInfo) -> None:
    from services.time_lords import calculate_firdaria
    from services import zodiacal_releasing as zr

    birth_local = datetime(birth["year"], birth["month"], birth["day"],
                           birth["hour"], birth["minute"], tzinfo=zone,
                           fold=natal["birth_context"].get("fold") or 0)
    birth_utc = birth_local.astimezone(timezone.utc)
    is_day = natal["sect"] == "日生人"
    firdaria = calculate_firdaria(birth_utc, zone.key, is_day,
                                  max_age=120, now=start)
    for major in firdaria["major_periods"]:
        opened = _moment(major["start_at"])
        closed = _moment(major["end_at"])
        if opened < end and closed > start:
            at = max(start, opened)
            ruler = major["ruler"]["key"]
            events.append(_event("firdaria", "period_start" if opened >= start else "period_active",
                                 "context", at, zone, f"planet:{ruler}",
                                 {"level": "major", "planet": ruler,
                                  "start_utc": opened.astimezone(timezone.utc).isoformat(),
                                  "end_utc": closed.astimezone(timezone.utc).isoformat()}))
    for row in firdaria["rows"]:
        if row["minor_lord"] is None:
            continue
        opened = _moment(row["start_at"])
        closed = _moment(row["end_at"])
        if opened < end and closed > start:
            at = max(start, opened)
            ruler = row["minor_lord"]["key"]
            events.append(_event("firdaria", "period_start" if opened >= start else "period_active",
                                 "context", at, zone, f"planet:{ruler}",
                                 {"level": "minor", "planet": ruler,
                                  "major_lord": row["major_lord"]["key"],
                                  "start_utc": opened.astimezone(timezone.utc).isoformat(),
                                  "end_utc": closed.astimezone(timezone.utc).isoformat()}))

    # The public ZR tree formats boundaries as YYYY-MM-DD. Use its same period
    # engine here so distinct events on one date retain their true order.
    fortune_sign = zr._Sign(int(float(natal["fof_lon"]) % 360 // 30))
    spirit_shifted = zr._spirit_needs_shift(natal["fof_lon"], natal["pos_lon"])
    horizon = birth_local + timedelta(days=zr.LIFESPAN_AGE_YEARS * zr._CIVIL_YEAR_DAYS)
    for lot_key, longitude in (("fortune", natal["fof_lon"]), ("spirit", natal["pos_lon"])):
        periods = zr._compute_releasing(
            longitude, birth_local, max_level=2, year_length_days=360.0,
            capricorn_years=27, end=horizon, fortune_sign=fortune_sign,
            shift_start=spirit_shifted and lot_key == "spirit")
        for period in periods:
            opened, closed = period.start, period.end
            if opened >= end or closed <= start:
                continue
            at = max(start, opened)
            nature = "peak_start" if opened >= start and period.peak else (
                "period_start" if opened >= start else "period_active")
            events.append(_event("zodiacal_releasing", nature,
                                 "marker" if period.peak or period.is_lb else "context",
                                 at, zone, f"sign:{period.sign.name.lower()}",
                                 {"lot": lot_key, "level": period.level,
                                  "sign": period.sign.name, "peak": period.peak,
                                  "loosing_of_bond": period.is_lb,
                                  "start_utc": opened.astimezone(timezone.utc).isoformat(),
                                  "end_utc": closed.astimezone(timezone.utc).isoformat()}))


def _secondary_events(events: list, snapshot, start: datetime, end: datetime,
                      zone: ZoneInfo) -> None:
    """Find exact progressed sign and hard-aspect crossings on a bounded grid.

    The longitude source and day-for-a-year scale are the existing secondary
    progressions engine. The Moon uses a one-day civil grid, other planets a
    seven-day grid; bisection resolves crossings to one civil minute. Tangencies
    without a sign change inside one grid interval remain outside this MVP.
    """
    from services.secondary_progressions import PLANET_DEFS
    from services import transit_natal

    apply_ephe_path()
    birth_jd = snapshot.birth_jd_ut
    lo = _jd_from_utc(start)
    hi = _jd_from_utc(end)
    if lo < birth_jd or (hi - birth_jd) / TROPICAL_YEAR_DAYS > MAX_SUPPORTED_AGE:
        raise ValueError("时间线需在出生后 120 年内")
    natal_targets = {key: point.longitude for key, point in snapshot.planets.items()
                     if key in {name for name, _ in PLANET_DEFS}}
    natal_targets.update(snapshot.axes)
    prog_lo = birth_jd + (lo - birth_jd) / TROPICAL_YEAR_DAYS
    prog_hi = birth_jd + (hi - birth_jd) / TROPICAL_YEAR_DAYS

    def position(body_id: int, jd: float) -> float:
        values, flags = swe.calc_ut(jd, body_id, swe.FLG_SWIEPH)
        if not flags & swe.FLG_SWIEPH or flags & swe.FLG_MOSEPH:
            raise ValueError("次限扫描未使用 Swiss 星历文件")
        return values[0] % 360.0

    def signed(lon: float, target: float) -> float:
        return (lon - target + 180) % 360 - 180

    def roots(body_id: int, target: float, jd_a: float, jd_b: float):
        a, b = jd_a, jd_b
        fa = signed(position(body_id, a), target)
        fb = signed(position(body_id, b), target)
        if fa * fb > 0 or abs(fa - fb) >= 180:
            return None
        for _ in range(32):
            if (b - a) * TROPICAL_YEAR_DAYS <= SECONDARY_ROOT_TOLERANCE_DAYS:
                break
            mid = (a + b) / 2
            fm = signed(position(body_id, mid), target)
            if fa * fm <= 0:
                b, fb = mid, fm
            else:
                a, fa = mid, fm
        return (a + b) / 2

    for planet, body_id in PLANET_DEFS:
        step = (SECONDARY_MOON_SCAN_DAYS if planet == "moon"
                else SECONDARY_SCAN_DAYS) / TROPICAL_YEAR_DAYS
        prior_jd = prog_lo
        prior_lon = position(body_id, prior_jd)
        seen = set()
        while prior_jd < prog_hi:
            next_jd = min(prior_jd + step, prog_hi)
            next_lon = position(body_id, next_jd)
            targets = []
            if planet == "moon":
                for index in range(12):
                    targets.append((index * 30.0, "sign_ingress", "", 0))
            for natal_key, natal_lon in natal_targets.items():
                for angle in _SECONDARY_ASPECTS:
                    for direction in (1, -1) if angle == 90 else (1,):
                        targets.append(((natal_lon + direction * angle) % 360,
                                        "exact_aspect", natal_key, angle))
            for target_lon, nature, natal_key, angle in targets:
                if signed(prior_lon, target_lon) * signed(next_lon, target_lon) > 0:
                    continue
                root = roots(body_id, target_lon, prior_jd, next_jd)
                if root is None:
                    continue
                key = (nature, natal_key, angle, round(root, 5))
                if key in seen:
                    continue
                seen.add(key)
                civil_jd = birth_jd + (root - birth_jd) * TROPICAL_YEAR_DAYS
                at = _utc_from_jd(civil_jd)
                if not start <= at.astimezone(zone) < end:
                    continue
                if nature == "sign_ingress":
                    # Use the future side to disambiguate retrograde boundary exits.
                    sign = int(position(body_id, min(root + 1e-5, prog_hi)) // 30)
                    focus = f"sign:{('aries','taurus','gemini','cancer','leo','virgo','libra','scorpio','sagittarius','capricorn','aquarius','pisces')[sign]}"
                    source = {"planet": planet, "sign_index": sign, "longitude": round(target_lon, 6)}
                else:
                    focus = f"axis:{natal_key}" if natal_key in transit_natal.AXES else f"planet:{natal_key}"
                    source = {"planet": planet, "target": natal_key, "angle": angle,
                              "longitude": round(target_lon, 6)}
                events.append(_event("secondary_progressions", nature, "exact",
                                     at, zone, focus, source))
            prior_jd, prior_lon = next_jd, next_lon


def _transit_events(events: list, snapshot, start: datetime, end: datetime,
                    zone: ZoneInfo) -> None:
    from services.transit_natal import compute_filtered_events
    data = compute_filtered_events(snapshot, _jd_from_utc(start), _jd_from_utc(end),
                                   planets=_TRANSIT_PLANETS, natal_points=_AXES,
                                   aspects=(0.0,), max_days=None,
                                   collapse_series=False)
    for row in data["events"]:
        when = _moment(row["exact_utc"])
        events.append(_event("transits", "axis_contact", "exact", when, zone,
                             f"axis:{row['natal_point']}",
                             {"planet": row["transit_planet"], "target": row["natal_point"],
                              "angle": 0, "direction": row["direction"],
                              "contact_index": row["contact_index"],
                              "contact_total": row["contact_total"]}))


def _resonances(events: list[dict]) -> list[dict]:
    """Pair exact events with other hits or active periods on the same focus."""
    buckets: dict[str, list[dict]] = {}
    for row in events:
        buckets.setdefault(row["focus"], []).append(row)
    out = []
    for focus, rows in sorted(buckets.items()):
        rows.sort(key=_sort_key)
        exacts = [row for row in rows if row["weight"] == "exact"]
        periods = [row for row in rows if row["weight"] != "exact"
                   and row["source"].get("end_utc")]
        covered_until = None
        for anchor in exacts:
            at = _moment(anchor["exact_utc"])
            if covered_until is not None and at < covered_until:
                continue
            window_end = at + timedelta(days=RESONANCE_WINDOW_DAYS)
            cluster_exacts = [row for row in exacts
                              if at <= _moment(row["exact_utc"]) < window_end]
            cluster = cluster_exacts + [
                row for row in periods
                if any(_moment(row["source"].get("start_utc", row["exact_utc"]))
                       <= _moment(hit["exact_utc"])
                       < _moment(row["source"]["end_utc"])
                       for hit in cluster_exacts)
            ]
            cluster.sort(key=_sort_key)
            if len({row["technique"] for row in cluster}) >= 2:
                out.append(_resonance_row(focus, cluster, anchor["exact_utc"],
                                          max(hit["exact_utc"] for hit in exacts
                                              if at <= _moment(hit["exact_utc"]) < window_end)))
                covered_until = window_end
    out.sort(key=lambda item: (item["start_utc"], item["focus"]))
    return out


def _resonance_row(focus: str, rows: list[dict], start_utc: str, end_utc: str) -> dict:
    techniques = sorted({row["technique"] for row in rows}, key=TECHNIQUE_PRIORITY.__getitem__)
    return {"focus": focus, "start_utc": start_utc,
            "end_utc": end_utc, "techniques": techniques,
            "technique_count": len(techniques), "event_indices": [row["index"] for row in rows],
            "event_count": len(rows)}


def compute_timeline_synthesis(natal: dict, birth: dict, target_year: int,
                               span_years: int = 1, *, snapshot=None) -> dict:
    """Compute one to three complete birth-place calendar years.

    ``natal`` is the validated ``services.calculator.compute`` result; ``birth``
    contains canonical location_id and resolved fold. Supplying a forecast
    snapshot avoids a second natal calculation in callers that already have it.
    """
    if isinstance(target_year, bool) or not isinstance(target_year, int) or not 1900 <= target_year <= 2099:
        raise ValueError("target_year 需在 1900–2099")
    if isinstance(span_years, bool) or not isinstance(span_years, int) or not 1 <= span_years <= MAX_SPAN_YEARS:
        raise ValueError("span_years 需在 1–3")
    zone = ZoneInfo(natal["birth_context"]["tz_iana"])
    birth_local = datetime(birth["year"], birth["month"], birth["day"],
                           birth["hour"], birth["minute"], tzinfo=zone,
                           fold=natal["birth_context"].get("fold") or 0)
    start = max(datetime(target_year, 1, 1, tzinfo=zone), birth_local)
    end = datetime(target_year + span_years, 1, 1, tzinfo=zone)
    if end <= birth_local or end > birth_local + timedelta(days=100 * 365.2425):
        raise ValueError("时间线需在出生后、黄道释放的 100 年窗口内")
    if snapshot is None:
        from services.forecast_natal import build_forecast_natal
        snapshot = build_forecast_natal(birth)
    events = []
    _append_periods(events, natal, birth, start, end, zone)
    _secondary_events(events, snapshot, start, end, zone)
    _transit_events(events, snapshot, start, end, zone)
    events.sort(key=_sort_key)
    for index, row in enumerate(events):
        row["index"] = index
    return {
        "engine_version": ENGINE_VERSION,
        "settings": {"target_year": target_year, "span_years": span_years,
                     "timezone": zone.key, "interval_semantics": "start_inclusive_end_exclusive",
                     "secondary_scan_days": SECONDARY_SCAN_DAYS,
                     "secondary_moon_scan_days": SECONDARY_MOON_SCAN_DAYS,
                     "secondary_root_tolerance_civil_minutes": 1,
                     "resonance_window_days": RESONANCE_WINDOW_DAYS,
                     "pyswisseph_package_version": version("pyswisseph"),
                     "pyswisseph_version": swe.version,
                     "ephemeris_expected_sha256": dict(EXPECTED_SHA256)},
        "event_count": len(events), "events": events,
        "resonances": _resonances(events),
    }
