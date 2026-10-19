"""Small, data-only projection of the existing natal calculation for MCP."""

from datetime import date
import json
import os
import subprocess

from services.calculator import BirthContextError, compute
from services.mcp_contract import BIRTH_FIELDS, ClarificationRequired, clarification, missing
from services.mcp_compat_utils import _search_city_options


HOUSE_SYSTEMS = {"placidus": "house_p", "whole_sign": "house_w"}


def search_birthplace(query: str) -> dict:
    """Return selectable canonical locations; never silently choose a city."""
    query = (query or "").strip()
    if len(query) < 2 or len(query) > 100:
        return {"status": "invalid_input", "error": "地点关键词需为 2–100 个字符"}
    options = _search_city_options(query, limit=10)
    result = {"status": "ok" if options else "not_found", "options": options}
    if len(options) > 1:
        guidance = clarification(["location_id"], prompt="找到多个地点，请让用户确认地区后选择对应的 location_id。")
        result.update({key: guidance[key] for key in ("required_fields", "clarification", "next_action")})
    elif not options:
        result["next_action"] = "refine_location_query"
    return result


def _compute_source(*, year: int, month: int, day: int, hour: int,
                    minute: int, location_id: str,
                    house_system: str, fold: int | None) -> dict:
    """Validate birth inputs once, then use the Mini Program calculation entry point."""
    values = dict(year=year, month=month, day=day, hour=hour, minute=minute,
                  location_id=location_id, house_system=house_system)
    absent = [field for field in (*BIRTH_FIELDS, "house_system") if missing(values[field])]
    if absent:
        raise ClarificationRequired(absent)
    if not all(isinstance(v, int) and not isinstance(v, bool)
               for v in (year, month, day, hour, minute)):
        raise ValueError("出生日期和时间必须是整数")
    if not 1 <= year <= 3000:
        raise ValueError("year 超出范围（1–3000）")
    date(year, month, day)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("出生时间超出范围")
    if not isinstance(location_id, str) or not location_id.strip():
        raise ValueError("请先用 search_birthplace 选择 location_id")
    if house_system not in HOUSE_SYSTEMS:
        raise ValueError("house_system 只支持 placidus 或 whole_sign")
    if fold is not None and (isinstance(fold, bool) or fold not in (0, 1)):
        raise ValueError("fold 只支持 0 或 1")
    return compute("", year, month, day, hour, minute, "",
                   location_id=location_id.strip(), fold=fold)


def _input_error(exc: Exception) -> dict:
    if isinstance(exc, ClarificationRequired):
        return exc.response
    if isinstance(exc, BirthContextError):
        from services.mcp_compat_utils import _serialize_candidate
        prefix = getattr(exc, "mcp_field_prefix", "")
        fields = ("fold",) if exc.status in {"ambiguous", "invalid_fold"} else BIRTH_FIELDS
        return clarification([prefix + field for field in fields],
                             prompt=exc.status_message, status=exc.status,
                             candidates=[_serialize_candidate(c) for c in exc.candidates])
    return {"status": "invalid_input", "error": str(exc),
            "next_action": "correct_input", "retryable": False}


