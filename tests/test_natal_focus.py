"""Counterexamples to promoting every participant; no personal-chart ranking."""
import copy
import pytest
from services.natal_focus import select_focus
from services.natal_salience import build_salience
from services.natal_structure_graph import calculate_structure_graph


def example():
    # A kite contains a grand trine; only the sextile apex has its unique role.
    edges=['e1','e2','e3','e4','e5','e6']
    kite=dict(id='kite',members=['a','b','c','d'],depends_on=edges,
        contains=['trine'],roles={'a':['sextile_apex'],'b':['opposition_endpoint'],
                                 'c':['member'],'d':['member']})
    trine=dict(id='trine',members=['b','c','d'],depends_on=edges[:3],
        contains=[],roles={p:['member'] for p in ['b','c','d']})
    evidence={}; reasons={p:[] for p in 'abcd'}
    for m in (kite,trine):
        evidence[m['id']]=dict(family='configuration',detail=m)
        for p in m['members']:
            reasons[p].append(dict(category='configuration',evidence_id=m['id']))
    return reasons,evidence,[kite,trine]


def test_kite_does_not_promote_all_members_or_count_nested_edges_as_corroboration():
    reasons,evidence,motifs=example()
    evidence['e1']=dict(family='aspect',detail={})
    reasons['c'].append(dict(category='tight_aspect',evidence_id='e1'))
    rows,_=select_focus(reasons,evidence,motifs)
    assert {p for p,r in rows.items() if r['selected']}=={'a'}
    assert set(rows['c']['structural_families'])=={'configuration'}
    assert [r['disposition'] for r in rows['c']['candidate_evaluations']]==[
        'group_member','contained_structure','contained_aspect']
    # Removing child motif/edge annotations cannot change the focal object.
    reduced={p:[m for m in rs if m['evidence_id']=='kite'] for p,rs in reasons.items()}
    other,_=select_focus(reduced,evidence,[motifs[0]])
    assert {p for p,r in other.items() if r['selected']}=={'a'}


def test_symmetric_group_has_no_arbitrary_single_winner():
    reasons,evidence,motifs=example(); trine=motifs[1]
    reasons={p:[dict(category='configuration',evidence_id='trine')] for p in trine['members']}
    rows,_=select_focus(reasons,evidence,[trine])
    assert not any(r['selected'] for r in rows.values())
    assert all(r['candidate_evaluations'][0]['represented_by']==['trine'] for r in rows.values())


def test_terminal_group_is_distinct_from_external_entry_and_keeps_ties():
    reasons={p:[dict(category='terminal',evidence_id='terminal:ab')] for p in 'ab'}
    evidence={'terminal:ab':dict(family='dispositor',detail={})}
    for p in 'ab':
        identity='entry:terminal:ab:'+p
        evidence[identity]=dict(family='dispositor',detail={})
        reasons[p].append(dict(category='terminal',evidence_id=identity))
    rows,_=select_focus(reasons,evidence,[])
    assert all(r['selected'] for r in rows.values())
    reasons['b'].pop()
    rows,_=select_focus(reasons,evidence,[])
    assert rows['a']['selected'] and not rows['b']['selected']
    assert rows['b']['candidate_evaluations'][0]['represented_by']==['terminal:ab']


def test_axis_aspects_are_not_all_conjunctions_and_house_systems_are_not_votes():
    evidence={'axis:a':dict(family='angularity',detail={'angle':60}),
              'house:p':dict(family='house_ruler',detail={}),
              'house:w':dict(family='house_ruler',detail={})}
    reasons={'a':[dict(category='axis' if k=='axis:a' else 'house_ruler',evidence_id=k) for k in evidence]}
    rows,_=select_focus(reasons,evidence,[])
    assert not rows['a']['selected']
    evidence['axis:a']['detail']['angle']=180
    assert select_focus(reasons,evidence,[])[0]['a']['selected']
    evidence['axis:a']['detail']['angle']=60
    evidence['edge']=dict(family='aspect',detail={})
    reasons['a'].append(dict(category='tight_aspect',evidence_id='edge'))
    row=select_focus(reasons,evidence,[])[0]['a']
    assert row['selected'] and row['rules'][0]['rule']=='cross_family_convergence'
    assert len(row['structural_families'])==3


@pytest.fixture(scope='module')
def graph():
    return calculate_structure_graph(year=2000,month=1,day=1,hour=12,minute=0,lat=39.9042,lng=116.4074)


def test_all_ten_profiles_and_connections_survive_selection(graph):
    data=build_salience(graph)
    assert len(data['planet_profiles'])==10
    assert len(data['priority_planets'])<10
    assert {r['planet'] for r in data['priority_planets']}==set(data['focus_selection']['planet_ids'])
    for p,profile in data['planet_profiles'].items():
        expected={e['id'] for e in graph['aspects']['6']['edges'] if p in (e['from'],e['to'])}
        assert {e['id'] for e in profile['aspects']}==expected
    assert all(not t['unavailable_endpoint_profiles'] for t in data['resource_checks']['topics'])


def test_state_cannot_promote_or_demote_focus(graph):
    original=build_salience(graph); changed=copy.deepcopy(graph)
    for n in changed['nodes']: n['retrograde']=not n['retrograde']
    for condition in changed['conditions'].values():
        condition['essential']['fall']=not condition['essential']['fall']
    out=build_salience(changed)
    assert out['focus_selection']==original['focus_selection']
    assert out['selection_audit']==original['selection_audit']


def test_missing_axes_never_supplies_axis_anchor(graph):
    changed=copy.deepcopy(graph);changed['axes']={}
    data=build_salience(changed)
    assert data['core_structures']==build_salience(graph)['core_structures']
    assert all(r['rule']!='axis_conjunction' for a in data['selection_audit'] for r in a['focus_rules'])
    assert all(a['unknowns'] for a in data['selection_audit'])


