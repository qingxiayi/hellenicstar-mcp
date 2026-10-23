"""Book observation actions, caller-defined minors and explicit role ownership."""
import json
from copy import deepcopy
from itertools import product
from pathlib import Path

import pytest

from services.mcp_result_facts import checked_result, lookup, verify_calculation_claims_data
from services.relationship_observation import calculate_observation_data, settings_for
from services.relationship_charts import separation
from test_relationship_observation import build, geometry, BIRTH, PARTNER

CASES = json.loads((Path(__file__).parent / 'fixtures/relationship_book_observation_actions.json').read_text())['cases']


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_book_observation_action_with_synthetic_geometry(case):
    r = build(geometry(**case['a_points']), include_minor_aspects=True,
              minor_orbs_degrees=case['minor_orbs_degrees'], sextile_orb_degrees=case.get('sextile_orb_degrees'))
    if 'expected_pair' in case:
        edge = next(e for e in r['relationship_profiles']['a']['natal_aspects']
                    if {e['first_point'], e['second_point']} == set(case['expected_pair']))
        assert edge['angle'] == case['expected_angle'] and edge['rule_id'] == 'minor_orbs'
        if case.get('parental_ruler_pair'):
            assert edge['id'] in r['relationship_profiles']['a']['parental_context']['ruler_4_10_aspect_ids']
    else:
        row = next(c for c in r['observation_complexes']['people']['a']
                   if set(c['core_members']) == set(case['expected_yod']))
        yod = next(p for p in row['representations'] if p['kind'] == 'yod')
        assert yod['apex'] == case['expected_apex']
        assert sorted(lookup(r, ref)['angle'] for ref in row['fact_refs']) == [60, 150, 150]
        if case.get('expected_satellite'):
            assert case['expected_satellite'] in {p['point'] for p in row['attached_members']}


def test_minor_thresholds_are_explicit_and_axes_have_no_duplicate_contacts():
    a, b = geometry(), geometry(13)
    r = build(a, b, include_minor_aspects=True, minor_orbs_degrees={str(x): 1 for x in (30, 45, 135, 150)}, sextile_orb_degrees=6)
    expected, observed = set(), set()
    for p, q in product(a['points'], b['points']):
        for angle, limit in r['settings']['orbs'].items():
            if abs(separation(a['points'][p], b['points'][q])-int(angle)) <= limit:
                expected.add((p, q, int(angle)))
    for e in r['contacts']:
        for v in e['endpoint_variants']:
            if str(v['angle']) in r['settings']['orbs'] and e['orb_degrees'] <= r['settings']['orbs'][str(v['angle'])]:
                observed.add((v['first_point'], v['second_point'], v['angle']))
    assert expected == observed
    assert len({(e['first_point'], e['second_point']) for e in r['contacts']}) == len(r['contacts'])
    base = build(geometry(moon=0, venus=150))
    assert not any({e['first_point'], e['second_point']} == {'moon', 'venus'} for e in base['relationship_profiles']['a']['natal_aspects'])
    assert base['layer_availability']['minor_aspects']['status'] == 'not_computed'


@pytest.mark.parametrize('options', [
    {'include_minor_aspects': True}, {'minor_orbs_degrees': {'150': 1}},
    {'include_minor_aspects': True, 'minor_orbs_degrees': {'72': 1}},
    {'include_minor_aspects': True, 'minor_orbs_degrees': {'150': True}},
    {'include_minor_aspects': True, 'minor_orbs_degrees': {'150': float('nan')}},
    {'include_minor_aspects': True, 'minor_orbs_degrees': {'45': 5}},
    {'relationship_context': {'roles': {'a': 'parent'}}},
    {'relationship_context': {'roles': {'a': 'child', 'b': 'supervisor'}}},
    {'relationship_context': {'roles': {'a': 'parent', 'b': 'child'}}},
    {'relationship_context': {'cohabiting': 'yes'}},
    {'relationship_context': {'additional_types': ['country']}},
    {'relationship_context': {'attachment': 'avoidant'}},
])
def test_unsupported_or_ambiguous_options_rejected(options):
    with pytest.raises(ValueError): settings_for(**options)


def test_yod_requires_both_orbs_and_exact_boundary_is_inclusive():
    g = geometry(sun=0, pluto=60, saturn=211)
    missing = build(g, include_minor_aspects=True, minor_orbs_degrees={'150': 1})
    assert missing['layer_availability']['yod_context']['status'] == 'not_computed'
    yes = build(g, include_minor_aspects=True, minor_orbs_degrees={'150': 1}, sextile_orb_degrees=6)
    def target_yods(r):
        return [c for c in r['observation_complexes']['people']['a'] if set(c['core_members']) == {'sun', 'pluto', 'saturn'}
                and any(v['kind'] == 'yod' for v in c['representations'])]
    assert target_yods(yes)
    no = build(geometry(sun=0, pluto=60, saturn=211.001), include_minor_aspects=True,
               minor_orbs_degrees={'150': 1}, sextile_orb_degrees=6)
    assert not target_yods(no)