def calculate_natal_data(*, year: int, month: int, day: int, hour: int,
                         minute: int, location_id: str,
                         house_system: str = "placidus", fold: int | None = None) -> dict:
    """Reuse compute() and return a bounded table without reports or chart images."""
    try:
        result = _compute_source(year=year, month=month, day=day, hour=hour,
                                 minute=minute, location_id=location_id,
                                 house_system=house_system, fold=fold)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)

    house_key = HOUSE_SYSTEMS[house_system]
    asc_sign = int(result["asc_lon"] // 30) % 12
    cusps = (result["cusps"] if house_system == "placidus"
             else [((asc_sign + i) % 12) * 30.0 for i in range(12)])
    table = {
        "status": "ok",
        "input": {"year": year, "month": month, "day": day,
                  "hour": hour, "minute": minute,
                  "location_id": location_id.strip(), "house_system": house_system,
                  "fold": fold},
        "birth_context": result["birth_context"],
        "settings": {"zodiac": "tropical", "house_system": house_system,
                     "longitude_unit": "degrees_0_360", "coordinate_datum": "WGS84"},
        "planets": [
            {"key": p["key"], "name": p["cn"], "longitude": p["lon"],
             "sign": p["sign"], "house": p[house_key],
             "retrograde": p["retrograde"]}
            for p in result["natal_planets_full"]
            if p["key"] in {"sun", "moon", "mercury", "venus", "mars",
                            "jupiter", "saturn", "uranus", "neptune", "pluto",
                            "chiron", "north_node", "south_node", "pars_fortuna", "pars_spiritus"}
        ],
        "house_cusps": [{"house": i + 1, "longitude": float(lon)}
                        for i, lon in enumerate(cusps)],
        "axes": result["axes"],
        "aspects": result["aspects"],
    }
    from services.mcp_facts import natal_reference
    table["fact_reference"] = natal_reference(table)
    table["interpretation_workflow"] = {
        "next_tool": "verify_natal_claims",
        "when": "Before presenting a natal interpretation, even if the user did not ask for verification.",
        "reference": "Copy fact_reference unchanged into the reference argument.",
        "claims": "Submit every natal sign, house, retrograde and aspect assertion in the draft; use one structured claim per fact and its exact draft quote.",
        "claim_example": {"quote": "太阳在白羊座", "kind": "sign", "point": "sun", "value": "白羊座"},
        "example_only": "The example describes the schema, not this chart. Use actual draft facts.",
        "after_verification": "Correct contradicted facts and identify unverified facts. Verification covers submitted structured facts only, not the full report or psychological interpretation.",
    }
    return table


def render_natal_chart_png(*, year: int, month: int, day: int, hour: int,
                           minute: int, location_id: str,
                           house_system: str = "placidus", fold: int | None = None
                           ) -> tuple[dict, bytes | None]:
    """Render the existing wheel with the same input and birth-time checks."""
    try:
        result = _compute_source(year=year, month=month, day=day, hour=hour,
                                 minute=minute, location_id=location_id,
                                 house_system=house_system, fold=fold)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc), None

    from services.mcp_compat_utils import _svg_to_png
    from services.chart_cache import render_with_cache
    from services.chart_svg import generate_chart_svg

    svg_data = result["svg_data"]
    size = 720  # fixed size bounds anonymous rendering cost

    def _render() -> bytes | None:
        return _svg_to_png(generate_chart_svg(system=house_system, **svg_data), size)

    png = render_with_cache(svg_data, house_system, size, _render)
    if not png:
        return {"status": "render_failed", "error": "星盘图生成失败"}, None
    return {"status": "ok", "house_system": house_system,
            "birth_context": result["birth_context"],
            "mime_type": "image/png", "size_px": size}, png


def render_jones_pattern_png(*, year: int, month: int, day: int, hour: int,
                             minute: int, location_id: str,
                             fold: int | None = None) -> tuple[dict, bytes | None]:
    """Draw the Mini Program Jones ring using its own presentation geometry."""
    try:
        result = _compute_source(year=year, month=month, day=day, hour=hour,
                                 minute=minute, location_id=location_id,
                                 house_system="placidus", fold=fold)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc), None

    script = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          "scripts", "jones_mcp_geometry.js")
    payload = {"jones": result["jones_pattern"], "asc": result["asc_lon"],
               "cusps": result["cusps"], "rulerChains": result.get("house_ruler_chains"),
               "ascRuler": result.get("asc_ruler"), "aspects": result.get("aspects")}
    try:
        proc = subprocess.run(["node", script], input=json.dumps(payload, ensure_ascii=False),
                              text=True, capture_output=True, timeout=8, check=True)
        geometry = json.loads(proc.stdout)
        from services.mcp_compat_utils import _svg_to_png
        from services.jones_chart_svg import render_jones_svg
        png = _svg_to_png(render_jones_svg(geometry), 720)
    except (OSError, ValueError, subprocess.SubprocessError, KeyError, TypeError):
        png = None
    if not png:
        return {"status": "render_failed", "error": "琼斯格局图生成失败"}, None
    jones = result["jones_pattern"]
    return {"status": "ok", "birth_context": result["birth_context"],
            "pattern_zh": jones["pattern_zh"], "pattern_en": jones["pattern_en"],
            "state_label": jones["state_label"], "mime_type": "image/png",
            "size_px": 720}, png

# ── 古典要素 / 黄道释放 / 法达与年小限 ─────────────────────────────────────

_TEXT_FIELDS = {"event_text", "description", "guide"}


def _strip_text(value):
    """Drop interpretive prose so the plugin returns calculation data only."""
    if isinstance(value, dict):
        return {k: _strip_text(v) for k, v in value.items() if k not in _TEXT_FIELDS}
    if isinstance(value, list):
        return [_strip_text(v) for v in value]
    return value


