"""Role intersections preserve single-role entries and all group context."""
import asyncio
import copy
import pytest
from services.natal_attention import build_attention_layers
from services.natal_salience import build_salience
from services.natal_structure_graph import calculate_structure_graph


def minimal(rules=(), evaluations=()):
    ids={i for r in rules for i in r['evidence_ids']}
    ids.update(e['evidence_id'] for e in evaluations)
    return dict(evidence_index={i:{} for i in ids},
        selection_audit=[dict(planet='mars', focus_rules=list(rules),
                             candidate_evaluations=list(evaluations), selected=bool(rules))],
        core_structures=[], priority_configurations=[],
        focus_selection=dict(configuration_group_ids=[]), availability={})


def rule(name,*ids):
    return dict(rule=name,evidence_ids=list(ids))


def test_same_mechanism_is_not_cross_focus_and_single_entry_is_retained():
    d=minimal([rule('main_external_entry','a'),rule('chart_ruler_dispositor','b')])
    result=build_attention_layers(d)
    assert result['cross_focus']==[]
    assert result['specific_focus']==['mars']
    assert result['planet_audit'][0]['role_groups']=={'rulership':['a','b']}
    d['selection_audit'][0]['focus_rules'].append(rule('axis_conjunction','c'))
    d['evidence_index']['c']={}
    assert build_attention_layers(d)['cross_focus']==['mars']


def test_nested_motifs_edges_and_family_counts_do_not_create_new_roles():
    d=minimal([rule('maximal_configuration_focus','kite'),
               rule('cross_family_convergence','kite','child','edge')],
              [dict(disposition='contained_structure',evidence_id='child'),
               dict(disposition='contained_aspect',evidence_id='edge')])
    result=build_attention_layers(d)
    assert result['specific_focus']==['mars']
    assert result['planet_audit'][0]['evidence_ids']==['edge','kite']
    assert list(result['planet_audit'][0]['role_groups'])==['aspect_network']
    d['selection_audit'][0]['focus_rules'].append(rule('maximal_configuration_focus','another'))
    d['evidence_index']['another']={}
    assert build_attention_layers(d)['specific_focus']==['mars']


def test_tight_local_aspects_can_corroborate_axis_but_not_each_other():
    d=minimal(evaluations=[dict(disposition='local_aspect',evidence_id=i) for i in ('a','b')])
    result=build_attention_layers(d)
    assert result['associated_context']==['mars']
    assert result['planet_audit'][0]['local_aspect_evidence_ids']==['a','b']
    d['selection_audit'][0]['focus_rules']=[rule('axis_conjunction','c')]
    d['evidence_index']['c']={}
    assert build_attention_layers(d)['cross_focus']==['mars']


def test_no_role_is_explicit_context_not_no_information():
    d=minimal([rule('cross_family_convergence','cycle','reception','houses')])
    r=build_attention_layers(d)
    assert r['associated_context']==['mars']
    assert r['planet_audit'][0]['legacy_selected']
    assert r['empty_cross_focus']


def test_containment_keeps_tight_geometry_without_an_extra_group():
    d=minimal([rule('identity_anchor','identity')],
              [dict(disposition='local_aspect',evidence_id='edge')])
    before=build_attention_layers(d)
    e=d['selection_audit'][0]['candidate_evaluations'][0]
    e.update(disposition='contained_aspect',represented_by=['parent'])
    after=build_attention_layers(d)
    assert before['cross_focus']==after['cross_focus']==['mars']
    assert before['planet_audit'][0]['role_groups']==after['planet_audit'][0]['role_groups']
    assert after['planet_audit'][0]['aspect_network_evidence'][0]['represented_by']==['parent']
    assert after['planet_audit'][0]['network_geometry_ids']==['edge']


