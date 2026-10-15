"""MCP projection must agree with the existing calculation and preserve time ambiguity."""

from services.calculator import compute
from services.mcp_natal import (calculate_classical_data, calculate_natal_data,
                                calculate_releasing_data, calculate_time_lord_data,
                                render_jones_pattern_png, render_natal_chart_png,
                                search_birthplace)


PARIS = "gn:2988507"
BIRTH = dict(year=1990, month=4, day=15, hour=18, minute=0, location_id=PARIS)


def test_mcp_table_reuses_miniprogram_values_for_both_house_systems():
    source = compute("", 1990, 4, 15, 18, 0, "", location_id=PARIS)
    for system, field in (("placidus", "house_p"), ("whole_sign", "house_w")):
        table = calculate_natal_data(year=1990, month=4, day=15, hour=18,
                                     minute=0, location_id=PARIS,
                                     house_system=system)
        assert table["status"] == "ok"
        assert table["birth_context"] == source["birth_context"]
        assert len(table["house_cusps"]) == 12
        assert table["aspects"] == source["aspects"]
        expected = {p["key"]: p for p in source["natal_planets_full"]}
        for planet in table["planets"]:
            original = expected[planet["key"]]
            assert planet["longitude"] == original["lon"]
            assert planet["house"] == original[field]
        if system == "placidus":
            assert [c["longitude"] for c in table["house_cusps"]] == list(source["cusps"])
        else:
            asc_sign = int(source["asc_lon"] // 30)
            assert [c["longitude"] for c in table["house_cusps"]] == [
                ((asc_sign + i) % 12) * 30.0 for i in range(12)]


def test_place_ambiguity_and_unknown_time_are_not_guessed():
    found = search_birthplace("Paris")
    options = found["options"]
    assert {p["country_code"] for p in options} >= {"FR", "US"}
    assert found["next_action"] == "ask_user"
    assert found["required_fields"] == ["location_id"]
    assert calculate_natal_data(year=1990, month=4, day=15, hour=None,
                                minute=0, location_id=PARIS)["status"] == "needs_clarification"
    assert calculate_natal_data(year=1990, month=4, day=15, hour=18,
                                minute=0, location_id="")["status"] == "needs_clarification"


def test_coordinate_location_id_reuses_natal_timezone_and_rejects_bad_values():
    import pytest
    from services.location_resolver import LocationResolver, coordinate_location_id

    location_id = coordinate_location_id(48.8566, 2.3522)
    snap = LocationResolver().resolve(location_id=location_id)
    assert snap.tz_iana == "Europe/Paris"
    chart = calculate_natal_data(year=1990, month=4, day=15, hour=18,
                                 minute=0, location_id=location_id)
    assert chart["status"] == "ok"
    assert chart["birth_context"]["source"] == "timezonefinder"
    assert chart["birth_context"]["tz_iana"] == "Europe/Paris"
    assert chart["birth_context"]["lat"] == 48.8566
    for lat, lng in ((91, 2), (48, 181), (float("nan"), 2), (True, 2)):
        with pytest.raises(ValueError):
            coordinate_location_id(lat, lng)
    assert LocationResolver().resolve(location_id="coord:91.000000,2.000000") is None


def test_dst_overlap_and_gap_require_user_correction():
    base = dict(year=2024, month=11, day=3, hour=1, minute=30,
                location_id="gn:5128581")
    ambiguous = calculate_natal_data(**base)
    assert ambiguous["status"] == "ambiguous"
    assert [c["fold"] for c in ambiguous["candidates"]] == [0, 1]
    first = calculate_natal_data(**base, fold=0)
    second = calculate_natal_data(**base, fold=1)
    assert first["status"] == second["status"] == "ok"
    assert first["birth_context"]["utc_offset"] == -4
    assert second["birth_context"]["utc_offset"] == -5
    gap = calculate_natal_data(year=2024, month=3, day=10, hour=2, minute=30,
                               location_id="gn:5128581")
    assert gap["status"] == "nonexistent"


def test_mcp_wheel_reuses_existing_png_renderer_for_both_house_systems():
    for system in ("placidus", "whole_sign"):
        info, png = render_natal_chart_png(
            year=1990, month=4, day=15, hour=18, minute=0,
            location_id=PARIS, house_system=system)
        assert info["status"] == "ok"
        assert info["house_system"] == system
        assert png and png.startswith(b"\x89PNG\r\n\x1a\n")
        assert int.from_bytes(png[16:20], "big") == 720
        assert int.from_bytes(png[20:24], "big") == 720
    invalid, image = render_natal_chart_png(
        year=1990, month=4, day=15, hour=None, minute=0,
        location_id=PARIS)
    assert invalid["status"] == "needs_clarification" and image is None


def test_jones_image_reuses_miniprogram_pattern_and_geometry():
    birth = dict(year=1989, month=7, day=11, hour=12, minute=30,
                 location_id="gn:1791247")
    source = compute("", 1989, 7, 11, 12, 30, "", location_id=birth["location_id"])
    info, png = render_jones_pattern_png(**birth)
    assert info["status"] == "ok"
    assert info["pattern_en"] == source["jones_pattern"]["pattern_en"] == "See-Saw"
    assert info["state_label"] == source["jones_pattern"]["state_label"]
    assert png and png.startswith(b"\x89PNG\r\n\x1a\n")
    assert int.from_bytes(png[16:20], "big") == 720
    assert int.from_bytes(png[20:24], "big") == 720
    invalid, image = render_jones_pattern_png(**{**birth, "hour": None})
    assert invalid["status"] == "needs_clarification" and image is None


def test_mcp_streamable_http_protocol_lists_and_calls_tools():
    import asyncio
    import json
    import uuid
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp_server import app, PUBLIC_BASE

    async def check():
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app, client=(str(uuid.uuid4()), 12345))
            async with httpx.AsyncClient(transport=transport,
                                         base_url="http://localhost") as http:
                policy = await http.get("/mcp/privacy")
                assert policy.status_code == 200
                assert "出生资料" in policy.text
                assert policy.headers["cache-control"] == "no-store"
                assert (await http.get("/mcp/support")).status_code == 200
                assert (await http.get("/mcp/terms")).status_code == 200
                icon = await http.get("/mcp/icon.png")
                assert icon.status_code == 200 and icon.content.startswith(b"\x89PNG")
                async with streamable_http_client("http://localhost/mcp", http_client=http) as streams:
                    async with ClientSession(streams[0], streams[1]) as session:
                        await session.initialize()
                        names = {t.name for t in (await session.list_tools()).tools}
                        assert names == {"search_birthplace", "resolve_birth_coordinates", "calculate_natal_chart",
                                         "render_jones_pattern", "verify_natal_claims", "verify_calculation_claims",
                                         "get_capabilities", "get_agent_protocol", "recommend_workflow",
                                         "render_natal_chart", "calculate_classical_factors",
                                         "calculate_zodiacal_releasing", "calculate_time_lords",
                                         *EXTENDED_TOOLS}
                        capabilities = await session.call_tool("get_capabilities", {})
                        assert not capabilities.isError
                        assert json.loads(capabilities.content[0].text)["tool_count"] == len(names)
                        protocol = await session.call_tool("get_agent_protocol", {})
                        assert not protocol.isError
                        text = json.loads(protocol.content[0].text)["content"]
                        resource = await session.read_resource("hellenicstar://agent-protocol")
                        prompt = await session.get_prompt("hellenicstar_agent_protocol")
                        assert text == resource.contents[0].text == prompt.messages[0].content.text
                        rel = await session.call_tool("calculate_relationship_charts", {
                            "person_a": {"year": 1990, "month": 4, "day": 15, "hour": 18,
                                         "minute": 0, "location_id": PARIS},
                            "person_b": {"year": 1988, "month": 8, "day": 1, "hour": 9,
                                         "minute": 30, "location_id": PARIS}})
                        assert json.loads(rel.content[0].text)["status"] == "ok"
                        timeline = await session.call_tool("calculate_timeline_synthesis", {
                            **BIRTH, "target_year": 2026})
                        assert not timeline.isError
                        timeline_data = json.loads(timeline.content[0].text)
                        assert timeline_data["status"] == "ok"
                        assert timeline_data["quality"]["status"] == "passed"
                        assert timeline_data["calculation_envelope"]["tool"] == "calculate_timeline_synthesis"
                        claim = await session.call_tool("verify_calculation_claims", {
                            "reference": timeline_data["calculation_reference"],
                            "claims": [{"quote": "第一条时间线事件", "path": "/events/0/date",
                                        "value": timeline_data["events"][0]["date"]}]})
                        assert not claim.isError
                        assert json.loads(claim.content[0].text)["counts"]["supported"] == 1
                        result = await session.call_tool("search_birthplace", {"query": "Paris"})
                        assert not result.isError
                        assert json.loads(result.content[0].text)["status"] == "ok"
                        resolved = await session.call_tool("resolve_birth_coordinates", {
                            "latitude": 48.8566, "longitude": 2.3522})
                        coordinate_id = json.loads(resolved.content[0].text)["location_id"]
                        assert coordinate_id == "coord:48.856600,2.352200"
                        coord_chart = await session.call_tool("calculate_natal_chart", {
                            "year": 1990, "month": 4, "day": 15,
                            "hour": 18, "minute": 0, "location_id": coordinate_id, "house_system": "placidus"})
                        assert json.loads(coord_chart.content[0].text)["birth_context"]["tz_iana"] == "Europe/Paris"
                        wheel = await session.call_tool("render_natal_chart", {
                            "year": 1990, "month": 4, "day": 15,
                            "hour": 18, "minute": 0, "location_id": PARIS,
                            "house_system": "whole_sign"})
                        assert not wheel.isError
                        assert [c.type for c in wheel.content] == ["text", "image"]
                        assert wheel.content[1].mimeType == "image/png"
                        url = wheel.structuredContent["image_url"]
                        assert url.startswith(f"{PUBLIC_BASE}/mcp/chart/")
                        served = await http.get(url.removeprefix(PUBLIC_BASE))
                        assert served.status_code == 200
                        assert served.content.startswith(b"\x89PNG")
                        jones_image = await session.call_tool("render_jones_pattern", {
                            "year": 1989, "month": 7, "day": 11,
                            "hour": 12, "minute": 30, "location_id": "gn:1791247"})
                        assert not jones_image.isError
                        assert jones_image.structuredContent["pattern_en"] == "See-Saw"
                        assert jones_image.content[1].mimeType == "image/png"
                        assert (await http.get("/mcp/chart/" + "0" * 64 + ".png")).status_code == 404
                        tools = {t.name: t for t in (await session.list_tools()).tools}
                        assert tools["render_composite_chart"].meta["openai/outputTemplate"] == \
                            "ui://widget/chart-wheel.html"
                        widget = await session.read_resource("ui://widget/chart-wheel.html")
                        assert widget.contents[0].mimeType == "text/html+skybridge"

    asyncio.run(check())


