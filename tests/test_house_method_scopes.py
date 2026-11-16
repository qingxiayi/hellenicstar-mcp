"""Selected placements must not silently change method definitions."""
import pytest

from services.house_systems import HOUSE_SYSTEMS, house_of
from services.mcp_natal import calculate_lots_data, calculate_time_lord_data
from services.natal_positions import calculate_positions
from services.mcp_extended import relationship_data, sky_chart_data, render_composite_png, render_sky_chart_png

BIRTH = dict(year=1990, month=4, day=15, hour=18, minute=0, location_id='gn:2988507')
PARTNER = dict(year=1988, month=8, day=1, hour=9, minute=30, location_id='gn:5128581')


@pytest.mark.parametrize('system', HOUSE_SYSTEMS)
def test_lots_keep_formulas_and_use_selected_cusps(system):
    source = calculate_positions(**BIRTH, house_system=system)
    result = calculate_lots_data(**BIRTH, house_system=system)
    assert result['status'] == 'ok'
    baseline = calculate_lots_data(**BIRTH, house_system='whole_sign')
    assert result['sect'] == baseline['sect']
    assert [(p['longitude'], p['formula']) for p in result['lots']] == [
        (p['longitude'], p['formula']) for p in baseline['lots']]
    for lot in result['lots']:
        assert lot['house'] == house_of(lot['longitude'], source['cusps'])
        assert lot['house_system'] == system
        if system != 'placidus':
            assert lot['house_placidus'] is None  # Never relabel another system as Placidus.


@pytest.mark.parametrize('system', HOUSE_SYSTEMS)
def test_time_lords_use_whole_sign_profections_and_selected_lord_placement(system):
    result = calculate_time_lord_data(**BIRTH, house_system=system, as_of='2026-11-16')
    baseline = calculate_time_lord_data(**BIRTH, house_system='whole_sign', as_of='2026-11-16')
    assert result['status'] == 'ok'
    assert result['firdaria'] == baseline['firdaria']
    prof = result['annual_profections']
    assert prof['house_system'] == 'whole_sign'
    assert prof['natal_house_system'] == system
    source = calculate_positions(**BIRTH, house_system=system)
    for row, base in zip(prof['years'], baseline['annual_profections']['years']):
        assert {k: v for k, v in row.items() if k != 'lord_natal_house'} == {
            k: v for k, v in base.items() if k != 'lord_natal_house'}
        assert row['house'] == row['age'] % 12 + 1
        assert row['lord_natal_house'] == next(
            p['house'] for p in source['natal_planets_full'] if p['cn'] == row['lord_of_year'])


@pytest.mark.parametrize('system', HOUSE_SYSTEMS)
def test_synastry_overlays_change_houses_without_changing_aspects(system):
    data = relationship_data(person_a=BIRTH, person_b=PARTNER, house_system=system)
    base = relationship_data(person_a=BIRTH, person_b=PARTNER, house_system='placidus')
    assert data['status'] == 'ok'
    assert data['settings']['house_system'] == system
    assert data['synastry_aspects'] == base['synastry_aspects']
    assert data['composite_chart']['planets'] == base['composite_chart']['planets']
    a = calculate_positions(**BIRTH, house_system=system)
    b = calculate_positions(**PARTNER, house_system=system)
    for p in a['natal_planets_full']:
        if p['cn'] in data['a_planets_in_b_houses']:
            # The source wheel stores unrounded longitudes.
            lon = a['svg_data']['planets'][p['key']]['lon']
            assert data['a_planets_in_b_houses'][p['cn']] == house_of(lon, b['cusps'])
    comp = data['composite_chart']
    if system in ('equal', 'whole_sign'):
        assert len(comp['house_cusps']) == 12
        assert all((comp['house_cusps'][(i + 1) % 12] - c) % 360 == pytest.approx(30, abs=.0002)
                   for i, c in enumerate(comp['house_cusps']))
        if system == 'whole_sign':
            assert all(c % 30 == 0 for c in comp['house_cusps'])


@pytest.mark.parametrize('system', HOUSE_SYSTEMS)
def test_sky_selected_houses_and_renderer(system):
    args = dict(moment='2026-11-16T12:00:00+08:00', location_id='gn:2988507', house_system=system)
    data = sky_chart_data(**args)
    assert data['status'] == 'ok'
    assert data['settings']['house_system'] == system
    cusps = [p['longitude'] for p in data['house_cusps']]
    for p in data['planets']:
        assert p['house'] == house_of(p['longitude'], cusps)
    info, png = render_sky_chart_png(**args)
    assert info['status'] == 'ok' and png.startswith(b'\x89PNG')
    info, png = render_composite_png(person_a=BIRTH, person_b=PARTNER, house_system=system)
    assert info['status'] == 'ok' and png.startswith(b'\x89PNG')


@pytest.mark.parametrize('system', ['whole_sign', 'equal'])
def test_lots_and_time_lords_at_polar_latitude_do_not_require_placidus(system):
    polar = {**BIRTH, 'location_id': 'coord:69.649200,18.955300'}
    assert calculate_lots_data(**polar, house_system=system)['status'] == 'ok'
    assert calculate_time_lord_data(**polar, house_system=system, as_of='2026-11-16')['status'] == 'ok'
