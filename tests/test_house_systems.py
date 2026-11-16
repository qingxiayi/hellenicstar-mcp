"""House-system migration: geometry, integration boundaries and regressions."""
import asyncio
from copy import deepcopy
import math

import pytest
import swisseph as swe

from services.house_systems import HOUSE_SYSTEMS, calculate_houses, house_of, houses_at_armc
from services.mcp_natal import calculate_natal_data, calculate_classical_data, calculate_time_lord_data
from services import mcp_extended as ext
from services.mcp_validation import validate_output

BIRTH = dict(year=1990, month=4, day=15, hour=18, minute=0, location_id='gn:2988507')
PARTNER = dict(BIRTH, year=1988, month=8, day=1, hour=9, minute=30)
SYSTEMS = tuple(HOUSE_SYSTEMS)


@pytest.mark.parametrize('system', SYSTEMS)
@pytest.mark.parametrize('lat,lon', [(48.8566, 2.3522), (-33.8688, 151.2093), (0, 0)])
def test_frames_match_swiss_and_every_cusp_has_half_open_ownership(system, lat, lon):
    jd = swe.julday(1990, 4, 15, 16)
    frame = calculate_houses(jd, lat, lon, system)
    cusps, axes = swe.houses(jd, lat, lon, HOUSE_SYSTEMS[system].code)
    assert frame.cusps == cusps
    assert frame.ascmc == axes
    for i, cusp in enumerate(cusps):
        assert frame.house_of(cusp) == i + 1
        assert frame.house_of(cusp + 1e-7) == i + 1
        assert frame.house_of(cusp - 1e-7) == (i - 1) % 12 + 1
    armc = houses_at_armc(axes[2], lat, swe.calc_ut(jd, swe.ECL_NUT)[0][0], system)
    assert armc.cusps == pytest.approx(cusps, abs=1e-9)


def test_equal_and_whole_sign_do_not_replace_real_mc_with_tenth_cusp():
    e = calculate_natal_data(**BIRTH, house_system='equal')
    w = calculate_natal_data(**BIRTH, house_system='whole_sign')
    assert e['axes'] == w['axes']
    assert e['house_cusps'][0]['longitude'] == e['axes']['asc']['lon']
    assert w['house_cusps'][0]['longitude'] == math.floor(w['axes']['asc']['lon'] / 30) * 30
    assert abs(e['house_cusps'][9]['longitude'] - e['axes']['mc']['lon']) > 0.1


@pytest.mark.parametrize('system', SYSTEMS)
def test_natal_positions_invariant_and_cached_results_are_not_shared_mutable_objects(system):
    reference = calculate_natal_data(**BIRTH, house_system='placidus')
    result = calculate_natal_data(**BIRTH, house_system=system)
    assert result['status'] == 'ok'
    assert not validate_output('calculate_natal_chart', result, dict(BIRTH, house_system=system))
    strip_house = lambda r: [{k: v for k, v in p.items() if k != 'house'} for p in r['planets']]
    assert strip_house(result) == strip_house(reference)
    assert result['axes'] == reference['axes']
    assert result['aspects'] == reference['aspects']
    expected = deepcopy(result)
    result['axes']['asc']['lon'] = 0
    result['planets'][0]['house'] = 99
    result['house_cusps'][0]['longitude'] = 0
    assert calculate_natal_data(**BIRTH, house_system=system) == expected


def test_polar_whole_sign_and_equal_do_not_require_placidus_or_clamped_latitude():
    from services.location_resolver import coordinate_location_id
    b = dict(year=2000, month=1, day=1, hour=12, minute=0,
             location_id=coordinate_location_id(69.65, 18.96))
    for system in ['whole_sign', 'equal']:
        result = calculate_natal_data(**b, house_system=system)
        assert result['status'] == 'ok'
        # January Norway is UTC+1. Compare against actual 69.65, not Kerykeion's
        # internally capped house latitude. Only geocentric planets come from it.
        frame = calculate_houses(swe.julday(2000, 1, 1, 11), 69.65, 18.96, system)
        assert result['axes']['asc']['lon'] == frame.ascmc[0]
        assert [c['longitude'] for c in result['house_cusps']] == list(frame.cusps)
    for system in ['placidus', 'koch']:
        result = calculate_natal_data(**b, house_system=system)
        assert result['status'] == 'invalid_input'
        assert '未替换宫制' in result['error']