def test_classical_factors_project_natal_calculation_without_interpretation():
    import json
    source = compute("", 1990, 4, 15, 18, 0, "", location_id=PARIS)
    data = calculate_classical_data(**BIRTH, house_system="whole_sign")
    assert data["status"] == "ok"
    assert data["sect"] == source["sect"] == "日生人"
    assert data["sect_light_triplicity"]["sequence"] == source["triplicity_seq"]
    assert data["lots"][0]["longitude"] == source["fof_lon"]
    assert data["lots"][1]["longitude"] == source["pos_lon"]
    # Virgo rising: domicile ruler Mercury; Venus is the first earth triplicity lord.
    assert data["ascendant"]["domicile_ruler"] == "水星"
    assert data["ascendant"]["first_triplicity_lord"] == "金星"
    # Fortune in Taurus: Venus in Pisces is the 7th whole-sign house from Virgo.
    assert data["lots"][0]["ruler"] == "金星"
    assert data["lots"][0]["ruler_position"]["house"] == 7
    assert data["jones_pattern"]["pattern_en"] == source["jones_pattern"]["pattern_en"]
    text = json.dumps(data, ensure_ascii=False)
    assert "event_text" not in text and '"description"' not in text


def test_timing_tools_mark_the_same_current_periods_as_the_miniprogram_services():
    from datetime import datetime, timezone
    from services.time_lords import calculate_firdaria_report
    from services.zodiacal_releasing import calculate_zodiacal_releasing
    now = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
    body = dict(BIRTH)

    zr = calculate_releasing_data(**BIRTH, as_of="2026-10-08")
    full = calculate_zodiacal_releasing(dict(body), max_level=3, now=now)
    for lot in ("fortune", "spirit"):
        expected = next(p for p in full["lots"][lot]["periods"] if p["is_current"])
        current = [p for p in zr["lots"][lot]["level1"] if p["is_current"]]
        assert [(p["sign"], p["start"]) for p in current] == [
            (expected["sign_cn"], expected["start"])]
        assert sum(p["is_current"] for p in zr["lots"][lot]["level2_in_current_level1"]) == 1

    lords = calculate_time_lord_data(**BIRTH, as_of="2026-10-08")
    fird = calculate_firdaria_report(dict(body), now=now)["firdaria"]["current"]
    current_sub = [p for p in lords["firdaria"]["sub_periods_in_current_major"]
                   if p["is_current"]]
    assert [(p["major_lord"], p["sub_lord"], p["start"]) for p in current_sub] == [
        (fird["major_lord"]["name_zh"], fird["minor_lord"]["name_zh"], fird["start_date"])]
    current_year = [y for y in lords["annual_profections"]["years"] if y["is_current"]]
    assert [(y["age"], y["house"]) for y in current_year] == [(36, 1)]


