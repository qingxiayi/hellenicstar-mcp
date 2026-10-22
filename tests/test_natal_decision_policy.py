"""Separate role/relationship/context facts without inventing global grades."""
import copy
import pytest
from services.natal_decision_policy import assess_resource, priority_decisions
from services.natal_salience import build_salience
from services.natal_structure_graph import calculate_structure_graph


def decision_fixture(kind='essential_condition'):
    essential={k:False for k in ('domicile','exaltation','triplicity','term','face','detriment','fall','peregrine')}
    essential['domicile']=True
    state=dict(condition={'essential':essential,'solar':{'state':'free'}},retrograde=False,
        aspects=[],houses={'placidus':1,'whole_sign':1},house_ruler_links={'placidus':[],'whole_sign':[]})
    row=dict(planet='venus',routes=[{'kind':'dispositor'},
        {'kind':'sextile_or_trine','detail':{'id':'a:sun:venus:60','angle':60,'orb':2}}],counterpart_state=state)
    data={'candidates':[row]}
    candidate=dict(planet='venus',coverage='all_affected',connections=[dict(endpoint='sun',candidate_ref='/candidates/0')])
    topic=dict(kind=kind,affected_planets=['sun'],unavailable_endpoint_profiles=[])
    return data,candidate,topic,state


def test_three_dimensions_no_global_grade_or_mutation():
    data,c,t,state=decision_fixture(); before=copy.deepcopy(data)
    out=assess_resource(t,c,data)
    assert data==before
    assert 'status' not in out and out['effective_remedy'] is None
    assert out['relationship']['status']=='established'
    assert out['applicability']['status']=='governance_or_reception_context'
    data['candidates'][0]['routes']=data['candidates'][0]['routes'][1:]
    assert assess_resource(t,c,data)['applicability']['status']=='aspect_context_only'


@pytest.mark.parametrize('change',['retrograde','detriment','peregrine','hard_aspect','house','rules_house'])
def test_counterpart_state_never_downgrades_established_relation(change):
    data,c,t,state=decision_fixture(); before=assess_resource(t,c,data)
    if change=='retrograde': state['retrograde']=True
    if change in ('detriment','peregrine'): state['condition']['essential'][change]=True
    if change=='hard_aspect': state['aspects']=[{'id':'other','from':'venus','to':'mars','angle':90,'orb':1}]
    if change=='house': state['houses']['placidus']=12
    if change=='rules_house': state['house_ruler_links']['placidus']=[{'house':8}]
    after=assess_resource(t,c,data)
    assert after['relationship']==before['relationship']
    assert after['applicability']==before['applicability']
    assert after['counterpart_state']!=before['counterpart_state']


@pytest.mark.parametrize('missing',['condition','houses','endpoint'])
def test_missing_data_are_local_to_dimension(missing):
    data,c,t,state=decision_fixture(); before=assess_resource(t,c,data)
    if missing=='condition': state['condition']=None
    if missing=='houses': state['houses']['placidus']=None
    if missing=='endpoint': t['unavailable_endpoint_profiles']=['moon']
    out=assess_resource(t,c,data)
    assert out['relationship']['status']=='established'
    assert out['applicability']['status']==before['applicability']['status']
    if missing=='condition':
        assert out['counterpart_state']['essential'] is None
        assert out['counterpart_state']['availability']['essential']=='classical_condition_not_defined'
    if missing=='houses': assert out['counterpart_state']['availability']['houses']['placidus']=='unavailable'
    if missing=='endpoint': assert out['applicability']['coverage']=='partial'


def test_geometry_one_or_two_endpoint_connection_is_not_resolution():
    data,c,t,state=decision_fixture('square_or_opposition'); t['affected_planets']=['sun','moon']
    c['coverage']='some_affected'
    assert assess_resource(t,c,data)['applicability']['status']=='one_endpoint_aspect_connection'
    c['coverage']='all_affected'; c['connections'].append(dict(endpoint='moon',candidate_ref='/candidates/0'))
    out=assess_resource(t,c,data)
    assert out['applicability']['status']=='two_endpoint_aspect_connection'
    assert out['applicability']['ability_to_resolve_issue']=='not_established'
    data['candidates'][0]['routes']=[{'kind':'dispositor'}]
    assert assess_resource(t,c,data)['applicability']['status']=='governance_connection_only'


@pytest.mark.parametrize('kind',['motion','solar_condition','house_association'])
def test_context_does_not_claim_to_change_natal_state(kind):
    data,c,t,state=decision_fixture(kind)
    out=assess_resource(t,c,data)
    assert out['applicability']['status']=='background_connection_only'
    assert out['effective_remedy'] is None


def test_hard_aspect_elsewhere_distinguished_from_contact_to_topic():
    data,c,t,state=decision_fixture()
    state['aspects']=[{'from':'venus','to':'mars','angle':90}, {'from':'venus','to':'sun','angle':180}]
    hard=assess_resource(t,c,data)['counterpart_state']['hard_aspects']
    assert [a['relation_to_topic'] for a in hard]==['elsewhere_in_chart','touches_affected_planet']


def test_conflicting_counterpart_snapshots_rejected():
    data,c,t,state=decision_fixture()
    data['candidates'].append(copy.deepcopy(data['candidates'][0]))
    data['candidates'][1]['counterpart_state']['retrograde']=True
    c['connections'].append(dict(endpoint='moon',candidate_ref='/candidates/1'))
    with pytest.raises(ValueError,match='Conflicting'): assess_resource(t,c,data)


def test_all_terminals_get_roles_including_smaller_basins():
    def terminal(p,n):
        return dict(id='terminal:'+p,members=[p],main_entries=[],numerator=n,denominator=7)
    data=dict(core_structures=[terminal('sun',5),terminal('moon',2)],
        scope_comparison={'ten':{'terminals':[]}},priority_planets=[],
        priority_configurations=[],house_ruler_links=[],priority_aspects=[],
        resource_checks={'topics':[]},evidence_index={},
        selection_audit=[{'planet':p,'selected':False} for p in ('sun','moon')])
    out=priority_decisions(data)
    assert out['role_groups']['terminal_member']==['moon','sun']
    assert all('tier' not in r for r in out['rows'])
    assert out['policy']['ranking'] is None


def test_duplicate_input_and_state_do_not_change_roles():
    graph=calculate_structure_graph(year=2000,month=1,day=1,hour=12,minute=0,lat=39.9042,lng=116.4074)
    out=build_salience(graph); changed=copy.deepcopy(graph)
    for n in changed['nodes']: n['retrograde']=not n['retrograde']
    assert build_salience(changed)['priority_decisions']==out['priority_decisions']
    changed=copy.deepcopy(graph); changed['nodes']*=2
    for view in changed['aspects'].values():
        view['edges']*=2; view['motifs']*=2
    repeated=build_salience(changed)
    assert repeated['priority_decisions']==out['priority_decisions']
    assert repeated['resource_decisions']==out['resource_decisions']
