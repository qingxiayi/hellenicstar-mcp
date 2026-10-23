"""Sprint 5 timeline regressions and observed public-calculator day markers."""
import asyncio
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from time import monotonic

import pytest
import swisseph as swe

from services.forecast_natal import build_forecast_natal
from services.mcp_natal import _compute_source
from services.secondary_progressions import PLANET_DEFS
from services.solar_arc_engine import TROPICAL_YEAR_DAYS
from services.zodiacal_releasing import calculate_zodiacal_releasing
from services.timeline_synthesis import (NATURES, TECHNIQUE_PRIORITY, WEIGHTS,
                                         _resonances, _sort_key,
                                         compute_timeline_synthesis)


@pytest.fixture(scope="module")
def emma():
    birth = dict(year=1990, month=4, day=15, hour=18, minute=0,
                 location_id="gn:2988507")
    natal = _compute_source(**birth, house_system="placidus", fold=None)
    birth["fold"] = natal["birth_context"]["fold"]
    return natal, birth


def test_emma_2026_timeline_is_stable_and_matches_existing_event_families(emma):
    natal, birth = emma
    started = monotonic()
    first = compute_timeline_synthesis(natal, birth, 2026)
    elapsed = monotonic() - started
    second = compute_timeline_synthesis(natal, birth, 2026)
    assert first == second
    # This is a local performance budget on a fixed sample, not a production SLA.
    assert elapsed < 2.0
    assert first["event_count"] == len(first["events"])
    assert first["events"] == sorted(first["events"], key=_sort_key)
    assert {row["technique"] for row in first["events"]} == set(TECHNIQUE_PRIORITY)
    assert all(row["nature"] in NATURES and row["weight"] in WEIGHTS
               for row in first["events"])
    assert all(datetime.fromisoformat(row["exact_utc"].replace("Z", "+00:00")).tzinfo
               for row in first["events"])
    assert all("2026-01-01" <= row["date"] < "2027-01-01"
               for row in first["events"])
    assert first["settings"]["timezone"] == "Europe/Paris"
    assert first["settings"]["pyswisseph_package_version"]
    assert len(first["settings"]["ephemeris_expected_sha256"]) == 3
    # Fixed local regression markers; these are not presented as external proof.
    assert ("2026-06-06", "firdaria", "planet:sun") in {
        (e["date"], e["technique"], e["focus"]) for e in first["events"]
    }
    assert ("2026-12-10", "secondary_progressions", "sign:taurus") in {
        (e["date"], e["technique"], e["focus"]) for e in first["events"]
    }


def test_three_year_window_is_bounded_and_preserves_prior_year(emma):
    natal, birth = emma
    started = monotonic()
    wide = compute_timeline_synthesis(natal, birth, 2026, 3)
    assert monotonic() - started < 2.0
    narrow = compute_timeline_synthesis(natal, birth, 2026)
    assert all("2026-01-01" <= row["date"] < "2029-01-01"
               for row in wide["events"])
    assert Counter(e["technique"] for e in wide["events"])["secondary_progressions"] > 0
    assert [(e["technique"], e["nature"], e["date"], e["focus"]) for e in wide["events"]
            if e["date"] < "2027-01-01"] == [
                (e["technique"], e["nature"], e["date"], e["focus"])
                for e in narrow["events"]]


def test_birth_year_starts_at_birth_instead_of_january(emma):
    natal, birth = emma
    result = compute_timeline_synthesis(natal, birth, 1990)
    assert result["events"]
    assert all("1990-04-15" <= row["date"] < "1991-01-01"
               for row in result["events"])


def test_period_dates_match_existing_releasing_engine(emma):
    natal, birth = emma
    zr = calculate_zodiacal_releasing(
        {**birth, "fof_lon": natal["fof_lon"], "pos_lon": natal["pos_lon"],
         "sect": natal["sect"]}, max_level=2,
        now=datetime.fromisoformat("2026-01-01T00:00:00+00:00"))
    expected = set()
    for lot_key, lot in zr["lots"].items():
        for major in lot["periods"]:
            for period in (major, *major["children"]):
                if period["start"].startswith("2026"):
                    expected.add((lot_key, period["level"], period["sign"], period["start"]))
    timeline = compute_timeline_synthesis(natal, birth, 2026)
    actual = {(e["source"]["lot"], e["source"]["level"], e["source"]["sign"], e["date"])
              for e in timeline["events"] if e["technique"] == "zodiacal_releasing"
              and e["nature"] != "period_active"}
    assert actual == expected


