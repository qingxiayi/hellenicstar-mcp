"""Return points must reach the public data and the PNG renderer."""
from unittest.mock import patch
import pytest
from services import mcp_extended as m
from services.ephemeris_guard import apply_ephe_path
from services.solar_return import _chart_at

@pytest.mark.parametrize('system', ['placidus', 'whole_sign'])
def test_solar_return_points_reach_data_and_renderer(system):
    apply_ephe_path()
    args = dict(year=1990, month=4, day=15, hour=18, minute=0,
                location_id='gn:2988507', target_year=2026,
                residence_location_id='gn:1816670', house_system=system)
    source = m._solar_return_source(**args, fold=None)
    sr = source[1]
    points = _chart_at(sr['sr_jd'], sr['residence']['lat'], sr['residence']['lng'],
                       b'W' if system == 'whole_sign' else b'P')['special_points']
    assert sr['single']['special_points'] == points
    with patch.object(m, '_solar_return_source', return_value=source):
        data = m.solar_return_data(**args)
        assert data['chart']['special_points'].keys() == points.keys()
        for key, point in points.items():
            public = data['chart']['special_points'][key]
            assert public['longitude'] == pytest.approx(point['longitude'], abs=0.00005)
            assert public['house'] == point['house']
            assert public['retrograde'] == point['retrograde']
        with patch.object(m, '_render', return_value=b'png') as render:
            assert m.render_solar_return_png(**args)[0]['status'] == 'ok'
        plotted = render.call_args.args[0]
        assert len(plotted) == 13
        for src, dst in [('chiron','chiron'), ('true_north_lunar_node','north_node'),
                         ('true_south_lunar_node','south_node')]:
            assert plotted[dst] == dict(lon=points[src]['longitude'], retrograde=points[src]['retrograde'])
    assert abs((points['true_south_lunar_node']['longitude'] - points['true_north_lunar_node']['longitude']) % 360 - 180) < 1e-8
