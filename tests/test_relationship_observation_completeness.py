"""Source-audit gaps: bounded grouping, factual comparison and selection rules."""
from copy import deepcopy

import pytest

from services.mcp_result_facts import checked_result, lookup, verify_calculation_claims_data
from services.relationship_observation import calculate_observation_data
from services.relationship_observation_routes import is_relationship_role
from services.relationship_observation_complexes import canonical
from test_relationship_observation import build, geometry, BIRTH, PARTNER


def complex_for(result, kind, core):
    return next(c for c in result['observation_complexes']['people']['a']
                if c['seed_type'] == kind and set(c['core_members']) == set(core))


def test_conjunction_context_groups_indirect_neighbors_but_stops_before_next_hop():
    r = build(geometry(sun=0, saturn=8, moon=16, jupiter=24), geometry(11, neptune=351))
    c = complex_for(r, 'conjunction_pair', ['sun', 'saturn'])
    assert 'moon' in c['members'] and 'jupiter' not in c['members']
    moon = next(p for p in c['attached_members'] if p['point'] == 'moon')
    assert moon['via_core_members'] == ['saturn']
    source = next(g for g in c['source_groups'] if g['source_point'] == 'neptune')
    assert 'sun' in source['direct_members'] and 'moon' not in source['direct_members']
    assert source['core_contact_ids']
    assert not c['whole_complex_activation_inferred']
    assert not any(e['first_point'] == 'moon' and e['second_point'] == 'neptune' for e in r['contacts'])


def test_named_core_adds_only_conjunction_satellites_not_satellites_neighbors():
    r = build(geometry(sun=0, moon=120, mars=240, venus=8, mercury=16))
    c = complex_for(r, 'named_pattern', ['sun', 'moon', 'mars'])
    assert {'sun', 'moon', 'mars', 'venus'} <= set(c['members'])
    assert 'mercury' not in c['members']
    assert all(p['relation'] == 'conjunction_satellite' for p in c['attached_members'])
    assert c['legacy_configuration_ids']


def test_axis_patterns_keep_actual_endpoint_representations_and_one_axis_vertex():
    r = build(geometry(sun=0, mars=240, north_node=300, south_node=120))
    c = complex_for(r, 'named_pattern', ['sun', 'mars', 'north_node'])
    assert {'kind': 'grand_trine', 'members': ['mars', 'south_node', 'sun']} in c['representations']
    assert not c['legacy_configuration_ids']
    assert all('north_node' not in p['members'] for p in r['natal_configurations']['a'])
    for rows in r['observation_complexes']['people'].values():
        for row in rows:
            assert len(row['core_members']) == len(set(row['core_members']))
            for v in row['representations']:
                assert len(v['members']) == len({canonical(p) for p in v['members']})
                assert v['kind'] not in ('kite', 'minor_grand_trine', 'wedge', 'mystic_rectangle')
    angle = build(geometry(180, sun=0, moon=90))
    assert complex_for(angle, 'named_pattern', ['sun', 'moon', 'ascendant'])
    enabled = build(geometry(sun=0, mars=240, north_node=300, south_node=120), sextile_orb_degrees=6)
    c = complex_for(enabled, 'named_pattern', ['sun', 'mars', 'north_node'])
    assert any(v['kind'] == 'minor_grand_trine' for v in c['representations'])


def test_shared_natal_pair_is_independent_of_cross_contact_and_preserves_aspect_difference():
    r = build(geometry(sun=0, neptune=90), geometry(11, sun=45, neptune=225))
    row = next(p for p in r['observation_comparisons']['shared_natal_pairs']
               if set(p['points']) == {'sun', 'neptune'})
    assert lookup(r, row['a_natal_aspect_ref'])['aspect'] == 'square'
    assert lookup(r, row['b_natal_aspect_ref'])['aspect'] == 'opposition'
    assert not row['same_aspect'] and row['contact_ids'] == []
    assert row['shared_psychological_theme'] == 'not_inferred'
    assert r['layer_availability']['shared_natal_pairs']['status'] == 'computed'
    assert r['layer_availability']['shared_themes']['status'] == 'not_computed'


def test_descendant_correspondence_is_directional_sign_equality_not_an_aspect():
    r = build(geometry(), geometry(11, moon=205))
    matches = r['observation_comparisons']['descendant_sign_correspondences']
    row = next(p for p in matches if p['person'] == 'a' and p['partner_point'] == 'moon')
    assert row['sign'] == 'Lib' and row['partner'] == 'b'
    assert not row['creates_direct_contact'] and row['attraction'] == 'not_inferred'
    assert not any(c['first_point'] == 'ascendant' and c['second_point'] == 'moon' for c in r['contacts'])
    boundary = build(geometry(), geometry(11, moon=210))
    assert not any(p['person'] == 'a' and p['partner_point'] == 'moon'
                   for p in boundary['observation_comparisons']['descendant_sign_correspondences'])
    swapped = build(geometry(11, moon=205), geometry())
    assert any(p['person'] == 'b' and p['partner_point'] == 'moon'
               for p in swapped['observation_comparisons']['descendant_sign_correspondences'])