def test_no_arbitrary_cap_when_every_planet_has_an_anchor():
    reasons={str(p):[dict(category='axis',evidence_id='axis:'+str(p))] for p in range(10)}
    evidence={'axis:'+str(p):dict(family='angularity',detail={'angle':0}) for p in range(10)}
    rows,policy=select_focus(reasons,evidence,[])
    assert all(r['selected'] for r in rows.values())
    assert policy['maximum_planets'] is None


def test_real_mcp_focus_claim_and_tamper_check():
    import asyncio
    import mcp_server as m
    from services.mcp_result_facts import checked_result
    async def run():
        args=dict(year=2000,month=1,day=1,hour=12,minute=0,location_id='coord:39.904200,116.407400')
        out=await m.calculate_natal_salience(**args)
        assert out['status']=='ok' and out['schema_version']=='natal-priorities-v4'
        path='/focus_selection/planet_ids'
        result=await m.verify_calculation_claims(reference=m.CalculationReference(**out['calculation_reference']),
            claims=[m.CalculationClaim(quote='selected planets',path=path,value=out['focus_selection']['planet_ids'])])
        assert result['claims'][0]['verdict']=='supported'
        out['focus_selection']['planet_ids']=[]
        assert checked_result('calculate_natal_salience',out,args)['status']=='validation_failed'
    asyncio.run(run())


def test_mutual_relation_is_candidate_not_automatic_focus_and_cycle_alias_is_not_a_vote():
    evidence={'terminal:a:b':dict(family='dispositor',detail={}),
              'reception:a:b':dict(family='reception',detail={},synonym_group='terminal:a:b'),
              'house:a':dict(family='house_ruler',detail={})}
    reasons={'a':[dict(category='terminal',evidence_id=k) for k in evidence]}
    row=select_focus(reasons,evidence,[])[0]['a']
    assert not row['selected']
    assert set(row['structural_families'])=={'dispositor','house_ruler'}
    alias=next(e for e in row['candidate_evaluations'] if e['evidence_id']=='reception:a:b')
    assert alias['disposition']=='synonymous_relation'
    assert alias['represented_by']==['terminal:a:b']
    # A distinct mixed-dignity exchange is a different structural description.
    evidence['reception:a:b']['synonym_group']='reception:a:b'
    row=select_focus(reasons,evidence,[])[0]['a']
    assert row['selected'] and row['rules'][0]['rule']=='cross_family_convergence'
    only={'a':[dict(category='reception',evidence_id='reception:a:b')]}
    assert not select_focus(only,evidence,[])[0]['a']['selected']


def test_mutuals_without_aspects_reach_both_candidate_lists():
    import json
    from pathlib import Path
    from services.mcp_structure_graph import calculate_graph_data
    row=next(r for r in json.loads((Path(__file__).parent/'fixtures/natal-structure-synthetic.json').read_text()) if r['id']=='random-000')
    graph=calculate_graph_data(**{k:v for k,v in row.items() if k not in ('id','group')})
    data=build_salience(graph)
    assert any(not r['has_aspect'] for r in graph['receptions']['mutual_receptions'])
    for r in graph['receptions']['mutual_receptions']:
        a,b=sorted((r['planet1'],r['planet2']))
        identity=f'reception:{a}:{b}'
        for p in (a,b):
            audit=next(a for a in data['selection_audit'] if a['planet']==p)
            assert identity in {e['evidence_id'] for e in audit['candidate_evaluations']}
        assert data['evidence_index'][identity]['detail']['has_aspect']==r['has_aspect']


@pytest.mark.parametrize('rulership',['traditional','modern'])
def test_chart_ruler_bridge_is_one_hop_uses_selected_rulership_and_requires_asc(graph,rulership):
    from services.natal_house_rulers import SIGN_KEYS,TRADITIONAL_RULERS,MODERN_RULERS
    rules=TRADITIONAL_RULERS if rulership=='traditional' else MODERN_RULERS
    for sign in range(12):
        g=copy.deepcopy(graph);g['axes']['asc']['lon']=sign*30+10
        data=build_salience(g,{'rulership':rulership})
        guest=rules[SIGN_KEYS[sign]]
        host=data['planet_profiles'][guest]['dispositor']['planet']
        bridges=[e for e in data['evidence_index'].values() if e['id'].startswith('bridge:')]
        assert len(bridges)==(host!=guest)
        if bridges:
            assert bridges[0]['detail']==dict(planet=host,guest=guest,role='chart_ruler_dispositor',rulership=rulership,depth=1)
            assert host in data['focus_selection']['planet_ids']
    g['axes']={}
    assert 'bridge:chart_ruler' not in build_salience(g)['evidence_index']


@pytest.mark.parametrize('name,planet,status',[
    ('水星','mercury','available'),('uranus','uranus','available'),
    (None,None,'no_focus_supplied'),('水星/金星',None,'unrecognized_focus')])
def test_pattern_focus_consumes_single_upstream_result_without_guessing(graph,name,planet,status):
    g=copy.deepcopy(graph);g['jones']=dict(engine_version='test',high_focus_planet=name,confidence='moderate')
    data=build_salience(g)
    assert data['jones_view']['upstream_focus']['status']==status
    assert data['jones_view']['upstream_focus']['planet']==planet
    assert 'pattern:jones:focus' not in data['evidence_index']
    without=copy.deepcopy(g);without.pop('jones')
    plain=build_salience(without)
    assert data['focus_selection']==plain['focus_selection']
    assert data['attention_layers']==plain['attention_layers']
    assert plain['jones_view']['upstream_focus']['status']=='unavailable'
