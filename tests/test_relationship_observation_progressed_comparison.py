"""Fair synastry comparisons: same orbs, owner identity and node convention."""
from copy import deepcopy

import pytest

from services.relationship_observation import build_observation, settings_for, calculate_observation_data
from services.mcp_result_facts import lookup
from tests.test_relationship_observation import geometry, BIRTH, PARTNER


def synthetic(natal_moon=90, progressed_moon=90, orbs=None, enabled=True):
    orbs = orbs or {'0': 2, '60': 2, '90': 2, '120': 2, '180': 2}
    a, b = geometry(sun=0), geometry(11, moon=natal_moon)
    source = dict(transit={'points': {p: v for p, v in a['points'].items()
        if p not in ('ascendant', 'descendant', 'midheaven', 'imum_coeli')}},
        progressed={'a': geometry(sun=0), 'b': geometry(11, moon=progressed_moon)})
    cfg = dict(at='2020-01-01T00:00:00Z', transit_orbs_degrees=orbs, progression_orbs_degrees=orbs,
               include_progressed_synastry=enabled)
    return build_observation({'a': a, 'b': b}, {'a': {}, 'b': {}},
        settings_for(include_timing=True, timing=cfg), timing_sources=source)


def view(r):
    return r['timing_observations']['progressed_synastry_comparison']


def pair(r, a='sun', b='moon'):
    return next((x for x in view(r)['entries'] if (x['a_point'], x['b_point']) == (a, b)), None)


@pytest.mark.parametrize('natal,current,state', [
    (90, 90, 'same_aspect'), (90, 120, 'different_aspect'),
    (90, 100, 'natal_only'), (100, 90, 'progressed_only'), (100, 110, None)])
def test_selected_snapshot_states(natal, current, state):
    r = synthetic(natal, current); row = pair(r)
    if state is None:
        assert row is None
        return
    assert row['state'] == state
    assert ('natal_comparison_contact_ref' in row) == (natal == 90)
    assert ('progressed_contact_ref' in row) == (current in (90, 120))
    assert row['independent_evidence_added'] is False


def test_wider_static_orb_is_not_compared_with_narrower_progressed_orb():
    r = synthetic(87, 87)
    assert any(c['first_point'] == 'sun' and c['second_point'] == 'moon' for c in r['contacts'])
    assert pair(r) is None  # Neither is within 2deg; no false loss from the static 10deg policy.
    r = synthetic(87, 90)
    row = pair(r)
    assert row['state'] == 'progressed_only' and row['existing_static_contact_refs']
    assert 'natal_comparison_contact_ref' not in row


def test_sextile_comparison_does_not_enable_static_sextiles():
    r = synthetic(60, 60, {'60': 2})
    row = pair(r)
    assert row['state'] == 'same_aspect' and row['existing_static_contact_refs'] == []
    assert lookup(r, row['natal_comparison_contact_ref'])['angle'] == 60
    assert r['settings']['sextile_orb_degrees'] is None


def test_baseline_uses_actual_geometry_and_references_preserve_owners():
    r = synthetic(); v = view(r)
    for c in v['natal_comparison_contacts']:
        a, b = lookup(r, c['first_point_ref']), lookup(r, c['second_point_ref'])
        sep = abs((a-b+180) % 360-180)
        assert c['separation_degrees'] == sep
        assert c['orb_degrees'] == abs(sep-c['angle'])
        assert lookup(r, c['orb_settings_ref']) == r['settings']['timing']['progression_orbs_degrees']
        assert 'tight_contact' not in c and c['independent_evidence_added'] is False
    for row in v['entries']:
        assert len(row['natal_geometry_refs']) == len(row['progressed_geometry_refs']) == 2
        for field in ('natal_comparison_contact_ref', 'progressed_contact_ref'):
            if field in row:
                c = lookup(r, row[field])
                assert (c['first_point'], c['second_point']) == (row['a_point'], row['b_point'])
        for ref in row['existing_static_contact_refs']:
            c = lookup(r, ref)
            assert (c['first_point'], c['second_point']) == (row['a_point'], row['b_point'])
    assert v['counts']['point_pairs'] == len(v['entries']) == sum(v['counts']['by_state'].values())
    assert len({(r['a_point'], r['b_point']) for r in v['entries']}) == len(v['entries'])
    assert v['policy']['first_appearance_or_duration_inferred'] is False