def test_secondary_crossings_are_geometrically_exact(emma):
    natal, birth = emma
    snapshot = build_forecast_natal(birth)
    timeline = compute_timeline_synthesis(natal, birth, 2026, snapshot=snapshot)
    bodies = dict(PLANET_DEFS)
    checked = 0
    for row in timeline["events"]:
        if row["technique"] != "secondary_progressions":
            continue
        moment = datetime.fromisoformat(row["exact_utc"].replace("Z", "+00:00"))
        hour = moment.hour + moment.minute / 60 + moment.second / 3600
        civil_jd = swe.julday(moment.year, moment.month, moment.day, hour)
        progressed_jd = snapshot.birth_jd_ut + (civil_jd - snapshot.birth_jd_ut) / TROPICAL_YEAR_DAYS
        values, _ = swe.calc_ut(progressed_jd, bodies[row["source"]["planet"]],
                                swe.FLG_SWIEPH | swe.FLG_SPEED)
        lon = values[0]
        error = abs((lon - row["source"]["longitude"] + 180) % 360 - 180)
        one_civil_minute_deg = abs(values[3]) / TROPICAL_YEAR_DAYS / 1440
        assert error <= one_civil_minute_deg + 1e-6
        checked += 1
    assert checked > 0


def test_resonance_counts_distinct_techniques_and_source_rows():
    rows = [
        {"index": 0, "technique": "firdaria", "nature": "period_start", "weight": "context",
         "focus": "planet:saturn", "exact_utc": "2026-01-01T00:00:00Z",
         "source": {"planet": "saturn", "end_utc": "2026-02-01T00:00:00Z"}},
        {"index": 1, "technique": "secondary_progressions", "nature": "exact_aspect",
         "weight": "exact", "focus": "planet:saturn", "exact_utc": "2026-01-15T00:00:00Z",
         "source": {"planet": "moon", "target": "saturn"}},
        {"index": 2, "technique": "transits", "nature": "axis_contact", "weight": "exact",
         "focus": "axis:mc", "exact_utc": "2026-01-16T00:00:00Z",
         "source": {"planet": "saturn", "target": "mc"}},
        {"index": 3, "technique": "secondary_progressions", "nature": "exact_aspect",
         "weight": "exact", "focus": "planet:saturn", "exact_utc": "2026-03-01T00:00:00Z",
         "source": {"planet": "venus", "target": "saturn"}},
    ]
    assert _resonances(rows) == [{
        "focus": "planet:saturn", "start_utc": "2026-01-15T00:00:00Z",
        "end_utc": "2026-01-15T00:00:00Z",
        "techniques": ["firdaria", "secondary_progressions"],
        "technique_count": 2, "event_indices": [0, 1], "event_count": 2,
    }]


@pytest.mark.parametrize("target,span", [(2026, 0), (2026, 4), (1899, 1), (2026, True),
                                           (1989, 1), (2090, 1)])
def test_invalid_or_unsupported_windows_rejected(emma, target, span):
    natal, birth = emma
    with pytest.raises(ValueError):
        compute_timeline_synthesis(natal, birth, target, span)


def test_resonance_excludes_period_expired_before_later_exact_hit():
    rows = [
        {"index": 0, "technique": "firdaria", "nature": "period_start", "weight": "context",
         "focus": "axis:mc", "exact_utc": "2026-01-01T00:00:00Z",
         "source": {"start_utc": "2026-01-01T00:00:00Z", "end_utc": "2027-01-01T00:00:00Z"}},
        {"index": 1, "technique": "zodiacal_releasing", "nature": "period_start", "weight": "context",
         "focus": "axis:mc", "exact_utc": "2026-01-01T00:00:00Z",
         "source": {"start_utc": "2026-01-01T00:00:00Z", "end_utc": "2026-01-10T00:00:00Z"}},
        {"index": 2, "technique": "transits", "nature": "axis_contact", "weight": "exact",
         "focus": "axis:mc", "exact_utc": "2026-01-20T00:00:00Z", "source": {}},
    ]
    result = _resonances(rows)
    assert len(result) == 1
    assert result[0]["event_indices"] == [0, 2]
    assert result[0]["event_count"] == 2
    assert result[0]["technique_count"] == 2


