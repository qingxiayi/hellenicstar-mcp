"""MCP gates and claim verification must not turn missing evidence into success."""

import asyncio
import copy
import itertools
import json
import uuid

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from services import mcp_extended as ext
from services.mcp_facts import verify_natal_claims_data
from services.mcp_natal import calculate_natal_data

BIRTH = dict(year=1990, month=4, day=15, hour=18, minute=0, location_id="gn:2988507")


@pytest.fixture(scope="module")
def natal():
    return calculate_natal_data(**BIRTH, house_system="placidus")


def claim(kind, point, value, **extra):
    return dict(kind=kind, point=point, value=value, quote=f"{point} {kind} {value}", **extra)


def test_verifier_uses_real_chart_and_reports_conflicts_and_coverage(natal):
    checks = [claim("sign", "太阳", "Aries"),
              claim("sign", "moon", "处女座"),
              claim("house", "moon", 3),
              claim("retrograde", "sun", False),
              claim("aspect", "海王星", "拱", other_point="水星"),
              claim("aspect", "mercury", "square", other_point="neptune"),
              claim("sign", "ascendant", "处女"),
              claim("psychology", "moon", "缺乏安全感"),
              claim("sign", "sun", "白羊座", scope="solar_return")]
    result = verify_natal_claims_data(natal["fact_reference"], checks)
    assert result["assessment"] == "contains_conflicts"
    assert result["counts"] == dict(supported=5, contradicted=2, unverified=2)
    wrong_moon = result["claims"][1]
    assert wrong_moon["evidence"] == [{"path": "/planets/1/sign", "value": "射手座"}]
    assert result["claims"][4]["evidence"][0]["value"]["angle"] == 120
    assert "未核对整篇解读" in result["scope"]


def test_house_system_is_part_of_evidence_and_reference(natal):
    whole = calculate_natal_data(**BIRTH, house_system="whole_sign")
    assert whole["fact_reference"] != natal["fact_reference"]
    result = verify_natal_claims_data(whole["fact_reference"], [claim("house", "moon", 3)])
    assert result["claims"][0]["verdict"] == "contradicted"
    assert result["claims"][0]["evidence"][0]["value"] == 4


@pytest.mark.parametrize("field,value", [("house_system", "whole_sign"), ("hour", 17)])
def test_changed_chart_input_cannot_reuse_a_reference(natal, field, value):
    ref = copy.deepcopy(natal["fact_reference"])
    ref["input"][field] = value
    result = verify_natal_claims_data(ref, [claim("sign", "sun", "白羊座")])
    assert result["status"] == "reference_mismatch"
    assert "claims" not in result


def test_verifier_recomputes_and_rejects_changed_calculation(natal, monkeypatch):
    calls = []
    original = calculate_natal_data

    def changed(**inputs):
        calls.append(inputs)
        table = original(**inputs)
        table["fact_reference"]["fingerprint"] = "0" * 64
        return table

    monkeypatch.setattr("services.mcp_natal.calculate_natal_data", changed)
    result = verify_natal_claims_data(natal["fact_reference"], [claim("sign", "sun", "白羊座")])
    assert calls == [natal["fact_reference"]["input"]]
    assert result["status"] == "reference_mismatch"


@pytest.mark.parametrize("check", [claim("house", "sun", True),
                                   claim("house", "sun", "8"),
                                   claim("house", "sun", 13),
                                   claim("retrograde", "asc", True),
                                   claim("sign", "fortune", "白羊座"),
                                   claim("sign", "sun", "unknown"),
                                   claim("sign", "sun", "白羊座", other_point="moon"),
                                   claim("aspect", "sun", "none", other_point="moon")])
def test_unknown_or_ambiguous_claims_are_not_marked_supported(natal, check):
    result = verify_natal_claims_data(natal["fact_reference"], [check])
    assert result["counts"] == dict(supported=0, contradicted=0, unverified=1)
    assert result["assessment"] == "no_verifiable_claims"
    assert result["coverage"]["checked_claims"] == 0


def test_absent_aspect_is_not_called_invented_or_supported(natal):
    pairs = {frozenset((a["point1"], a["point2"])) for a in natal["aspects"]}
    first, second = next(pair for pair in itertools.combinations(
        [p["key"] for p in natal["planets"]], 2) if frozenset(pair) not in pairs)
    result = verify_natal_claims_data(natal["fact_reference"],
                                     [claim("aspect", first, "trine", other_point=second)])
    assert result["claims"][0]["verdict"] == "unverified"


def test_no_empty_claims_or_unknown_reference_version(natal):
    assert verify_natal_claims_data(natal["fact_reference"], [])["status"] == "invalid_input"
    ref = {**natal["fact_reference"], "schema_version": "future"}
    assert verify_natal_claims_data(ref, [claim("sign", "sun", "白羊座")])["status"] == "invalid_reference"
    mixed = verify_natal_claims_data(natal["fact_reference"], [
        claim("sign", "sun", "白羊座"), claim("psychology", "sun", "独立")])
    assert mixed["assessment"] == "partially_verified"
    assert mixed["coverage"]["checked_claims"] == 1
    assert not mixed["coverage"]["full_report_checked"]


