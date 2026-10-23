"""Direction, factual states, compatibility and real MCP view delivery."""
import asyncio
import copy
import json
from pathlib import Path
import sys

import pytest

from services.mcp_structure_graph import calculate_graph_data
from services.natal_relationship_views import build_relationship_views, classify_routes
from services.natal_salience import build_salience

BIRTH = dict(year=2000, month=1, day=1, hour=12, minute=0,
             location_id='coord:39.904200,116.407400')


@pytest.fixture(scope='module')
def data():
    return build_salience(calculate_graph_data(**BIRTH))


def route(kind, **detail):
    return dict(kind=kind, detail=detail, source_refs=['/source_graph'])


def test_direction_exchange_and_shared_configuration_are_distinct():
    assert classify_routes('a', 'b', [route('dignity_relation', host='b', guest='a')], 6) == ['host_of_target']
    assert classify_routes('a', 'b', [route('dignity_relation', host='a', guest='b')], 6) == ['guest_of_target']
    assert classify_routes('a', 'b', [route('mutual_reception')], 6) == ['exchange']
    assert classify_routes('a', 'b', [route('shared_configuration')], 6) == ['shared_configuration']
    assert classify_routes('a', 'b', [route('future_kind')], 6) == ['unclassified']
    with pytest.raises(ValueError, match='endpoints'):
        classify_routes('a', 'b', [route('dignity_relation', host='b', guest='c')], 6)


@pytest.mark.parametrize('limit', [6, 8, 10])
def test_selected_orb_boundary_and_legal_legacy_views(limit):
    for angle, kind in [(0,'conjunction'), (60,'sextile_or_trine'), (90,'square_or_opposition'),
                        (120,'sextile_or_trine'), (180,'square_or_opposition')]:
        assert classify_routes('a','b',[route(kind, angle=angle, orb=limit)],limit) == ['degree_contact']
        for orb in (limit+0.000001, -1, float('nan'), True):
            with pytest.raises(ValueError, match='selected aspect view'):
                classify_routes('a','b',[route(kind, angle=angle, orb=orb)],limit)


def test_views_keep_background_and_do_not_use_states_to_delete_relations(data):
    changed = copy.deepcopy(data)
    p = changed['planet_profiles']['sun']
    p['resource_review']['candidates'] = [
        dict(planet='saturn', routes=[route('dignity_relation', host='saturn', guest='sun')]),
        dict(planet='moon', routes=[route('dignity_relation', host='sun', guest='moon')]),
        dict(planet='venus', routes=[route('mutual_reception')]),
        dict(planet='mars', routes=[route('square_or_opposition', id='probe', angle=90, orb=6)]),
        dict(planet='mercury', routes=[route('shared_configuration')]),
        dict(planet='uranus', routes=[route('future_kind')])]
    layer = build_relationship_views(changed)
    row = layer['planets']['sun']
    assert row['dependency_review'] == ['saturn','venus']
    assert row['direct_aspect_review'] == ['mars']
    assert row['context_review'] == ['mercury','moon','uranus']
    assert row['relations']['mars']['degree_contacts'][0]['phase']['status'] == 'unknown'
    assert row['relations']['venus']['degree_contacts'] == []
    for state in changed['planet_profiles'].values():
        state['retrograde'] = not state['retrograde']
        state['houses'] = dict(placidus=None, whole_sign=None)
        state['condition'] = None
        state['condition_availability'] = 'unavailable'
    other = build_relationship_views(changed)
    for key in ('dependency_review','direct_aspect_review','context_review','groups'):
        assert other['planets']['sun'][key] == row[key]
    assert other['states'] != layer['states']


def test_duplicate_and_order_invariance_and_no_mutation(data):
    changed = copy.deepcopy(data)
    for profile in changed['planet_profiles'].values():
        rows = profile['resource_review']['candidates']
        for candidate in rows:
            candidate['routes'] = list(reversed(candidate['routes'] * 2))
        profile['resource_review']['candidates'] = list(reversed(rows * 2))
    before = copy.deepcopy(changed)
    assert build_relationship_views(changed) == data['relationship_views']
    assert changed == before


def resolve(data, pointer):
    value = data
    for part in pointer.lstrip('/').split('/'):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


