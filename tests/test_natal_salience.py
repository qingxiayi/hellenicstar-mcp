"""Rule-selection acceptance, without a target ranking for a personal chart."""
import asyncio
import copy
import json
import random
from pathlib import Path
import sys
import pytest
from services.natal_structure_graph import calculate_structure_graph, TEN, SEVEN
from services.natal_salience import build_salience, normalize_config, terminal_metrics
from services.natal_house_rulers import TRADITIONAL_RULERS, MODERN_RULERS

BIRTH=dict(year=2000,month=1,day=1,hour=12,minute=0,location_id='coord:39.904200,116.407400')


@pytest.mark.parametrize('case_id,expected',[
    ('random-000', {('mars','mercury','saturn'):7}),
    ('random-001', {('moon','sun'):5, ('saturn',):2}),
    ('random-019', {('venus',):7}),
])
def test_distinct_synthetic_births_preserve_distinct_terminal_solutions(case_id,expected):
    from services.mcp_structure_graph import calculate_graph_data
    path=Path(__file__).parent/'fixtures/natal-structure-synthetic.json'
    row=next(r for r in json.loads(path.read_text()) if r['id']==case_id)
    graph=calculate_graph_data(**{k:v for k,v in row.items() if k not in ('id','group')})
    result=build_salience(graph)
    actual={tuple(c['members']):c['numerator'] for c in result['core_structures']}
    assert actual==expected
    assert sum(actual.values())==7
    # Reported birth metadata is not an input to the pure extraction layer.
    graph['birth_context']={'label':'different person', 'year':1234}
    assert build_salience(graph)==result


def test_triplicity_roles_disclosed_without_changing_active_dignity():
    from services.classical_engine import DOROTHEAN_TRIPLICITY
    from services.natal_resource_context import triplicity_context
    for sign, rulers in DOROTHEAN_TRIPLICITY.items():
        for active in rulers[:2]:
            for planet in SEVEN:
                condition={'essential': {'triplicity': planet==active,
                                         'active_triplicity_lord': active}}
                old=copy.deepcopy(condition)
                context=triplicity_context(planet,sign,condition)
                assert condition==old
                assert context['counted_by_engine']==(planet==active)
                assert context['planet_roles']==[r for r,p in context['rulers'].items() if p==planet]
                order=list(rulers) if active==rulers[0] else [rulers[1],rulers[0],rulers[2]]
                assert context['is_triplicity_ruler']==(planet in rulers)
                assert context['sect_order']==order
                assert context['sect_priority']==(order.index(planet)+1 if planet in order else None)
    context=triplicity_context('jupiter',0,{'essential': {
        'triplicity':False,'active_triplicity_lord':'sun'}})
    assert context['planet_roles']==['night']
    assert context['counted_by_engine'] is False
    assert context['is_triplicity_ruler'] is True and context['sect_priority']==2
    assert context['counting_reason']=='secondary_ruler_not_counted_by_active_only_policy'
    assert triplicity_context('uranus',0,None)['status'].startswith('classical_conditions_not_defined')


def test_triplicity_unknown_sect_does_not_fabricate_priority():
    from services.natal_resource_context import triplicity_context
    for active in (None,'venus'):
        c=triplicity_context('jupiter',0,{'essential':dict(triplicity=False,active_triplicity_lord=active)})
        assert c['is_triplicity_ruler'] is True
        assert c['sect_order'] is None and c['sect_priority'] is None
        assert c['order_status']=='unknown_sect'


