"""MCP projections for timing, relationship and sky calculations.

Every function first runs the same birth-time check as the natal table, then
calls the existing Mini Program service and trims the payload to table fields.
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import swisseph as swe

from services.calculator import BirthContextError, compute
from services.mcp_contract import ClarificationRequired, missing
from services.mcp_natal import (HOUSE_SYSTEMS, _birth_body, _compute_source,
                                _input_error, _reference_moment, _strip_text,
                                _zr_period)

_DROP = {"event_id", "series_id", "exact_jd", "civil_jd", "leave_jd", "julian_day",
         "glyph", "description", "reading", "guide", "engine", "schema_version",
         "event_tz", "returned_flags", "birth_timezone", "chapter_index",
         "natal_jd", "sr_jd", "birth_jd_ut", "from_jd", "to_jd"}

_POINT_ZH = {
    "sun": "太阳", "moon": "月亮", "mercury": "水星", "venus": "金星",
    "mars": "火星", "jupiter": "木星", "saturn": "土星", "uranus": "天王星",
    "neptune": "海王星", "pluto": "冥王星", "chiron": "凯龙星",
    "north_node": "北交点", "south_node": "南交点", "fortuna": "福点",
    "fortune": "福点", "spirit": "精神点",
    "asc": "上升点", "dsc": "下降点", "mc": "中天", "ic": "天底",
    "ascendant": "上升点", "descendant": "下降点", "midheaven": "中天",
    "imum_coeli": "天底",
}
_SIGNS = ("白羊座", "金牛座", "双子座", "巨蟹座", "狮子座", "处女座",
          "天秤座", "天蝎座", "射手座", "摩羯座", "水瓶座", "双鱼座")
_ASPECT_ZH = {"conjunction": "合", "sextile": "六分", "square": "刑",
              "trine": "拱", "opposition": "冲"}


def _compact(value):
    """Drop internal ids, Julian days and prose; round floats for readable tables."""
    if isinstance(value, dict):
        return {k: _compact(v) for k, v in value.items() if k not in _DROP}
    if isinstance(value, list):
        return [_compact(v) for v in value]
    if isinstance(value, float):
        return round(value, 4)
    return value


def _zh(key):
    return _POINT_ZH.get(key, key)


def _sign(lon: float) -> dict:
    lon = float(lon) % 360
    return {"longitude": round(lon, 4), "sign": _SIGNS[int(lon // 30)],
            "degree_in_sign": round(lon % 30, 2)}


def _validated(year, month, day, hour, minute, location_id, fold,
               house_system="placidus"):
    """Return (natal compute result, service body with the resolved fold)."""
    result = _compute_source(year=year, month=month, day=day, hour=hour,
                             minute=minute, location_id=location_id,
                             house_system=house_system, fold=fold)
    body = _birth_body(year, month, day, hour, minute, location_id,
                       result["birth_context"]["fold"])
    return result, body


def _age_at(result: dict, moment: datetime) -> float:
    ctx = result["birth_context"]
    birth = datetime.fromisoformat(ctx["civil_dt"]).replace(
        tzinfo=ZoneInfo(ctx["tz_iana"]))
    return (moment - birth).total_seconds() / (365.2425 * 86400)


def _local(utc_text: str | None, tz_name: str) -> str | None:
    if not utc_text:
        return None
    dt = datetime.fromisoformat(utc_text.replace("Z", "+00:00"))
    return dt.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M")


def _date_jd(text: str, end: bool = False) -> float:
    try:
        d = date.fromisoformat(str(text).strip())
    except ValueError:
        raise ValueError("日期需为 YYYY-MM-DD") from None
    return swe.julday(d.year, d.month, d.day, 24.0 if end else 0.0)


def _parse_moment(text: str | None) -> datetime:
    if text in (None, ""):
        return datetime.now(timezone.utc)
    from services.mcp_compat_utils import _parse_datetime_param
    return _parse_datetime_param(text)


def _jd(moment: datetime) -> float:
    u = moment.astimezone(timezone.utc)
    return swe.julday(u.year, u.month, u.day,
                      u.hour + u.minute / 60 + u.second / 3600)


def _forecast_snapshot(body: dict):
    from services.forecast_natal import build_forecast_natal
    return build_forecast_natal(body)


def timeline_synthesis_data(*, year, month, day, hour, minute, location_id,
                            target_year, span_years=1, fold=None) -> dict:
    """MCP-only projection of the bounded multi-technique timeline."""
    try:
        result, body = _validated(year, month, day, hour, minute, location_id, fold)
        from services.timeline_synthesis import compute_timeline_synthesis
        timeline = compute_timeline_synthesis(result, body, target_year, span_years,
                                              snapshot=_forecast_snapshot(body))
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    return {"status": "ok", "birth_context": result["birth_context"], **timeline}


# ── 太阳弧 ───────────────────────────────────────────────────────────────

def solar_arc_data(*, year, month, day, hour, minute, location_id,
                   age_from=None, age_to=None, as_of=None, fold=None, wheel_age=None) -> dict:
    try:
        result, body = _validated(year, month, day, hour, minute, location_id, fold)
        ref_day, ref = _reference_moment(as_of)
        age_now = max(0.0, min(80.0, _age_at(result, ref)))
        if wheel_age is not None:
            age_now = float(wheel_age)
            if not 0 <= age_now <= 80:
                raise ValueError('wheel_age 需在 0–80 岁之间')
        lo = float(age_from) if age_from is not None else max(0.0, age_now - 5)
        hi = float(age_to) if age_to is not None else min(80.0, age_now + 5)
        if not 0 <= lo < hi <= 80:
            raise ValueError("年龄范围需在 0–80 岁之间，且 age_from 小于 age_to")
        from services.solar_arc_compute import compute_solar_arc_events
        sa = compute_solar_arc_events(_forecast_snapshot(body), year, month, day,
                                      hour, minute, age_from=lo, age_to=hi,
                                      wheel_age=age_now)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    wheel = sa["bi_wheel"]
    return {
        "status": "ok",
        "birth_context": result["birth_context"],
        "settings": {"method": "solar_arc_true_sun", "age_from": lo, "age_to": hi,
                     "wheel_age": round(age_now, 3), "wheel_date": ref_day.isoformat()},
        "axis_contacts_by_directed_points": sa["type1"],
        "directed_axes_to_natal_points": sa["type2"],
        "aspect_matrix": [{**m, "sa_point": _zh(m["sa_point"]),
                           "natal_point": _zh(m["natal_point"])} for m in sa["matrix"]],
        "directed_positions_at_wheel_age": {
            "planets": {_zh(k): {**_sign(v["lon"])}
                        for k, v in wheel["solar_arc"]["planets"].items()},
            "angles": {_zh(k): _sign(v) for k, v in wheel["solar_arc"]["angles"].items()},
        },
        "cross_aspects_at_wheel_age": _compact(wheel.get("cross_aspects", [])),
    }


# ── 行运 ─────────────────────────────────────────────────────────────────

def _transit_event(e: dict, tz_name: str) -> dict:
    return {"transit_planet": e["transit_planet_zh"], "aspect": e["aspect"],
            "natal_point": e["natal_point_zh"], "exact_utc": e["exact_utc"],
            "exact_local": _local(e["exact_utc"], tz_name),
            "direction": e.get("direction_zh"),
            "contact": f'{e.get("contact_index")}/{e.get("contact_total")}',
            "age": e.get("age_decimal")}


def transit_events_data(*, year, month, day, hour, minute, location_id,
                        from_date, to_date, target_scope="all", planet=None,
                        fold=None) -> dict:
    try:
        result, body = _validated(year, month, day, hour, minute, location_id, fold)
        lo_jd, hi_jd = _date_jd(from_date), _date_jd(to_date, end=True)
        if lo_jd >= hi_jd:
            raise ValueError("from_date 不可晚于 to_date")
        if hi_jd - lo_jd > 3 * 366:
            raise ValueError("插件单次最多查询 3 年，请分段查询")
        from services.transit_lifetime import compute_range_events
        data = compute_range_events(
            _forecast_snapshot(body), lo_jd, hi_jd,
            group=None, planet=planet or None, target_scope=target_scope,
            natal_point=None, aspects=None)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    tz_name = result["birth_context"]["tz_iana"]
    return {
        "status": "ok", "birth_context": result["birth_context"],
        "settings": {"from_date": from_date, "to_date": to_date, **data["filters"],
                     "aspects": [0.0] if target_scope == "axes" else data["filters"]["aspects"],
                     "aspects_by_target": {
                         "axes": [0.0] if target_scope in ("all", "axes") else [],
                         "points": data["filters"]["aspects"] if target_scope in ("all", "points") else [],
                     },
                     "coverage_note": "四轴仅计算合相（0度）；空事件不代表不存在四轴的其他相位。本命行星/点计算所列主要相位。",
                     "transit_planets": "木星、火星、土星、天王星、海王星、冥王星"},
        "event_count": data["event_count"],
        "events": [_transit_event(e, tz_name) for e in data["events"]],
    }


def transit_snapshot_data(*, year, month, day, hour, minute, location_id,
                          moment=None, fold=None) -> dict:
    try:
        result, body = _validated(year, month, day, hour, minute, location_id, fold)
        when = _parse_moment(moment)
        from services.transit_natal import compute_wheel
        w = compute_wheel(_forecast_snapshot(body), _jd(when), when.isoformat())
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    return {
        "status": "ok", "birth_context": result["birth_context"],
        "moment": when.isoformat(),
        "transit_positions": {_zh(k): {**_sign(v["lon"]), "retrograde": v.get("retrograde")}
                              for k, v in w["transit"]["planets"].items()},
        "active_aspects_to_natal": [
            {"transit_planet": a["transit_planet_zh"], "aspect": a["aspect"],
             "natal_point": a["natal_point_zh"], "orb": round(a["orb"], 3),
             "orb_limit": a.get("orb_limit"), "applying": a.get("applying")}
            for a in w["active_aspects"]],
    }


def _engine_context(body: dict, year, month, day, hour, minute):
    """Same location/civil-time chain as the Flask timing routes."""
    from services.civil_time_resolver import CivilTimeResolver
    from services.engine_adapter import calc_from_context
    from services.location_resolver import LocationResolver
    loc = LocationResolver().resolve(location_id=body["location_id"], lat=None,
                                     lng=None, query="")
    ctx = CivilTimeResolver().resolve(loc, year, month, day, hour, minute,
                                      fold=body.get("fold")).context
    data = calc_from_context(ctx, name="", city="", country_code=loc.country_code or "CN")
    return loc, ctx, data


def saturn_jupiter_data(*, year, month, day, hour, minute, location_id,
                        as_of=None, max_age=80, fold=None) -> dict:
    try:
        result, body = _validated(year, month, day, hour, minute, location_id, fold)
        if isinstance(max_age, bool) or not isinstance(max_age, int) or not 1 <= max_age <= 120:
            raise ValueError("max_age 需在 1–120")
        ref_day, ref = _reference_moment(as_of)
        from services.mcp_compat_utils import _natal_axes_from_data
        from services.transit_presentation import assemble_transit_report
        loc, ctx, data = _engine_context(body, year, month, day, hour, minute)
        report = assemble_transit_report(
            _natal_axes_from_data(data), ctx.julian_day_ut,
            natal_meta={"name": "", "civil_datetime": ctx.civil_dt,
                        "timezone": loc.tz_iana, "location_name": loc.location_id},
            max_age=max_age, tz=ZoneInfo(loc.tz_iana), as_of_jd=_jd(ref))
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    out = _compact({k: v for k, v in report.items() if k != "phase_guide"})
    out.update(status="ok", birth_context=result["birth_context"], as_of=ref_day.isoformat())
    return out


def house_ingress_data(*, year, month, day, hour, minute, location_id, planet=None,
                       from_date=None, to_date=None, fold=None) -> dict:
    try:
        result, body = _validated(year, month, day, hour, minute, location_id, fold)
        lo = _date_jd(from_date) if from_date else None
        hi = _date_jd(to_date, end=True) if to_date else None
        if lo is not None and hi is not None and lo >= hi:
            raise ValueError("from_date 不可晚于 to_date")
        from services.transit_lifetime import compute_house_ingresses
        data = compute_house_ingresses(_forecast_snapshot(body), planet=planet or None,
                                       house=None)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    tz_name = result["birth_context"]["tz_iana"]
    events = [e for e in data["events"]
              if (lo is None or e["exact_jd"] >= lo) and (hi is None or e["exact_jd"] <= hi)]
    return {
        "status": "ok", "birth_context": result["birth_context"],
        "settings": {"house_system": "placidus", "planet": planet or "木星、土星",
                     "from_date": from_date, "to_date": to_date, "age_range": "0–84"},
        "event_count": len(events),
        "events": [{"planet": e["transit_planet_zh"], "entered_house": e["entered_house"],
                    "left_house": e["left_house"], "entry": e["entry_type_zh"],
                    "exact_utc": e["exact_utc"],
                    "enter_local": _local(e["exact_utc"], tz_name),
                    "leave_local": _local(e.get("leave_utc"), tz_name),
                    "contact": f'{e.get("contact_index")}/{e.get("contact_total")}',
                    "age": e["age_decimal"]} for e in events],
    }


# ── 次限月相 / 日返 ─────────────────────────────────────────────────────

def progressed_lunation_data(*, year, month, day, hour, minute, location_id,
                             as_of=None, fold=None) -> dict:
    try:
        result, body = _validated(year, month, day, hour, minute, location_id, fold)
        ref_day, ref = _reference_moment(as_of)
        from services import progressed_phase
        from services.mcp_compat_utils import _natal_axes_from_data
        loc, ctx, data = _engine_context(body, year, month, day, hour, minute)
        report = progressed_phase.build_report(
            ctx.julian_day_ut, _jd(ref), data["houses"]["cusps"],
            _natal_axes_from_data(data), max_age=100, tz=ZoneInfo(loc.tz_iana))
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    out = _compact(report)
    out.update(status="ok", birth_context=result["birth_context"], as_of=ref_day.isoformat(),
               settings={"method": "secondary_progression_rudhyar_8_phases",
                         "phase_boundaries": "45° from exact phase"})
    out.pop("summary", None)
    return out


def _residence(residence_location_id):
    if missing(residence_location_id):
        raise ClarificationRequired(["residence_location_id"])
    from services.location_resolver import LocationResolver
    snap = LocationResolver().resolve(location_id=residence_location_id.strip(),
                                      lat=None, lng=None)
    if snap is None or not snap.tz_iana:
        raise ValueError("无法解析现居地，请先用 search_birthplace 选择 location_id")
    return snap.lat_wgs84, snap.lng_wgs84, snap.tz_iana, snap.location_id


def _solar_return_source(year, month, day, hour, minute, location_id, target_year,
                         residence_location_id, house_system, fold):
    result, body = _validated(year, month, day, hour, minute, location_id, fold, house_system)
    if not isinstance(target_year, int) or not 1800 <= target_year <= 2200:
        raise ValueError("target_year 需在 1800–2200")
    ctx = result["birth_context"]
    rlat, rlng, rtz, rid = _residence(residence_location_id)
    from services.solar_return import compute_solar_return_full
    sr = compute_solar_return_full(
        year, month, day, hour, minute, ctx["lat"], ctx["lng"], target_year,
        rlat, rlng, residence_tz=rtz, residence_city="",
        house_system="W" if house_system == "whole_sign" else "P",
        birth_location_id=body["location_id"], birth_fold=body.get("fold"))
    return result, sr, rid


def solar_return_data(*, year, month, day, hour, minute, location_id, target_year,
                      residence_location_id=None, house_system="placidus", fold=None) -> dict:
    try:
        result, sr, rid = _solar_return_source(year, month, day, hour, minute, location_id,
                                               target_year, residence_location_id,
                                               house_system, fold)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    single = sr["single"]
    jones = single.get("jones_pattern") or {}
    return {
        "status": "ok", "birth_context": result["birth_context"],
        "solar_return": {"utc": sr["sr_utc"], "local": sr["sr_local"],
                         "residence_location_id": rid, "residence": sr["residence"],
                         "house_system": sr["house_system"]},
        "chart": _compact({
            "planets": single["planets"], "angles": single["angles"],
            "house_cusps": single["houses"]["cusps"], "aspects": single["aspects"],
            "angular_planets": single["angular_planets"],
            "lunation_phase": single["lunation_phase"],
            "intercepted_signs": single["intercepted_signs"],
            "elements": single["elements"],
            "unaspected_planets": single["unaspected_planets"],
            "jones_pattern": {"pattern_zh": jones.get("pattern_zh"),
                              "state_label": jones.get("state_label")},
        }),
        "overlay_with_natal": _compact(sr["overlay"]),
        "focus": _compact(sr["focus"]),
        "monthly_moon_progressions": _compact(sr["timeline"]),
    }


# ── 双盘 ─────────────────────────────────────────────────────────────────

def _rel_aspect(a: dict) -> dict:
    return {"first": f'{a["first_chart"].upper() if a["first_chart"] != "composite" else "组合"}:{_zh(a["first_point"])}',
            "second": f'{a["second_chart"].upper() if a["second_chart"] != "composite" else "组合"}:{_zh(a["second_point"])}',
            "aspect": _ASPECT_ZH.get(a["aspect"], a["aspect"]), "angle": a["angle"],
            "orb": round(a["orb"], 3), "tight": a.get("tight_contact")}


def _relationship_source(person_a: dict, person_b: dict, orb_profile: str):
    from services.relationship_charts import ORB_PROFILES, build_relationship_charts
    if orb_profile not in ORB_PROFILES:
        raise ValueError("orb_profile 只支持 greene 或 tight")
    summaries = {}
    for key, p in (("a", person_a), ("b", person_b)):
        if not isinstance(p, dict):
            raise ValueError(f"person_{key} 需包含出生资料")
        try:
            summaries[key] = _compute_source(
                year=p.get("year"), month=p.get("month"), day=p.get("day"),
                hour=p.get("hour"), minute=p.get("minute"),
                location_id=p.get("location_id") or "", house_system="placidus",
                fold=p.get("fold"))
        except BirthContextError as exc:
            exc.status_message = f"person_{key}：{exc.status_message}"
            exc.mcp_field_prefix = f"person_{key}."
            raise
        except ClarificationRequired as exc:
            raise ClarificationRequired(
                [f"person_{key}.{field}" for field in exc.response["required_fields"]]) from None
        except ValueError as exc:
            raise ValueError(f"person_{key}：{exc}") from None
    return summaries, build_relationship_charts(summaries["a"], summaries["b"], orb_profile)


def relationship_data(*, person_a: dict, person_b: dict, orb_profile="greene") -> dict:
    try:
        summaries, rc = _relationship_source(person_a, person_b, orb_profile)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    comp = rc["charts"]["composite"]
    return {
        "status": "ok",
        "birth_context": {"a": summaries["a"]["birth_context"],
                          "b": summaries["b"]["birth_context"]},
        "settings": {"house_system": "placidus", "orb_profile": orb_profile,
                     "orbs": rc["method"].get("orbs"),
                     "composite": "short-arc midpoints; composite cusps are midpoints of Placidus cusps"},
        "synastry_aspects": [_rel_aspect(a) for a in rc["synastry"]["aspects"]],
        "a_planets_in_b_houses": {_zh(x["point"]): x["house"] for x in rc["synastry"]["a_in_b"]},
        "b_planets_in_a_houses": {_zh(x["point"]): x["house"] for x in rc["synastry"]["b_in_a"]},
        "composite_chart": {
            "planets": {_zh(k): _sign(v["longitude"]) for k, v in comp["planets"].items()
                        if v.get("longitude") is not None},
            "axes": {_zh(k): _sign(v["longitude"]) for k, v in comp["axes"].items()
                     if v.get("longitude") is not None},
            "house_cusps": [round(c, 4) for c in comp["houses"]["cusps"]],
            "planet_houses": {_zh(x["point"]): x["house"] for x in comp["point_houses"]},
            "aspects": [_rel_aspect(a) for a in comp["aspects"]],
        },
        "composite_to_natal_aspects": {
            k: [_rel_aspect(a) for a in rc["composite_to_natal"][k]["aspects"]]
            for k in ("a", "b")},
        "shared_house_patterns": _compact(_strip_text(rc["natal_house_patterns"])),
    }


# ── 天象 ─────────────────────────────────────────────────────────────────

def sky_data(*, moment=None) -> dict:
    try:
        when = _parse_moment(moment)
        from services.sky_now import sky_at
        sky = sky_at(_jd(when), when.isoformat())
    except ValueError as exc:
        return _input_error(exc)
    out = _compact(_strip_text(sky))
    out["status"] = "ok"
    return out


# ── 单圈图：组合中点盘 / 日返盘 ─────────────────────────────────────────

def _render(planets: dict, cusps, asc, mc, aspects, system="placidus",
            outline_zodiac=False) -> bytes | None:
    from services.mcp_compat_utils import _svg_to_png
    from services.chart_svg import generate_chart_svg
    svg = generate_chart_svg(planets=planets, cusps=list(cusps), asc_lon=asc, mc_lon=mc,
                             aspects=aspects, system=system)
    if outline_zodiac:
        from services.zodiac_svg_outline import outline_zodiac_text
        svg = outline_zodiac_text(svg)
    return _svg_to_png(svg, 720)


_WHEEL_POINTS = {"sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn",
                 "uranus", "neptune", "pluto", "chiron", "north_node", "south_node"}


def render_composite_png(*, person_a: dict, person_b: dict) -> tuple[dict, bytes | None]:
    try:
        _summaries, rc = _relationship_source(person_a, person_b, "greene")
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc), None
    comp = rc["charts"]["composite"]
    planets = {k: {"lon": v["longitude"], "retrograde": False}
               for k, v in comp["planets"].items()
               if k in _WHEEL_POINTS and v.get("longitude") is not None}
    aspects = [{"p1": a["first_point"], "p2": a["second_point"], "angle": a["angle"],
                "orb": a["orb"]} for a in comp["aspects"]
               if a["first_point"] in planets and a["second_point"] in planets]
    png = _render(planets, comp["houses"]["cusps"], comp["axes"]["ascendant"]["longitude"],
                  comp["axes"]["midheaven"]["longitude"], aspects)
    if not png:
        return {"status": "render_failed", "error": "星盘图生成失败"}, None
    return {"status": "ok"}, png


def render_solar_return_png(*, year, month, day, hour, minute, location_id, target_year,
                            residence_location_id=None, house_system="placidus",
                            fold=None) -> tuple[dict, bytes | None]:
    try:
        _r, sr, _rid = _solar_return_source(year, month, day, hour, minute, location_id,
                                            target_year, residence_location_id,
                                            house_system, fold)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc), None
    single = sr["single"]
    planets = {k: {"lon": v["longitude"], "retrograde": v.get("retrograde", False)}
               for k, v in single["planets"].items() if k in _WHEEL_POINTS}
    aspects = [{"p1": a["point1"], "p2": a["point2"], "angle": a["angle"], "orb": a["orb"]}
               for a in single["aspects"] if a["point1"] in planets and a["point2"] in planets]
    asc = single["angles"]["ascendant"]["longitude"]
    cusps = single["houses"]["cusps"]
    png = _render(planets, cusps, asc, single["angles"]["midheaven"]["longitude"], aspects,
                  system="whole_sign" if house_system == "whole_sign" else "placidus")
    if not png:
        return {"status": "render_failed", "error": "星盘图生成失败"}, None
    return {"status": "ok"}, png


# ── 宫主星定位链 / 福点看护 / 相位格局（本命补充）─────────────────────────

def _chain_node(n: dict, house_system: str) -> dict:
    house_key = "house_p" if house_system == "placidus" else "house_w"
    return {"planet": n["planet_zh"], "sign": n["sign_zh"], "house": n[house_key],
            "longitude": n["longitude"], "retrograde": n["retrograde"]}


def house_ruler_data(*, year, month, day, hour, minute, location_id,
                     house_system="placidus", fold=None) -> dict:
    """Twelve house-ruler dispositor chains, traditional and modern tracks."""
    try:
        result, _body = _validated(year, month, day, hour, minute, location_id,
                                   fold, house_system)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    chains = result["house_ruler_chains"]
    houses = []
    for house in chains[house_system]:
        houses.append({
            "house": house["house"], "cusp_sign": house["sign_zh"],
            "cusp_longitude": house["cusp_lon"], "cross": house["cross"],
            "is_chart_ruler": house["chart_ruler"],
            "tracks": [{
                "track": track["label"], "house_ruler": track["house_ruler_zh"],
                "chain": [_chain_node(n, house_system) for n in track["nodes"]],
                "ending": track["status"],
                "loop_from_step": track["cycle_start"],
                "loop_planets": [_zh(p) for p in track["cycle_planets"]],
            } for track in house["tracks"]],
        })
    return {
        "status": "ok", "birth_context": result["birth_context"],
        "settings": {"house_system": house_system,
                     "ending": "self = ruler rules its own sign; cycle = the chain loops",
                     "crosses": chains["crosses"]},
        "houses": houses,
    }


# ── 黄道释放 L4 ──────────────────────────────────────────────────────────

def releasing_l4_data(*, year, month, day, hour, minute, location_id, lot,
                      parent_start, parent_sign, as_of=None, fold=None) -> dict:
    """Subdivide one verified level-3 period into its level-4 periods."""
    try:
        result, body = _validated(year, month, day, hour, minute, location_id, fold)
        ref_day, ref = _reference_moment(as_of)
        from services.zodiacal_releasing import calculate_zodiacal_releasing_l4
        l4 = calculate_zodiacal_releasing_l4(
            dict(body), lot=str(lot or ""), parent_start=str(parent_start or ""),
            parent_sign=str(parent_sign or "").upper(), now=ref)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    return {
        "status": "ok", "birth_context": result["birth_context"],
        "as_of": ref_day.isoformat(),
        "lot": "福点" if l4["lot"] == "fortune" else "精神点",
        "parent_period": {"start": l4["parent_start"], "sign": l4["parent_sign"]},
        "level4": [_zr_period(p) for p in l4["periods"]],
    }


# ── 终身流年摘要 ─────────────────────────────────────────────────────────

def lifetime_summary_data(*, year, month, day, hour, minute, location_id,
                          fold=None) -> dict:
    """Counts of exact transit hits per seven-year chapter from birth to age 84."""
    try:
        result, body = _validated(year, month, day, hour, minute, location_id, fold)
        from services.transit_lifetime import compute_lifetime_summary
        data = compute_lifetime_summary(_forecast_snapshot(body))
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    return {
        "status": "ok", "birth_context": result["birth_context"],
        "settings": {"age_range": "0–84", "chapter_years": 7,
                     "transit_planets": "木星、火星、土星、天王星、海王星、冥王星",
                     "aspects": "0/60/90/120/180"},
        "total_events": data["event_count"],
        "chapters": [{"ages": c["label"], **c["counts"]} for c in data["chapters"]],
        "totals_by_group": data["groups"], "totals_by_target": data["targets"],
        "totals_by_aspect": data["aspects"],
    }


# ── 行星相位出入窗口 ─────────────────────────────────────────────────────

def aspect_window_data(*, moment=None, location_id=None) -> dict:
    """Planet-to-planet aspects in orb at one moment, with their orb windows."""
    try:
        if missing(location_id):
            raise ClarificationRequired(["location_id"],
                                        "此工具包含福点与精神点，请先确认计算地点。")
        when = _parse_moment(moment)
        from services.location_resolver import LocationResolver
        snap = LocationResolver().resolve(location_id=str(location_id).strip(),
                                          lat=None, lng=None)
        if snap is None:
            raise ValueError("无法解析地点，请先用 search_birthplace 选择 location_id")
        lat, lng, place = snap.lat_wgs84, snap.lng_wgs84, snap.location_id
        from services.aspect_windows import aspect_groups, unique_aspects
        rows = unique_aspects(aspect_groups(_jd(when), float(lat), float(lng)))
    except ValueError as exc:
        return _input_error(exc)
    return {
        "status": "ok", "moment": when.isoformat(),
        "location_id": place,
        "settings": {"note": "total_days 是仍落在容许度内的天数，不代表影响力持续时间",
                     "lots_location": "福点与精神点使用本次明确选择的地点"},
        "aspect_count": len(rows),
        "aspects": [{"point1": a["p1_cn"], "point2": a["p2_cn"], "aspect": a["aspect_cn"],
                     "angle": a["angle"], "orb": a["orb_deg"], "orb_limit": a["orb_limit"],
                     "applying": a["applying"], "phase": a["phase_cn"],
                     "total_days": a["total_days"], "elapsed_days": a["elapsed_days"],
                     "remaining_days": a["remaining_days"],
                     "progress_pct": a["progress_pct"]} for a in rows],
    }


# ── 天象盘（任一时刻 + 地点的完整盘）─────────────────────────────────────

def _sky_chart_source(moment, location_id):
    if missing(location_id):
        raise ClarificationRequired(["location_id"])
    when = _parse_moment(moment)
    from services.location_resolver import LocationResolver
    snap = LocationResolver().resolve(location_id=str(location_id or "").strip() or None,
                                      lat=None, lng=None)
    if snap is None:
        raise ValueError("请先用 search_birthplace 选择 location_id")
    local = when.astimezone(ZoneInfo(str(snap.tz_iana)))
    result = compute("天象盘", local.year, local.month, local.day, local.hour,
                     local.minute, "", location_id=snap.location_id or None,
                     lat=None if snap.location_id else snap.lat_wgs84,
                     lng=None if snap.location_id else snap.lng_wgs84,
                     fold=local.fold)
    return when, snap, local, result


def sky_chart_data(*, moment=None, location_id=None) -> dict:
    """A full chart cast for any moment and place, not for a birth."""
    try:
        when, snap, local, result = _sky_chart_source(moment, location_id)
        from services.retrograde_motion import motion_status_at
        motion = motion_status_at(_jd(when))
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    return {
        "status": "ok",
        "moment": when.isoformat(),
        "local_time": local.strftime("%Y-%m-%d %H:%M"),
        "location": {"location_id": snap.location_id, "lat": snap.lat_wgs84,
                     "lng": snap.lng_wgs84, "tz_iana": snap.tz_iana},
        "settings": {"zodiac": "tropical", "house_system": "placidus",
                     "chart_time_precision": "minute",
                     "chart_moment": local.replace(second=0, microsecond=0).isoformat(),
                     "motion_moment": when.isoformat()},
        "planets": [{"name": p["cn"], "longitude": p["lon"], "sign": p["sign"],
                     "house": p["house_p"], "retrograde": p["retrograde"]}
                    for p in result["natal_planets_full"]],
        "house_cusps": [{"house": i + 1, "longitude": float(c)}
                        for i, c in enumerate(result["cusps"])],
        "axes": result["axes"],
        "aspects": result["aspects"],
        "moon_phase": result["moon_phase"],
        "aspect_patterns": {k: v for k, v in result["phase_patterns"].items() if v},
        "planet_motion": _compact(motion),
    }


def render_sky_chart_png(*, moment=None, location_id=None) -> tuple[dict, bytes | None]:
    try:
        when, snap, local, result = _sky_chart_source(moment, location_id)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc), None
    from services.mcp_compat_utils import _svg_to_png
    from services.chart_svg import generate_chart_svg
    png = _svg_to_png(generate_chart_svg(system="placidus", **result["svg_data"]), 720)
    if not png:
        return {"status": "render_failed", "error": "星盘图生成失败"}, None
    return {"status": "ok", "moment": when.isoformat(),
            "local_time": local.strftime("%Y-%m-%d %H:%M"),
            "location_id": snap.location_id}, png


# ── 双圈图：行运双盘 / 太阳弧双盘 ───────────────────────────────────────

def _ring_lon(container: dict, key: str):
    node = (container.get("planets") or {}).get(key)
    if isinstance(node, dict) and node.get("lon") is not None:
        return node["lon"]
    value = (container.get("angles") or {}).get(key)
    if isinstance(value, dict):
        return value.get("lon")
    return value


def _biwheel_png(natal: dict, outer: dict, cross_aspects, inner_label: str,
                 outer_label: str, outer_axes=None, outline_zodiac=False) -> bytes | None:
    from services.mcp_compat_utils import _svg_to_png
    from services.chart_biwheel_svg import generate_biwheel_svg
    lines = []
    for a in cross_aspects or ():
        outer_lon = _ring_lon(outer, a.get("sr_planet", ""))
        inner_lon = _ring_lon(natal, a.get("natal_planet", a.get("natal_point", "")))
        if outer_lon is not None and inner_lon is not None:
            lines.append({"outer_lon": outer_lon, "inner_lon": inner_lon,
                          "angle": a.get("angle", 0)})
    svg = generate_biwheel_svg(
        inner_planets=natal["planets"], outer_planets=outer["planets"],
        cusps=natal["cusps"], asc_lon=natal["asc_lon"], mc_lon=natal["mc_lon"],
        cross_aspects=lines, system="placidus",
        inner_label=inner_label, outer_label=outer_label, outer_axes=outer_axes)
    if outline_zodiac:
        from services.zodiac_svg_outline import outline_zodiac_text
        svg = outline_zodiac_text(svg)
    return _svg_to_png(svg, 760)


def render_transit_biwheel_png(*, year, month, day, hour, minute, location_id,
                               moment=None, fold=None) -> tuple[dict, bytes | None]:
    """Natal inside, transiting planets outside, at one moment."""
    try:
        result, body = _validated(year, month, day, hour, minute, location_id, fold)
        when = _parse_moment(moment)
        from services.transit_natal import compute_wheel
        wheel = compute_wheel(_forecast_snapshot(body), _jd(when), when.isoformat())
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc), None
    label = when.astimezone(ZoneInfo(result["birth_context"]["tz_iana"])).strftime(
        "%Y-%m-%d %H:%M")
    png = _biwheel_png(wheel["natal"], wheel["transit"], wheel["cross_aspects"],
                       "本命", f"行运 {label}")
    if not png:
        return {"status": "render_failed", "error": "星盘图生成失败"}, None
    return {"status": "ok", "moment": when.isoformat(),
            "birth_context": result["birth_context"]}, png


def render_solar_arc_biwheel_png(*, year, month, day, hour, minute, location_id,
                                 age=None, as_of=None,
                                 fold=None) -> tuple[dict, bytes | None]:
    """Natal inside, solar arc directed positions outside, at one age."""
    try:
        result, body = _validated(year, month, day, hour, minute, location_id, fold)
        ref_day, ref = _reference_moment(as_of)
        wheel_age = float(age) if age is not None else _age_at(result, ref)
        if not 0.0 <= wheel_age <= 80.0:
            raise ValueError("age 需在 0–80 岁之间")
        from services.solar_arc_compute import compute_solar_arc_wheel
        wheel = compute_solar_arc_wheel(_forecast_snapshot(body), wheel_age)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc), None
    png = _biwheel_png(wheel["natal"], wheel["solar_arc"], wheel["cross_aspects"],
                       "本命", f"太阳弧 {wheel_age:.1f} 岁")
    if not png:
        return {"status": "render_failed", "error": "星盘图生成失败"}, None
    return {"status": "ok", "age": round(wheel_age, 2), "as_of": ref_day.isoformat(),
            "birth_context": result["birth_context"]}, png


# ── 月亮返照盘（Lunar Return）──

def _lunar_return_source(year, month, day, hour, minute, location_id, target_year,
                         target_month, target_day, residence_location_id, house_system, fold):
    result, body = _validated(year, month, day, hour, minute, location_id, fold, house_system)
    if not isinstance(target_year, int) or not 1800 <= target_year <= 2200:
        raise ValueError("target_year 需在 1800–2200")
    if not isinstance(target_month, int) or not 1 <= target_month <= 12:
        raise ValueError("target_month 需在 1–12")
    if target_day is not None and (not isinstance(target_day, int) or not 1 <= target_day <= 31):
        raise ValueError("target_day 需在 1–31")
    ctx = result["birth_context"]
    rlat, rlng, rtz, rid = _residence(residence_location_id)
    from services.lunar_return import compute_lunar_return_full
    lr = compute_lunar_return_full(
        year, month, day, hour, minute, ctx["lat"], ctx["lng"],
        target_year, target_month, target_day=target_day,
        residence_lat=rlat, residence_lng=rlng, residence_tz=rtz, residence_city="",
        house_system="W" if house_system == "whole_sign" else "P",
        birth_location_id=body["location_id"], birth_fold=body.get("fold"))
    return result, lr, rid


def lunar_return_data(*, year, month, day, hour, minute, location_id, target_year,
                      target_month, target_day=None, residence_location_id=None,
                      house_system="placidus", fold=None) -> dict:
    try:
        result, lr, rid = _lunar_return_source(year, month, day, hour, minute, location_id,
                                               target_year, target_month, target_day,
                                               residence_location_id, house_system, fold)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    single = lr["single"]
    jones = single.get("jones_pattern") or {}
    return {
        "status": "ok", "birth_context": result["birth_context"],
        "lunar_return": {"utc": lr["lr_utc"], "local": lr["lr_local"],
                         "residence_location_id": rid, "residence": lr["residence"],
                         "house_system": lr["house_system"],
                         "natal_moon_longitude": round(lr["natal"]["planets"]["moon"]["longitude"], 4)},
        "chart": _compact({
            "planets": single["planets"], "angles": single["angles"],
            "special_points": single["special_points"],
            "house_cusps": single["houses"]["cusps"], "aspects": single["aspects"],
            "angular_planets": single["angular_planets"],
            "lunation_phase": single["lunation_phase"],
            "intercepted_signs": single["intercepted_signs"],
            "elements": single["elements"],
            "unaspected_planets": single["unaspected_planets"],
            "jones_pattern": {"pattern_zh": jones.get("pattern_zh"),
                              "state_label": jones.get("state_label")},
        }),
        "overlay_with_natal": _compact(lr["overlay"]),
        "focus": _compact(lr["focus"]),
    }


def render_lunar_return_png(*, year, month, day, hour, minute, location_id, target_year,
                            target_month, target_day=None, residence_location_id=None,
                            house_system="placidus", fold=None) -> tuple[dict, bytes | None]:
    try:
        _r, lr, _rid = _lunar_return_source(year, month, day, hour, minute, location_id,
                                            target_year, target_month, target_day,
                                            residence_location_id, house_system, fold)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc), None
    single = lr["single"]
    planets = {k: {"lon": v["longitude"], "retrograde": v.get("retrograde", False)}
               for k, v in single["planets"].items() if k in _WHEEL_POINTS}
    aspects = [{"p1": a["point1"], "p2": a["point2"], "angle": a["angle"], "orb": a["orb"]}
               for a in single["aspects"] if a["point1"] in planets and a["point2"] in planets]
    asc = single["angles"]["ascendant"]["longitude"]
    cusps = single["houses"]["cusps"]
    png = _render(planets, cusps, asc, single["angles"]["midheaven"]["longitude"], aspects,
                  system="whole_sign" if house_system == "whole_sign" else "placidus",
                  outline_zodiac=True)
    if not png:
        return {"status": "render_failed", "error": "星盘图生成失败"}, None
    return {"status": "ok"}, png


# ── 完整次限推进（Secondary Progressions）──

def _secondary_progressions_source(year, month, day, hour, minute, location_id,
                                   age, as_of, house_system, fold, angle_progression_method):
    if age is not None and as_of is not None:
        raise ValueError("age 与 as_of 请只提供其一")
    result, body = _validated(year, month, day, hour, minute, location_id, fold, house_system)
    ctx = result["birth_context"]
    ref_day, ref = _reference_moment(as_of) if as_of is not None else (None, None)
    prog_age = float(age) if age is not None else None
    as_of_str = ref_day.isoformat() if ref_day is not None else None
    from services.secondary_progressions import compute_secondary_progressions
    prog = compute_secondary_progressions(
        year, month, day, hour, minute, ctx["lat"], ctx["lng"],
        age=prog_age, as_of=as_of_str,
        house_system="W" if house_system == "whole_sign" else "P",
        angle_progression_method=angle_progression_method,
        birth_location_id=body["location_id"], birth_fold=body.get("fold"))
    return result, prog, as_of_str


def secondary_progressions_data(*, year, month, day, hour, minute, location_id,
                                age=None, as_of=None, house_system="placidus",
                                fold=None, angle_progression_method="naibod") -> dict:
    try:
        result, prog, as_of_str = _secondary_progressions_source(
            year, month, day, hour, minute, location_id, age, as_of, house_system, fold,
            angle_progression_method)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    chart = prog["progressed_chart"]
    return {
        "status": "ok", "birth_context": result["birth_context"],
        "settings": {
            "method": "secondary_progressions_day_for_a_year",
            "angle_progression_method": prog["angle_progression_method"],
            "house_system": prog["house_system"],
            "age": prog["age"],
            "as_of": as_of_str,
        },
        "progressed_chart": _compact({
            "planets": chart["planets"],
            "special_points": chart["special_points"],
            "axes": chart["axes"],
            "house_cusps": chart["houses"]["cusps"],
            "lunation_phase": chart["lunation_phase"],
        }),
        "progressed_to_natal_aspects": _compact(prog["progressed_to_natal_aspects"]),
        "progressed_ephemeris_date": prog["progressed_ephemeris_date"],
    }


def render_secondary_progressions_biwheel_png(*, year, month, day, hour, minute, location_id,
                                              age=None, as_of=None, house_system="placidus",
                                              fold=None, angle_progression_method="naibod") -> tuple[dict, bytes | None]:
    try:
        result, prog, as_of_str = _secondary_progressions_source(
            year, month, day, hour, minute, location_id, age, as_of, house_system, fold,
            angle_progression_method)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc), None

    nat = prog["natal"]
    prg_chart = prog["progressed_chart"]

    natal_ring = {
        "planets": {k: {"lon": v["longitude"], "retrograde": v.get("retrograde", False)}
                    for k, v in nat["planets"].items() if k in _WHEEL_POINTS},
        "cusps": nat["houses"]["cusps"],
        "asc_lon": nat["axes"]["ascendant"]["longitude"],
        "mc_lon": nat["axes"]["midheaven"]["longitude"],
    }
    outer_ring = {
        "planets": {k: {"lon": v["longitude"], "retrograde": v.get("retrograde", False)}
                    for k, v in prg_chart["planets"].items() if k in _WHEEL_POINTS},
    }
    cross_lines = [
        {"sr_planet": a["progressed_point"], "natal_planet": a["natal_point"], "angle": a["angle"]}
        for a in prog["progressed_to_natal_aspects"]
        if a["progressed_point"] in _WHEEL_POINTS and a["natal_point"] in _WHEEL_POINTS
    ]
    age_label = f"次限 {prog['age']:.1f} 岁"
    outer_axes = {
        "asc": prg_chart["axes"]["ascendant"]["longitude"],
        "mc": prg_chart["axes"]["midheaven"]["longitude"],
        "dsc": prg_chart["axes"]["descendant"]["longitude"],
        "ic": prg_chart["axes"]["imum_coeli"]["longitude"],
    }
    png = _biwheel_png(natal_ring, outer_ring, cross_lines, "本命", age_label,
                       outer_axes=outer_axes, outline_zodiac=True)
    if not png:
        return {"status": "render_failed", "error": "星盘图生成失败"}, None
    return {"status": "ok", "age": prog["age"], "as_of": as_of_str,
            "birth_context": result["birth_context"]}, png


# ── Davison 时空中点盘 ───────────────────────────────────────────────────

def _davison_source(person_a: dict, person_b: dict, house_system="placidus", orb_profile="greene"):
    from services.davison_chart import compute_davison_chart_full, ORB_PROFILES
    import swisseph as swe
    from datetime import datetime

    if orb_profile not in ORB_PROFILES:
        raise ValueError("orb_profile 只支持 greene 或 tight")
    summaries = {}
    for key, p in (("a", person_a), ("b", person_b)):
        if not isinstance(p, dict):
            raise ValueError(f"person_{key} 需包含出生资料")
        try:
            summaries[key] = _compute_source(
                year=p.get("year"), month=p.get("month"), day=p.get("day"),
                hour=p.get("hour"), minute=p.get("minute"),
                location_id=p.get("location_id") or "", house_system=house_system,
                fold=p.get("fold"))
        except BirthContextError as exc:
            exc.status_message = f"person_{key}：{exc.status_message}"
            exc.mcp_field_prefix = f"person_{key}."
            raise
        except ClarificationRequired as exc:
            raise ClarificationRequired(
                [f"person_{key}.{field}" for field in exc.response["required_fields"]]) from None
        except ValueError as exc:
            raise ValueError(f"person_{key}：{exc}") from None

    bc_a = summaries["a"]["birth_context"]
    bc_b = summaries["b"]["birth_context"]

    dt_a = datetime.fromisoformat(bc_a["civil_dt"])
    jd_a = swe.julday(dt_a.year, dt_a.month, dt_a.day, dt_a.hour + dt_a.minute / 60.0 - bc_a["utc_offset"])
    dt_b = datetime.fromisoformat(bc_b["civil_dt"])
    jd_b = swe.julday(dt_b.year, dt_b.month, dt_b.day, dt_b.hour + dt_b.minute / 60.0 - bc_b["utc_offset"])

    dav = compute_davison_chart_full(
        jd_a, bc_a["lat"], bc_a["lng"],
        jd_b, bc_b["lat"], bc_b["lng"],
        house_system=house_system,
        orb_profile=orb_profile,
    )
    return summaries, dav


def davison_data(*, person_a: dict, person_b: dict, house_system="placidus",
                 orb_profile="greene") -> dict:
    try:
        summaries, dav = _davison_source(person_a, person_b, house_system, orb_profile)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    return {
        "status": "ok",
        "birth_context": {
            "a": summaries["a"]["birth_context"],
            "b": summaries["b"]["birth_context"],
        },
        "settings": {
            "house_system": house_system,
            "orb_profile": orb_profile,
        },
        "midpoint_space_time": dav["midpoint_space_time"],
        "chart": dav["chart"],
        "aspects": dav["aspects"],
    }


def render_davison_png(*, person_a: dict, person_b: dict, house_system="placidus") -> tuple[dict, bytes | None]:
    try:
        _summaries, dav = _davison_source(person_a, person_b, house_system, "greene")
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc), None
    chart = dav["chart"]
    planets = {k: {"lon": v["longitude"], "retrograde": v.get("retrograde", False)}
               for k, v in chart["planets"].items()
               if k in _WHEEL_POINTS and v.get("longitude") is not None}
    if "chiron" in chart.get("special_points", {}):
        chiron = chart["special_points"]["chiron"]
        planets["chiron"] = {"lon": chiron["longitude"], "retrograde": chiron["retrograde"]}
    aspects = [{"p1": a["point1"], "p2": a["point2"], "angle": a["angle"], "orb": a["orb"]}
               for a in dav["aspects"] if a["point1"] in planets and a["point2"] in planets]
    asc = chart["axes"]["ascendant"]["longitude"]
    mc = chart["axes"]["midheaven"]["longitude"]
    cusps = chart["house_cusps"]
    png = _render(planets, cusps, asc, mc, aspects,
                  system="whole_sign" if house_system == "whole_sign" else "placidus")
    if not png:
        return {"status": "render_failed", "error": "星盘图生成失败"}, None
    return {"status": "ok"}, png


def render_saturn_jupiter_cycles_png(*, year, month, day, hour, minute, location_id,
                                     as_of=None, max_age=80, person_name=None,
                                     fold=None) -> tuple[dict, bytes | None]:
    try:
        report = saturn_jupiter_data(year=year, month=month, day=day, hour=hour,
                                     minute=minute, location_id=location_id,
                                     as_of=as_of, max_age=max_age, fold=fold)
        if report.get("status") != "ok":
            return report, None
        from services.transit_wave_svg import render_transit_wave_svg, _svg_to_png_rect
        svg = render_transit_wave_svg(report, width=1200, height=660, person_name=person_name)
        png = _svg_to_png_rect(svg, 1200, 660)
        if not png:
            return {"status": "render_failed", "error": "土木流年图生成失败"}, None
        return {
            "status": "ok",
            "birth_context": report["birth_context"],
            "as_of": report.get("as_of"),
            "range": report.get("range"),
            "current": report.get("current"),
            "saturn_count": len(report.get("saturn_events", [])),
            "jupiter_count": len(report.get("jupiter_events", [])),
            "mime_type": "image/png",
            "width": 1200,
            "height": 660,
        }, png
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc), None


# ── Relocation 空间重置盘 ────────────────────────────────────────────────

def _relocation_source(year, month, day, hour, minute, location_id,
                       relocation_location_id, house_system="placidus", fold=None):
    from services.relocation_chart import compute_relocation_chart_full
    from services.location_resolver import LocationResolver
    if missing(relocation_location_id):
        raise ClarificationRequired(["relocation_location_id"])
    snap = LocationResolver().resolve(location_id=relocation_location_id.strip(),
                                      query=None, lat=None, lng=None)
    if snap is None:
        raise ValueError("无法解析 relocation_location_id")
    result = _compute_source(year=year, month=month, day=day, hour=hour, minute=minute,
                             location_id=location_id, house_system=house_system, fold=fold)
    reloc = compute_relocation_chart_full(
        result,
        reloc_lat=snap.lat_wgs84,
        reloc_lng=snap.lng_wgs84,
        reloc_location_id=snap.location_id,
        reloc_name=snap.location_id,
        reloc_tz=snap.tz_iana,
        house_system=house_system,
    )
    return result, reloc


def relocation_data(*, year, month, day, hour, minute, location_id,
                    relocation_location_id, house_system="placidus", fold=None) -> dict:
    try:
        result, reloc = _relocation_source(year, month, day, hour, minute, location_id,
                                           relocation_location_id, house_system, fold)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    return {
        "status": "ok",
        "birth_context": result["birth_context"],
        "settings": {
            "house_system": house_system,
        },
        "relocation_location": reloc["relocation_location"],
        "angular_shifts": reloc["angular_shifts"],
        "axes": reloc["axes"],
        "house_cusps": reloc["house_cusps"],
        "planets": reloc["planets"],
        "aspects": reloc["aspects"],
    }


def render_relocation_png(*, year, month, day, hour, minute, location_id,
                          relocation_location_id, house_system="placidus", fold=None) -> tuple[dict, bytes | None]:
    try:
        _r, reloc = _relocation_source(year, month, day, hour, minute, location_id,
                                       relocation_location_id, house_system, fold)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc), None
    planets = {p["key"]: {"lon": p["longitude"], "retrograde": p.get("retrograde", False)}
               for p in reloc["planets"] if p["key"] in _WHEEL_POINTS}
    aspects = [{"p1": a["point1"], "p2": a["point2"], "angle": a["angle"], "orb": a["orb"]}
               for a in reloc["aspects"] if a["point1"] in planets and a["point2"] in planets]
    asc = reloc["axes"]["ascendant"]["longitude"]
    mc = reloc["axes"]["midheaven"]["longitude"]
    cusps = reloc["house_cusps"]
    png = _render(planets, cusps, asc, mc, aspects,
                  system="whole_sign" if house_system == "whole_sign" else "placidus")
    if not png:
        return {"status": "render_failed", "error": "星盘图生成失败"}, None
    return {"status": "ok"}, png