def test_transit_timeline_keeps_middle_retrograde_contact(emma):
    from services.transit_natal import compute_filtered_events
    from services.timeline_synthesis import _jd_from_utc
    from zoneinfo import ZoneInfo
    natal, birth = emma
    snapshot = build_forecast_natal(birth)
    zone = ZoneInfo(natal["birth_context"]["tz_iana"])
    start = datetime(2026, 1, 1, tzinfo=zone)
    end = datetime(2029, 1, 1, tzinfo=zone)
    args = dict(planets=("jupiter", "saturn", "uranus", "neptune", "pluto"),
                natal_points=("asc", "mc", "dsc", "ic"), aspects=(0.0,), max_days=None)
    collapsed = compute_filtered_events(snapshot, _jd_from_utc(start), _jd_from_utc(end), **args)
    assert collapsed == compute_filtered_events(snapshot, _jd_from_utc(start),
                                                _jd_from_utc(end), collapse_series=True, **args)
    complete = compute_filtered_events(snapshot, _jd_from_utc(start), _jd_from_utc(end),
                                       collapse_series=False, **args)
    assert len(complete["events"]) > len(collapsed["events"])
    timeline = compute_timeline_synthesis(natal, birth, 2026, 3, snapshot=snapshot)
    actual = [row for row in timeline["events"] if row["technique"] == "transits"]
    assert len(actual) == len(complete["events"])
    jupiter_asc = [row for row in actual if row["source"]["planet"] == "jupiter"
                   and row["source"]["target"] == "asc"]
    assert [row["source"]["contact_index"] for row in jupiter_asc] == [1, 2, 3]
    assert any(row["date"] == "2028-01-30" and row["source"]["contact_index"] == 2
               for row in actual)


@pytest.mark.parametrize("birth,year,expected", [
    (dict(year=1990, month=4, day=15, hour=18, minute=0,
          location_id="gn:2988507"), 2026,
     [("2026-12-10", "sign:taurus"), ("2028-11-29", "sign:gemini")]),
    (dict(year=1948, month=11, day=14, hour=21, minute=14,
          location_id="gn:2643743"), 2028,
     [("2028-05-13", "sign:aries"), ("2030-11-25", "sign:taurus")]),
])
def test_public_progressed_moon_ingress_golden_set(birth, year, expected):
    """Observed on WitchcraftDaily's public calculator; day-level budget."""
    natal = _compute_source(**birth, house_system="placidus", fold=None)
    result = compute_timeline_synthesis(natal, birth, year, 3)
    actual = [(e["date"], e["focus"]) for e in result["events"]
              if e["technique"] == "secondary_progressions"
              and e["nature"] == "sign_ingress"]
    assert actual == expected


def test_public_ephemeris_brackets_three_jupiter_asc_contacts(emma):
    """Cafe Astrology daily tables bracket these dates, not minute-level roots."""
    natal, birth = emma
    result = compute_timeline_synthesis(natal, birth, 2026, 3)
    contacts = [e for e in result["events"] if e["technique"] == "transits"
                and e["source"]["planet"] == "jupiter"
                and e["source"]["target"] == "asc"]
    assert [(e["date"], e["source"]["contact_index"]) for e in contacts] == [
        ("2027-12-25", 1), ("2028-01-30", 2), ("2028-08-08", 3)]