def test_peregrine_topics_keep_uncredited_triplicity_identity(graph):
    data=build_salience(graph)
    members=[p for p,v in data['planet_profiles'].items()
             if v['triplicity_context'].get('is_triplicity_ruler') and
             not v['triplicity_context']['counted_by_engine'] and v['condition']['essential']['peregrine']]
    assert members
    for p in members:
        context=data['planet_profiles'][p]['triplicity_context']
        topic=next(t for t in data['resource_checks']['topics'] if t['id']==f'state:{p}:peregrine')
        assert topic['fact']['policy_scope']=='active_day_or_night_only'
        assert topic['fact']['triplicity_context']==context
        assert topic['verdict'] is None
        for t in data['resource_checks']['topics']:
            if t['kind']=='soft_aspect_with_essential_condition' and t['fact']['counterpart']==p:
                assert t['fact']['counterpart_triplicity_context']==context
        for profile in data['planet_profiles'].values():
            for row in profile['resource_review']['candidates']:
                if row['planet']==p:
                    assert row['counterpart_state']['condition_context']['triplicity_context']==context


def test_resource_review_keeps_counterpart_limits_without_verdict(graph):
    result=build_salience(graph)
    for row in result['priority_planets']:
        p=row['profile']; review=p['resource_review']
        assert review['verdict'] is None
        expected={p['dispositor']['planet']}
        expected.update(r['planet1'] if r['planet2']==row['planet'] else r['planet2'] for r in p['receptions'])
        expected.update(e['to'] if e['from']==row['planet'] else e['from'] for e in p['aspects'])
        for relation in result['reception_facts']['rows']:
            if relation['meets_dignity_threshold'] and row['planet'] in (relation['host'],relation['guest']):
                expected.update((relation['host'],relation['guest']))
        for m in result['priority_configurations']:
            if row['planet'] in m['members']: expected.update(m['members'])
        expected.discard(row['planet'])
        assert {r['planet'] for r in review['candidates']}==expected
        for candidate in review['candidates']:
            state=candidate['counterpart_state']
            assert 'resource_review' not in state
            assert candidate['assessment']=='not_evaluated'
            assert {e['id'] for e in state['aspects']}=={
                e['id'] for e in graph['aspects']['6']['edges'] if candidate['planet'] in (e['from'],e['to'])}
            assert all(r['source_refs'] for r in candidate['routes'])


def test_resource_routes_survive_narrow_selection_gate(graph):
    wide=build_salience(graph)
    narrow=build_salience(graph,{'tight_orb':0})
    by_planet={r['planet']:r['profile']['resource_review'] for r in wide['priority_planets']}
    for r in narrow['priority_planets']:
        assert r['profile']['resource_review']==by_planet[r['planet']]

@pytest.fixture(scope='module')
def graph():
    return calculate_structure_graph(year=2000,month=1,day=1,hour=12,minute=0,lat=39.9042,lng=116.4074)


def test_no_score_complete_profiles_and_no_mutation(graph):
    old=copy.deepcopy(graph); d=build_salience(graph)
    assert graph==old
    assert d['method']['score'] is None
    assert d['global_distribution']['point_count']==12
    assert len(d['selection_audit'])==10
    edges=graph['aspects']['6']['edges']
    for row in d['priority_planets']:
        assert 'score' not in row
        expected={e['id'] for e in edges if row['planet'] in (e['from'],e['to'])}
        assert {e['id'] for e in row['profile']['aspects']}==expected
        assert all(r['evidence_id'] in d['evidence_index'] for r in row['selection_reasons'])


def test_duplicate_and_order_invariance(graph):
    original=build_salience(graph)
    g=copy.deepcopy(graph)
    g['nodes']=list(reversed(g['nodes']))*2
    for view in g['aspects'].values():
        view['edges']=list(reversed(view['edges']))*2
        view['motifs']=list(reversed(view['motifs']))*2
    g['receptions']['mutual_receptions']=list(reversed(g['receptions']['mutual_receptions']))*2
    for system in g['houses']: g['houses'][system]=list(reversed(g['houses'][system]))*2
    assert build_salience(g)==original