def test_timing_tools_do_not_guess_repeated_time_or_bad_reference_date():
    ny = dict(year=2024, month=11, day=3, hour=1, minute=30, location_id="gn:5128581")
    assert calculate_releasing_data(**ny)["status"] == "ambiguous"
    assert calculate_time_lord_data(**ny)["status"] == "ambiguous"
    assert calculate_time_lord_data(**ny, fold=1)["birth_context"]["utc_offset"] == -5
    assert calculate_time_lord_data(**BIRTH, as_of="2026-13-01")["status"] == "invalid_input"
    assert calculate_time_lord_data(**BIRTH, tradition="x")["status"] == "invalid_input"


EXTENDED_TOOLS = {"calculate_solar_arc", "calculate_transits_to_natal", "calculate_timeline_synthesis", "get_transit_snapshot",
                  "calculate_saturn_jupiter_cycles", "calculate_house_ingresses",
                  "calculate_progressed_lunation", "calculate_solar_return",
                  "render_solar_return_chart", "calculate_relationship_charts",
                  "render_composite_chart", "get_current_sky",
                  "calculate_house_rulers", "calculate_zodiacal_releasing_l4",
                  "calculate_lifetime_transit_summary", "calculate_aspect_windows",
                  "calculate_sky_chart", "render_sky_chart",
                  "render_transit_biwheel", "render_solar_arc_biwheel", "calculate_lunar_return", "render_lunar_return_chart", "calculate_secondary_progressions", "render_secondary_progressions_chart", "calculate_davison_chart", "render_davison_chart", "calculate_relocation_chart", "render_relocation_chart"}