def test_public_progressed_moon_natal_sun_conjunction_day_and_orb(emma):
    """WitchcraftDaily UTC dates/orbs; ±0.025° allows its observed offset.

    This verifies the event day and nearby trend, not the minute-level root.
    """
    from services.timeline_synthesis import _jd_from_utc
    natal, birth = emma
    snapshot = build_forecast_natal(birth)
    timeline = compute_timeline_synthesis(natal, birth, 2026, snapshot=snapshot)
    hits = [e for e in timeline["events"] if e["technique"] == "secondary_progressions"
            and e["nature"] == "exact_aspect" and e["source"]["planet"] == "moon"
            and e["source"]["target"] == "sun" and e["source"]["angle"] == 0]
    assert [e["date"] for e in hits] == ["2026-08-20"]
    observed_orbs = {19: 0.05, 20: 0.01, 21: 0.03}
    for day, external_orb in observed_orbs.items():
        civil_jd = _jd_from_utc(datetime(2026, 8, day, tzinfo=timezone.utc))
        progressed_jd = (snapshot.birth_jd_ut
                         + (civil_jd - snapshot.birth_jd_ut) / TROPICAL_YEAR_DAYS)
        moon_lon = swe.calc_ut(progressed_jd, swe.MOON, swe.FLG_SWIEPH)[0][0]
        natal_sun = snapshot.planets["sun"].longitude
        local_orb = abs((moon_lon - natal_sun + 180) % 360 - 180)
        assert abs(local_orb - external_orb) <= 0.025


def test_public_progressed_moon_natal_jupiter_square_day_and_orb():
    """Second public birth sample on WitchcraftDaily; UTC day-level budget."""
    from services.timeline_synthesis import _jd_from_utc
    birth = dict(year=1948, month=11, day=14, hour=21, minute=14,
                 location_id="gn:2643743")
    natal = _compute_source(**birth, house_system="placidus", fold=None)
    snapshot = build_forecast_natal(birth)
    timeline = compute_timeline_synthesis(natal, birth, 2028, snapshot=snapshot)
    hits = [e for e in timeline["events"] if e["technique"] == "secondary_progressions"
            and e["nature"] == "exact_aspect" and e["source"]["planet"] == "moon"
            and e["source"]["target"] == "jupiter" and e["source"]["angle"] == 90]
    assert [e["exact_utc"][:10] for e in hits] == ["2028-05-09"]
    target_longitude = hits[0]["source"]["longitude"]
    for day, external_orb in ((8, 0.03), (9, 0.00), (10, 0.03)):
        civil_jd = _jd_from_utc(datetime(2028, 5, day, tzinfo=timezone.utc))
        progressed_jd = (snapshot.birth_jd_ut
                         + (civil_jd - snapshot.birth_jd_ut) / TROPICAL_YEAR_DAYS)
        moon_lon = swe.calc_ut(progressed_jd, swe.MOON, swe.FLG_SWIEPH)[0][0]
        local_orb = abs((moon_lon - target_longitude + 180) % 360 - 180)
        assert abs(local_orb - external_orb) <= 0.025


def test_public_ephemeris_brackets_neptune_mc_direct_and_retrograde_contacts():
    """WitchcraftDaily 2030 daily tables: minute-rounded positions only."""
    birth = dict(year=1948, month=11, day=14, hour=21, minute=14,
                 location_id="gn:2643743")
    natal = _compute_source(**birth, house_system="placidus", fold=None)
    timeline = compute_timeline_synthesis(natal, birth, 2030)
    contacts = [e for e in timeline["events"] if e["technique"] == "transits"
                and e["source"]["planet"] == "neptune"
                and e["source"]["target"] == "mc"]
    assert [(e["date"], e["source"]["direction"]) for e in contacts] == [
        ("2030-06-30", "direct"), ("2030-08-02", "retrograde")]
    assert abs(natal["axes"]["mc"]["lon"] - (13 + 18 / 60)) < 1 / 60
    # Public table rounds to arcminutes. One full arcminute includes the
    # observed small inter-engine offset; it does not prove an exact day.
    observed = ((6, 28, 18), (6, 29, 18), (6, 30, 19),
                (8, 1, 19), (8, 2, 19), (8, 3, 18), (8, 4, 17))
    for month, day, minute in observed:
        jd = swe.julday(2030, month, day, 12)  # table is at 12:00 UTC
        longitude = swe.calc_ut(jd, swe.NEPTUNE, swe.FLG_SWIEPH)[0][0]
        assert abs(longitude - (13 + minute / 60)) <= 1 / 60
    assert "2030-06-28" <= contacts[0]["date"] <= "2030-07-01"
    assert "2030-08-01" <= contacts[1]["date"] <= "2030-08-04"