@pytest.mark.parametrize('orb_view', [6,8,10])
def test_full_states_all_relations_and_direct_contacts_retained(orb_view):
    graph = calculate_graph_data(**BIRTH)
    data = build_salience(graph, {'orb_view':orb_view})
    before = copy.deepcopy(data['planet_profiles'])
    layer = data['relationship_views']
    for target, row in layer['planets'].items():
        profile = data['planet_profiles'][target]
        state = resolve(data, row['target_state_ref'])
        assert {k:v for k,v in state.items() if k != 'condition_context'} == {
            k:v for k,v in profile.items() if k != 'resource_review'}
        assert set(row['all_associations']) == {c['planet'] for c in profile['resource_review']['candidates']}
        selected = set(row['dependency_review']) | set(row['direct_aspect_review'])
        assert selected.isdisjoint(row['context_review'])
        assert selected | set(row['context_review']) == set(row['all_associations'])
        assert set(row['direct_aspect_review']) == {
            e['to'] if e['from']==target else e['from'] for e in profile['aspects']}
        for other, relation in row['relations'].items():
            assert resolve(data, relation['target_state_ref'])['planet'] == target
            assert resolve(data, relation['counterpart_state_ref'])['planet'] == other
            for ref in relation['source_refs']:
                resolve(data, ref)
            assert relation['efficacy'] == 'not_evaluated'
    layer['states']['sun']['houses']['placidus'] = 'changed'
    assert data['planet_profiles'] == before


def test_partial_data_preserves_unknown_houses_and_outer_state():
    graph = calculate_graph_data(**{**BIRTH,'month':6,'day':21,'location_id':'coord:78.223200,15.646900'})
    assert graph['completeness'] == 'partial'
    layer = build_salience(graph)['relationship_views']
    assert len(layer['states']) == 10
    for state in layer['states'].values():
        assert all(h['availability']=='unavailable' and h['located_house'] is None
                   for h in state['condition_context']['houses'].values())
    assert layer['states']['uranus']['condition'] is None
    assert layer['states']['uranus']['condition_availability'] == 'classical_conditions_not_defined_for_outer_planets'


def test_real_stdio_selection_states_and_claim_verification():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run():
        params = StdioServerParameters(command=sys.executable,
            args=[str(Path(__file__).resolve().parents[1]/'mcp_server.py')])
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                tool = next(t for t in (await session.list_tools()).tools if t.name=='calculate_natal_salience')
                assert 'relationship_views' in tool.description
                for birth, orb in [(BIRTH,6),({**BIRTH,'month':6,'day':21,'location_id':'coord:78.223200,15.646900'},8)]:
                    reply = await session.call_tool('calculate_natal_salience',dict(birth,orb_view=orb,include=['relationship_views']))
                    assert not reply.isError
                    out = json.loads(reply.content[0].text)
                    assert out['status']=='ok' and out['quality']['status']=='passed', out
                    assert 'planet_profiles' not in out  # The selected layer has its own states.
                    layer = out['relationship_views']
                    for row in layer['planets'].values():
                        for relation in row['relations'].values():
                            for key in ('target_state_ref','counterpart_state_ref'):
                                assert resolve(out, relation[key])['planet'] in layer['states']
                    contacts = [c for row in layer['planets'].values() for r in row['relations'].values() for c in r['degree_contacts']]
                    assert contacts and any(c['phase']['status'] in ('applying','separating','exact') for c in contacts)
                    path='/relationship_views/planets/sun/dependency_review'
                    claims=[dict(quote='dependency list',path=path,value=resolve(out,path)),
                            dict(quote='incorrect dependency',path=path,value=['not-a-planet'])]
                    verified=await session.call_tool('verify_calculation_claims',dict(reference=out['calculation_reference'],claims=claims))
                    assert [c['verdict'] for c in json.loads(verified.content[0].text)['claims']] == ['supported','contradicted']
    asyncio.run(run())


def test_output_tampering_is_rejected():
    from services.mcp_salience import calculate_salience_data
    from services.mcp_result_facts import checked_result
    result=calculate_salience_data(**BIRTH)
    result['relationship_views']['states']['sun']['retrograde'] = True
    assert checked_result('calculate_natal_salience',result,BIRTH)['status']=='validation_failed'