def test_parent_child_focal_objects_and_parallel_ruler_background_match_mother_case():
    # Synthetic fifth-house Aquarius -> Uranus -> Sun conjunction (book p159).
    r = build(geometry(180, uranus=0, sun=0), relationship_type='family',
              relationship_context={'roles': {'a': 'parent', 'b': 'child'}})
    a, b = (r['relationship_context_observations']['people'][p] for p in ('a', 'b'))
    assert a[0]['houses'] == [5] and b[0]['houses'] == [4, 10]
    assert b[0]['points'] == ['sun', 'moon', 'saturn', 'mars', 'venus']
    fifth = r['house_ruler_comparisons']['a'][4]
    assert fifth['selected_ruler'] == 'saturn'
    assert {p['point'] for p in fifth['routes']} == {'saturn', 'uranus'}
    uranus = next(p for p in fifth['routes'] if p['point'] == 'uranus')
    assert any({lookup(r, ref)['first_point'], lookup(r, ref)['second_point']} == {'sun', 'uranus'}
               for ref in uranus['natal_aspect_refs'])
    path = next(p for p in r['review_paths'] if p['id'] == 'parallel_ruler:a:5:uranus')
    assert not path['selected'] and path['policies'] == ['modern']
    assert not path['creates_direct_contact']


def test_sibling_gemini_cusp_and_employee_authority_belong_to_correct_person():
    r = build(geometry(330), relationship_type='family',
              relationship_context={'roles': {'a': 'sibling', 'b': 'sibling'}})
    focal = r['relationship_context_observations']['people']['a']
    assert next(p for p in focal if p['reason'] == 'sibling_communication')['houses'] == [3]
    assert next(p for p in focal if p['reason'] == 'sibling_gemini_cusps')['houses'] == [4]
    work = build(relationship_type='work', relationship_context={'roles': {'a': 'supervisor', 'b': 'employee'}})
    assert work['relationship_context_observations']['people']['a'] == []
    assert work['relationship_context_observations']['people']['b'][0]['reason'] == 'employee_authority_indicators'
    swapped = build(relationship_type='work', relationship_context={'roles': {'a': 'employee', 'b': 'supervisor'}})
    assert swapped['relationship_context_observations']['people']['a'][0]['reason'] == 'employee_authority_indicators'


def test_multiple_contexts_and_cohabitation_change_selection_not_geometry():
    base = build(relationship_type='work')
    mixed = build(relationship_type='work', relationship_context={'additional_types': ['friendship', 'work'], 'cohabiting': True})
    for field in ('contacts', 'source_geometry', 'relationship_profiles', 'counts', 'observation_paths'):
        assert base[field] == mixed[field]
    assert mixed['settings']['relationship_context']['types'] == ['friendship', 'work']
    assert 'jupiter' in mixed['settings']['scenario']['points']
    assert mixed['special_contact_observations']['friendship_status'] == 'computed'
    assert mixed['special_contact_observations']['friendship_supportive_contact_ids']
    assert mixed['relationship_context_observations']['people']['a'][0]['houses'] == [4, 8, 10, 12]
    ids = [c['id'] for c in mixed['natal_observation_candidates']['a']]
    assert len(ids) == len(set(ids))
    identical = next(h for h in mixed['house_ruler_comparisons']['a'] if h['house'] == 1)
    assert len(identical['routes']) == 1 and set(identical['routes'][0]['policies']) == {'traditional', 'modern'}


def test_special_views_preserve_source_and_background_not_weight():
    r = build(geometry(), geometry(11, venus=2, saturn=1, uranus=242), relationship_type='friendship', sextile_orb_degrees=6)
    view = r['special_contact_observations']
    by_id = {c['id']: c for c in r['contacts']}
    venus = next(c for c in r['contacts'] if c['first_point']=='ascendant' and c['second_point']=='venus')
    saturn = next(c for c in r['contacts'] if c['first_point']=='ascendant' and c['second_point']=='saturn')
    assert venus['id'] in view['personal_asc_tight_contact_ids']
    assert saturn['id'] not in view['personal_asc_contact_ids']
    assert all(by_id[i]['angle'] in (0, 90, 180) for i in view['nodal_primary_contact_ids'])
    assert all(by_id[i]['angle'] not in (0, 90, 180) for i in view['nodal_background_contact_ids'])
    assert view['weights'] is None and view['contacts_omitted'] is False
    assert view['slow_planet_contexts']
    hemi = r['hemisphere_backgrounds']['a']
    assert 'sun' in hemi['below_horizon']
    assert len(hemi['below_horizon'] + hemi['above_horizon']) == 10


def test_new_views_refs_and_facts_verified_for_explicit_minor_and_context_options():
    import mcp_server
    args = dict(person_a=BIRTH, person_b=PARTNER, relationship_type='family',
        relationship_context={'roles': {'a': 'parent', 'b': 'child'}, 'cohabiting': True},
        include_minor_aspects=True, minor_orbs_degrees={'45': 1, '150': 1}, sextile_orb_degrees=6)
    raw = calculate_observation_data(**args)
    def walk(obj):
        if isinstance(obj, list):
            for v in obj: walk(v)
        elif isinstance(obj, dict):
            for k,v in obj.items():
                if k.endswith('_ref') and v is not None: lookup(raw,v)
                if k.endswith('_refs'):
                    for ref in v: lookup(raw,ref)
                if k=='rule_id': assert v in raw['provenance']
                walk(v)
    keys = ('relationship_context_observations','house_ruler_comparisons','hemisphere_backgrounds',
            'special_contact_observations','observation_comparisons','review_paths')
    for key in keys: walk(raw[key])
    good = checked_result('calculate_relationship_observation',raw,args)
    assert good['status']=='ok'
    checked = verify_calculation_claims_data(good['calculation_reference'],[
        dict(quote='Selected child role', path='/settings/relationship_context/roles/b',value='child'),
        dict(quote='Explicit quincunx', path='/settings/orbs/150',value=1.0),
        dict(quote='Yod evaluated', path='/layer_availability/yod_context/status',value='computed')])
    assert checked['counts']['supported']==3
    for key in keys[:4]:
        bad=deepcopy(raw);bad[key]={}
        assert checked_result('calculate_relationship_observation',bad,args)['status']=='validation_failed'
