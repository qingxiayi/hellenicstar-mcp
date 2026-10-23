"""Observation condition coverage, ownership and non-propagation boundaries."""
from copy import deepcopy

import pytest

from services.mcp_result_facts import checked_result, lookup, verify_calculation_claims_data
from services.relationship_observation import calculate_observation_data
from test_relationship_observation import build, geometry, BIRTH, PARTNER


def candidate(result, person, point):
    return next(r for r in result['natal_observation_candidates'][person] if r['point'] == point)


def roles(row):
    return {r['role'] for r in row['selection_reasons']}


def test_natal_candidates_do_not_require_partner_hit_or_salience_selection():
    r = build(geometry(neptune=130, mars=359), mode='natal')
    assert not r['contacts'] and not r['overlay_contexts']
    assert 'communication_indicator' in roles(candidate(r, 'a', 'mercury'))
    assert 'scenario_house_5_planet' in roles(candidate(r, 'a', 'neptune'))
    assert 'projection_twelfth_candidate' in roles(candidate(r, 'a', 'mars'))
    assert 'mars' not in r['relationship_profiles']['a']['projected_planets']
    assert all(not c['contact_ids'] for c in r['natal_observation_candidates']['a'])
    assert not r['observation_route_policy']['selection_uses_natal_salience']
    assert r['observation_comparisons']['cross_chart_status'] == 'not_computed'
    assert r['observation_comparisons']['moon_venus_natal'][0]['status'] == 'computed'
    assert not any(p['kind'] == 'direct_contact' for p in r['review_paths'])


def test_projection_candidates_use_real_planet_oppositions_and_both_node_ends():
    r = build(geometry(mars=40, venus=220, jupiter=210), mode='natal')
    assert 'projection_opposition_candidate' in roles(candidate(r, 'a', 'mars'))
    assert 'projection_opposition_candidate' in roles(candidate(r, 'a', 'venus'))
    assert 'natal_node_conjunction_candidate' in roles(candidate(r, 'a', 'jupiter'))
    for row in r['natal_observation_candidates']['a']:
        if row['point'] in ('ascendant', 'descendant', 'midheaven', 'imum_coeli'):
            assert 'projection_opposition_candidate' not in roles(row)
        assert row['actual_projection'] == 'not_inferred'


def test_context_can_reach_moon_without_fabricating_a_cross_contact():
    r = build(geometry(neptune=0, moon=99), geometry(11, uranus=351))
    hit = next(c for c in r['contacts'] if (c['first_point'], c['second_point']) == ('neptune', 'uranus'))
    assert not any((c['first_point'], c['second_point']) == ('moon', 'uranus') for c in r['contacts'])
    paths = {p['id']: p for p in r['review_paths']}
    direct = paths['direct:' + hit['id'] + '->a']
    linked = next(paths[k] for k in direct['natal_context_path_ids']
                  if paths[k]['kind'] == 'natal_aspect_context' and paths[k]['target_point'] == 'moon')
    assert 'mother_indicator' in roles(lookup(r, linked['target_candidate_ref']))
    assert linked['creates_direct_contact'] is False
    assert 'contact_id' not in linked
    reverse = paths['direct:' + hit['id'] + '->b']
    assert reverse['target_ref'] == '/relationship_profiles/b/points/uranus'
    assert all(paths[k]['person'] == 'b' for k in reverse['natal_context_path_ids'])
    assert r['counts']['observation_paths'] == 2 * r['counts']['unique_contacts']


def test_natal_routes_stop_at_one_hop_and_do_not_follow_dispositor_chains():
    r = build(geometry(sun=0, moon=9, mercury=18))
    routes = [p for p in r['review_paths'] if p['kind'] == 'natal_aspect_context'
              and p['origin_ref'] == '/relationship_profiles/a/points/sun']
    assert 'moon' in {p['target_point'] for p in routes}
    assert 'mercury' not in {p['target_point'] for p in routes}
    assert all('natal_context_path_ids' not in p for p in routes)
    assert not any(p['kind'] in ('dispositor', 'mutual_reception') for p in r['review_paths'])


def test_fifth_house_ruler_is_context_and_multiple_roles_do_not_duplicate_candidates():
    r = build(geometry(180, uranus=0, sun=0), mode='natal', ruler_profile='modern')
    prof = r['relationship_profiles']['a']
    assert prof['houses'][4]['cusp_sign'] == 'Aqu'
    path = next(p for p in r['review_paths'] if p['id'] == 'ruler:a:5')
    assert path['target_point'] == 'uranus'
    assert 'scenario_house_5_ruler' in roles(candidate(r, 'a', 'uranus'))
    assert any(p['id'] in path['natal_context_path_ids'] and p.get('target_point') == 'sun'
               for p in r['review_paths'])
    ids = [c['id'] for c in r['natal_observation_candidates']['a']]
    assert len(ids) == len(set(ids))
    assert all(not p['creates_direct_contact'] for p in r['review_paths'])