def test_invalid_system_and_degenerate_geometry_never_fall_back():
    for system in ['typo', 'P', '', None]:
        with pytest.raises(ValueError):
            calculate_houses(2451545, 45, 2, system)
    for cusps in [[0]*12, list(range(11)), [float('nan')]+list(range(11))]:
        with pytest.raises(ValueError):
            house_of(45, cusps)
    with pytest.raises(ValueError):
        calculate_houses(2451545, 90, 0, 'equal')


@pytest.mark.parametrize('system', SYSTEMS)
def test_all_migrated_data_tools_honor_selected_cusps_and_house_rulers(system):
    cases = [
        ('calculate_house_rulers', ext.house_ruler_data, BIRTH),
        ('calculate_solar_return', ext.solar_return_data, dict(BIRTH, target_year=2026, residence_location_id=BIRTH['location_id'])),
        ('calculate_lunar_return', ext.lunar_return_data, dict(BIRTH, target_year=2026, target_month=4, residence_location_id=BIRTH['location_id'])),
        ('calculate_secondary_progressions', ext.secondary_progressions_data, dict(BIRTH, age=30)),
        ('calculate_davison_chart', ext.davison_data, dict(person_a=BIRTH, person_b=PARTNER)),
        ('calculate_relocation_chart', ext.relocation_data, dict(BIRTH, relocation_location_id='gn:5128581')),
    ]
    natal = calculate_natal_data(**BIRTH, house_system=system)
    for tool, fn, args in cases:
        args = dict(args, house_system=system)
        result = fn(**args)
        assert result['status'] == 'ok', (tool, result)
        assert not validate_output(tool, result, args), tool
        if tool == 'calculate_house_rulers':
            for house in result['houses']:
                assert house['cusp_longitude'] == round(natal['house_cusps'][house['house']-1]['longitude'], 4)
                for track in house['tracks']:
                    for node in track['chain']:
                        assert node['house'] == next(p['house'] for p in natal['planets'] if p['name'] == node['planet'])
        elif tool in ('calculate_solar_return', 'calculate_lunar_return', 'calculate_davison_chart'):
            chart = result['chart']
            for point in chart['planets'].values():
                assert point['house'] == house_of(point['longitude'], chart['house_cusps'])
        elif tool == 'calculate_secondary_progressions':
            chart = result['progressed_chart']
            for point in chart['planets'].values():
                assert point['house'] == house_of(point['longitude'], chart['house_cusps'])
        else:
            for point in result['planets']:
                assert point['relocated_house'] == house_of(point['longitude'], result['house_cusps'])


@pytest.mark.parametrize('system', SYSTEMS[2:])
def test_method_specific_tools_explicitly_reject_unmigrated_systems(system):
    for fn, extras in [(calculate_classical_data, {})]:
        result = fn(**BIRTH, house_system=system, **extras)
        assert result['status'] == 'invalid_input'
        assert '此方法目前只支持' in result['error']


def test_discovery_and_clarification_agree_with_capability_boundary():
    import mcp_server
    from services.house_systems import GENERIC_HOUSE_TOOLS
    from services.mcp_contract import tool_clarification
    tools = asyncio.run(mcp_server.mcp.list_tools())
    for tool in tools:
        if tool.name not in GENERIC_HOUSE_TOOLS:
            continue
        prop = tool.inputSchema['properties']['house_system']
        variants = prop.get('anyOf', [prop])
        assert next(v['enum'] for v in variants if 'enum' in v) == list(SYSTEMS)
        assert prop['default'] == 'placidus'
        response = tool_clarification(tool.name, {}, ['house_system'])
        assert response is None or 'house_system' not in response['required_fields']
    restricted = tool_clarification('calculate_classical_factors', {}, ['house_system'])
    assert restricted is None