def _triplicity_stages(stages):
    """Only publish calculated stage attributes, never report annotations."""
    fields = {"stage", "stage_label", "planet_cn", "sign_cn", "house",
              "dignity", "house_type", "tags"}
    return [{key: value for key, value in stage.items() if key in fields}
            for stage in stages]


def _reference_moment(as_of: str | None):
    """Parse YYYY-MM-DD (default today) into a UTC-noon reference instant."""
    from datetime import datetime, timezone
    if as_of in (None, ""):
        day = datetime.now(timezone.utc).date()
    else:
        if not isinstance(as_of, str):
            raise ValueError("as_of 需为 YYYY-MM-DD")
        try:
            day = date.fromisoformat(as_of.strip())
        except ValueError:
            raise ValueError("as_of 需为 YYYY-MM-DD") from None
    return day, datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)


def _birth_body(year, month, day, hour, minute, location_id, fold) -> dict:
    body = {"year": year, "month": month, "day": day, "hour": hour,
            "minute": minute, "location_id": location_id.strip()}
    if fold is not None:
        body["fold"] = fold
    return body


def _domicile_ruler(longitude: float) -> str:
    from services.zodiac_constants import SIGN_RULER
    keys = ("Ari", "Tau", "Gem", "Can", "Leo", "Vir",
            "Lib", "Sco", "Sag", "Cap", "Aqu", "Pis")
    return SIGN_RULER[keys[int(float(longitude) % 360 // 30)]]


def _planet_position(result: dict, planet_cn: str, house_system: str) -> dict | None:
    house_key = HOUSE_SYSTEMS[house_system]
    for p in result["natal_planets_full"]:
        if p["cn"] == planet_cn:
            return {"planet": planet_cn, "longitude": p["lon"],
                    "sign": p["sign"], "house": p[house_key]}
    return None


def _lot(result: dict, prefix: str, label: str, house_system: str) -> dict:
    lon = result[f"{prefix}_lon"]
    ruler = _domicile_ruler(lon)
    house_key = "p" if house_system == "placidus" else "w"
    return {"name": label, "longitude": lon, "sign": result[f"{prefix}_sign"],
            "house": result[f"{prefix}_house_{house_key}"],
            "ruler": ruler,
            "ruler_position": _planet_position(result, ruler, house_system)}


def calculate_classical_data(*, year: int, month: int, day: int, hour: int,
                             minute: int, location_id: str,
                             house_system: str = "placidus",
                             planets: list[str] | None = None,
                             fold: int | None = None) -> dict:
    """Project sect, triplicity lords, planet condition, lots and Jones pattern."""
    try:
        result = _compute_source(year=year, month=month, day=day, hour=hour,
                                 minute=minute, location_id=location_id,
                                 house_system=house_system, fold=fold)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)
    complement = result.get("complement_luminary_tri_stages") or {}

    from services.classical_engine import (
        compute_essential_dignities,
        compute_solar_state,
        compute_orientality,
        compute_receptions,
        TRADITIONAL_PLANETS,
        SOLAR_THRESHOLDS,
    )

    is_diurnal = (result["sect"] == "日生人")
    planets_by_key = {p["key"]: p for p in result["natal_planets_full"]}
    sun_lon = planets_by_key["sun"]["lon"]
    house_key = HOUSE_SYSTEMS[house_system]

    target_keys = TRADITIONAL_PLANETS
    if planets:
        allowed = {k.strip().lower() for k in planets}
        filtered = [k for k in TRADITIONAL_PLANETS if k in allowed]
        if filtered:
            target_keys = tuple(filtered)

    dignities_detail = []
    for pk in target_keys:
        p = planets_by_key[pk]
        lon = p["lon"]
        ed = compute_essential_dignities(pk, lon, is_diurnal)
        p_house = p[house_key]
        cross = "angular" if p_house in (1, 4, 7, 10) else ("succedent" if p_house in (2, 5, 8, 11) else "cadent")
        accidental = {
            "house": p_house,
            "cross": cross,
            "in_sect": (result["sect_labels"][house_system].get(p["cn"]) == "得时"),
            "retrograde": p["retrograde"],
        }
        if pk != "sun":
            sol = compute_solar_state(lon, sun_lon)
            accidental["solar_state"] = sol["state"]
            accidental["solar_state_zh"] = sol["state_zh"]
            accidental["solar_separation_deg"] = sol["solar_separation_deg"]
            ori = compute_orientality(lon, sun_lon)
            accidental["orientality"] = ori["orientality"]
            accidental["orientality_zh"] = ori["orientality_zh"]
        else:
            accidental["solar_state"] = "luminary"
            accidental["solar_state_zh"] = "发光体"
            accidental["orientality"] = "luminary"
            accidental["orientality_zh"] = "发光体"

        dignities_detail.append({
            "planet": pk,
            "planet_zh": p["cn"],
            "longitude": round(lon, 4),
            "sign": p["sign"],
            "essential_dignities": ed,
            "accidental_status": accidental,
        })
    receptions_data = compute_receptions(planets_by_key, result.get("aspects", []), is_diurnal)

    return {
        "status": "ok",
        "birth_context": result["birth_context"],
        "settings": {"zodiac": "tropical", "house_system": house_system},
        "sect": result["sect"],
        "sect_light": result["light_body"],
        "planet_sect_status": result["sect_labels"][house_system],
        "ascendant": {
            "longitude": result["asc_lon"], "sign": result["asc_sign_cn"],
            "domicile_ruler": _domicile_ruler(result["asc_lon"]),
            "domicile_ruler_position": _planet_position(
                result, _domicile_ruler(result["asc_lon"]), house_system),
            "first_triplicity_lord": result["asc_ruler"][house_system],
        },
        "planet_condition": _strip_text(result["planet_scores"][house_system]),
        "sect_light_triplicity": {
            "sequence": result["triplicity_seq"],
            "stages": _triplicity_stages(result["triplicity_stages"][house_system]),
        },
        "ascendant_triplicity": _strip_text(result["asc_tri_stages"][house_system]),
        "other_light_triplicity": _strip_text(complement.get(house_system)),
        "lots": [_lot(result, "fof", "福点", house_system),
                 _lot(result, "pos", "精神点", house_system)],
        "fortune_house_care": result[f"fortune_care_{'p' if house_system == 'placidus' else 'w'}"],
        "malefic_care": result[f"malefic_check_{'p' if house_system == 'placidus' else 'w'}"],
        "moon_phase": result["moon_phase"],
        "aspect_patterns": {k: v for k, v in result["phase_patterns"].items() if v},
        "lunations_around_birth": result["lunation_data"],
        "jones_pattern": _strip_text({k: v for k, v in result["jones_pattern"].items()
                                      if k != "distribution"}),
        "classical_dignities_detail": dignities_detail,
        "receptions": receptions_data,
        "solar_state_thresholds": SOLAR_THRESHOLDS,
    }


def calculate_lots_data(*, year: int, month: int, day: int, hour: int,
                        minute: int, location_id: str,
                        lots: list[str] | None = None,
                        house_system: str = "whole_sign",
                        fold: int | None = None) -> dict:
    """Calculate Hellenistic and Arabic lots on demand."""
    try:
        result = _compute_source(year=year, month=month, day=day, hour=hour,
                                 minute=minute, location_id=location_id,
                                 house_system=house_system, fold=fold)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)

    from services.classical_engine import compute_lots
    is_diurnal = (result["sect"] == "日生人")
    planets_map = {p["key"]: p["lon"] for p in result["natal_planets_full"]}
    asc_lon = result["asc_lon"]
    sun_lon = planets_map["sun"]
    moon_lon = planets_map["moon"]
    cusps = list(result["cusps"]) if result.get("cusps") else []

    lots_list = compute_lots(
        asc_lon=asc_lon, sun_lon=sun_lon, moon_lon=moon_lon,
        planets_map=planets_map, cusps=cusps, is_diurnal=is_diurnal,
        requested_lots=lots, house_system=house_system)
    return {
        "status": "ok",
        "birth_context": result["birth_context"],
        "settings": {"zodiac": "tropical", "house_system": house_system},
        "sect": result["sect"],
        "lots": lots_list,
    }


def _zr_period(p: dict) -> dict:
    return {"level": p["level"], "sign": p["sign_cn"], "start": p["start"],
            "end": p["end"], "age_start": p["age_start"], "age_end": p["age_end"],
            "peak": p.get("peak"), "loosing_of_bond": p.get("is_lb", False),
            "is_current": p.get("is_current", False)}


def calculate_releasing_data(*, year: int, month: int, day: int, hour: int,
                             minute: int, location_id: str, as_of: str | None = None,
                             fold: int | None = None) -> dict:
    """Zodiacal releasing from Fortune and Spirit, trimmed around one reference date."""
    try:
        result = _compute_source(year=year, month=month, day=day, hour=hour,
                                 minute=minute, location_id=location_id,
                                 house_system="placidus", fold=fold)
        ref_day, now = _reference_moment(as_of)
        from services.zodiacal_releasing import calculate_zodiacal_releasing
        zr = calculate_zodiacal_releasing(
            _birth_body(year, month, day, hour, minute, location_id,
                        result["birth_context"]["fold"]),
            max_level=3, now=now)
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)

    lots = {}
    for key, lot in zr["lots"].items():
        l1 = lot["periods"]
        cur1 = next((p for p in l1 if p.get("is_current")), None)
        cur2 = next((p for p in (cur1 or {}).get("children", []) if p.get("is_current")), None)
        lots[key] = {
            "lot": lot["lot_label"], "lot_sign": lot["lot_sign"],
            "releasing_sign": lot["releasing_sign"], "shifted": lot["shifted"],
            "level1": [_zr_period(p) for p in l1],
            "level2_in_current_level1": [_zr_period(p) for p in (cur1 or {}).get("children", [])],
            "level3_in_current_level2": [_zr_period(p) for p in (cur2 or {}).get("children", [])],
            "turning_points": lot["turning_points"],
        }
    return {
        "status": "ok",
        "birth_context": result["birth_context"],
        "as_of": ref_day.isoformat(),
        "settings": {"method": "Valens", "year_length_days": zr["year_length_days"],
                     "capricorn_years": zr["capricorn_years"],
                     "spirit_shifted": zr["spirit_shifted"], "levels": 3},
        "sect": zr["sect"],
        "lots": lots,
    }


