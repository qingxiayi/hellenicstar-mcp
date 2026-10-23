"""Full configurations must not manufacture contacts or psychological propagation."""
from copy import deepcopy

from services.relationship_charts import PLANETS
from services.relationship_observation import calculate_observation_data, contacts_between, settings_for
from services.natal_structure_graph import motifs
from test_relationship_observation import build, geometry, BIRTH, PARTNER


def test_full_t_square_includes_members_without_direct_contact():
    a = geometry(sun=0, moon=189, mars=99)
    b = geometry(20, **{p: 351 for p in PLANETS})
    r = build(a, b)
    config = next(c for c in r['natal_configurations']['a']
                  if set(c['members']) == {'sun', 'moon', 'mars'})
    activation = next(c for c in r['configuration_activations'] if c['configuration_id'] == config['id'])
    assert config['kind'] == 't_square'
    assert activation['direct_members'] == ['sun']
    assert activation['associated_only_members'] == ['mars', 'moon']
    assert len(activation['contact_ids']) == len(set(activation['contact_ids']))
    assert all(g['direct_members'] == ['sun'] for g in activation['source_groups'])
    baseline = contacts_between(a['points'], b['points'], 'a', 'b', settings_for())
    assert r['contacts'] == baseline
    assert r['counts']['observation_paths'] == 2 * len(baseline)
    assert not any(c['target_person'] == 'a' and c['target_point'] in ('moon', 'mars')
                   for c in r['activation_clusters'])


def test_chiron_membership_and_no_axis_patterns_or_recursive_expansion():
    r = build(geometry(moon=0, jupiter=90, chiron=180))
    assert any(set(c['members']) == {'moon', 'jupiter', 'chiron'}
               for c in r['natal_configurations']['a'])
    assert all(set(c['members']) <= set(PLANETS) for rows in r['natal_configurations'].values() for c in rows)
    r = build(geometry(sun=0, moon=9, mercury=18))
    assert not any(set(c['members']) == {'sun', 'moon', 'mercury'} for c in r['natal_configurations']['a'])
    assert r['layer_availability']['configuration_membership']['recursive_expansion'] is False


def test_sextile_dependent_pattern_requires_explicit_orb_and_keeps_containment():
    a = geometry(sun=0, moon=120, mars=240, jupiter=180)
    no, yes = build(a), build(a, sextile_orb_degrees=5)
    members = {'sun', 'moon', 'mars', 'jupiter'}
    assert not any(set(c['members']) == members for c in no['natal_configurations']['a'])
    kite = next(c for c in yes['natal_configurations']['a'] if c['kind'] == 'kite' and set(c['members']) == members)
    assert kite['contains']
    for p in members:
        assert kite['id'] in yes['configuration_memberships']['a'][p]
    assert yes['layer_availability']['configuration_bridges']['counts_are_additive'] is False


def test_two_sided_bridges_only_reference_actual_contacts_and_swap_symmetrically():
    a, b = geometry(sun=0, moon=180, mars=90), geometry(11, venus=0, saturn=180, chiron=90)
    r, swapped = build(a, b), build(b, a)
    assert r['configuration_bridges']
    contacts = {c['id']: c for c in r['contacts']}
    configs = {c['id']: c for rows in r['natal_configurations'].values() for c in rows}
    for bridge in r['configuration_bridges']:
        assert len(set(bridge['contact_ids'])) == bridge['direct_contact_count']
        for identity in bridge['contact_ids']:
            c = contacts[identity]
            assert c['first_point'] in configs[bridge['a_configuration_id']]['members']
            assert c['second_point'] in configs[bridge['b_configuration_id']]['members']
    def normalize(result, reverse=False):
        return {(r['b_configuration_id'][2:] if reverse else r['a_configuration_id'][2:],
                 r['a_configuration_id'][2:] if reverse else r['b_configuration_id'][2:],
                 r['direct_contact_count']) for r in result['configuration_bridges']}
    assert normalize(r) == normalize(swapped, True)