@pytest.mark.parametrize('role',['opposition_endpoint','sextile_vertex','mediator','apex','sextile_apex'])
def test_contained_configuration_role_survives_and_is_not_repeated(role):
    d=minimal([rule('identity_anchor','identity')])
    child=dict(id='child',members=['mars'],roles={'mars':[role]},contains=[],depends_on=['e1'],shared_with=[])
    parent=dict(id='parent',members=['mars'],roles={'mars':['member']},contains=['child'],depends_on=['e1','e2'])
    d['priority_configurations']=[child]
    d['focus_selection']['configuration_group_ids']=['child']
    d['evidence_index'].update(child={},parent={})
    before=build_attention_layers(d)
    d['priority_configurations']=[parent,child,child]
    d['focus_selection']['configuration_group_ids']=['parent']
    parent['shared_with']=[]
    after=build_attention_layers(d)
    assert before['cross_focus']==after['cross_focus']==['mars']
    assert before['planet_audit'][0]['role_groups']==after['planet_audit'][0]['role_groups']
    facet=after['planet_audit'][0]['aspect_network_evidence'][0]
    assert facet['roles']==[role] and facet['represented_by']==['parent']
    assert after['planet_audit'][0]['network_geometry_ids']==['e1']


def test_symmetric_opposition_endpoints_are_equal_and_members_not_promoted():
    d=minimal()
    d['selection_audit']=[dict(planet=p,focus_rules=[],candidate_evaluations=[],selected=False) for p in ('mars','venus','sun')]
    motif=dict(id='motif',members=['mars','venus','sun'],roles={'mars':['opposition_endpoint'],'venus':['opposition_endpoint'],'sun':['member']},contains=[],depends_on=['opposition'],shared_with=[])
    d['priority_configurations']=[motif];d['focus_selection']['configuration_group_ids']=['motif']
    d['evidence_index']['motif']={}
    view=build_attention_layers(d)
    assert view['specific_focus']==['mars','venus']
    assert view['associated_context']==['sun'] and view['cross_focus']==[]


@pytest.fixture(scope='module')
def graph():
    return calculate_structure_graph(year=2000,month=1,day=1,hour=12,minute=0,
                                     lat=39.9042,lng=116.4074,include_supplementary=True)


def test_all_planets_partitioned_all_structures_preserved_without_mutation(graph):
    data=build_salience(graph); original=copy.deepcopy(data)
    view=build_attention_layers(data)
    assert data==original
    ids=sum((view[k] for k in ('cross_focus','specific_focus','associated_context')),[])
    assert len(ids)==len(set(ids))==10
    assert set(ids)==set(data['planet_profiles'])
    assert [t['id'] for t in view['primary_structures']['terminals']]==[t['id'] for t in data['core_structures']]
    assert {m['id'] for m in view['primary_structures']['configurations']}==set(data['focus_selection']['configuration_group_ids'])
    for r in view['planet_audit']:
        assert set(r['evidence_ids'])<=set(data['evidence_index'])
    data['selection_audit'].reverse()
    for r in data['selection_audit']:
        r['focus_rules']=list(reversed(r['focus_rules']))*2
        r['candidate_evaluations']=list(reversed(r['candidate_evaluations']))*2
    assert build_attention_layers(data)==view


def test_changed_condition_does_not_promote_focus(graph):
    before=build_salience(graph)['attention_layers']
    altered=copy.deepcopy(graph)
    for c in altered['conditions'].values():
        c['essential']['detriment']=not c['essential']['detriment']
        c['essential']['fall']=not c['essential']['fall']
    for n in altered['nodes']:
        n['retrograde']=not n['retrograde']
    assert build_salience(altered)['attention_layers']==before


def test_partial_graph_retains_structures_without_fabricated_axis_roles():
    graph=calculate_structure_graph(year=2000,month=6,day=21,hour=12,minute=0,
                                   lat=78.2232,lng=15.6469)
    view=build_salience(graph)['attention_layers']
    assert view['primary_structures']['terminals']
    assert view['availability']['axes']['asc']=='unavailable'
    assert all('axis_contact' not in r['role_groups'] for r in view['planet_audit'])


def test_real_tool_verifies_new_view_and_rejects_tampering():
    import mcp_server as m
    from services.mcp_result_facts import checked_result
    async def run():
        args=dict(year=2000,month=1,day=1,hour=12,minute=0,location_id='coord:39.904200,116.407400')
        data=await m.calculate_natal_salience(**args)
        assert data['status']=='ok'
        value=data['attention_layers']['cross_focus']
        out=await m.verify_calculation_claims(reference=m.CalculationReference(**data['calculation_reference']),
            claims=[m.CalculationClaim(quote='role intersections',path='/attention_layers/cross_focus',value=value)])
        assert out['claims'][0]['verdict']=='supported'
        data['attention_layers']['cross_focus']=['fabricated']
        assert checked_result('calculate_natal_salience',data,args)['status']=='validation_failed'
    asyncio.run(run())
