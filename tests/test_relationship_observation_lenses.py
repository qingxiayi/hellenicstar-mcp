"""Source actions across contexts; no filtering, inferred facts or duplicate evidence."""
from copy import deepcopy

from services.mcp_result_facts import checked_result, lookup, verify_calculation_claims_data
from services.relationship_observation import calculate_observation_data, build_observation, settings_for
from test_relationship_observation import BIRTH, PARTNER, build, geometry


def lens(result, person, key):
    return next(x for x in result['scenario_observation_lenses']['people'][person]
                if x['id'] == f'{person}:{key}')


def test_same_planet_and_house_retain_different_topics_and_shared_geometry():
    results = {t: build(relationship_type=t) for t in ('love', 'friendship', 'work', 'family')}
    baseline = results['love']
    for r in results.values():
        for key in ('source_geometry', 'contacts', 'observation_paths', 'counts', 'configuration_bridges'):
            assert r[key] == baseline[key]
        # Scenario flags may change; actual placements cannot.
        assert [(o['id'],o['house']) for o in r['house_overlays']] == [(o['id'],o['house']) for o in baseline['house_overlays']]
        assert r['scenario_observation_lenses']['policy']['planet_whitelist'] is False
    mars = [lens(results[t], 'a', key) for t,key in (
        ('love','love:mars_desires'), ('friendship','friendship:mars_action'), ('work','work:mars_assertion'))]
    assert len({x['observation_topic'] for x in mars}) == 3
    assert len({x['objects'][0]['fact_ref'] for x in mars}) == 1
    fifth = [lens(results[t],'a',key) for t,key in (
        ('friendship','friendship:play'),('work','work:creative_project'),('family','family:children'))]
    assert len({x['observation_topic'] for x in fifth}) == 3
    assert all(x['objects'][0]['house']==5 for x in fifth)


def test_optional_conditions_do_not_become_client_facts_or_automatic_focus():
    f = build(relationship_type='friendship')
    third=lens(f,'a','friendship:early_sibling_like')
    assert third['tier']=='supplementary' and third['condition']['status']=='optional_unconfirmed'
    assert third['client_experience']=='not_inferred'
    w=build(relationship_type='work')
    assert lens(w,'a','work:creative_project')['condition']['status']=='optional_unconfirmed'
    assert lens(w,'a','work:colleague_friendship')['condition']['status']=='optional_unconfirmed'
    pluto=lens(w,'a','work:pluto_power')
    assert pluto['objects'][0]['point']=='pluto' and pluto['tier']=='supplementary'
    mixed=build(relationship_type='work',relationship_context={'additional_types':['friendship']})
    assert lens(mixed,'a','work:colleague_friendship')['condition']['status']=='applicable_by_context'
    assert mixed['contacts']==w['contacts']
    assert len({x['id'] for x in mixed['scenario_observation_lenses']['people']['a']})==len(mixed['scenario_observation_lenses']['people']['a'])


def test_role_direction_and_parental_house_profile_are_respected():
    r=build(relationship_type='family',relationship_context={'roles':{'a':'parent','b':'child'}},
            parental_house_mapping_profile='reversed')
    assert lens(r,'a','family:children')['condition']['status']=='applicable_by_context'
    assert not any(x['id']=='b:family:children' for x in r['scenario_observation_lenses']['people']['b'])
    father=lens(r,'b','family:father_image')
    assert [x['house'] for x in father['objects'] if x['kind']=='house']==[10]
    w=build(relationship_type='work',relationship_context={'roles':{'a':'supervisor','b':'employee'}})
    assert not any(x['id']=='a:work:authority' for x in w['scenario_observation_lenses']['people']['a'])
    assert lens(w,'b','work:authority')['condition']['status']=='applicable_by_context'
    home=build(relationship_type='friendship',relationship_context={'cohabiting':True})
    assert lens(home,'a','friendship:shared_home')['condition']['status']=='applicable_by_context'


def test_no_contact_does_not_remove_natal_topics_and_axis_refs_keep_direction():
    r=build_observation({'a':geometry()}, {'a':{}}, settings_for(mode='natal',relationship_type='friendship'))
    view=r['scenario_observation_lenses']
    assert set(view['people'])=={'a'} and lens(r,'a','friendship:mars_action')
    assert all(not c['contact_refs'] and not c['observation_path_refs'] for c in view['point_contexts']['a'].values())
    both=build(geometry(),geometry(sun=180))
    desc=both['scenario_observation_lenses']['point_contexts']['a']['descendant']
    for ref in desc['contact_refs']:
        contact=lookup(both,ref)
        assert any(v['first_point']=='descendant' for v in contact['endpoint_variants'])
    assert all(lookup(both,ref)['target_person']=='a' for ref in desc['observation_path_refs'])


def test_lens_references_recompute_and_tampering_fails_validation():
    import mcp_server  # register the real reference model and calculator
    args=dict(person_a=BIRTH,person_b=PARTNER,relationship_type='work',
              relationship_context={'roles':{'a':'employee','b':'supervisor'},'additional_types':['friendship']})
    raw=calculate_observation_data(**args)
    def walk(obj):
        if isinstance(obj,list):
            for item in obj:walk(item)
        elif isinstance(obj,dict):
            for k,v in obj.items():
                if k.endswith('_ref'):lookup(raw,v)
                if k.endswith('_refs'):
                    for ref in v:lookup(raw,ref)
                if k=='rule_id':assert v in raw['provenance']
                walk(v)
    walk(raw['scenario_observation_lenses'])
    checked=checked_result('calculate_relationship_observation',raw,args)
    assert checked['status']=='ok'
    claims=verify_calculation_claims_data(checked['calculation_reference'],[
        dict(quote='This view is not a planet filter',path='/scenario_observation_lenses/policy/planet_whitelist',value=False),
        dict(quote='Optional conditions remain unconfirmed',path='/scenario_observation_lenses/policy/optional_conditions_are_inferred',value=False)])
    assert claims['counts']['supported']==2
    bad=deepcopy(raw)
    lens(bad,'a','work:creative_project')['condition']['status']='applicable_by_context'
    assert checked_result('calculate_relationship_observation',bad,args)['status']=='validation_failed'