def test_public_timeline_tool_envelope_quality_and_claim_recalculation():
    import mcp_server
    from services.mcp_result_facts import CalculationClaim, CalculationReference

    birth = dict(year=1990, month=4, day=15, hour=18, minute=0,
                 location_id="gn:2988507")
    result = asyncio.run(mcp_server.calculate_timeline_synthesis(
        **birth, target_year=2026))
    assert result["status"] == "ok"
    assert result["quality"]["status"] == "passed"
    assert result["calculation_envelope"]["tool"] == "calculate_timeline_synthesis"
    assert result["calculation_envelope"]["provenance"]["coverage"] == "partial"
    first = result["events"][0]
    verified = asyncio.run(mcp_server.verify_calculation_claims(
        reference=CalculationReference.model_validate(result["calculation_reference"]),
        claims=[CalculationClaim(quote="首条时间线事件", path="/events/0", value=first)]))
    assert verified["status"] == "ok"
    assert verified["counts"] == dict(supported=1, contradicted=0, unverified=0)
    assert verified["coverage"]["independent_algorithm_verification"] is False


def test_public_timeline_tool_requires_year_and_rejects_invalid_span():
    import mcp_server
    birth = dict(year=1990, month=4, day=15, hour=18, minute=0,
                 location_id="gn:2988507")
    missing = asyncio.run(mcp_server.calculate_timeline_synthesis(**birth))
    assert missing["status"] == "needs_clarification"
    assert missing["required_fields"] == ["target_year"]
    invalid = asyncio.run(mcp_server.calculate_timeline_synthesis(
        **birth, target_year=2026, span_years=4))
    assert invalid["status"] == "invalid_input"


@pytest.mark.parametrize("damage", ["order", "nature", "timezone", "resonance_count"])
def test_timeline_contract_rejects_semantic_corruption(emma, damage):
    from services.mcp_validation import validate_output
    natal, birth = emma
    good = {"status": "ok", "birth_context": natal["birth_context"],
            **compute_timeline_synthesis(natal, birth, 2026)}
    assert good["resonances"]
    bad = deepcopy(good)
    if damage == "order":
        bad["events"][0], bad["events"][1] = bad["events"][1], bad["events"][0]
    elif damage == "nature":
        bad["events"][0]["nature"] = "prediction"
    elif damage == "timezone":
        bad["events"][0]["local_at"] = bad["events"][0]["exact_utc"]
    else:
        bad["resonances"][0]["technique_count"] += 1
    assert validate_output("calculate_timeline_synthesis", good,
                           {**birth, "target_year": 2026, "span_years": 1}) == []
    assert validate_output("calculate_timeline_synthesis", bad,
                           {**birth, "target_year": 2026, "span_years": 1})


def test_secondary_moon_scan_detects_two_crossings_within_seven_days(monkeypatch):
    from types import SimpleNamespace
    from datetime import timezone, timedelta
    from zoneinfo import ZoneInfo
    from services import timeline_synthesis as timeline
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    natal_jd = timeline._jd_from_utc(start)
    snapshot = SimpleNamespace(birth_jd_ut=natal_jd, planets={}, axes={})
    real_calc = swe.calc_ut

    def two_crossings(jd, body, flags=swe.FLG_SWIEPH):
        if body != swe.MOON:
            return real_calc(jd, body, flags)
        day = (jd - natal_jd) * TROPICAL_YEAR_DAYS
        longitude = 29 + (day - 2) * (day - 4)
        return ((longitude % 360, 0, 0, 0, 0, 0), swe.FLG_SWIEPH)

    monkeypatch.setattr(timeline.swe, "calc_ut", two_crossings)
    events = []
    timeline._secondary_events(events, snapshot, start, end, ZoneInfo("UTC"))
    ingresses = [row for row in events if row["nature"] == "sign_ingress"]
    assert len(ingresses) == 2
    assert [row["focus"] for row in sorted(ingresses, key=timeline._sort_key)] == [
        "sign:aries", "sign:taurus"]
    assert all(start <= datetime.fromisoformat(row["exact_utc"].replace("Z", "+00:00")) < end
               for row in ingresses)
