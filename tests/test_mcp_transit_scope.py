"""Published transit settings must disclose the engine's narrower axis scope."""
from services.mcp_extended import transit_events_data
from types import SimpleNamespace

import pytest
import swisseph as swe

from services import mcp_extended, transit_natal, transit_utils, transit_lifetime


def test_axis_events_disclose_conjunction_only_scope():
    result = transit_events_data(year=1990, month=4, day=15, hour=18, minute=0,
        location_id='coord:48.856600,2.352200', from_date='2026-01-01',
        to_date='2026-12-31', planet='jupiter', target_scope='axes')
    assert result['status'] == 'ok'
    assert result['settings']['aspects'] == [0.0]
    assert result['settings']['aspects_by_target']['axes'] == [0.0]
    assert result['settings']['aspects_by_target']['points'] == []
    assert result['settings']['coverage_note']


@pytest.mark.parametrize('scope', ['axes', 'points'])
@pytest.mark.parametrize('narrow', [False, True])
def test_mcp_preserves_middle_retrograde_contact_without_changing_legacy(monkeypatch, scope, narrow):
    # Artificial fixed natal target; this is not a verification of a user's chart.
    lon = transit_utils.body_lon(swe.PLUTO, swe.julday(2029, 8, 14, 12))
    snapshot = SimpleNamespace(
        axes={key: lon if key == 'asc' else 0.0 for key in transit_natal.AXES},
        planets={
            key: SimpleNamespace(longitude=(lon + 180) % 360 if key == 'chiron' else 0.0)
            for key in transit_natal.NATAL_POINT_ORDER if key not in transit_natal.AXES
        },
        context=SimpleNamespace(civil_dt='1990-01-01T00:00:00',
                                snapshot=SimpleNamespace(tz_iana='UTC')),
    )
    monkeypatch.setattr(mcp_extended, '_validated', lambda *args: (
        {'birth_context': {'tz_iana': 'UTC'}}, {}))
    monkeypatch.setattr(mcp_extended, '_forecast_snapshot', lambda body: snapshot)
    start, end = ('2029-08-01', '2029-08-31') if narrow else ('2029-01-01', '2029-12-31')
    result = transit_events_data(
        year=1990, month=1, day=1, hour=0, minute=0, location_id='synthetic-only',
        from_date=start, to_date=end, planet='pluto', target_scope=scope,
    )
    assert result['status'] == 'ok'
    assert [row['contact'] for row in result['events']] == (
        ['2/3'] if narrow else ['1/3', '2/3', '3/3'])
    middle = next(row for row in result['events'] if row['contact'] == '2/3')
    assert middle['direction'] == '逆行'
    assert middle['exact_utc'].startswith('2029-08-14')
    assert result['settings']['contact_policy'] == 'all_exact_contacts'
    # The shared range service still defaults to the Mini Program's first/last view.
    legacy = transit_lifetime.compute_range_events(
        snapshot, swe.julday(2029, 1, 1, 0), swe.julday(2030, 1, 1, 0),
        planet='pluto', target_scope=scope,
    )
    assert [row['contact_index'] for row in legacy['events']] == [1, 3]
