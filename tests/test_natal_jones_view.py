"""Jones is a parallel view: it cannot change any natal selection or fact."""
import asyncio
import copy
import json
from pathlib import Path
import sys

import pytest

from services.mcp_structure_graph import calculate_graph_data
from services.natal_salience import build_salience
from services.natal_jones_view import project_observation_details

BIRTH = dict(year=2000, month=1, day=1, hour=12, minute=0,
             location_id='coord:39.904200,116.407400')


@pytest.fixture(scope='module')
def graph():
    return calculate_graph_data(**BIRTH)


def original_view(result):
    return {k: v for k, v in result.items() if k not in ('jones_view', 'view_comparison')}


@pytest.mark.parametrize('orb', [6, 8, 10])
def test_removing_or_replacing_jones_cannot_affect_any_original_layer(graph, orb):
    baseline = build_salience(graph, dict(orb_view=orb))
    without = copy.deepcopy(graph)
    without.pop('jones')
    assert original_view(build_salience(without, dict(orb_view=orb))) == original_view(baseline)
    changed = copy.deepcopy(graph)
    changed['jones'] = dict(engine_version='probe', pattern_en='unknown',
        confidence='ambiguous', high_focus_planet='土星', observation_details=dict(
            roles_available=True, classification=dict(borderline=True),
            roles=[dict(planet_name='木星', role_type='handle', longitude=12.0)]))
    result = build_salience(changed, dict(orb_view=orb))
    assert original_view(result) == original_view(baseline)
    assert result['jones_view']['upstream_focus']['planet'] == 'saturn'
    assert result['jones_view']['observation_roles'][0]['planet'] == 'jupiter'
    assert result['jones_view']['classification']['borderline'] is True
    assert all(e['family'] != 'chart_pattern' for e in result['evidence_index'].values())
    assert all('chart_pattern' not in r['role_groups'] for r in result['attention_layers']['planet_audit'])
    assert result['reading_plan']['identity_and_local']['pattern_evidence_ids'] == []


def test_projection_excludes_interpretations_and_preserves_boundary_uncertainty():
    raw=dict(borderline=True, confidence='moderate',
             borderline_alternates=[dict(pattern_en='Bucket', delta_deg=2)],
             key_roles=[dict(planet_name='火星', role_type='leader_loco',
                             longitude=10, description='Do not copy advice')],
             guide='Do not copy interpretation')
    facts=project_observation_details(raw)
    assert 'description' not in facts['roles'][0]
    assert 'guide' not in facts
    assert facts['classification']['borderline_alternates']==raw['borderline_alternates']


def test_wide_core_opposition_is_disclosed_but_not_a_selected_contact(graph):
    g=copy.deepcopy(graph)
    g['jones']['high_focus_planet']='水星'
    g['jones']['observation_details']=dict(roles_available=True,roles=[
        dict(planet_name='水星',role_type='sellar_hfp',longitude=0)],
        core_opposition=dict(planet_name='水星',opposite_planet_name='土星',orb=7,
                             upstream_orb_limit=10))
    # Fixture contains no 6-degree Mercury/Saturn opposition. The supplied
    # upstream classification must not manufacture one in the current view.
    out=build_salience(g)
    core=out['jones_view']['core_opposition']
    assert core['upstream_orb_limit']==10
    assert core['current_view']==dict(orb_view=6,has_aspect=False,aspect=None)
    assert not any(e['from']=='mercury' and e['to']=='saturn' and e['angle']==180
                   for e in out['priority_aspects'])


def test_complete_roles_contacts_and_comparison_do_not_rank_or_mutate(graph):
    before=copy.deepcopy(graph)
    out=build_salience(graph)
    view=out['jones_view']
    assert view['roles_status']=='available'
    assert len(view['observation_roles'])==len(graph['jones']['observation_details']['roles'])
    edges={e['id']:e for p in out['planet_profiles'].values() for e in p['aspects']}
    for contact in view['direct_contacts']:
        assert contact['aspect']==edges[contact['aspect']['id']]
        assert contact['aspect']['orb']<=6
    assert len(out['view_comparison']['rows'])==10
    for row in out['view_comparison']['rows']:
        audit=next(r for r in out['selection_audit'] if r['planet']==row['planet'])
        assert row['natal']['selected']==audit['selected']
    assert view['method']['score'] is None and out['view_comparison']['method']['score'] is None
    view['classification']['pattern_en']='mutated'
    assert graph==before


def test_missing_metadata_is_not_certainty_or_a_guessed_role(graph):
    g=copy.deepcopy(graph)
    g['jones']={'high_focus_planet':'unknown'}
    view=build_salience(g)['jones_view']
    assert view['upstream_focus']['status']=='unrecognized_focus'
    assert view['roles_status']=='not_supplied'
    assert view['observation_roles']==[] and view['observation_planets']==[]
    assert 'borderline' not in view['classification']


def test_partial_chart_retains_shape_but_not_fabricated_houses():
    graph=calculate_graph_data(**{**BIRTH,'month':6,'day':21,
                                  'location_id':'coord:78.223200,15.646900'})
    assert graph['completeness']=='partial'
    out=build_salience(graph)
    assert out['jones_view']['status']=='available'
    assert all(p['houses']['placidus'] is None for p in out['planet_profiles'].values())


def test_real_mcp_discovery_selective_delivery_and_claim_verification():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run():
        params=StdioServerParameters(command=sys.executable,
            args=[str(Path(__file__).resolve().parents[1]/'mcp_server.py')])
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                tool=next(t for t in (await session.list_tools()).tools if t.name=='calculate_natal_salience')
                assert 'jones_view' in tool.description and tool.inputSchema['properties']['orb_view']['default']==6
                reply=await session.call_tool(tool.name,dict(BIRTH,include=['schema_version','jones_view','view_comparison']))
                assert not reply.isError
                data=json.loads(reply.content[0].text)
                assert data['quality']['status']=='passed'
                assert data['schema_version']=='natal-priorities-v4'
                assert 'planet_profiles' not in data
                path='/jones_view/classification/pattern_en'
                claims=[dict(quote='pattern',path=path,value=data['jones_view']['classification']['pattern_en']),
                        dict(quote='false pattern',path=path,value='nonexistent')]
                check=await session.call_tool('verify_calculation_claims',dict(reference=data['calculation_reference'],claims=claims))
                assert [c['verdict'] for c in json.loads(check.content[0].text)['claims']]==['supported','contradicted']
    asyncio.run(run())


def test_tampered_parallel_output_is_rejected():
    from services.mcp_salience import calculate_salience_data
    from services.mcp_result_facts import checked_result
    data=calculate_salience_data(**BIRTH)
    data['jones_view']['classification']['pattern_en']='false'
    assert checked_result('calculate_natal_salience',data,BIRTH)['status']=='validation_failed'
