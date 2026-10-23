"""Independent geometry cases and real MCP recomputation for observation v0.2."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from services.relationship_charts import PLANETS, ORB_PROFILES
from services.relationship_observation import (
    build_observation, settings_for, contacts_between,
)


def geometry(offset=0, **overrides):
    ps = {p: (i * 27 + offset) % 360 for i, p in enumerate(PLANETS)}
    ps.update(north_node=(30 + offset) % 360, south_node=(210 + offset) % 360,
              ascendant=offset % 360, descendant=(180 + offset) % 360,
              midheaven=(270 + offset) % 360, imum_coeli=(90 + offset) % 360)
    ps.update(overrides)
    return dict(points=ps, cusps=[(offset + 30 * i) % 360 for i in range(12)])


def build(a=None, b=None, **options):
    return build_observation({'a': a or geometry(), 'b': b or geometry(11)},
                             {'a': {}, 'b': {}}, settings_for(**options))


def test_one_contact_two_paths_and_axis_equivalents_are_not_new_evidence():
    r = build(geometry(sun=30), geometry())
    c = next(c for c in r['contacts'] if c['first_point'] == 'sun' and c['second_point'] == 'north_node')
    assert c['angle'] == 0 and c['orb_degrees'] == 0
    assert {(v['second_point'], v['angle']) for v in c['endpoint_variants']} == {('north_node', 0), ('south_node', 180)}
    assert len([p for p in r['observation_paths'] if p['contact_id'] == c['id']]) == 2
    assert len({c['id'] for c in r['contacts']}) == len(r['contacts'])
    assert r['counts']['observation_paths'] == 2 * r['counts']['unique_contacts']
    aa = next(c for c in r['contacts'] if c['first_point'] == c['second_point'] == 'ascendant')
    assert len(aa['endpoint_variants']) == 4
    assert all(e['first_point'] != e['second_point'] for e in r['relationship_profiles']['a']['natal_aspects'])


def test_one_hop_stops_even_when_neighbor_has_more_neighbors():
    r = build(geometry(sun=0, moon=9, mercury=18), geometry(saturn=0))
    cluster = next(c for c in r['activation_clusters'] if c['id'] == 'a:sun')
    assert 'moon' in cluster['local_natal_context']['neighbors']
    assert 'mercury' not in cluster['local_natal_context']['neighbors']
    group = next(g for g in r['source_contact_groups'] if g['id'] == 'b:saturn->a')
    assert {'a:sun', 'a:moon'} <= set(group['cluster_ids'])
    assert group['linking_natal_edge_ids']
    assert r['layer_availability']['configuration_membership']['status'] == 'computed'


@pytest.mark.parametrize('lon,near,house', [(175, True, 6), (174.999, False, 6), (179.999, True, 6), (180, False, 7)])
def test_seventh_cusp_rule_preserves_actual_house(lon, near, house):
    r = build(geometry(venus=lon))
    p = r['relationship_profiles']['a']['points']['venus']
    assert p['house'] == house and p['seventh_cusp_effect'] is near
    assert ('venus' in r['relationship_profiles']['a']['projected_planets']) == (near or house == 7)
    if near:
        row = next(x for x in r['projected_planet_overlays'] if x['overlay_id'].startswith('a:venus->'))
        assert row['source_natal_house'] == 6 and row['seventh_cusp_effect']


def test_other_cusps_do_not_apply_seventh_rule_and_wrap_is_correct():
    r = build(geometry(venus=235, mars=359))
    p = r['relationship_profiles']['a']['points']
    assert p['venus']['distance_to_next_cusp'] == 5 and not p['venus']['seventh_cusp_effect']
    assert p['mars']['house'] == 12 and p['mars']['distance_to_next_cusp'] == 1
    assert not p['mars']['seventh_cusp_effect']


def test_element_counts_use_nine_points_without_outer_chiron_or_nodes():
    a = geometry(**{p: 1 for p in PLANETS[:7]}, uranus=31, neptune=61, pluto=91, chiron=121)
    p = build(a)['relationship_profiles']['a']
    assert {k: v['count'] for k, v in p['element_balance'].items()} == {'fire': 8, 'earth': 1, 'air': 0, 'water': 0}
    assert p['element_balance']['earth']['singleton']
    assert p['modality_balance']['cardinal']['count'] == 9
    assert p['saturn_element'] == 'fire'


def test_profile_is_separate_and_unknown_sextile_is_not_silently_six_degrees():
    before = deepcopy(ORB_PROFILES)
    a, b = geometry(sun=0), geometry(sun=65)
    no = build(a, b)
    assert not any(c['first_point'] == c['second_point'] == 'sun' for c in no['contacts'])
    yes = build(a, b, sextile_orb_degrees=5)
    c = next(c for c in yes['contacts'] if c['first_point'] == c['second_point'] == 'sun')
    assert c['angle'] == 60 and c['orb_degrees'] == 5 and c['tight_contact']
    assert ORB_PROFILES == before
    assert no['layer_availability']['sextile']['status'] == 'not_computed'


def test_axis_complement_trine_is_retained_without_inventing_sextile_orb():
    r = build(geometry(sun=90), geometry())  # NN 30 / SN 210: 60 / 120
    c = next(c for c in r['contacts'] if c['first_point'] == 'sun' and c['second_point'] == 'north_node')
    assert c['angle'] == 60 and c['evaluated_angles'] == [120]
    assert not c['canonical_angle_enabled']
    assert any(v['second_point'] == 'south_node' and v['angle'] == 120 for v in c['endpoint_variants'])


@pytest.mark.parametrize('orb,found,tight', [(0, True, True), (5, True, True), (5.001, True, False), (10, True, False), (10.001, False, None)])
def test_main_orb_and_tight_boundaries(orb, found, tight):
    rows = build(geometry(sun=0), geometry(sun=90 + orb))['contacts']
    hits = [c for c in rows if c['first_point'] == c['second_point'] == 'sun']
    assert bool(hits) is found
    if found:
        assert hits[0]['orb_degrees'] == pytest.approx(orb)
        assert hits[0]['tight_contact'] is tight


def test_reciprocity_excludes_saturn_saturn_and_axes():
    a = geometry(**{p: (0 if p == 'saturn' else 55) for p in PLANETS})
    r = build(a, a)
    assert r['saturn_reciprocity']['value'] == 'none'
    b = deepcopy(a); b['points']['moon'] = 0
    assert build(a, b)['saturn_reciprocity']['value'] == 'A_only'
    assert build(b, a)['saturn_reciprocity']['value'] == 'B_only'
    assert build(b, b)['saturn_reciprocity']['value'] == 'both'


def test_swap_and_scenario_preserve_geometry_and_change_only_observation_focus():
    a, b = geometry(350), geometry(20)
    ab, ba = build(a, b), build(b, a)
    values = lambda r: {(c['first_point'], c['second_point'], c['angle']): c['orb_degrees'] for c in r['contacts']}
    assert values(ab) == pytest.approx({(q, p, angle): orb for (p, q, angle), orb in values(ba).items()})
    for kind in ('friendship', 'work', 'family'):
        changed = build(a, b, relationship_type=kind)
        assert changed['contacts'] == ab['contacts']
        assert changed['settings']['scenario'] != ab['settings']['scenario']
    rows = {(x['source_point'], x['house']) for x in ab['house_overlays'] if x['source_person'] == 'a'}
    assert rows == {(x['source_point'], x['house']) for x in ba['house_overlays'] if x['source_person'] == 'b'}


def test_ruler_switch_parent_mapping_and_sorting():
    a = geometry(150)  # seventh cusp Pisces
    old, new = build(a, sort_by='natal_hard_aspects'), build(a, ruler_profile='modern', parental_house_mapping_profile='reversed')
    assert old['relationship_profiles']['a']['houses'][6]['ruler'] == 'jupiter'
    assert new['relationship_profiles']['a']['houses'][6]['ruler'] == 'neptune'
    assert new['relationship_profiles']['a']['parental_context']['father_house'] == 10
    keys = [(-c['natal_hard_aspect_count'], c['min_direct_orb_degrees'], c['id']) for c in old['activation_clusters']]
    assert keys == sorted(keys)


@pytest.mark.parametrize('option', [dict(include_timing=True), dict(include_minor_aspects=True),
    dict(sextile_orb_degrees=True), dict(sextile_orb_degrees=float('nan')),
    dict(sextile_orb_degrees=-1), dict(sextile_orb_degrees=11), dict(house_system='whole_sign')])
def test_unsupported_options_fail_explicitly(option):
    with pytest.raises(ValueError):
        settings_for(**option)


BIRTH = dict(year=2000, month=1, day=1, hour=12, minute=0, location_id='coord:39.904200,116.407400')
PARTNER = {**BIRTH, 'year': 1995, 'month': 5, 'day': 12}


def test_real_source_no_composite_and_output_corruption_is_withheld(monkeypatch):
    import mcp_server as m
    import services.relationship_charts as rc
    from services.mcp_result_facts import checked_result
    from services.relationship_observation import calculate_observation_data
    monkeypatch.setattr(rc, 'composite_chart', lambda *a: pytest.fail('must not compute composite'))
    args = dict(person_a=BIRTH, person_b=PARTNER)
    raw = calculate_observation_data(**args)
    assert checked_result('calculate_relationship_observation', raw, args)['status'] == 'ok'
    for field, value in [('counts', {'unique_contacts': -1}), ('interpretations', ['psychology']),
                         ('observation_paths', []), ('settings', {}), ('house_overlays', [])]:
        corrupt = deepcopy(raw); corrupt[field] = value
        result = checked_result('calculate_relationship_observation', corrupt, args)
        assert result['status'] == 'validation_failed' and 'contacts' not in result
    assert m.calculate_relationship_observation is not None


def test_contact_coverage_matches_independent_full_endpoint_geometry():
    import random
    from services.relationship_charts import separation
    rng = random.Random(20261022)
    for sextile in (None, 0, 3, 10):
        settings = settings_for(sextile_orb_degrees=sextile)
        for _ in range(12):
            a, b = geometry(rng.random() * 360), geometry(rng.random() * 360)
            for g in (a, b):
                for p in PLANETS:
                    g['points'][p] = rng.random() * 360
            actual = contacts_between(a['points'], b['points'], 'a', 'b', settings)
            # Compare actual endpoints, not the implementation's grouping key.
            expected = set()
            for p, x in a['points'].items():
                for q, y in b['points'].items():
                    for angle, limit in settings['orbs'].items():
                        if abs(separation(x, y) - int(angle)) <= limit:
                            expected.add((p, q, int(angle)))
            observed = set()
            for c in actual:
                for v in c['endpoint_variants']:
                    angle = str(v['angle'])
                    if angle in settings['orbs'] and abs(v['separation_degrees'] - v['angle']) <= settings['orbs'][angle]:
                        observed.add((v['first_point'], v['second_point'], v['angle']))
            assert observed == expected


def test_birth_time_ambiguity_and_polar_failure_do_not_invent_houses():
    from services.relationship_observation import calculate_observation_data
    dst = dict(year=2020, month=11, day=1, hour=1, minute=30, location_id='coord:40.712800,-74.006000')
    r = calculate_observation_data(person_a=BIRTH, person_b=dst)
    assert r['status'] == 'ambiguous' and r['required_fields'] == ['person_b.fold']
    polar = {**BIRTH, 'month': 6, 'day': 21, 'location_id': 'coord:78.223200,15.646900'}
    r = calculate_observation_data(person_a=BIRTH, person_b=polar)
    assert r['status'] == 'unavailable' and r['failed_person'] == 'b' and 'house_overlays' not in r


def test_unrelated_engine_failures_are_not_hidden(monkeypatch):
    from services.relationship_observation import calculate_observation_data
    import services.mcp_natal as natal
    def broken(**kwargs):
        raise RuntimeError('unexpected source failure')
    monkeypatch.setattr(natal, '_compute_source', broken)
    with pytest.raises(RuntimeError, match='unexpected source failure'):
        calculate_observation_data(person_a=BIRTH, person_b=PARTNER)


@pytest.mark.parametrize('orb', [0, 5, 5.25])
def test_explicit_orb_reference_survives_numeric_schema_normalization(orb):
    import mcp_server as m
    from services.relationship_observation import calculate_observation_data
    from services.mcp_result_facts import checked_result, verify_calculation_claims_data
    args = dict(person_a=BIRTH, person_b=PARTNER, sextile_orb_degrees=orb)
    raw = calculate_observation_data(**args)
    checked = checked_result('calculate_relationship_observation', raw, args)
    result = verify_calculation_claims_data(checked['calculation_reference'], [dict(
        quote='count', path='/counts/unique_contacts', value=raw['counts']['unique_contacts'])])
    assert result['status'] == 'ok' and result['counts']['supported'] == 1


def test_real_stdio_discovery_calculation_verification_and_missing_input():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    async def run():
        params = StdioServerParameters(command=sys.executable,
            args=[str(Path(__file__).resolve().parents[1] / 'mcp_server.py')])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tool = next(t for t in (await session.list_tools()).tools if t.name == 'calculate_relationship_observation')
                assert 'v0.14' in tool.description and 'observation_complexes' in tool.description
                assert 'scenario_observation_lenses' in tool.description
                assert 'observation_complex_links' in tool.description
                async def call(name, args):
                    result = await session.call_tool(name, args)
                    assert not result.isError, result
                    return json.loads(result.content[0].text)
                r = await call('calculate_relationship_observation', dict(person_a=BIRTH, person_b=PARTNER))
                assert r['status'] == 'ok' and r['quality']['status'] == 'passed'
                assert r['interpretations'] == [] and 'composite_chart' not in r
                assert r['natal_observation_candidates']['a'] and r['review_paths']
                v = await call('verify_calculation_claims', dict(reference=r['calculation_reference'], claims=[
                    dict(quote='contact count', path='/counts/unique_contacts', value=r['counts']['unique_contacts']),
                    dict(quote='incorrect count', path='/counts/unique_contacts', value=-1),
                    dict(quote='routes do not add contacts', path='/observation_route_policy/affects_contact_counts', value=False),
                    dict(quote='bounded complexes', path='/observation_complexes/policy/recursive_expansion', value=False)]))
                assert [c['verdict'] for c in v['claims']] == ['supported', 'contradicted', 'supported', 'supported']
                projected = await call('calculate_relationship_observation', dict(person_a=BIRTH, person_b=PARTNER,
                    detail_level='summary', include=['activation_clusters', 'natal_observation_candidates', 'review_paths', 'observation_complexes', 'observation_comparisons']))
                assert projected['layer_availability'] == r['layer_availability']
                assert projected['calculation_reference'] == r['calculation_reference']
                assert '/review_paths' in projected['presentation']['omitted_array_items']
                extended_args = dict(person_a=BIRTH, person_b=PARTNER, relationship_type='family',
                    relationship_context={'roles': {'a': 'parent', 'b': 'child'}, 'additional_types': ['friendship'], 'cohabiting': True, 'early_or_sibling_like_friendship': True},
                    include_minor_aspects=True, minor_orbs_degrees={'45': 1, '150': 1}, sextile_orb_degrees=6)
                extended = await call('calculate_relationship_observation', extended_args)
                assert extended['quality']['status'] == 'passed'
                assert extended['layer_availability']['yod_context']['status'] == 'computed'
                assert extended['special_contact_observations']['friendship_status'] == 'computed'
                verified = await call('verify_calculation_claims', dict(reference=extended['calculation_reference'], claims=[
                    dict(quote='Role input retained', path='/settings/relationship_context/roles/b', value='child'),
                    dict(quote='Explicit minor threshold', path='/settings/orbs/45', value=1.0),
                    dict(quote='Topics do not filter geometry', path='/scenario_observation_lenses/policy/geometry_filtered', value=False),
                    dict(quote='Explicit friendship condition', path='/settings/relationship_context/early_or_sibling_like_friendship', value=True),
                    dict(quote='No Cartesian complex pairs', path='/observation_complex_links/policy/all_complex_pairs_materialized', value=False)]))
                assert verified['counts']['supported'] == 5
                summary = await call('calculate_relationship_observation', dict(extended_args, detail_level='summary',
                    include=['relationship_context_observations', 'house_ruler_comparisons', 'special_contact_observations', 'scenario_observation_lenses', 'observation_complex_links']))
                assert summary['calculation_reference'] == extended['calculation_reference']
                assert summary['layer_availability'] == extended['layer_availability']
                assert summary['scenario_observation_lenses']['policy']['planet_whitelist'] is False
                assert summary['observation_complex_links']['status'] == 'computed'
                assert '/scenario_observation_lenses/people/a' in summary['presentation']['omitted_array_items']
                missing = await call('calculate_relationship_observation', dict(person_a=BIRTH))
                assert missing['status'] == 'needs_clarification'
                assert 'person_b.hour' in missing['required_fields']
                invalid = await call('calculate_relationship_observation', dict(person_a=BIRTH, person_b=PARTNER, include_timing=True))
                assert invalid['status'] == 'invalid_input'
                timing_args = dict(person_a=BIRTH, person_b=PARTNER, include_timing=True, timing={
                    'at': '2020-06-01T15:30:00+08:00',
                    'window_start': '2020-06-01T07:00:00Z', 'window_end': '2020-06-01T08:00:00Z',
                    'transit_orbs_degrees': {'0': 1, '90': 1, '180': 1},
                    'progression_orbs_degrees': {'0': 1, '90': 1, '180': 1}})
                timed = await call('calculate_relationship_observation', timing_args)
                assert timed['status'] == 'ok' and timed['quality']['status'] == 'passed'
                assert timed['timing_observations']['window_scan']['status'] == 'computed'
                assert timed['counts'] == r['counts'] and timed['contacts'] == r['contacts']
                verified = await call('verify_calculation_claims', dict(reference=timed['calculation_reference'], claims=[
                    dict(quote='Selected time UTC', path='/timing_observations/sources/at_utc', value='2020-06-01T07:30:00+00:00'),
                    dict(quote='True nodes', path='/timing_observations/sources/node_type', value='true'),
                    dict(quote='No propagated activation', path='/timing_observations/policy/recursive_expansion', value=False),
                    dict(quote='Numerical window', path='/timing_observations/window_scan/status', value='computed'),
                    dict(quote='Fair progressed comparison', path='/timing_observations/progressed_synastry_comparison/policy/natal_and_progressed_use_same_orbs', value=True)]))
                assert verified['counts']['supported'] == 5
                short = await call('calculate_relationship_observation', dict(timing_args, detail_level='summary', include=['timing_observations']))
                assert short['calculation_reference'] == timed['calculation_reference']
                assert short['layer_availability']['timing']['status'] == 'computed'
                assert short['layer_availability']['timing_window']['status'] == 'computed'
                assert short['layer_availability']['progressed_synastry_comparison']['status'] == 'computed'
                assert '/timing_observations/contacts' in short['presentation']['omitted_array_items']
                child_args = dict(person_a={**BIRTH, 'year': 1970}, person_b=BIRTH,
                    relationship_type='family', relationship_context={'roles': {'a': 'parent', 'b': 'child'}},
                    include_timing=True, timing={'event': 'childbirth',
                    'transit_orbs_degrees': {'0': 2, '90': 2, '180': 2},
                    'progression_orbs_degrees': {'0': 2, '90': 2, '180': 2}})
                child = await call('calculate_relationship_observation', child_args)
                assert child['status'] == 'ok'
                verified = await call('verify_calculation_claims', dict(reference=child['calculation_reference'], claims=[
                    dict(quote='Child birth UTC', path='/timing_observations/childbirth_observation/at_utc', value='2000-01-01T04:00:00+00:00'),
                    dict(quote='Mean nodes consistent', path='/timing_observations/node_conventions/same_convention', value=True)]))
                assert verified['counts']['supported'] == 2
                short = await call('calculate_relationship_observation', dict(child_args, detail_level='summary', include=['timing_observations']))
                assert short['layer_availability']['childbirth']['status'] == 'computed'
                assert short['calculation_reference'] == child['calculation_reference']
    asyncio.run(run())
