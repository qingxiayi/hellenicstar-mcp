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


@pytest.mark.parametrize('phrase,goal,tool,renderer', [
    ('画今日天象盘', 'sky_chart', 'calculate_sky_chart', 'render_sky_chart'),
    ('今日天象盘', 'sky_chart', 'calculate_sky_chart', 'render_sky_chart'),
    ('draw a sky chart', 'sky_chart', 'calculate_sky_chart', 'render_sky_chart'),
    ('看看现在的行运双盘', 'transit_snapshot', 'get_transit_snapshot', 'render_transit_biwheel'),
    ('current transits', 'transit_snapshot', 'get_transit_snapshot', 'render_transit_biwheel'),
    ('次限月相', 'progressed_lunation', 'calculate_progressed_lunation', None),
    ('progressed lunation', 'progressed_lunation', 'calculate_progressed_lunation', None),
    ('琼斯格局图', 'jones', 'calculate_classical_factors', 'render_jones_pattern'),
    ('Jones pattern', 'jones', 'calculate_classical_factors', 'render_jones_pattern'),
    ('关系观察', 'relationship_observation', 'calculate_relationship_observation', None),
    ('relationship observation', 'relationship_observation', 'calculate_relationship_observation', None),
    ('natal structure', 'natal_structure', 'calculate_natal_structure_graph', None),
    ('natal salience', 'salience', 'calculate_natal_salience', None),
    ('组合中点盘', 'composite', 'calculate_relationship_charts', 'render_composite_chart'),
    ('宫主定位链', 'house_rulers', 'calculate_house_rulers', None),
    ('相位出入窗口', 'aspect_windows', 'calculate_aspect_windows', None),
    ('生涯行运摘要', 'lifetime_transits', 'calculate_lifetime_transit_summary', None),
    ('土木进宫', 'house_ingresses', 'calculate_house_ingresses', None),
])
def test_specific_tasks_do_not_fall_back_to_generic_techniques(phrase, goal, tool, renderer):
    result = asyncio.run(m.recommend_workflow(goal=phrase))
    assert result['status'] == 'ok', result
    assert result['goal'] == goal
    assert result['first_calculation_tool'] == tool
    images = [s for s in result['steps'] if s['tool'].startswith('render_')]
    assert [s['tool'] for s in images] == ([renderer] if renderer else [])
    assert all(s['when'] == '用户要求出图时' for s in images)
    if goal == 'transit_snapshot':
        assert not any('from_date' in x for x in result['required_information'])
    if goal == 'sky_chart':
        assert '观测地点' in result['steps'][0]['purpose']
        assert not any('出生' in x for x in result['required_information'])


@pytest.mark.parametrize('phrase,choices', [
    ('sky chart and current sky', {'sky_chart', 'sky'}),
    ('natal structure and natal chart', {'natal_structure', 'natal'}),
    ('关系观察和比较盘', {'relationship_observation', 'relationship'}),
    ('次限月相和次限推进', {'progressed_lunation', 'secondary_progressions'}),
    ('行运双盘和未来三年的行运', {'transit_snapshot', 'transits'}),
])
def test_specific_match_does_not_swallow_an_independent_request(phrase, choices):
    result = asyncio.run(m.recommend_workflow(goal=phrase))
    assert result['status'] == 'needs_clarification'
    assert {x['goal'] for x in result['options']} == choices


@pytest.mark.parametrize('phrase', ['黄道释放 L4', '黄道释放第四层', 'zodiacal releasing level 4'])
def test_l4_retains_parent_selection_prerequisite(phrase):
    result = asyncio.run(m.recommend_workflow(goal=phrase))
    assert result['goal'] == 'releasing_l4'
    assert [s['tool'] for s in result['steps']] == [
        'search_birthplace', 'calculate_zodiacal_releasing',
        'calculate_zodiacal_releasing_l4', 'verify_calculation_claims']
    assert result['steps'][2]['when'] == '确认 L3 父周期后'
    assert any('parent_start' in x and 'parent_sign' in x for x in result['required_information'])


def test_new_route_never_calls_calculation_and_checks_missing_renderer(monkeypatch):
    def must_not_run(*args, **kwargs):
        raise AssertionError('Routing must not calculate a chart')
    monkeypatch.setattr(m.ext, 'sky_chart_data', must_not_run)
    result = asyncio.run(m.recommend_workflow(goal='画今日天象盘'))
    assert result['status'] == 'ok'
    names = {t.name for t in asyncio.run(m.mcp.list_tools())}
    result = recommend('画今日天象盘', names - {'render_sky_chart'})
    assert result['status'] == 'unavailable'
    assert result['missing_tools'] == ['render_sky_chart']