def test_nodal_house_candidate_is_one_axis_and_chart_ruler_role_is_additive():
    r = build(geometry(north_node=20, south_node=200, mars=190), mode='natal')
    rows = r['natal_observation_candidates']['a']
    nodes = [p for p in rows if p['point'] in ('north_node', 'south_node')]
    assert len(nodes) == 1 and nodes[0]['point'] == 'north_node'
    assert {lookup(r, ref)['house'] for ref in nodes[0]['axis_endpoint_refs']} == {1, 7}
    assert 'nodal_axis_first_seventh' in {p['role'] for p in nodes[0]['selection_reasons']}
    mars = next(p for p in rows if p['point'] == 'mars')
    roles = {p['role'] for p in mars['selection_reasons']}
    assert {'chart_ruler_in_seventh', 'projection_house_planet'} <= roles
    outside = build(geometry(north_node=175, south_node=355), mode='natal')
    assert not any(p['point'] == 'north_node' for p in outside['natal_observation_candidates']['a'])


def test_relationship_sort_uses_same_target_role_classifier_without_changing_facts():
    a, b = geometry(sun=0, neptune=90), geometry(11, sun=45, neptune=225)
    base, sorted_ = build(a, b), build(a, b, sort_by='relationship_indicators')
    assert base['contacts'] == sorted_['contacts'] and base['counts'] == sorted_['counts']
    assert base['observation_complexes'] == sorted_['observation_complexes']
    for c in sorted_['activation_clusters']:
        rows = sorted_['natal_observation_candidates'][c['target_person']]
        candidate = next((p for p in rows if p['point'] == c['target_point']), None)
        expected = bool(candidate and any(is_relationship_role(r['role']) for r in candidate['selection_reasons']))
        assert c['observation_context']['target_relationship_indicator'] == expected
    mercury = next(c for c in sorted_['activation_clusters'] if c['id'] == 'a:mercury')
    assert mercury['observation_context']['target_relationship_indicator']
    assert not mercury['observation_context']['scenario_indicator']
    keys = [(-int(c['observation_context']['target_relationship_indicator']), c['min_direct_orb_degrees'], c['id'])
            for c in sorted_['activation_clusters']]
    assert keys == sorted(keys)


@pytest.mark.parametrize('mode', ['natal', 'synastry'])
def test_complex_and_comparison_references_are_valid_and_counts_never_add(mode):
    r = build(mode=mode, sextile_orb_degrees=6)
    def walk(obj):
        if isinstance(obj, list):
            for item in obj: walk(item)
        elif isinstance(obj, dict):
            for key, value in obj.items():
                if key.endswith('_ref') and value is not None: lookup(r, value)
                if key.endswith('_refs'):
                    for ref in value: lookup(r, ref)
                if key == 'rule_id': assert value in r['provenance']
                walk(value)
    for key in ('observation_complexes', 'observation_comparisons', 'review_paths', 'natal_observation_candidates'):
        walk(r[key])
    contacts = {c['id']: c for c in r['contacts']}
    for who, rows in r['observation_complexes']['people'].items():
        assert len({c['id'] for c in rows}) == len(rows)
        side = 'first' if who == 'a' else 'second'
        for c in rows:
            assert len(c['contact_ids']) == len(set(c['contact_ids']))
            assert set(c['contact_ids']) <= contacts.keys()
            direct = {contacts[i][side + '_point'] for i in c['contact_ids']}
            assert set(c['direct_core_members']) | set(c['direct_attached_members']) == direct
            assert set(c['associated_only_members']) == set(c['members']) - direct
    assert r['counts']['observation_paths'] == 2 * r['counts']['unique_contacts']
    if mode == 'natal':
        assert not r['observation_comparisons']['shared_natal_pairs']
        assert not r['observation_comparisons']['descendant_sign_correspondences']
        assert r['observation_complexes']['cross_contact_status'] == 'not_computed'


def test_complexes_and_comparisons_are_recomputed_and_tampering_rejected():
    import mcp_server
    args = dict(person_a=BIRTH, person_b=PARTNER)
    raw = calculate_observation_data(**args)
    good = checked_result('calculate_relationship_observation', raw, args)
    assert good['status'] == 'ok'
    verified = verify_calculation_claims_data(good['calculation_reference'], [
        dict(quote='Bounded context', path='/observation_complexes/policy/recursive_expansion', value=False),
        dict(quote='Comparison evaluated', path='/layer_availability/shared_natal_pairs/status', value='computed')])
    assert verified['counts']['supported'] == 2
    for key, value in [('observation_complexes', {}), ('observation_comparisons', {})]:
        bad = deepcopy(raw); bad[key] = value
        assert checked_result('calculate_relationship_observation', bad, args)['status'] == 'validation_failed'
