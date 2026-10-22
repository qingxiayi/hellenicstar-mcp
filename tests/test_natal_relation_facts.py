"""Counterexamples for structural routes; no personal or psychological oracle."""
import copy
import pytest
from services.natal_relation_facts import reception_facts
from services.natal_resource_context import resource_review
from services.natal_salience import normalize_config, build_salience
from services.mcp_salience import calculate_salience_data
from services.natal_structure_graph import calculate_structure_graph


def relations(longitudes, edges=(), sect='日生人', view=8):
    nodes={k:dict(lon=v,sign_idx=int(v//30)) for k,v in longitudes.items()}
    return reception_facts(nodes,edges,sect,view)


def test_sign_trine_is_not_lost_when_degree_aspect_is_outside_view():
    # Sun in Aries is in Mars' domicile; Mars in Leo can receive it despite
    # their 148-degree separation not being a trine within 8 degrees.
    row=next(r for r in relations({'sun':1.,'mars':149.})['rows'] if r['host']=='mars')
    assert row['guest']=='sun' and row['meets_dignity_threshold']
    assert row['sign_geometry']['ptolemaic_angle']==120
    assert row['sign_geometry']['aversion'] is False
    assert row['degree_geometry']['separation']==148
    assert row['current_view']['has_aspect'] is False
    assert row['phase']['status']=='not_applicable'


def test_out_of_sign_degree_aspect_does_not_erase_sign_aversion():
    edge={'id':'test','from':'sun','to':'venus','angle':60,'orb':2.}
    row=next(r for r in relations({'sun':59.,'venus':1.},[edge])['rows'] if r['host']=='venus')
    assert row['sign_geometry']['aversion'] is True
    assert row['current_view']['has_aspect'] is True
    assert row['current_view']['angle']==60


def test_mixed_domicile_exaltation_mutuality_keeps_direction_and_both_bases():
    rows=relations({'jupiter':280.,'saturn':100.})['rows']
    assert len(rows)==2
    by_host={r['host']:r for r in rows}
    assert '旺' in [b['dignity'] for b in by_host['jupiter']['bases']]
    assert '庙' in [b['dignity'] for b in by_host['saturn']['bases']]
    assert all(r['mutual_dignity_threshold'] for r in rows)
    assert by_host['jupiter']['reverse_id']==by_host['saturn']['id']
    assert all(not r['current_view']['has_aspect'] for r in rows)


def test_unknown_sect_does_not_silently_select_night_rules():
    out=relations({'sun':1.,'mars':149.},sect=None)
    assert out['availability']=='unavailable_sect' and out['rows']==[]


def profile(planet, aspects=(), configs=(), condition=None):
    return dict(planet=planet,dispositor={'planet':planet},path={},receptions=[],
        aspects=list(aspects),configurations=list(configs),condition=condition,
        condition_availability='available' if condition else 'not_defined',triplicity_context={},
        retrograde=False,houses={'placidus':None,'whole_sign':None},
        house_ruler_links={'placidus':[],'whole_sign':[]},axis_contacts=[],source_refs=['/source_graph'])


@pytest.mark.parametrize('angle,kind',[(0,'conjunction'),(60,'sextile_or_trine'),(90,'square_or_opposition'),(120,'sextile_or_trine'),(180,'square_or_opposition')])
def test_all_contacts_are_routes_without_efficacy_or_self_loops(angle,kind):
    edge={'id':'x','from':'sun','to':'mars','angle':angle,'orb':1.}
    ps={p:profile(p,[edge]) for p in ('sun','mars')}
    original=copy.deepcopy(ps)
    out=resource_review('sun',ps)
    assert ps==original
    assert [r['planet'] for r in out['candidates']]==['mars']
    assert out['candidates'][0]['routes'][0]['kind']==kind
    assert out['verdict'] is None
    assert out['candidates'][0]['assessment']=='not_evaluated'
    assert out['intrinsic']['condition_context']['houses']['placidus']['in_6_8_12'] is None


def test_intrinsic_dignities_do_not_require_an_external_connection():
    p=profile('mercury',condition={'essential':{'domicile':True,'exaltation':True},'solar':None})
    out=resource_review('mercury',{'mercury':p})
    assert not out['candidates']
    assert out['intrinsic']['condition_context']['essential']=={'domicile':True,'exaltation':True}


def test_configuration_only_connection_is_explicit_not_invented_aspect():
    ps={p:profile(p,configs=[{'id':'grand_cross:x','roles':['member']}]) for p in ('sun','mars')}
    out=resource_review('sun',ps)
    assert [r['kind'] for r in out['candidates'][0]['routes']]==['shared_configuration']


def test_withdrawn_policy_is_rejected_instead_of_ignored():
    with pytest.raises(ValueError): normalize_config({'interpretation_policy':'functional-v1'})
    assert calculate_salience_data(interpretation_policy='functional-v1')['status']=='invalid_input'


def test_state_changes_do_not_rewrite_reception_or_terminals():
    graph=calculate_structure_graph(year=2000,month=1,day=1,hour=12,minute=0,lat=39.9042,lng=116.4074)
    before=build_salience(graph)
    for node in graph['nodes']: node['retrograde']=not node['retrograde']
    after=build_salience(graph)
    assert before['reception_facts']==after['reception_facts']
    assert before['core_structures']==after['core_structures']
    assert 'interpretation_hypotheses' not in after
