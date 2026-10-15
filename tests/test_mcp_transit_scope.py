"""Published transit settings must disclose the engine's narrower axis scope."""
from services.mcp_extended import transit_events_data


def test_axis_events_disclose_conjunction_only_scope():
    result = transit_events_data(year=1990, month=4, day=15, hour=18, minute=0,
        location_id='coord:48.856600,2.352200', from_date='2026-01-01',
        to_date='2026-12-31', planet='jupiter', target_scope='axes')
    assert result['status'] == 'ok'
    assert result['settings']['aspects'] == [0.0]
    assert result['settings']['aspects_by_target']['axes'] == [0.0]
    assert result['settings']['aspects_by_target']['points'] == []
    assert result['settings']['coverage_note']