def test_existing_natal_motif_default_scope_does_not_change():
    edges = [dict(id=str(i), **{'from': a, 'to': b}, angle=angle, orb=0)
             for i, (a, b, angle) in enumerate([
                 ('moon', 'chiron', 180), ('moon', 'jupiter', 90), ('chiron', 'jupiter', 90)])]
    assert motifs(edges) == []
    assert motifs(edges, point_ids=PLANETS)[0]['kind'] == 't_square'


def test_real_background_reuses_natal_selection_and_two_source_calculations(monkeypatch):
    import services.mcp_natal as natal
    from services.natal_salience import build_salience
    calls = []
    original = natal._compute_source
    def counted(**args):
        calls.append(args)
        return original(**args)
    monkeypatch.setattr(natal, '_compute_source', counted)
    result = calculate_observation_data(person_a=BIRTH, person_b=PARTNER)
    assert result['status'] == 'ok' and len(calls) == 2
    assert result['settings']['node_type'] == 'mean'
    for who, bg in result['natal_backgrounds'].items():
        expected = build_salience(bg['source_graph'], dict(rulership='traditional'))
        assert bg['schema_version'] == expected['schema_version']
        assert bg['settings'] == expected['method']['config']
        assert bg['relationship_orbs_applied'] is False
        for evidence in bg['evidence_index'].values():
            for ref in evidence['source_refs']:
                value = bg
                for key in ref.lstrip('/').split('/'):
                    value = value[int(key)] if isinstance(value, list) else value[key]
        assert {p for p, row in bg['points'].items() if row['selected_as_natal_priority']} == set(expected['focus_selection']['planet_ids'])
        for point, row in bg['points'].items():
            assert row['mutual_receptions'] == expected['planet_profiles'][point]['receptions']
            assert row['contact_effect'] == 'none'
        for cluster in result['activation_clusters']:
            if cluster['target_person'] == who and cluster['target_point'] in bg['points']:
                assert cluster['natal_background_ref'].endswith('/' + cluster['target_point'])


def test_new_layers_verified_and_tampering_blocked():
    import mcp_server  # registers reference contracts
    from services.mcp_result_facts import checked_result, verify_calculation_claims_data
    args = dict(person_a=BIRTH, person_b=PARTNER)
    raw = calculate_observation_data(**args)
    good = checked_result('calculate_relationship_observation', raw, args)
    assert good['status'] == 'ok'
    check = verify_calculation_claims_data(reference=good['calculation_reference'], claims=[
        dict(quote='No automatic activation through identity',
             path='/natal_backgrounds/a/points/venus/contact_effect', value='none'),
        dict(quote='Rule version', path='/schema_version', value='john-green-observation-v0.14')])
    assert check['counts']['supported'] == 2
    for field in ('configuration_bridges', 'configuration_activations'):
        assert raw[field]
        bad = deepcopy(raw)
        bad[field][0]['contact_ids'].append('invented')
        assert checked_result('calculate_relationship_observation', bad, args)['status'] == 'validation_failed'
    bad = deepcopy(raw)
    bad['natal_backgrounds']['a']['points']['venus']['selected_as_natal_priority'] = not bad['natal_backgrounds']['a']['points']['venus']['selected_as_natal_priority']
    assert checked_result('calculate_relationship_observation', bad, args)['status'] == 'validation_failed'


def test_natal_mode_has_memberships_but_no_activation_or_bridge():
    r = calculate_observation_data(person_a=BIRTH, mode='natal', ruler_profile='modern')
    assert r['natal_configurations']['a']
    assert r['natal_backgrounds']['a']['settings']['rulership'] == 'modern'
    assert r['configuration_activations'] == r['configuration_bridges'] == []
    assert r['layer_availability']['configuration_bridges']['status'] == 'not_computed'


def test_same_source_hitting_multiple_members_is_one_group():
    r = build(geometry(sun=0, moon=180, mars=90), geometry(11, saturn=0))
    config = next(c for c in r['natal_configurations']['a'] if set(c['members']) == {'sun', 'moon', 'mars'})
    activation = next(a for a in r['configuration_activations'] if a['configuration_id'] == config['id'])
    groups = [g for g in activation['source_groups'] if g['source_point'] == 'saturn']
    assert len(groups) == 1
    assert set(groups[0]['direct_members']) == {'sun', 'moon', 'mars'}
    assert len(set(groups[0]['contact_ids'])) == 3