def test_semantic_aliases_and_opposite_edge_order_merge(graph):
    g=copy.deepcopy(graph)
    edge=copy.deepcopy(g['aspects']['6']['edges'][0])
    edge['id']='client-alias'
    edge['from'],edge['to']=edge['to'],edge['from']
    edge['depends_on'].reverse()
    g['aspects']['6']['edges'].append(edge)
    if g['aspects']['6']['motifs']:
        m=copy.deepcopy(g['aspects']['6']['motifs'][0]);m['id']='alias';m['members'].reverse()
        g['aspects']['6']['motifs'].append(m)
    assert build_salience(g)==build_salience(graph)


def test_contradictory_duplicates_rejected(graph):
    g=copy.deepcopy(graph)
    n=copy.deepcopy(g['nodes'][0]); n['lon']+=1;g['nodes'].append(n)
    with pytest.raises(ValueError,match='Contradictory duplicate'): build_salience(g)


def test_outer_positions_and_retrograde_do_not_change_classical_core(graph):
    original=build_salience(graph)
    g=copy.deepcopy(graph)
    for n in g['nodes']:
        n['retrograde']=not n['retrograde']
        if n['id'] not in SEVEN: n['lon']=15; n['sign_idx']=0
    assert build_salience(g)['core_structures']==original['core_structures']


def test_no_axes_no_fake_contacts_but_topology_and_signs_survive(graph):
    g=copy.deepcopy(graph);g['axes']={}
    d=build_salience(g)
    assert d['core_structures']==build_salience(graph)['core_structures']
    assert d['global_distribution']['point_count']==10
    assert d['global_distribution']['missing_points']==['asc','mc']
    assert all(not r['profile']['axis_contacts'] and r['profile']['chart_ruler'] is None for r in d['priority_planets'])


def test_gate_does_not_filter_selected_planet_profile(graph):
    d=build_salience(graph,{'tight_orb':0})
    assert d['priority_aspects']==[]
    sun=next(r for r in d['priority_planets'] if r['planet']=='sun')
    assert sun['profile']['aspects']
    assert any(e['orb']>0 for e in sun['profile']['aspects'])


def test_terminal_ingress_separate_from_cycle_internal_edges():
    # A synthetic geometry, not a real birth: Moon Aquarius, Saturn Cancer.
    longs=dict(sun=300,moon=300,mercury=270,venus=270,mars=60,jupiter=0,saturn=90)
    nodes={k:{'lon':v} for k,v in longs.items()}
    cores,_=terminal_metrics(nodes,TRADITIONAL_RULERS,SEVEN)
    assert len(cores)==1
    core=cores[0]
    assert core['members']==['moon','saturn']
    assert core['numerator']==core['denominator']==7
    assert set(core['feeders']['direct'])=={'sun','mercury','venus'}
    assert set(core['feeders']['indirect'])=={'mars','jupiter'}
    assert core['main_entries']==['saturn']
    assert core['first_entry']['saturn']['count']==5
    assert core['first_entry']['moon']['count']==0
    assert len(core['internal_edges'])==2
    nodes.update({k:{'lon':300} for k in TEN if k not in SEVEN})
    assert terminal_metrics(nodes,TRADITIONAL_RULERS,SEVEN)[0]==cores


def test_multi_terminal_and_independent_reachability():
    rng=random.Random(101); seen=set(); multiple=False
    for _ in range(250):
        nodes={k:{'lon':rng.randrange(12)*30+15} for k in TEN}
        for rules in (TRADITIONAL_RULERS,MODERN_RULERS):
            for origins in (SEVEN,TEN):
                cores,full=terminal_metrics(nodes,rules,origins)
                nxt={e['from']:e['to'] for e in full['edges']}
                multiple |= len(cores)>1
                assert sum(t['numerator'] for t in cores)==len(origins)
                for start in origins:
                    visited=[];cur=start
                    while cur not in visited: visited.append(cur);cur=nxt[cur]
                    assert set(full['paths'][start]['terminal'])==set(visited[visited.index(cur):])
                seen.update(t['type'] for t in cores)
    assert multiple and seen=={'self','two_node_cycle','multi_node_cycle'}


