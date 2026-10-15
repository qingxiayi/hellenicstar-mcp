"""Workflow recommendations route only to registered tools and preserve choice boundaries."""

import asyncio
import json
import pytest

import mcp_server as m
from services.mcp_validation import validate_meta_output
from services.mcp_workflow import WORKFLOWS, recommend


def test_each_goal_uses_registered_tools_and_never_calculates():
    names = {tool.name for tool in asyncio.run(m.mcp.list_tools())}
    for goal, spec in WORKFLOWS.items():
        result = asyncio.run(m.recommend_workflow(goal=goal))
        assert result["status"] == "ok", (goal, result)
        assert result["first_calculation_tool"] == spec["steps"][0][0]
        assert {row["tool"] for row in result["steps"]} <= names
        assert validate_meta_output("recommend_workflow", result) == []
        assert "calculation_reference" not in result
        assert result["calculation_envelope"]["provenance"]["coverage"] == "not_applicable"


def test_natural_goal_and_ambiguous_goal():
    return_workflow = asyncio.run(m.recommend_workflow(goal="请看 2026 年的太阳返照"))
    assert return_workflow["goal"] == "solar_return"
    assert any("residence_location_id" in item
               for item in return_workflow["required_information"])
    assert return_workflow["steps"][-1]["tool"] == "verify_calculation_claims"

    ambiguous = asyncio.run(m.recommend_workflow(goal="想同时看太阳弧和行运"))
    assert ambiguous["status"] == "needs_clarification"
    assert {row["goal"] for row in ambiguous["options"]} == {"solar_arc", "transits"}
    assert "calculation_envelope" not in ambiguous

    unknown = asyncio.run(m.recommend_workflow(goal="想知道明年会不会中奖"))
    assert unknown["status"] == "needs_clarification"
    assert {row["goal"] for row in unknown["options"]} == set(WORKFLOWS)


def test_live_mcp_schema_and_call():
    listed = {tool.name: tool for tool in asyncio.run(m.mcp.list_tools())}
    assert set(listed["recommend_workflow"].inputSchema["required"]) == {"goal"}
    blocks = asyncio.run(m.mcp.call_tool("recommend_workflow", {"goal": "关系盘"}))
    data = json.loads(blocks[0].text)
    assert data["goal"] == "relationship"
    assert data["first_calculation_tool"] == "calculate_relationship_charts"
    assert data["steps"][0]["tool"] == "search_birthplace"


def test_unregistered_tool_is_not_recommended():
    available = {tool.name for tool in asyncio.run(m.mcp.list_tools())}
    available.remove("calculate_solar_arc")
    result = recommend("太阳弧", available)
    assert result == {"status": "unavailable", "error": "所需工具当前未注册。",
                      "missing_tools": ["calculate_solar_arc"]}


@pytest.mark.parametrize("goal,tool", [
    ("多技法综合时间线", "calculate_timeline_synthesis"),
    ("timeline synthesis", "calculate_timeline_synthesis"),
    ("土木流年大表图", "calculate_saturn_jupiter_cycles"),
    ("saturn jupiter cycles", "calculate_saturn_jupiter_cycles"),
])
def test_new_techniques_route_to_existing_tools(goal, tool):
    result = asyncio.run(m.recommend_workflow(goal=goal))
    assert result["status"] == "ok"
    assert result["first_calculation_tool"] == tool
    steps = result["steps"]
    assert steps[-1]["tool"] == "verify_calculation_claims"
    if tool == "calculate_timeline_synthesis":
        assert any("target_year" in x for x in result["required_information"])
    else:
        drawing = next(x for x in steps if x["tool"] == "render_saturn_jupiter_cycles")
        assert drawing["when"] == "用户要求出图时"


def test_new_workflows_preserve_ambiguity_and_check_renderer_availability():
    result = asyncio.run(m.recommend_workflow(goal="多技法综合时间线和太阳返照"))
    assert result["status"] == "needs_clarification"
    assert {x["goal"] for x in result["options"]} == {"timeline_synthesis", "solar_return"}
    available = {tool.name for tool in asyncio.run(m.mcp.list_tools())}
    available.remove("render_saturn_jupiter_cycles")
    result = recommend("土木流年大表图", available)
    assert result["status"] == "unavailable"
    assert result["missing_tools"] == ["render_saturn_jupiter_cycles"]