def test_equal_wheel_keeps_mc_and_house_lines_independent_and_unknown_system_fails():
    from services.natal_positions import calculate_positions
    from services.chart_svg import generate_chart_svg
    chart = calculate_positions(**BIRTH, house_system='equal')
    svg = generate_chart_svg(**chart['svg_data'], system='equal')
    assert 'data-axis="MC"' in svg
    assert svg.count('class="chart-house"') == 12
    with pytest.raises(ValueError):
        generate_chart_svg(**chart['svg_data'], system='typo')


def test_progressed_biwheel_receives_selected_system(monkeypatch):
    seen = []
    def render(*args, **kwargs):
        seen.append(kwargs['system'])
        return b'png'
    monkeypatch.setattr(ext, '_biwheel_png', render)
    for system in SYSTEMS:
        result, png = ext.render_secondary_progressions_biwheel_png(**BIRTH, house_system=system, age=30)
        assert result['status'] == 'ok' and png
    assert seen == list(SYSTEMS)


@pytest.mark.parametrize('system', SYSTEMS)
def test_each_migrated_renderer_produces_png(system, tmp_path):
    from services.mcp_natal import render_natal_chart_png
    cases = [
        (render_natal_chart_png, BIRTH),
        (ext.render_solar_return_png, dict(BIRTH, target_year=2026, residence_location_id=BIRTH['location_id'])),
        (ext.render_lunar_return_png, dict(BIRTH, target_year=2026, target_month=4, residence_location_id=BIRTH['location_id'])),
        (ext.render_secondary_progressions_biwheel_png, dict(BIRTH, age=30)),
        (ext.render_davison_png, dict(person_a=BIRTH, person_b=PARTNER)),
        (ext.render_relocation_png, dict(BIRTH, relocation_location_id='gn:5128581')),
    ]
    for fn, args in cases:
        result, png = fn(**args, house_system=system)
        assert result['status'] == 'ok', (fn.__name__, result)
        assert png.startswith(b'\x89PNG\r\n\x1a\n')


def test_captured_astrocom_tables_match_public_mcp_inputs_and_outputs():
    from scripts.verify_house_system_web_fixtures import compare_astrocom
    assert len(compare_astrocom()) == 21


@pytest.mark.parametrize('location,year,month,day,hour', [
    ('coord:-33.868800,151.209300', 2000, 1, 1, 23),
    ('coord:40.712800,-74.006000', 2024, 11, 3, 1),
])
def test_legacy_two_system_results_remain_compatible_at_other_locations(location, year, month, day, hour):
    from services.calculator import compute
    args=dict(year=year,month=month,day=day,hour=hour,minute=30,location_id=location,fold=0)
    legacy=compute('', year, month, day, hour, 30, '',location_id=location,fold=0)
    by_key={p['key']:p for p in legacy['natal_planets_full']}
    for system,field in [('placidus','house_p'),('whole_sign','house_w')]:
        r=calculate_natal_data(**args,house_system=system)
        assert r['status']=='ok'
        assert r['aspects']==legacy['aspects']
        for p in r['planets']:
            assert p['longitude']==by_key[p['key']]['lon']
            assert p['house']==by_key[p['key']][field]


def test_legacy_internal_codes_still_work_but_unknown_codes_fail():
    from services.house_systems import system_from_code
    assert system_from_code('w') == 'whole_sign'
    assert system_from_code(b'p') == 'placidus'
    assert system_from_code('A') == 'equal'
    with pytest.raises(ValueError):
        system_from_code('Z')


def test_captured_astrotheme_tables_match_with_cusp_shift_disabled():
    from scripts.verify_house_system_web_fixtures import compare_astrotheme
    assert len(compare_astrotheme()) == 6

def test_legacy_engine_uses_the_shared_exact_cusp_convention():
    from engine.natal_chart import NatalChartCalculator
    frame = calculate_houses(swe.julday(1990,4,15,16),48.8566,2.3522,'placidus')
    calculator = NatalChartCalculator()
    for i, cusp in enumerate(frame.cusps):
        assert calculator.get_planet_house(cusp,frame.cusps) == i+1