@pytest.mark.parametrize("render", [False, True])
def test_return_location_missing_blocks_data_and_image(render, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Return calculation must not run with an implicit location")

    monkeypatch.setattr("services.solar_return.compute_solar_return_full", forbidden)
    result = (ext.render_solar_return_png if render else ext.solar_return_data)(
        **BIRTH, target_year=2026)
    if render:
        result, png = result
        assert png is None
    assert result["status"] == "needs_clarification"
    assert result["required_fields"] == ["residence_location_id"]


def test_lots_and_sky_chart_do_not_use_an_implicit_location():
    for fn in (ext.aspect_window_data, ext.sky_chart_data):
        result = fn(moment="2026-10-08T12:00:00+08:00")
        assert result["status"] == "needs_clarification"
        assert result["required_fields"] == ["location_id"]


def test_relationship_dst_clarification_identifies_the_person():
    repeated = dict(year=2024, month=11, day=3, hour=1, minute=30, location_id="gn:5128581")
    result = ext.relationship_data(person_a=BIRTH, person_b=repeated)
    assert result["status"] == "ambiguous"
    assert result["required_fields"] == ["person_b.fold"]
    assert [c["fold"] for c in result["candidates"]] == [0, 1]


def test_actual_mcp_contract_clarifies_partial_inputs_and_verifies_claims():
    import runpy
    from pathlib import Path

    # A FastMCP session manager can run only once. Give this protocol test its
    # own module instance, independent of the existing protocol regression.
    app = runpy.run_path(str(Path(__file__).resolve().parents[1] / "mcp_server.py"))["app"]

    async def check():
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app, client=(str(uuid.uuid4()), 12345))
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as http:
                async with streamable_http_client("http://localhost/mcp", http_client=http) as streams:
                    async with ClientSession(streams[0], streams[1]) as session:
                        await session.initialize()

                        async def call(name, args):
                            response = await session.call_tool(name, args)
                            assert not response.isError, response
                            return json.loads(response.content[0].text)

                        tools = {t.name: t for t in (await session.list_tools()).tools}
                        assert len(tools) == 48
                        assert {"verify_natal_claims", "get_capabilities", "get_agent_protocol"} <= set(tools)
                        for name in ("calculate_natal_chart", "render_natal_chart",
                                     "calculate_classical_factors", "calculate_solar_arc",
                                     "calculate_solar_return", "render_solar_return_chart"):
                            missing = await call(name, {"year": 1990})
                            assert missing["status"] == "needs_clarification"
                            assert {"month", "day", "hour", "minute", "location_id"} <= set(missing["required_fields"])
                            assert missing["next_action"] == "ask_user"
                        no_house = await call("calculate_natal_chart", BIRTH)
                        assert no_house["required_fields"] == ["house_system"]
                        no_place = await call("calculate_solar_return", {
                            **BIRTH, "target_year": 2026, "house_system": "placidus"})
                        assert no_place["required_fields"] == ["residence_location_id"]
                        partial = await call("calculate_relationship_charts", {
                            "person_a": BIRTH, "person_b": {"year": 1988}})
                        assert "person_b.hour" in partial["required_fields"]
                        repeated = await call("calculate_natal_chart", {
                            "year": 2024, "month": 11, "day": 3, "hour": 1, "minute": 30,
                            "location_id": "gn:5128581", "house_system": "placidus"})
                        assert repeated["required_fields"] == ["fold"]
                        table = await call("calculate_natal_chart", {**BIRTH, "house_system": "placidus"})
                        result = await call("verify_natal_claims", {
                            "reference": table["fact_reference"],
                            "claims": [claim("sign", "sun", "白羊座"), claim("house", "moon", 4)]})
                        assert result["counts"] == dict(supported=1, contradicted=1, unverified=0)
                        generic = await call("verify_calculation_claims", {
                            "reference": table["calculation_reference"],
                            "claims": [{"quote": "太阳第八宫", "path": "/planets/0/house", "value": 8},
                                       {"quote": "太阳第九宫", "path": "/planets/0/house", "value": 9}]})
                        assert generic["counts"] == dict(supported=1, contradicted=1, unverified=0)
                        invalid = await session.call_tool("calculate_natal_chart", {
                            **BIRTH, "hour": True, "house_system": "placidus"})
                        assert invalid.isError

    asyncio.run(check())


def test_natal_verifier_recognizes_node_and_lot_source_aliases(natal):
    rows = [a for a in natal['aspects']
            if a['point1'] in {'true_north_lunar_node', 'part_of_spirit', 'part_of_fortune'}]
    assert rows
    checks = [claim('aspect', a['point1'], a['angle'], other_point=a['point2']) for a in rows]
    out = verify_natal_claims_data(natal['fact_reference'], checks)
    assert out['counts']['supported'] == len(checks)
