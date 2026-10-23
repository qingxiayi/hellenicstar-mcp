"""Priority reasons and display containment must not alter calculation evidence."""
from copy import deepcopy

from services.relationship_observation import calculate_observation_data
from services.relationship_observation_views import build_review, build_structure_display
from test_relationship_observation import build, geometry, BIRTH, PARTNER


def test_reasons_refer_to_actual_contacts_and_preserve_direction_and_orb():
    r = build(geometry(sun=0, mercury=17), geometry(11, pluto=0, mercury=22))
    review = r['observation_review']
    assert review['policy']['score'] is None
    assert review['policy']['cross_dimension_order'] is None
    assert review['policy']['actual_life_difficulty'] == 'not_inferred'
    contact = next(c for c in r['contacts'] if c['first_point'] == 'sun' and c['second_point'] == 'pluto')
    a = next(e for e in review['entries'] if e['cluster_id'] == 'a:sun')
    b = next(e for e in review['entries'] if e['cluster_id'] == 'b:pluto')
    for row in (a, b):
        assert contact['id'] in row['reasons']['inner_outer_contacts']['contact_ids']
        assert contact['id'] in row['reasons']['parental_indicators']['contact_ids']
        assert contact['id'] in row['reasons']['tight_contacts']['contact_ids']
        assert any(x['person'] == 'a' and x['point'] == 'sun' and 'father_indicator' in x['roles']
                   for x in row['endpoint_roles'])
    hits = {c['id']: c for c in r['contacts']}
    for row in review['entries']:
        for reason in row['reasons'].values():
            assert set(reason.get('contact_ids', [])) <= set(row['contact_ids'])
        tight = row['reasons']['tight_contacts']['contact_ids']
        wide = row['reasons']['wider_contacts']['contact_ids']
        assert set(tight).isdisjoint(wide)
        assert set(tight + wide) == set(row['contact_ids'])
        assert all(hits[i]['orb_degrees'] <= 5 for i in tight)
        assert all(hits[i]['orb_degrees'] > 5 for i in wide)


def test_role_lenses_change_with_scenario_without_changing_evidence():
    a = build(relationship_type='love')
    b = build(relationship_type='friendship')
    assert a['contacts'] == b['contacts'] and a['counts'] == b['counts']
    def mercury_roles(result):
        return [x['roles'] for row in result['observation_review']['entries'] for x in row['endpoint_roles']
                if x['person'] == 'a' and x['point'] == 'mercury']
    assert all('scenario_planet' not in roles for roles in mercury_roles(a))
    assert all('scenario_planet' in roles for roles in mercury_roles(b))
    for person, lenses in b['observation_review']['lenses'].items():
        for ids in lenses.values():
            assert len(set(ids)) == len(ids)
            assert all(i.startswith(person + ':') for i in ids)


def test_review_builder_does_not_mutate_or_infer_from_background_priority():
    r = build()
    before = deepcopy(r)
    build_review(r['relationship_profiles'], r['contacts'], r['activation_clusters'], r, r['settings'])
    assert r == before
    assert all('selected_as_natal_priority' not in e['reasons'] for e in r['observation_review']['entries'])


def test_kite_folds_contained_patterns_and_bridge_children_but_keeps_all_raw_rows():
    a = geometry(sun=0, moon=120, mars=240, jupiter=180)
    r = build(a, a, sextile_orb_degrees=5)
    view = r['structure_display']
    configs = {c['id']: c for rows in r['natal_configurations'].values() for c in rows}
    bridges = {b['id']: b for b in r['configuration_bridges']}
    assert view['folded_bridges']
    for who, person in view['people'].items():
        all_ids = set(person['top_level_configuration_ids']) | {c['configuration_id'] for c in person['folded_configurations']}
        assert all_ids == {c['id'] for c in r['natal_configurations'][who]}
        for child in person['folded_configurations']:
            for parent in child['parent_configuration_ids']:
                assert parent in person['top_level_configuration_ids']
                assert set(configs[child['configuration_id']]['depends_on']) < set(configs[parent]['depends_on'])
    assert set(view['top_level_bridge_ids']) | {b['bridge_id'] for b in view['folded_bridges']} == set(bridges)
    for child in view['folded_bridges']:
        for parent in child['parent_bridge_ids']:
            assert parent in view['top_level_bridge_ids']
            assert set(bridges[child['bridge_id']]['contact_ids']) <= set(bridges[parent]['contact_ids'])
    assert len({c['id'] for c in r['contacts']}) == r['counts']['unique_contacts']
    activations = {a['id']: a for a in r['configuration_activations']}
    for entry in r['observation_review']['configuration_entries']:
        assert entry['contact_ids'] == activations[entry['activation_id']]['contact_ids']
        for ids in entry['reason_contact_ids'].values():
            assert len(set(ids)) == len(ids)
            assert set(ids) <= set(entry['contact_ids'])


def test_partial_overlap_remains_separate_and_multiple_parents_are_retained():
    associations = dict(natal_configurations={'a': [
        dict(id='a:child', contains=[], overlaps=['a:left', 'a:right']),
        dict(id='a:left', contains=['a:child'], overlaps=['a:child', 'a:right']),
        dict(id='a:right', contains=['a:child'], overlaps=['a:child', 'a:left'])]},
        configuration_activations=[], configuration_bridges=[])
    result = build_structure_display(associations)['people']['a']
    assert result['top_level_configuration_ids'] == ['a:left', 'a:right']
    assert result['folded_configurations'][0]['parent_configuration_ids'] == ['a:left', 'a:right']


def test_natal_mode_folds_natal_structures_without_suggesting_cross_contacts():
    r = calculate_observation_data(person_a=BIRTH, mode='natal')
    assert r['status'] == 'ok'
    assert r['observation_review']['status'] == 'not_computed'
    assert r['observation_review']['entries'] == []
    assert r['structure_display']['top_level_bridge_ids'] == []
    assert r['structure_display']['people']['a']['top_level_configuration_ids']


def test_new_views_are_verified_and_tampering_is_blocked():
    import mcp_server
    from services.mcp_result_facts import checked_result, verify_calculation_claims_data
    args = dict(person_a=BIRTH, person_b=PARTNER, sextile_orb_degrees=6.0)
    raw = calculate_observation_data(**args)
    result = checked_result('calculate_relationship_observation', raw, args)
    assert result['status'] == 'ok'
    verified = verify_calculation_claims_data(reference=result['calculation_reference'], claims=[
        dict(quote='No inferred client difficulty', path='/observation_review/policy/actual_life_difficulty', value='not_inferred'),
        dict(quote='Folded view top level', path='/structure_display/people/a/top_level_configuration_ids',
             value=raw['structure_display']['people']['a']['top_level_configuration_ids'])])
    assert verified['counts']['supported'] == 2
    bad = deepcopy(raw)
    bad['observation_review']['entries'][0]['reasons']['inner_outer_contacts']['contact_ids'].append('invented')
    assert checked_result('calculate_relationship_observation', bad, args)['status'] == 'validation_failed'
    bad = deepcopy(raw)
    bad['structure_display']['people']['a']['top_level_configuration_ids'].append('invented')
    assert checked_result('calculate_relationship_observation', bad, args)['status'] == 'validation_failed'
