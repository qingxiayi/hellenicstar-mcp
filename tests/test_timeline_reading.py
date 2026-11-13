"""Numerical overlap, bounded natal linkage, axis equivalence and MCP acceptance."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import random

import pytest

from services.timeline_reading import (reading_windows, concurrent_segments, window_overlaps,
                                       exact_contacts, build_reading_views)


def stamp(day):
    return (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)).isoformat().replace('+00:00', 'Z')


def window(start, end, target='moon', planet='saturn', technique='transits', directed=0, hits=()):
    return dict(start_utc=stamp(start), end_utc=stamp(end), target=target, planet=planet,
                technique=technique, directed_angle=directed, exact_event_indices=list(hits))


def test_true_intersections_do_not_chain_nonoverlapping_windows_or_touching_boundaries():
    rows = reading_windows([window(0, 10), window(5, 15, planet='uranus'), window(12, 20, planet='neptune')])
    groups = window_overlaps(rows, {'aspects': []})
    assert [(g['start_utc'], g['end_utc']) for g in groups] == [(stamp(5), stamp(10)), (stamp(12), stamp(15))]
    assert all(len(g['reading_window_indices']) == 2 for g in groups)
    assert concurrent_segments(reading_windows([window(0, 5), window(5, 10, planet='uranus')])) == []


def test_sweep_matches_independent_midpoint_membership_for_random_windows():
    rng = random.Random(47)
    windows = []
    for i in range(35):
        start = rng.randrange(25)
        windows.append(dict(index=i, start_utc=stamp(start), end_utc=stamp(start + rng.randrange(1, 8))))
    segments = concurrent_segments(windows)
    for day in range(33):
        at = stamp(day + .5)
        expected = [i for i, w in enumerate(windows) if w['start_utc'] <= at < w['end_utc']]
        found = [s for s in segments if s['start_utc'] <= at < s['end_utc']]
        assert len(found) == (1 if len(expected) > 1 else 0)
        if found:
            assert found[0]['reading_window_indices'] == expected
    assert len(segments) <= 2 * len(windows) - 1


def test_year_long_secondary_window_without_exact_hit_is_background_for_transit():
    rows = reading_windows([window(0, 365, technique='secondary_progressions', planet='sun'), window(80, 105)])
    overlap, = window_overlaps(rows, {'aspects': []})
    assert (overlap['start_utc'], overlap['end_utc']) == (stamp(80), stamp(105))
    assert overlap['different_techniques'] and all(w['exact_event_indices'] == [] for w in rows)


def test_only_direct_natal_edge_links_different_targets_and_no_ruler_chain():
    rows = reading_windows([window(0, 10, target='sun'), window(0, 10, target='venus'), window(0, 10, target='saturn')])
    context = {'aspects': [dict(index=0, point_a='sun', point_b='venus'), dict(index=1, point_a='saturn', point_b='venus')]}
    groups = window_overlaps(rows, context)
    pairs = [{rows[i]['target_key'] for i in g['reading_window_indices']} for g in groups]
    assert {'planet:sun', 'planet:saturn'} not in pairs
    assert len(groups) == 2
    assert all(g['rule_id'] == 'direct_natal_aspect' for g in groups)


def test_axis_equivalence_not_double_evidence_and_disconnected_visits_retained():
    raw = [window(0, 10, target='asc'), window(0, 10, target='dsc', directed=180),
           window(12, 20, target='asc'), window(12, 20, target='dsc', directed=180),
           window(0, 10, target='dsc', directed=0), window(0, 10, target='asc', planet='neptune')]
    rows = reading_windows(raw)
    assert len(rows) == 4
    assert sorted(i for w in rows for i in w['window_indices']) == list(range(6))
    equivalent = [r for r in rows if len(r['window_indices']) == 2]
    assert len(equivalent) == 2
    assert all(r['target_key'] == 'axis:asc_dsc' and r['directed_angle'] == 0 for r in equivalent)
    only = reading_windows(raw[:2])
    assert window_overlaps(only, {'aspects': []}) == []
    assert concurrent_segments(only) == []


def event(day, target, directed, technique='transits'):
    return dict(technique=technique, nature='exact_aspect', exact_utc=stamp(day),
                source=dict(planet='saturn', target=target, directed_angle=directed))


def test_equivalent_exact_hits_dedup_but_repeat_passes_and_different_geometry_stay():
    events = [event(2, 'asc', 90), event(2, 'dsc', 270), event(2, 'dsc', 90),
              event(50, 'asc', 90), event(50, 'dsc', 270)]
    raw = [window(0, 10, 'asc', directed=90, hits=[0]), window(0, 10, 'dsc', directed=270, hits=[1])]
    rows = exact_contacts(events, reading_windows(raw), {'points': {}})
    assert len(rows) == 3
    assert [r['event_indices'] for r in rows] == [[0, 1], [2], [3, 4]]
    assert rows[0]['matching_reading_window_indices'] == [0]
    assert rows[-1]['concurrent_reading_window_indices'] == []


@pytest.fixture(scope='module')
def computed():
    from services.mcp_natal import _compute_source
    from services.timeline_synthesis import compute_timeline_synthesis
    birth = dict(year=1990, month=4, day=15, hour=18, minute=0, location_id='gn:2988507')
    natal = _compute_source(**birth, house_system='placidus', fold=None)
    result = compute_timeline_synthesis(natal, birth, 2026, 3)
    return birth, natal, result


def test_real_context_matches_natal_facts_and_known_house_rulership_policy(computed):
    birth, natal, result = computed
    context = result['natal_context']
    for row in natal['natal_planets_full']:
        if row['key'] not in context['points'] or context['points'][row['key']]['kind'] != 'planet':
            continue
        point = context['points'][row['key']]
        assert point['longitude'] == row['lon']
        assert point['houses'] == {'placidus': row['house_p'], 'whole_sign': row['house_w']}
    for key in ('asc', 'dsc', 'mc', 'ic'):
        assert context['points'][key]['longitude'] == natal['axes'][key]['lon']
    # Paris fixture: Pisces seventh cusp has different ruler policies.
    seventh = context['house_cusps']['whole_sign'][6]
    assert seventh['sign_key'] == 'Pis'
    assert seventh['rulers'] == {'traditional': 'jupiter', 'modern': 'neptune'}
    assert 7 in context['points']['jupiter']['ruled_houses']['whole_sign']['traditional']
    assert 7 not in context['points']['jupiter']['ruled_houses']['whole_sign']['modern']
    for p in context['points'].values():
        assert all(p['key'] in (context['aspects'][i]['point_a'], context['aspects'][i]['point_b']) for i in p['direct_aspect_indices'])


def test_reading_preserves_raw_data_covers_every_window_and_aspect_event(computed):
    _, natal, data = computed
    before = deepcopy((natal, data['events'], data['aspect_windows']))
    build_reading_views(natal, data['events'], data['aspect_windows'])
    assert (natal, data['events'], data['aspect_windows']) == before
    assert sorted(i for w in data['reading_windows'] for i in w['window_indices']) == list(range(len(data['aspect_windows'])))
    expected = [i for i, e in enumerate(data['events']) if e['nature'] in ('axis_contact', 'exact_aspect')]
    assert sorted(i for g in data['exact_contacts'] for i in g['event_indices']) == expected
    for g in data['exact_contacts']:
        for i in g['concurrent_reading_window_indices']:
            w = data['reading_windows'][i]
            assert all(w['start_utc'] <= data['events'][j]['exact_utc'] < w['end_utc'] for j in g['event_indices'])


@pytest.mark.parametrize('corruption', ['overlap_time', 'overlap_reason', 'missing_window', 'recursive_edge', 'house_ruler', 'layer_omission'])
def test_contract_rejects_false_associations_and_dropped_members(computed, corruption):
    from services.mcp_validation import validate_output
    birth, natal, data = computed
    good = dict(status='ok', birth_context=natal['birth_context'], **data)
    args = dict(birth, target_year=2026, span_years=3)
    assert validate_output('calculate_timeline_synthesis', good, args) == []
    bad = deepcopy(good)
    if corruption == 'overlap_time':bad['window_overlaps'][0]['end_utc'] = stamp(10000)
    elif corruption == 'overlap_reason':bad['window_overlaps'][0]['rule_id'] = 'psychological_theme'
    elif corruption == 'missing_window':bad['reading_windows'].pop()
    elif corruption == 'recursive_edge':bad['natal_context']['points']['sun']['direct_aspect_indices'].append(999)
    elif corruption == 'house_ruler':bad['natal_context']['points']['sun']['ruled_houses']['placidus']['traditional'].append(13)
    elif corruption == 'layer_omission':bad['reading_layers']['stage_configurations']['reading_window_indices'].pop()
    assert validate_output('calculate_timeline_synthesis', bad, args)


def test_mcp_full_selective_summary_and_claim_recalculation(computed):
    import mcp_server as m
    from services.mcp_result_facts import CalculationReference, CalculationClaim
    birth, _, _ = computed
    args = dict(birth, target_year=2026, span_years=3)
    full = asyncio.run(m.calculate_timeline_synthesis(**args))
    assert full['status'] == 'ok' and full['quality']['status'] == 'passed'
    selected = asyncio.run(m.calculate_timeline_synthesis(**args, include=['reading_layers', 'reading_counts', 'window_overlaps']))
    summary = asyncio.run(m.calculate_timeline_synthesis(**args, detail_level='summary'))
    assert selected['window_overlaps'] == full['window_overlaps'] and 'events' not in selected
    assert summary['reading_counts'] == full['reading_counts']
    assert summary['presentation']['is_truncated']
    assert selected['calculation_reference'] == full['calculation_reference'] == summary['calculation_reference']
    claims = [CalculationClaim(quote='归并区间数量', path='/reading_counts/reading_windows', value=full['reading_counts']['reading_windows']),
              CalculationClaim(quote='错误的分组理由', path='/window_overlaps/0/rule_id', value='shared_psychological_theme')]
    verified = asyncio.run(m.verify_calculation_claims(reference=CalculationReference(**summary['calculation_reference']), claims=claims))
    assert verified['counts'] == {'supported': 1, 'contradicted': 1, 'unverified': 0}
