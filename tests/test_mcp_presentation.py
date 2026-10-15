"""Optional response controls preserve the checked calculation and old calls."""

import asyncio
import inspect
import json

import mcp_server as m
from services.mcp_result_facts import CalculationClaim, CalculationReference
from services.mcp_validation import CONTRACTS, RENDER_SOURCES


BIRTH = dict(year=1990, month=4, day=15, hour=18, minute=0,
             location_id="gn:2988507", house_system="placidus")


def test_controls_appear_on_data_tools_only():
    listed = {tool.name: tool for tool in asyncio.run(m.mcp.list_tools())}
    for name in CONTRACTS:
        props = listed[name].inputSchema["properties"]
        assert "detail_level" in props and "include" in props
        assert "detail_level" not in inspect.signature(getattr(m, name).__wrapped__).parameters
    for name in set(RENDER_SOURCES) | {"verify_natal_claims", "verify_calculation_claims"}:
        props = listed[name].inputSchema["properties"]
        assert "detail_level" not in props and "include" not in props


def test_default_is_unchanged_and_selection_keeps_full_reference():
    full = asyncio.run(m.calculate_natal_chart(**BIRTH))
    explicit_full = asyncio.run(m.calculate_natal_chart(**BIRTH, detail_level="full"))
    assert explicit_full == full
    assert "presentation" not in full

    selected = asyncio.run(m.calculate_natal_chart(
        **BIRTH, detail_level="summary", include=["planets", "aspects"]))
    assert selected["status"] == "ok"
    assert "axes" not in selected and "house_cusps" not in selected
    assert "birth_context" in selected and "settings" in selected
    assert selected["planets"] == full["planets"][:5]
    assert selected["aspects"] == full["aspects"][:5]
    assert selected["presentation"]["omitted_array_items"]["/aspects"] == len(full["aspects"]) - 5
    assert selected["calculation_reference"] == full["calculation_reference"]
    assert selected["fact_reference"] == full["fact_reference"]
    assert "detail_level" not in selected["calculation_reference"]["input"]
    assert "include" not in selected["calculation_reference"]["input"]

    path = "/planets/0/house"
    claim = CalculationClaim(quote="首颗行星宫位", path=path,
                             value=full["planets"][0]["house"])
    verified = asyncio.run(m.verify_calculation_claims(
        reference=CalculationReference(**selected["calculation_reference"]),
        claims=[claim]))
    assert verified["counts"]["supported"] == 1


def test_include_only_and_invalid_controls():
    selected = asyncio.run(m.get_current_sky(
        moment="2026-10-08T12:00:00+08:00", include=["moon_phase"]))
    assert selected["status"] == "ok"
    assert "moon_phase" in selected and "sun" not in selected
    assert selected["presentation"]["omitted_array_items"] == {}
    assert asyncio.run(m.calculate_natal_chart(**BIRTH, detail_level="tiny"))["status"] == "invalid_input"
    assert asyncio.run(m.calculate_natal_chart(**BIRTH, include=[]))["status"] == "invalid_input"
    unknown = asyncio.run(m.calculate_natal_chart(**BIRTH, include=["not_a_section"]))
    assert unknown["status"] == "invalid_input"
    assert "planets" in unknown["available_fields"]


def test_fastmcp_call_accepts_controls():
    blocks = asyncio.run(m.mcp.call_tool(
        "calculate_natal_chart", {**BIRTH, "detail_level": "summary",
                                  "include": ["planets"]}))
    result = json.loads(blocks[0].text)
    assert result["status"] == "ok"
    assert len(result["planets"]) == 5
    assert "aspects" not in result
