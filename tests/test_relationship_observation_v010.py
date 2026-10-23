"""Audit gap regressions: truthful cusp/context inputs and factorized complexes."""
from copy import deepcopy
import pytest
from services.mcp_result_facts import checked_result, lookup, verify_calculation_claims_data
from services.relationship_observation import calculate_observation_data, settings_for, build_observation
from services.relationship_observation_topics import DESCENDANT_TOPICS, SEVENTH_TOPICS
from test_relationship_observation import build, geometry, BIRTH, PARTNER


def lens(r, key, who='a'):
    return next(x for x in r['scenario_observation_lenses']['people'][who] if x['id']==f'{who}:love:{key}')


@pytest.mark.parametrize('lon,in_seventh', [(174.999,False),(175,True),(179.999,True),(180,True),(209.999,True),(210,False),(235,False)])
def test_effective_seventh_lens_matches_natal_fact_without_relocating(lon,in_seventh):
    r=build(geometry(jupiter=lon))
    p=r['relationship_profiles']['a']['points']['jupiter']
    row=lens(r,'partner_projection')
    assert p['effective_seventh_house'] is in_seventh
    near=[x for x in row['objects'] if x['kind']=='effective_seventh_house_point' and x['point']=='jupiter']
    assert bool(near)==(175<=lon<180)
    if near:
        assert near[0]['actual_house']==6 and near[0]['observation_house']==7
        assert near[0]['rule_id']=='seventh_cusp'
        assert 'jupiter' not in r['relationship_profiles']['a']['houses'][6]['planets']
        assert '/scenario_observation_lenses/point_contexts/a/jupiter' in row['point_context_refs']
    assert any(x['id']=='a:love:seventh_jupiter' for x in r['scenario_observation_lenses']['people']['a'])==in_seventh
    assert r['counts']['observation_paths']==2*r['counts']['unique_contacts']


@pytest.mark.parametrize('sign_index,sign', list(enumerate(DESCENDANT_TOPICS)))
def test_all_descendant_conditions_select_only_matching_topic(sign_index,sign):
    # ASC/MC and fixture cusps are rotated together; DSC sign follows the rotation.
    r=build(geometry((sign_index*30+180)%360))
    rows=[x for x in r['scenario_observation_lenses']['people']['a'] if ':love:descendant_' in x['id']]
    assert len(rows)==1 and rows[0]['id']=='a:love:descendant_'+sign.lower()
    assert rows[0]['condition']['status']=='applicable_by_geometry'
    assert rows[0]['client_experience']=='not_inferred'
    assert lookup(r,rows[0]['condition']['fact_refs'][0])['sign']==sign


@pytest.mark.parametrize('planet',SEVENTH_TOPICS)
def test_seventh_planet_topic_keeps_own_natal_edges(planet):
    r=build(geometry(**{planet:185}))
    row=lens(r,'seventh_'+planet)
    refs=row['point_context_refs'];assert len(refs)==1
    point=lookup(r,refs[0])
    assert lookup(r,point['point_ref'])['house']==7
    for ref in point['natal_aspect_refs']:
        assert any(planet in (v['first_point'],v['second_point']) for v in lookup(r,ref)['endpoint_variants'])
    assert row['condition']['experience_status']=='requires_client_confirmation'


@pytest.mark.parametrize('venus,mars,expected',[(175,180,True),(185,194,True),(185,196,False),(174.99,180,False),(215,218,False)])
def test_joint_venus_mars_requires_both_placements_and_actual_conjunction(venus,mars,expected):
    r=build(geometry(venus=venus,mars=mars))
    rows=[x for x in r['scenario_observation_lenses']['people']['a'] if x['id']=='a:love:seventh_venus_mars']
    assert bool(rows)==expected
    if rows:
        edge=lookup(r,rows[0]['condition']['fact_refs'][-1])
        assert edge['angle']==0 and {edge['first_point'],edge['second_point']}=={'venus','mars'}


@pytest.mark.parametrize('value,state',[(None,'optional_unconfirmed'),(True,'applicable_by_context'),(False,'not_applicable_by_context')])
def test_explicit_contexts_are_tristate_and_never_change_geometry(value,state):
    base=build(relationship_type='work',relationship_context={'additional_types':['friendship']})
    r=build(relationship_type='work',relationship_context={'additional_types':['friendship'],
          'creative_project':value,'early_or_sibling_like_friendship':value})
    for key in ('contacts','counts','observation_paths','observation_complexes','observation_complex_links'):
        assert r[key]==base[key]
    rows=r['scenario_observation_lenses']['people']['a']
    for key in ['a:work:creative_project','a:friendship:early_sibling_like']:
        assert next(x for x in rows if x['id']==key)['condition']['status']==state