def _lord(value):
    return (value or {}).get("name_zh")


def calculate_time_lord_data(*, year: int, month: int, day: int, hour: int,
                             minute: int, location_id: str, as_of: str | None = None,
                             house_system: str = "placidus", tradition: str = "abu_mashar",
                             fold: int | None = None) -> dict:
    """Firdaria and annual profections around one reference date."""
    try:
        if tradition not in ("abu_mashar", "al_biruni", "bonatti"):
            raise ValueError("tradition 只支持 abu_mashar、al_biruni 或 bonatti")
        result = _compute_source(year=year, month=month, day=day, hour=hour,
                                 minute=minute, location_id=location_id,
                                 house_system=house_system, fold=fold)
        ref_day, now = _reference_moment(as_of)
        from services.time_lords import (calculate_annual_profections_report,
                                         calculate_firdaria_report)
        body = _birth_body(year, month, day, hour, minute, location_id,
                           result["birth_context"]["fold"])
        fird = calculate_firdaria_report(dict(body), max_age=100,
                                         tradition=tradition, now=now)["firdaria"]
        prof = calculate_annual_profections_report(dict(body), max_age=100,
                                                   now=now)["annual_profections"]
    except (BirthContextError, ValueError) as exc:
        return _input_error(exc)

    current_major = next((m for m in fird["major_periods"] if m["is_current"]), None)
    sub_rows = [r for r in fird["rows"] if current_major
                and r["start_age"] >= current_major["start_age"]
                and r["end_age"] <= current_major["end_age"] + 1e-6]
    rows = prof["rows"]
    idx = next((i for i, r in enumerate(rows) if r["is_current"]), None)
    window = rows[max(0, idx - 1): idx + 4] if idx is not None else []
    return {
        "status": "ok",
        "birth_context": result["birth_context"],
        "as_of": ref_day.isoformat(),
        "firdaria": {
            "tradition": fird["tradition"], "sect": fird["sect"],
            "year_length_days": fird["year_length_days"],
            "major_periods": [{"lord": _lord(m["ruler"]), "start": m["start_date"],
                               "end": m["end_date"], "age_start": m["start_age"],
                               "age_end": m["end_age"], "is_current": m["is_current"]}
                              for m in fird["major_periods"]],
            "sub_periods_in_current_major": [
                {"major_lord": _lord(r["major_lord"]), "sub_lord": _lord(r["minor_lord"]),
                 "start": r["start_date"], "end": r["end_date"],
                 "is_current": r["is_current"]} for r in sub_rows],
        },
        "annual_profections": {
            "house_system": house_system,
            "boundary": prof["boundary"],
            "years": [{"age": r["age"], "start": r["start_date"], "end": r["end_date"],
                       "house": r["systems"][house_system]["house"],
                       "sign": r["systems"][house_system]["sign"]["name_zh"],
                       "lord_of_year": _lord(r["systems"][house_system]["lord"]),
                       "is_current": r["is_current"]} for r in window],
        },
    }