def test_overlay_context_belongs_to_house_owner_and_does_not_create_aspects():
    r = build(geometry(), geometry(11, venus=5, sun=12))
    row = next(o for o in r['overlay_contexts'] if o['id'] == 'b:venus->a:house:1')
    assert row['source_point_ref'] == '/relationship_profiles/b/points/venus'
    assert row['target_house_ref'] == '/relationship_profiles/a/houses/0'
    special = row['first_house_venus_context']
    assert special['ascendant_ref'] == '/relationship_profiles/a/points/ascendant'
    assert special['chart_ruler_ref'] == '/relationship_profiles/a/points/mars'
    assert row['distance_to_next_target_cusp'] == 25
    sun = next(o for o in r['overlay_contexts'] if o['id'] == 'b:sun->a:house:1')
    assert sun['first_house_venus_context'] is None  # Do not generalize a specific example silently.
    assert all(c['second_point'] == 'venus' for c in r['contacts'] if c['id'] in row['same_source_contact_ids'])
    swapped = build(geometry(11, venus=5, sun=12), geometry())
    row2 = next(o for o in swapped['overlay_contexts'] if o['id'] == 'a:venus->b:house:1')
    assert row2['target_ruler_ref'] == '/relationship_profiles/b/points/mars'


def test_reciprocal_pairs_are_two_contacts_not_two_views_of_one_contact():
    r = build(geometry(sun=0, mercury=90), geometry(11, mercury=0, sun=90))
    comparison = r['observation_comparisons']
    row = next(p for p in comparison['reciprocal_planet_pairs'] if p['points'] == ['mercury', 'sun'])
    assert len(set(row['contact_ids'])) == 2 and row['same_aspect']
    assert all(c['first_point'] != c['second_point'] for c in (lookup(r, p) for p in row['contact_refs']))
    same = next(p for p in comparison['same_planet_contexts'] if p['point'] == 'sun')
    assert len(same['contact_ids']) == 1
    assert same['a']['point_ref'] != same['b']['point_ref']


def test_same_element_without_aspect_does_not_generate_contact_or_match_score():
    r = build(geometry(sun=1), geometry(11, sun=25))
    row = next(x for x in r['observation_comparisons']['luminary_mercury_elements'] if x['point'] == 'sun')
    assert row['same_element'] and row['elements'] == {'a': 'fire', 'b': 'fire'}
    assert not any(c['first_point'] == c['second_point'] == 'sun' for c in r['contacts'])
    assert 'score' not in row


def test_scenario_changes_reasons_but_not_geometry_or_projected_overlay_scope():
    a = geometry(neptune=310)
    love, friends = build(a), build(a, relationship_type='friendship')
    assert love['contacts'] == friends['contacts'] and love['counts'] == friends['counts']
    assert love['projected_planet_overlays'] == friends['projected_planet_overlays']
    assert 'scenario_house_11_planet' in roles(candidate(friends, 'a', 'neptune'))
    maybe = next((r for r in love['natal_observation_candidates']['a'] if r['point'] == 'neptune'), None)
    assert maybe is None or 'scenario_house_11_planet' not in roles(maybe)
    assert 'communication_indicator' in roles(candidate(love, 'a', 'mercury'))


@pytest.mark.parametrize('mode', ['natal', 'synastry'])
def test_every_pointer_path_id_and_provenance_resolves(mode):
    r = build(mode=mode, sextile_orb_degrees=6)
    paths = {p['id']: p for p in r['review_paths']}
    assert len(paths) == len(r['review_paths'])
    def walk(obj):
        if isinstance(obj, list):
            for item in obj: walk(item)
        if not isinstance(obj, dict): return
        for key, value in obj.items():
            if key.endswith('_ref') and value is not None:
                lookup(r, value)
            elif key in ('fact_refs', 'contact_refs', 'target_occupant_refs'):
                for ref in value: lookup(r, ref)
            elif key.endswith('_path_ids'):
                # Observation path IDs live in the original, separate collection.
                allowed = {p['id'] for p in r['observation_paths']} if key == 'observation_path_ids' else paths
                assert set(value) <= set(allowed)
            elif key.endswith('_path_id'):
                assert value in paths
            elif key == 'rule_id':
                assert value in r['provenance']
            walk(value)
    for key in ('natal_observation_candidates', 'review_paths', 'overlay_contexts',
                'observation_comparisons', 'observation_route_policy'):
        walk(r[key])


def test_new_fields_are_verified_and_tampering_is_withheld():
    import mcp_server  # registers calculation verifier
    args = dict(person_a=BIRTH, person_b=PARTNER)
    raw = calculate_observation_data(**args)
    good = checked_result('calculate_relationship_observation', raw, args)
    assert good['status'] == 'ok'
    verified = verify_calculation_claims_data(good['calculation_reference'], [
        dict(quote='Selected role', path='/natal_observation_candidates/a/0/selection_reasons/0/role',
             value=raw['natal_observation_candidates']['a'][0]['selection_reasons'][0]['role']),
        dict(quote='No new geometric contacts', path='/observation_route_policy/affects_contact_counts', value=False)])
    assert verified['counts']['supported'] == 2
    for field in ('natal_observation_candidates', 'review_paths', 'overlay_contexts', 'observation_comparisons'):
        bad = deepcopy(raw)
        bad[field] = {} if isinstance(raw[field], dict) else []
        assert checked_result('calculate_relationship_observation', bad, args)['status'] == 'validation_failed'