def test_node_convention_difference_blocks_change_classification():
    r = synthetic(); node_rows = [x for x in view(r)['entries'] if 'north_node' in (x['a_point'], x['b_point'])]
    assert node_rows and all(x['state'] == 'not_comparable_node_conventions' and not x['comparable'] for x in node_rows)
    # Same source convention: the ordinary geometric classification becomes available.
    from services.relationship_observation_progressed_comparison import progressed_synastry_comparison
    r['settings']['node_type'] = r['settings']['timing']['node_type']
    consistent = progressed_synastry_comparison(r, r['timing_observations'])
    assert all(x['comparable'] for x in consistent['entries'])
    assert consistent['counts']['by_state']['not_comparable_node_conventions'] == 0


def test_axis_variants_do_not_make_multiple_comparison_pairs():
    r = synthetic(); v = view(r)
    for row in v['entries']:
        assert row['a_point'] not in ('south_node', 'descendant', 'imum_coeli')
        assert row['b_point'] not in ('south_node', 'descendant', 'imum_coeli')
    # Axis endpoint aliases remain representations inside a single pair.
    r = synthetic(90, 90, {'0': 10, '180': 10})
    axis_rows = [c for c in view(r)['natal_comparison_contacts']
                 if c['first_point'] in ('north_node', 'ascendant', 'midheaven')]
    assert axis_rows and all(len(c['endpoint_variants']) >= 2 for c in axis_rows)


def test_disabling_progressed_synastry_disables_comparison_without_changing_static():
    on, off = synthetic(), synthetic(enabled=False)
    assert view(off) == {'status': 'not_computed', 'reason': 'progressed_synastry_not_requested'}
    assert off['layer_availability']['progressed_synastry_comparison']['status'] == 'not_computed'
    for key in ('contacts', 'counts', 'activation_clusters', 'observation_paths', 'house_overlays'):
        assert on[key] == off[key]


def real_args():
    return dict(person_a=BIRTH, person_b=PARTNER, include_timing=True, timing={
        'at': '2020-06-01T07:30:00Z', 'transit_orbs_degrees': {'0': 2, '90': 2, '180': 2},
        'progression_orbs_degrees': {'0': 2, '60': 2, '90': 2, '120': 2, '180': 2}})


def test_real_birth_exchange_preserves_comparison_with_owners_reversed():
    args = real_args(); ab = calculate_observation_data(**args)
    args['person_a'], args['person_b'] = args['person_b'], args['person_a']
    ba = calculate_observation_data(**args)
    assert ab['status'] == ba['status'] == 'ok'
    assert {(r['a_point'], r['b_point']): r['state'] for r in view(ab)['entries']} == {
        (r['b_point'], r['a_point']): r['state'] for r in view(ba)['entries']}


def test_recompute_reference_and_corrupt_comparison_rejected():
    import mcp_server
    from services.mcp_result_facts import checked_result, verify_calculation_claims_data
    args = real_args(); raw = calculate_observation_data(**args)
    result = checked_result('calculate_relationship_observation', raw, args)
    assert result['status'] == 'ok', result
    claims = [dict(quote='Same orb comparison', path='/timing_observations/progressed_synastry_comparison/policy/natal_and_progressed_use_same_orbs', value=True),
              dict(quote='Comparison count', path='/timing_observations/progressed_synastry_comparison/counts/point_pairs', value=view(result)['counts']['point_pairs'])]
    assert verify_calculation_claims_data(result['calculation_reference'], claims)['counts']['supported'] == 2
    for field in ('entries', 'natal_comparison_contacts'):
        bad = deepcopy(raw); view(bad)[field].pop()
        assert checked_result('calculate_relationship_observation', bad, args)['status'] == 'validation_failed'
    bad = deepcopy(raw); view(bad)['entries'][0]['state'] = 'same_aspect' if view(bad)['entries'][0]['state'] != 'same_aspect' else 'natal_only'
    assert checked_result('calculate_relationship_observation', bad, args)['status'] == 'validation_failed'
