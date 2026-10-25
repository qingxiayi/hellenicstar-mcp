"""Regressions for failures observed in ordinary and professional client requests."""
import asyncio
import copy
import json
from datetime import datetime, timezone

import pytest
import mcp_server as m
from services import time_lords as tl
from services.mcp_natal import search_birthplace
from services.mcp_result_facts import CalculationClaim, CalculationReference
from services.mcp_validation import validate_output

BIRTH = dict(year=1990, month=4, day=15, hour=18, minute=0,
             location_id='gn:2988507', house_system='whole_sign')

@pytest.mark.parametrize('diurnal', [True, False])
def test_firdaria_alias_preserves_requested_name_without_changing_periods(diurnal):
    args = dict(birth_utc=datetime(1990, 4, 15, tzinfo=timezone.utc),
                timezone_name='Europe/Paris', is_diurnal=diurnal, max_age=100,
                now=datetime(2026, 10, 25, tzinfo=timezone.utc))
    base = tl.calculate_firdaria(**args, tradition='abu_mashar')
    alias = tl.calculate_firdaria(**args, tradition='al_biruni')
    assert alias['tradition'] == 'al_biruni'
    assert alias['effective_tradition'] == 'abu_mashar'
    assert '不证明' in alias['tradition_note']
    for key in ('major_periods', 'rows', 'current', 'sect', 'year_length_days'):
        assert alias[key] == base[key]
    bonatti = tl.calculate_firdaria(**args, tradition='bonatti')
    assert bonatti['tradition'] == bonatti['effective_tradition'] == 'bonatti'
    assert (bonatti['rows'] == base['rows']) is diurnal

@pytest.mark.parametrize('tradition', ['al_biruni', 'abu_mashar', 'bonatti'])
def test_time_lords_mcp_roundtrip_and_validation_reject_mislabeled_result(tradition):
    async def run():
        args = {**BIRTH, 'as_of':'2026-10-25', 'tradition':tradition}
        blocks = await m.mcp.call_tool('calculate_time_lords', args)
        data = json.loads(blocks[0].text)
        assert data['status'] == 'ok'
        assert data['calculation_reference']['input']['tradition'] == tradition
        assert data['firdaria']['tradition'] == tradition
        claims = [dict(quote='Requested convention', path='/firdaria/tradition', value=tradition),
                  dict(quote='Effective implementation', path='/firdaria/effective_tradition',
                       value=data['firdaria']['effective_tradition'])]
        checked = await m.verify_calculation_claims(
            reference=CalculationReference(**data['calculation_reference']),
            claims=[CalculationClaim(**c) for c in claims])
        assert checked['counts'] == dict(supported=2, contradicted=0, unverified=0)
        wrong = copy.deepcopy(data)
        wrong['firdaria']['tradition'] = 'bonatti' if tradition != 'bonatti' else 'al_biruni'
        issues = validate_output('calculate_time_lords', wrong, args)
        assert any(i['path'] == '/firdaria/tradition' for i in issues)
    asyncio.run(run())

@pytest.mark.parametrize('query,expected', [
    ('Paris, France','gn:2988507'), ('巴黎, 法国','gn:2988507'),
    ('London, Canada','gn:6058560')])
def test_explicit_region_unique_exact_city_proceeds(query, expected):
    result = search_birthplace(query)
    assert result['next_action'] == 'use_location_id'
    assert [o['location_id'] for o in result['options']] == [expected]
    assert result['options'][0]['match_basis'] == 'unique_exact_match_in_explicit_region'
    assert 'clarification' not in result

@pytest.mark.parametrize('query', ['Paris','Springfield, US','Paris, Atlantis, France'])
def test_ambiguous_or_unverified_region_still_asks(query):
    result = search_birthplace(query)
    assert result['next_action'] == 'ask_user'
    assert len(result['options']) > 1


def test_discovered_include_fields_support_real_focused_calls():
    async def run():
        listed = {t.name:t for t in await m.mcp.list_tools()}
        for tool, field in [('get_current_sky','retrograde_planets'),
                            ('calculate_relationship_charts','composite_chart')]:
            assert field in listed[tool].inputSchema['properties']['include']['description']
        sky = await m.get_current_sky(moment='2026-10-25T12:00:00+08:00', include=['retrograde_planets'])
        assert sky['status'] == 'ok' and 'retrograde_planets' in sky
        birth = {k:v for k,v in BIRTH.items() if k != 'house_system'}
        composite = await m.calculate_relationship_charts(person_a=m.BirthInput(**birth),
            person_b=m.BirthInput(**{**birth,'year':1988}), include=['composite_chart'])
        assert composite['status'] == 'ok' and 'composite_chart' in composite
        assert 'synastry_aspects' not in composite
    asyncio.run(run())


def test_single_candidate_with_unverified_region_still_asks(monkeypatch):
    import services.mcp_natal as natal
    monkeypatch.setattr(natal, '_search_city_options', lambda *a, **k: [
        {'location_id':'gn:2988507', 'city':'Paris', 'region_verified':False}])
    result = natal.search_birthplace('Paris, Unknown region, France')
    assert result['next_action'] == 'ask_user'
    assert result['required_fields'] == ['location_id']


def test_explicit_region_distinguishes_prefixes_from_exact_homonyms(tmp_path, monkeypatch):
    import sqlite3
    from services import mcp_compat_utils as locations
    for exact_count in (1, 2):
        db = tmp_path / f'locations-{exact_count}.db'
        with sqlite3.connect(db) as conn:
            conn.execute('CREATE TABLE places (location_id TEXT, country_code TEXT, lat_wgs84 REAL, lng_wgs84 REAL, tz_iana TEXT, admin1 TEXT, population INTEGER)')
            conn.execute('CREATE TABLE place_names (location_id TEXT, name TEXT, name_lower TEXT, lang TEXT, is_preferred INTEGER)')
            names = ['London'] * exact_count + ['London Bridge']
            for i, name in enumerate(names):
                conn.execute('INSERT INTO places VALUES (?, ?, ?, ?, ?, ?, ?)',
                             (f'fixture:{i}', 'GB', 51.5, -0.1, 'Europe/London', 'ENG', 1000-i))
                conn.execute('INSERT INTO place_names VALUES (?, ?, ?, ?, ?)',
                             (f'fixture:{i}', name, name.lower(), 'main', 1))
        monkeypatch.setattr(locations, 'DEFAULT_DB_PATH', str(db))
        result = search_birthplace('London, UK')
        if exact_count == 1:
            assert result['next_action'] == 'use_location_id'
            assert [o['location_id'] for o in result['options']] == ['fixture:0']
        else:
            assert result['next_action'] == 'ask_user'
            assert {'fixture:0', 'fixture:1'} <= {o['location_id'] for o in result['options']}