@pytest.mark.parametrize('config',[dict(scope='unknown'),dict(orb_view=True),dict(orb_view=9),
    dict(tight_orb=9),dict(axis_orb=float('nan')),dict(axis_orb=True),dict(include_mc_ruler=1),dict(weights={})])
def test_invalid_config(config):
    with pytest.raises(ValueError): normalize_config(config)


def test_configuration_containment_and_axis_expression_dedup(graph):
    d=build_salience(graph)
    for m in d['priority_configurations']:
        for child in m['contains']:
            sub=next(n for n in d['priority_configurations'] if n['id']==child)
            assert set(sub['depends_on'])<set(m['depends_on'])
    for r in d['priority_planets']:
        contacts=r['profile']['axis_contacts']
        assert len({a['id'] for a in contacts})==len(contacts)
        for a in contacts:
            assert len(a['expressions'])==2
            assert sum(e['angle'] for e in a['expressions'])==180
            assert abs(a['expressions'][0]['orb']-a['expressions'][1]['orb'])<.00001


def test_real_mcp_custom_policy_partial_reference_and_tampering():
    import mcp_server as m
    from services.mcp_result_facts import checked_result
    async def run():
        for args in (dict(BIRTH,scope='classical7',rulership='modern',tight_orb=1),
                     dict(BIRTH,month=6,day=21,location_id='coord:78.223200,15.646900')):
            out=await m.calculate_natal_salience(**args)
            assert out['status']=='ok',out
            path='/core_structures/0/denominator';value=out['core_structures'][0]['denominator']
            result=await m.verify_calculation_claims(reference=m.CalculationReference(**out['calculation_reference']),
                claims=[m.CalculationClaim(quote='origin denominator',path=path,value=value)])
            assert result['claims'][0]['verdict']=='supported',result
            wrong={**args,'scope':'ten'}
            assert checked_result('calculate_natal_salience',out,wrong)['status']=='validation_failed'
            out['core_structures'][0]['denominator']=99
            assert checked_result('calculate_natal_salience',out,args)['status']=='validation_failed'
    asyncio.run(run())


def test_real_stdio_discovery_selection_and_reference():
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    async def run():
        params=StdioServerParameters(command=sys.executable,args=[str(Path(__file__).resolve().parents[1]/'mcp_server.py')])
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as s:
                await s.initialize()
                schema = next(t for t in (await s.list_tools()).tools if t.name == 'calculate_natal_salience')
                assert 'interpretation_policy' not in schema.inputSchema['properties']
                assert schema.inputSchema['properties']['orb_view']['default'] == 6
                async def call(args):
                    r=await s.call_tool('calculate_natal_salience',args)
                    assert not r.isError,r
                    return json.loads(r.content[0].text)
                assert (await call({}))['status']=='needs_clarification'
                d=await call(dict(BIRTH,include=['core_structures','priority_planets','method','reading_plan','evidence_matrix','resource_checks','reception_facts']))
                assert d['quality']['status']=='passed',d
                assert d['method']['score'] is None
                assert d['reading_plan']['order'][0]=='structural_backbone'
                assert len(d['evidence_matrix']['rows'])==10
                assert all(t['verdict'] is None for t in d['resource_checks']['topics'])
                assert d['reception_facts']['availability']=='available'
                assert 'interpretation_hypotheses' not in d
                assert (await call(dict(BIRTH,axis_orb=-1)))['status']=='invalid_input'
                result=await s.call_tool('verify_calculation_claims',dict(reference=d['calculation_reference'],claims=[dict(quote='seven origins',path='/core_structures/0/denominator',value=7)]))
                assert json.loads(result.content[0].text)['claims'][0]['verdict']=='supported'
                path='/reception_facts/rows/0/host'
                result=await s.call_tool('verify_calculation_claims',dict(reference=d['calculation_reference'],claims=[dict(quote='host',path=path,value=d['reception_facts']['rows'][0]['host'])]))
                assert json.loads(result.content[0].text)['claims'][0]['verdict']=='supported'
    asyncio.run(run())