EXTENDED_TOOLS.add("render_saturn_jupiter_cycles")
PARTNER = dict(year=1988, month=8, day=1, hour=9, minute=30, location_id=PARIS)


def test_extended_tools_match_the_miniprogram_services():
    import swisseph as swe
    from services import mcp_extended as ext
    from services.forecast_natal import build_forecast_natal
    from services.relationship_charts import build_relationship_charts
    from services.solar_arc_compute import compute_solar_arc_events
    from services.solar_return import compute_solar_return_full
    from services.transit_lifetime import compute_range_events

    snap = build_forecast_natal(dict(BIRTH))
    arc = ext.solar_arc_data(**BIRTH, age_from=30, age_to=40, as_of="2026-10-08")
    source = compute_solar_arc_events(snap, 1990, 4, 15, 18, 0, age_from=30, age_to=40,
                                      wheel_age=36.5)
    assert [m["date"] for m in arc["aspect_matrix"]] == [m["date"] for m in source["matrix"]]
    assert arc["axis_contacts_by_directed_points"] == source["type1"]

    events = ext.transit_events_data(**BIRTH, from_date="2026-01-01", to_date="2026-12-31")
    direct = compute_range_events(snap, swe.julday(2026, 1, 1, 0), swe.julday(2026, 12, 31, 24),
                                  target_scope="all")
    assert [e["exact_utc"] for e in events["events"]] == [e["exact_utc"] for e in direct["events"]]

    ret = ext.solar_return_data(**BIRTH, target_year=2026, residence_location_id=PARIS)
    sr = compute_solar_return_full(1990, 4, 15, 18, 0, 48.85341, 2.3488, 2026,
                                   48.85341, 2.3488, residence_tz="Europe/Paris",
                                   birth_location_id=PARIS)
    assert ret["solar_return"]["utc"] == sr["sr_utc"]

    rel = ext.relationship_data(person_a=BIRTH, person_b=PARTNER)
    rc = build_relationship_charts(compute("", 1990, 4, 15, 18, 0, "", location_id=PARIS),
                                   compute("", 1988, 8, 1, 9, 30, "", location_id=PARIS))
    assert len(rel["synastry_aspects"]) == len(rc["synastry"]["aspects"])
    assert rel["composite_chart"]["axes"]["上升点"]["longitude"] == round(
        rc["charts"]["composite"]["axes"]["ascendant"]["longitude"], 4)


