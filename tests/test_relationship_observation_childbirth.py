"""Childbirth source identity, scope, timezone handling and evidence reuse."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from services.relationship_observation import calculate_observation_data, settings_for
from tests.test_relationship_observation import BIRTH
from tests.test_relationship_observation_v010 import lookup

PARENT = {**BIRTH, 'year': 1970}


def request():
    return dict(person_a=PARENT, person_b=BIRTH, relationship_type='family',
        relationship_context={'roles': {'a': 'parent', 'b': 'child'}}, include_timing=True,
        timing={'event': 'childbirth', 'transit_orbs_degrees': {'0': 2, '60': 2, '90': 2, '180': 2},
                'progression_orbs_degrees': {'0': 2, '90': 2, '180': 2}})


@pytest.fixture(scope='module')
def result():
    r = calculate_observation_data(**request())
    assert r['status'] == 'ok', r
    return r


def test_child_birth_is_resolved_not_assumed_noon_and_all_bodies_agree(result):
    t = result['timing_observations']; v = t['childbirth_observation']
    assert v['at_utc'] == '2000-01-01T04:00:00+00:00'
    assert v['source_agreement']['max_residual_degrees'] < 1e-8
    assert len(v['source_agreement']['checked_points']) == 13
    assert result['settings']['timing']['excluded_transit_points'] == []
    assert t['node_conventions'] == {'natal': 'mean', 'transit': 'mean', 'progressed': 'mean', 'same_convention': True}
    assert t['sources']['progressed']['b']['age_years'] == 0
    assert v['policy']['birth_input_historical_accuracy_independently_verified'] is False
    assert result['layer_availability']['childbirth']['status'] == 'computed'


def test_parent_only_context_and_static_identity_are_references_not_extra_evidence(result):
    t = result['timing_observations']; v = t['childbirth_observation']
    assert v['contacts']
    selected = {r['timing_contact_ref'] for r in v['contacts']}
    expected = {f'/timing_observations/contacts/{i}' for i, c in enumerate(t['contacts'])
                if c['first_kind'] == 'transit' and c['second_kind'] == 'natal' and c['second_owner'] == 'a'}
    assert selected == expected
    assert v['counts']['parental_transit_contacts'] == len(selected)
    for row in v['contacts']:
        tc = lookup(result, row['timing_contact_ref'])
        assert tc['first_point'] not in ('ascendant', 'midheaven')
        assert lookup(result, row['child_natal_point_ref']) == lookup(result, tc['first_point_ref'])
        assert lookup(result, row['parent_natal_point_ref']) == lookup(result, tc['second_point_ref'])
        assert lookup(result, row['parent_natal_entry_ref'])['person'] == 'a'
        assert row['independent_evidence_added'] is False
        for ref in row['static_contact_refs']:
            c = lookup(result, ref)
            assert (c['second_point'], c['first_point'], c['angle']) == (tc['first_point'], tc['second_point'], tc['angle'])
        for kind in ('core', 'context'):
            for ref in row[kind+'_complex_refs']:
                comp = lookup(result, ref)
                assert tc['second_point'] in comp['members']
                assert (tc['second_point'] in comp['core_members']) == (kind == 'core')
    args = request(); args.pop('timing'); args.pop('include_timing')
    static = calculate_observation_data(**args)
    for key in ('contacts', 'counts', 'observation_paths', 'activation_clusters', 'house_overlays'):
        assert result[key] == static[key]
    assert any(lookup(result, r['timing_contact_ref'])['angle'] == 60 and not r['static_contact_refs'] for r in v['contacts'])


def test_swap_keeps_parent_child_meaning_and_geometric_set(result):
    args = request(); args['person_a'], args['person_b'] = args['person_b'], args['person_a']
    args['relationship_context']['roles'] = {'a': 'child', 'b': 'parent'}
    r = calculate_observation_data(**args)
    assert r['status'] == 'ok'
    v = r['timing_observations']['childbirth_observation']
    assert (v['parent_person'], v['child_person']) == ('b', 'a')
    def signature(data):
        return {(c['first_point'], c['second_point'], c['angle']): c['orb_degrees']
                for row in data['timing_observations']['childbirth_observation']['contacts']
                for c in [lookup(data, row['timing_contact_ref'])]}
    assert signature(r) == pytest.approx(signature(result))


@pytest.mark.parametrize('change', [
    {'event': 'marriage'}, {'event': True}, {'at': '2000-01-01T04:00:00Z'}, {'date': '2000-01-01'},
    {'month_part': 'early'}, {'transit_orbs_degrees': {}}, {'progression_orbs_degrees': None},
    {'window_end': '2000-01-02T04:00:00Z'},
])
def test_conflicting_or_incomplete_timing_rejected(change):
    args = request(); args['timing'].update(change)
    r = calculate_observation_data(**args)
    assert r['status'] == 'invalid_input'


@pytest.mark.parametrize('roles', [{}, {'a': 'sibling', 'b': 'sibling'}, {'a': 'parent'}])
def test_child_role_cannot_be_inferred(roles):
    args = request(); args['relationship_context']['roles'] = roles
    assert calculate_observation_data(**args)['status'] == 'invalid_input'


def test_wrong_scope_chronology_and_missing_birth_not_repaired():
    args = request(); args['relationship_type'] = 'love'
    assert calculate_observation_data(**args)['status'] == 'invalid_input'
    args = request(); args['person_a'], args['person_b'] = args['person_b'], args['person_a']
    assert calculate_observation_data(**args)['status'] == 'invalid_input'
    args = request(); args['person_b'] = {k: v for k, v in BIRTH.items() if k != 'minute'}
    assert calculate_observation_data(**args)['status'] == 'needs_clarification'
    args = request(); args['mode'] = 'natal'
    assert calculate_observation_data(**args)['status'] == 'invalid_input'


def test_event_window_contains_birth_and_never_uses_prebirth_progressions():
    args = request(); args['timing'].update(window_start='2000-01-01T04:00:00Z', window_end='2000-01-01T05:00:00Z')
    r = calculate_observation_data(**args)
    assert r['status'] == 'ok', r
    assert r['timing_observations']['window_scan']['status'] == 'computed'
    args['timing']['window_start'] = '2000-01-01T04:01:00Z'
    assert calculate_observation_data(**args)['status'] == 'invalid_input'
    args['timing']['window_start'] = '2000-01-01T03:00:00Z'
    assert calculate_observation_data(**args)['status'] == 'invalid_input'


def test_dst_fold_comes_from_child_birth_resolver():
    args = request()
    args['person_b'] = dict(year=2000, month=10, day=29, hour=1, minute=30, location_id='coord:40.712800,-74.006000')
    missing = calculate_observation_data(**args)
    assert missing['status'] == 'ambiguous' and 'person_b.fold' in missing['required_fields']
    for fold, utc in [(0, '2000-10-29T05:30:00+00:00'), (1, '2000-10-29T06:30:00+00:00')]:
        args['person_b']['fold'] = fold
        r = calculate_observation_data(**args)
        assert r['status'] == 'ok', r
        assert r['timing_observations']['childbirth_observation']['at_utc'] == utc


def test_reference_rebuild_and_tamper_rejection(result):
    import mcp_server
    from services.mcp_result_facts import checked_result, verify_calculation_claims_data
    args = request(); checked = checked_result('calculate_relationship_observation', result, args)
    assert checked['status'] == 'ok', checked
    claims = [dict(quote='Childbirth time', path='/timing_observations/childbirth_observation/at_utc', value='2000-01-01T04:00:00+00:00'),
              dict(quote='Mean node verified', path='/settings/node_type', value='mean')]
    assert verify_calculation_claims_data(checked['calculation_reference'], claims)['counts']['supported'] == 2
    for field, value in [('parent_person', 'b'), ('at_utc', '2000-01-01T12:00:00Z'), ('contacts', [])]:
        bad = deepcopy(result); bad['timing_observations']['childbirth_observation'][field] = value
        assert checked_result('calculate_relationship_observation', bad, args)['status'] == 'validation_failed'


def test_natal_mean_and_generic_timing_true_are_explicitly_distinct(result):
    import swisseph as swe
    from services.civil_time_resolver import _julian_day_ut
    from services.transit_utils import body_position
    args = request(); args['timing'].pop('event'); args['timing']['at'] = '2000-01-01T04:00:00Z'
    r = calculate_observation_data(**args)
    assert r['status'] == 'ok'
    jd = _julian_day_ut(datetime(2000, 1, 1, 4, tzinfo=timezone.utc))
    assert r['source_geometry']['b']['points']['north_node'] == body_position(swe.MEAN_NODE, jd)[0]
    assert r['timing_observations']['sources']['transit']['points']['north_node'] == body_position(swe.TRUE_NODE, jd)[0]
    assert abs(body_position(swe.MEAN_NODE, jd)[0]-body_position(swe.TRUE_NODE, jd)[0]) > 1
    assert r['timing_observations']['node_conventions']['same_convention'] is False
    assert r['timing_observations']['childbirth_observation']['status'] == 'not_computed'


def test_natal_node_mismatch_fails_without_replacing_geometry(monkeypatch):
    import services.relationship_observation as module
    original = module.geometry_from_summary
    def altered(*args):
        r = original(*args); r['points']['north_node'] += 0.1; r['points']['south_node'] += 0.1
        return r
    monkeypatch.setattr(module, 'geometry_from_summary', altered)
    r = calculate_observation_data(person_a=PARENT, person_b=BIRTH)
    assert r['status'] == 'unavailable' and 'contacts' not in r


def test_child_node_identity_cannot_be_faked(result):
    from services.relationship_observation_childbirth import childbirth_view
    bad = deepcopy(result); bad['timing_observations']['sources']['transit']['points']['north_node'] += 0.1
    with pytest.raises(ValueError, match='disagree'):
        childbirth_view(bad, bad['timing_observations'])