def test_synastry_is_not_silently_rendered_as_a_composite():
    result = asyncio.run(m.recommend_workflow(goal='比较盘'))
    assert result['goal'] == 'relationship'
    assert not any(s['tool'].startswith('render_') for s in result['steps'])


@pytest.mark.parametrize('phrase,choices', [
    ('画本命盘和天象', {'natal', 'sky_chart'}),
    ('画太阳弧和天象', {'solar_arc', 'sky_chart'}),
    ('画太阳返照和天象', {'solar_return', 'sky_chart'}),
    ('画琼斯图和天象', {'jones', 'sky_chart'}),
])
def test_shared_drawing_verb_preserves_each_requested_chart(phrase, choices):
    names = {t.name for t in asyncio.run(m.mcp.list_tools())}
    result = recommend(phrase, names)
    assert result['status'] == 'needs_clarification'
    assert {row['goal'] for row in result['options']} == choices
    assert result['next_action'] == 'ask_user'
    assert result['question']


@pytest.mark.parametrize('phrase', [
    '今天的行运到年底有哪些精确日期',
    '现在的行运到明年所有精确相位',
    '请看现在的行运精确日期',
    'current transits with exact dates through next year',
])
def test_event_search_is_not_misrouted_as_a_current_snapshot(phrase):
    result = asyncio.run(m.recommend_workflow(goal=phrase))
    assert result['goal'] == 'transits'
    assert result['first_calculation_tool'] == 'calculate_transits_to_natal'
    assert any('from_date' in item for item in result['required_information'])


@pytest.mark.parametrize('phrase', ['行运双盘以及精确日期', 'transit snapshot with exact dates'])
def test_explicit_snapshot_and_events_preserve_both_scopes(phrase):
    result = asyncio.run(m.recommend_workflow(goal=phrase))
    assert result['status'] == 'needs_clarification'
    assert {row['goal'] for row in result['options']} == {'transits', 'transit_snapshot'}


@pytest.mark.parametrize('goal', [key for key, spec in WORKFLOWS.items() if 'render_step' in spec])
def test_optional_renderer_does_not_block_data_workflow(goal):
    names = {t.name for t in asyncio.run(m.mcp.list_tools())}
    renderer = WORKFLOWS[goal]['render_step'][0]
    result = recommend(goal, names - {renderer})
    assert result['status'] == 'ok'
    assert not any(s['tool'] == renderer for s in result['steps'])


def test_explicit_data_request_has_no_image_step():
    result = asyncio.run(m.recommend_workflow(goal='只要本命盘数据，不要图片'))
    assert result['output_mode'] == 'data'
    assert not any(s['tool'].startswith('render_') for s in result['steps'])
    assert result['next_action'] == 'check_required_information'
    assert result['input_readiness'] == 'not_checked'


def test_image_only_does_not_require_separate_data_call_or_house_system():
    names = {t.name for t in asyncio.run(m.mcp.list_tools())}
    result = recommend('只画琼斯格局图', names - {'calculate_classical_factors', 'verify_calculation_claims'})
    assert result['status'] == 'ok'
    assert result['output_mode'] == 'image_only'
    assert result['first_calculation_tool'] == 'render_jones_pattern'
    assert [s['tool'] for s in result['steps']] == ['search_birthplace', 'render_jones_pattern']
    assert not any('宫制' in item for item in result['required_information'])
    live = asyncio.run(m.recommend_workflow(goal='只画琼斯格局图'))
    assert validate_meta_output('recommend_workflow', live) == []


def test_image_only_unsupported_chart_asks_instead_of_substituting():
    result = asyncio.run(m.recommend_workflow(goal='只画比较盘'))
    assert result['status'] == 'needs_clarification'
    assert result['reason'] == 'unsupported_output'
    assert 'steps' not in result


@pytest.mark.parametrize('phrase', ['黄道释放的 L4', '黄道释放的第四层', '黄道释放第四级'])
def test_l4_aliases_retain_the_parent_selection(phrase):
    result = asyncio.run(m.recommend_workflow(goal=phrase))
    assert result['goal'] == 'releasing_l4'
    assert any(s['when'] == '确认 L3 父周期后' for s in result['steps'])