@pytest.mark.parametrize('ctx,primary',[
    ({'creative_project':1},'work'),({'creative_project':'true'},'work'),
    ({'early_or_sibling_like_friendship':[]},'friendship'),
    ({'creative_project':False},'love'),({'early_or_sibling_like_friendship':True},'work')])
def test_invalid_or_incompatible_contexts_rejected(ctx,primary):
    with pytest.raises(ValueError):settings_for(relationship_type=primary,relationship_context=ctx)


def assert_links(r):
    view=r['observation_complex_links']
    assert len(view['links'])==view['unique_linked_contact_count']<=r['counts']['unique_contacts']
    assert len({x['contact_id'] for x in view['links']})==len(view['links'])
    for row in view['links']:
        c=lookup(r,row['contact_ref']);assert c['id']==row['contact_id']
        for who,field in [('a','first_point'),('b','second_point')]:
            side=row[who];assert side['person']==who and side['point']==c[field]
            for ref in side['core_complex_refs']:
                assert side['point'] in lookup(r,ref)['core_members']
            for ref in side['context_complex_refs']:
                comp=lookup(r,ref)
                assert side['point'] in comp['members'] and side['point'] not in comp['core_members']
        assert not row['creates_direct_contact'] and not row['whole_complex_activation_inferred']
    assert not view['policy']['all_complex_pairs_materialized']


def test_extended_axis_yod_links_and_natal_mode():
    a=geometry(sun=90,moon=180)
    r=build(a,a);assert_links(r)
    axis=next(c for c in r['observation_complexes']['people']['a'] if set(c['core_members'])=={'ascendant','sun','moon'})
    assert any(lookup(r,ref)['id']==axis['id'] for row in r['observation_complex_links']['links'] for ref in row['a']['core_complex_refs'])
    a=geometry(sun=0,moon=60,mars=210)
    r=build(a,a,sextile_orb_degrees=4,include_minor_aspects=True,minor_orbs_degrees={'150':2})
    assert_links(r)
    assert any(any(v['kind']=='yod' for v in lookup(r,ref)['representations'])
               for row in r['observation_complex_links']['links'] for ref in row['a']['core_complex_refs'])
    natal=build_observation({'a':a},{'a':{}},settings_for(mode='natal'))
    assert natal['observation_complex_links']['status']=='not_computed'
    assert natal['observation_complex_links']['links']==[]


def test_attached_member_is_not_core_hit_and_overlaps_do_not_multiply_contacts():
    a=geometry(sun=0,venus=8,moon=16,mercury=24)
    r=build(a,a);assert_links(r)
    pair=next(c for c in r['observation_complexes']['people']['a'] if c['seed_type']=='conjunction_pair' and set(c['core_members'])=={'sun','venus'})
    row=next(x for x in r['observation_complex_links']['links'] if x['a']['point']==x['b']['point']=='moon')
    assert any(lookup(r,ref)['id']==pair['id'] for ref in row['a']['context_complex_refs'])
    assert not any(lookup(r,ref)['id']==pair['id'] for ref in row['a']['core_complex_refs'])
    assert 'mercury' not in pair['members']  # still no second hop
    # Dense overlap stays one row per contact, never a complex-pair product.
    from services.relationship_charts import PLANETS
    dense=geometry(**{p:0 for p in PLANETS})
    assert_links(build(dense,dense))


def test_real_references_new_fields_and_tampering_are_verified():
    import mcp_server
    args=dict(person_a=BIRTH,person_b=PARTNER,relationship_type='work',
              relationship_context={'creative_project':True})
    raw=calculate_observation_data(**args)
    checked=checked_result('calculate_relationship_observation',raw,args)
    assert checked['status']=='ok';assert_links(raw)
    claims=verify_calculation_claims_data(checked['calculation_reference'],[
        dict(quote='Context supplied',path='/settings/relationship_context/creative_project',value=True),
        dict(quote='Contact memberships only',path='/observation_complex_links/policy/all_complex_pairs_materialized',value=False)])
    assert claims['counts']['supported']==2
    for key in ['observation_complex_links','scenario_observation_lenses']:
        bad=deepcopy(raw);bad[key]={}
        assert checked_result('calculate_relationship_observation',bad,args)['status']=='validation_failed'
