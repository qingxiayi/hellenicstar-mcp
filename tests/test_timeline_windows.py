"""Duration and extended-coverage acceptance tests, including missed-exact cases."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest
import swisseph as swe

from services.forecast_natal import build_forecast_natal
from services.mcp_natal import _compute_source
from services.secondary_progressions import PLANET_DEFS
from services.solar_arc_engine import TROPICAL_YEAR_DAYS
from services.timeline_synthesis import compute_timeline_synthesis, _jd_from_utc
from services.timeline_windows import motion_grid, orb_intervals


def intervals(position, lo, hi, step, target, orb):
    times, lons = motion_grid(position, lo, hi, step)
    return orb_intervals(position, times, lons, target, orb)


def test_station_turnaround_visit_without_exact_contact_inside_one_grid_step():
    # Both endpoints lie outside the orb, but the turning point lies inside.
    def position(t):
        return 0.8 + 2 * (t - .5) ** 2, 4 * (t - .5)
    rows = intervals(position, 0, 1, 1, 0, 1)
    assert len(rows) == 1
    assert rows[0][0] == pytest.approx(.5 - .1 ** .5, abs=1/1440)
    assert rows[0][1] == pytest.approx(.5 + .1 ** .5, abs=1/1440)


def test_exit_and_reentry_are_not_merged():
    def position(t):
        return 1.2 - 2 * (t - .5) ** 2, -4 * (t - .5)
    rows = intervals(position, 0, 1, 1, 0, 1)
    assert len(rows) == 2
    assert rows[0][1] < .5 < rows[1][0]


def test_wraparound_and_boundary_tangency():
    assert intervals(lambda t: ((358 + t) % 360, 1), 0, 4, .5, 0, 1) == [(1, 3)]
    assert intervals(lambda t: (1 + (t - .5) ** 2, 2 * (t - .5)), 0, 1, 1, 0, 1) == []
    assert intervals(lambda t: (.5, 0), 0, 4, 1, 0, 1) == [(0, 4)]


def test_east_asian_query_boundary_does_not_truncate_into_prior_day():
    from zoneinfo import ZoneInfo
    from services.timeline_synthesis import _utc_second_text
    for year in (2026, 2027):
        boundary = datetime(year, 1, 1, tzinfo=ZoneInfo('Asia/Shanghai'))
        actual = _utc_second_text(_jd_from_utc(boundary))
        assert actual == boundary.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


@pytest.fixture(scope='module')
def sample():
    birth = dict(year=1990, month=4, day=15, hour=18, minute=0, location_id='gn:2988507')
    natal = _compute_source(**birth, house_system='placidus', fold=None)
    snapshot = build_forecast_natal(birth)
    result = compute_timeline_synthesis(natal, birth, 2026, 3, snapshot=snapshot)
    return birth, natal, snapshot, result


def jd(text):
    return _jd_from_utc(datetime.fromisoformat(text.replace('Z', '+00:00')))


def test_extended_transits_are_geometrically_exact_and_have_windows(sample):
    _, _, snapshot, result = sample
    bodies = dict(PLANET_DEFS)
    planetary = [e for e in result['events'] if e['technique'] == 'transits' and e['nature'] == 'exact_aspect']
    assert planetary
    assert {e['source']['angle'] for e in planetary} == {0, 60, 90, 120, 180}
    for event in planetary:
        source = event['source']
        lon = swe.calc_ut(jd(event['exact_utc']), bodies[source['planet']], swe.FLG_SWIEPH)[0][0]
        sep = abs((lon - snapshot.planets[source['target']].longitude + 180) % 360 - 180)
        assert sep == pytest.approx(source['angle'], abs=1e-5)
        matches = [w for w in result['aspect_windows'] if event['index'] in w['exact_event_indices']]
        assert len(matches) == 1
        assert matches[0]['technique'] == 'transits'


def test_window_boundaries_and_interiors_recalculate_against_swiss(sample):
    _, _, snapshot, result = sample
    bodies = dict(PLANET_DEFS)
    checked = 0
    for row in result['aspect_windows']:
        target = snapshot.axes[row['target']] if row['target'] in snapshot.axes else snapshot.planets[row['target']].longitude

        def deviation(civil_jd):
            ephe = (snapshot.birth_jd_ut + (civil_jd - snapshot.birth_jd_ut) / TROPICAL_YEAR_DAYS
                    if row['technique'] == 'secondary_progressions' else civil_jd)
            lon = swe.calc_ut(ephe, bodies[row['planet']], swe.FLG_SWIEPH)[0][0]
            separation = abs((lon - target + 180) % 360 - 180)
            return abs(separation - row['angle'])

        for key in ('orb_entry_utc', 'orb_exit_utc'):
            if row[key]:
                assert deviation(jd(row[key])) == pytest.approx(row['orb_limit'], abs=1e-4)
                checked += 1
        assert deviation((jd(row['start_utc']) + jd(row['end_utc'])) / 2) <= row['orb_limit'] + 1e-5
        if row['planet'] == 'jupiter' and row['technique'] == 'transits':
            assert row['orb_limit'] == (1.5 if row['target'] in snapshot.axes or row['angle'] in (60, 120) else 2)
    assert checked > 30
    # Valid background can exist with no exact hit anywhere inside the query.
    assert any(not w['exact_event_indices'] for w in result['aspect_windows'])
    assert any(w['orb_entry_utc'] is None and w['entry_status'] == 'search_limit'
               for w in result['aspect_windows'])


def test_phase_context_and_transitions_use_progressed_sun_moon(sample):
    from services.progressed_phase import phase_snapshot, phase_timeline
    birth, natal, snapshot, result = sample
    context = result['progressed_context']
    age = (jd(context['as_of_utc']) - snapshot.birth_jd_ut) / TROPICAL_YEAR_DAYS
    assert context['phase_at_start'] == phase_snapshot(snapshot.birth_jd_ut, age)
    # The original three-year sample legitimately contains no phase change.
    boundary = phase_timeline(snapshot.birth_jd_ut, jd(context['as_of_utc']))['next_phase']
    year = int(boundary['date'][:4])
    with_change = compute_timeline_synthesis(natal, birth, year, snapshot=snapshot)
    assert with_change['progressed_context']['phase_transitions']
    for row in with_change['progressed_context']['phase_transitions']:
        age = (jd(row['exact_utc']) - snapshot.birth_jd_ut) / TROPICAL_YEAR_DAYS
        actual = phase_snapshot(snapshot.birth_jd_ut, age)['angle_diff']
        assert abs((actual - (row['phase_num'] - 1) * 45 + 180) % 360 - 180) < 1e-4


def test_solar_ingress_is_included_and_exact(sample):
    birth, natal, snapshot, _ = sample
    # Mid-April natal Sun reaches Taurus several symbolic days after birth.
    result = compute_timeline_synthesis(natal, birth, 1994, 3, snapshot=snapshot)
    hits = [e for e in result['events'] if e['technique'] == 'secondary_progressions'
            and e['nature'] == 'sign_ingress' and e['source']['planet'] == 'sun']
    assert len(hits) == 1
    ephe = snapshot.birth_jd_ut + (jd(hits[0]['exact_utc']) - snapshot.birth_jd_ut) / TROPICAL_YEAR_DAYS
    lon = swe.calc_ut(ephe, swe.SUN, swe.FLG_SWIEPH)[0][0]
    assert lon == pytest.approx(30, abs=1e-5)
    assert hits[0]['focus'] == 'sign:taurus'


def test_year_boundary_clipping_preserves_actual_window_and_contact_series(sample):
    birth, natal, snapshot, wide = sample
    narrow = compute_timeline_synthesis(natal, birth, 2027, snapshot=snapshot)
    for event in narrow['events']:
        if event['technique'] == 'transits':
            matching = next(e for e in wide['events'] if e['technique'] == 'transits'
                            and e['exact_utc'] == event['exact_utc'] and e['source'] == event['source'])
            assert matching['source']['series_id'] == event['source']['series_id']
    start, end = jd('2026-12-31T23:00:00Z'), jd('2027-12-31T23:00:00Z')
    for row in narrow['aspect_windows']:
        assert start <= jd(row['start_utc']) < jd(row['end_utc']) <= end
        if row['continues_before_query']:
            assert jd(row['start_utc']) == start
        if row['continues_after_query']:
            assert jd(row['end_utc']) == end


@pytest.mark.parametrize('field', ['window', 'link', 'phase'])
def test_new_fields_have_semantic_contract_checks(sample, field):
    from services.mcp_validation import validate_output
    birth, natal, _, result = sample
    good = {'status': 'ok', 'birth_context': natal['birth_context'], **result}
    args = {**birth, 'target_year': 2026, 'span_years': 3}
    assert validate_output('calculate_timeline_synthesis', good, args) == []
    bad = deepcopy(good)
    if field == 'window':
        bad['aspect_windows'][0]['end_utc'] = bad['aspect_windows'][0]['start_utc']
    elif field == 'link':
        bad['aspect_windows'][0]['exact_event_indices'] = [len(result['events'])]
    else:
        bad['progressed_context']['phase_at_start']['phase_num'] = 99
    assert validate_output('calculate_timeline_synthesis', bad, args)