def test_extended_tools_keep_birth_time_and_range_guards():
    from services import mcp_extended as ext
    ny = dict(year=2024, month=11, day=3, hour=1, minute=30, location_id="gn:5128581")
    assert ext.solar_arc_data(**ny)["status"] == "ambiguous"
    assert ext.saturn_jupiter_data(**ny)["status"] == "ambiguous"
    assert ext.relationship_data(person_a=BIRTH, person_b=ny)["status"] == "ambiguous"
    too_long = ext.transit_events_data(**BIRTH, from_date="2020-01-01", to_date="2026-12-31")
    assert too_long["status"] == "invalid_input"
    naive = ext.transit_snapshot_data(**BIRTH, moment="2026-10-08T12:00:00")
    assert naive["status"] == "invalid_input"


def test_remaining_miniprogram_algorithms_reach_the_plugin():
    import json
    from services import mcp_extended as ext

    source = compute("", 1990, 4, 15, 18, 0, "", location_id=PARIS)
    classical = calculate_classical_data(**BIRTH)
    assert classical["malefic_care"] == source["malefic_check_p"]
    assert classical["fortune_house_care"] == source["fortune_care_p"]
    assert classical["aspect_patterns"]["t_square"] == source["phase_patterns"]["t_square"]
    assert classical["lunations_around_birth"] == source["lunation_data"]

    chains = ext.house_ruler_data(**BIRTH)
    first = chains["houses"][0]
    assert first["is_chart_ruler"] and first["cusp_sign"] == "处女座"
    # Virgo rising: the traditional chain starts at Mercury, the domicile ruler.
    assert first["tracks"][0]["house_ruler"] == "水星"
    assert len(chains["houses"]) == 12

    from services.zodiacal_releasing import calculate_zodiacal_releasing_l4
    l4 = ext.releasing_l4_data(**BIRTH, lot="fortune", parent_start="2026-08-24",
                               parent_sign="GEMINI", as_of="2026-10-08")
    direct = calculate_zodiacal_releasing_l4(dict(BIRTH), lot="fortune",
                                             parent_start="2026-08-24",
                                             parent_sign="GEMINI")
    assert [p["start"] for p in l4["level4"]] == [p["start"] for p in direct["periods"]]

    windows = ext.aspect_window_data(moment="2026-10-08T12:00:00+08:00",
                                     location_id=PARIS)
    assert windows["aspect_count"] == len(windows["aspects"]) > 0
    assert all(a["total_days"] >= 0 for a in windows["aspects"])

    sky = ext.sky_chart_data(moment="2026-10-08T12:00:00+08:00", location_id=PARIS)
    assert sky["local_time"] == "2026-10-08 06:00"
    assert len(sky["house_cusps"]) == 12 and sky["planets"]


def test_biwheel_and_sky_wheels_render_and_guard_inputs():
    from services import mcp_extended as ext
    for render in (
        lambda: ext.render_transit_biwheel_png(**BIRTH, moment="2026-10-08T12:00:00+08:00"),
        lambda: ext.render_solar_arc_biwheel_png(**BIRTH, as_of="2026-10-08"),
        lambda: ext.render_saturn_jupiter_cycles_png(**BIRTH, as_of="2026-10-08", max_age=80),
        lambda: ext.render_sky_chart_png(moment="2026-10-08T12:00:00+08:00",
                                         location_id=PARIS),
    ):
        info, png = render()
        assert info["status"] == "ok"
        assert png and png.startswith(b"\x89PNG\r\n\x1a\n")

    ny = dict(year=2024, month=11, day=3, hour=1, minute=30, location_id="gn:5128581")
    assert ext.render_transit_biwheel_png(**ny)[0]["status"] == "ambiguous"
    assert ext.render_solar_arc_biwheel_png(**ny)[0]["status"] == "ambiguous"
    assert ext.render_solar_arc_biwheel_png(**BIRTH, age=99)[0]["status"] == "invalid_input"
    assert ext.sky_chart_data(moment="2026-10-08T12:00:00+08:00")["status"] == "needs_clarification"
