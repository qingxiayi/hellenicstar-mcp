"""Selection distinctions must survive live MCP discovery and optional routing."""
import asyncio
import pytest
import mcp_server as m
from services.mcp_workflow import recommend

@pytest.fixture(scope='module')
def tools():
    return {t.name:t for t in asyncio.run(m.mcp.list_tools())}

@pytest.mark.parametrize('phrase,expected', [
    ('行星相位扫描', 'scan_planetary_aspects'),
    ('scan planetary aspects', 'scan_planetary_aspects'),
    ('planetary_aspect_scan', 'scan_planetary_aspects'),
    ('本命行运', 'calculate_transits_to_natal'),
    ('现在的行运', 'get_transit_snapshot'),
    ('土木进宫', 'calculate_house_ingresses'),
    ('福点公式', 'calculate_lots'),
    ('日返', 'calculate_solar_return'),
    ('日反', 'calculate_solar_return'),
])
def test_nearby_requests_have_distinct_routes(tools, phrase, expected):
    result = recommend(phrase,set(tools))
    assert result['status']=='ok',result
    assert result['first_calculation_tool']==expected


def test_sky_pair_scan_never_requests_birth_or_location(tools):
    available=set(tools)-{'search_birthplace','resolve_birth_coordinates'}
    result=recommend('planetary_aspect_scan',available)
    assert result['status']=='ok'
    assert [s['tool'] for s in result['steps']]==['scan_planetary_aspects','verify_calculation_claims']
    assert all('出生' not in x and 'location_id' not in x for x in result['required_information'])
    mixed=recommend('行星相位扫描和本命行运',set(tools))
    assert mixed['reason']=='multiple_goals'
    assert {o['goal'] for o in mixed['options']}=={'planetary_aspect_scan','transits'}
    assert recommend('只画行星相位扫描图',set(tools))['reason']=='unsupported_output'

@pytest.mark.parametrize('name', ['calculate_classical_factors','calculate_house_ingresses','scan_planetary_aspects'])
def test_low_score_tools_explain_every_input_in_discovery(tools,name):
    props=tools[name].inputSchema['properties']
    assert all(p.get('description') for p in props.values())
    assert 'Returns' in tools[name].description


def test_pair_scan_explains_fixed_natal_alternative_and_date_format(tools):
    scan=tools['scan_planetary_aspects']
    assert 'calculate_transits_to_natal' in scan.description
    assert 'calculate_aspect_windows' in scan.description
    assert 'No birth data or location' in scan.description
    assert 'YYYY-MM-DD' in scan.inputSchema['properties']['start_date']['description']
    assert 'north_node' in scan.inputSchema['properties']['planet_a']['description']
    assert 'UTC' in scan.inputSchema['properties']['end_date']['description']


def test_classical_and_house_ingress_distinctions_are_explicit(tools):
    assert all(n in tools['calculate_classical_factors'].description for n in
               ['calculate_natal_chart','calculate_natal_structure_graph','calculate_natal_salience','calculate_lots'])
    assert all(n in tools['calculate_house_ingresses'].description for n in
               ['calculate_saturn_jupiter_cycles','calculate_transits_to_natal','get_transit_snapshot'])
