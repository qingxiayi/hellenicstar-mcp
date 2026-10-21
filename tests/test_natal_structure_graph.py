"""Graph boundary regressions and preservation of the existing natal source."""
import copy
import json

import pytest
import swisseph as swe

from services.birth_input import validated_birth_values
from services.calculator import BirthContextError, compute
from services.natal_structure_graph import (
    StructureInputError, build_structure_graph, calculate_structure_graph,
    _house_independent_source,
)

BIRTH = dict(year=2000, month=1, day=1, hour=12, minute=0,
             city="", lat=39.9042, lng=116.4074)


@pytest.fixture(scope="module")
def source():
    return compute("", **BIRTH)


@pytest.mark.parametrize("field", ["year", "month", "day", "hour", "minute"])
@pytest.mark.parametrize("bad", [9.5, 9.0, True, None, "9.5", "1e1"])
def test_birth_values_reject_truncation_and_boolean(field, bad):
    args = {k: BIRTH[k] for k in ("year", "month", "day", "hour", "minute")}
    args[field] = bad
    with pytest.raises(ValueError, match=field):
        validated_birth_values(**args)


def test_legacy_integer_strings_are_explicitly_supported():
    assert validated_birth_values("2000", "1", "1", "12", "0") == (2000, 1, 1, 12, 0)


def test_compute_rejects_fractional_hour_before_resolving(monkeypatch):
    from services.location_resolver import LocationResolver
    monkeypatch.setattr(LocationResolver, "resolve", lambda *a, **kw: pytest.fail("should validate first"))
    with pytest.raises(ValueError, match="hour"):
        compute("", **{**BIRTH, "hour": 9.5})


@pytest.mark.parametrize("mutation", [
    "missing", "duplicate", "nan", "index", "sign", "house_zero", "house_bool",
    "whole_house", "sect", "retrograde", "aspect_orb", "aspect_label", "aspect_duplicate",
    "house_row", "fake_partial",
])
def test_reject_contradictory_sources(source, mutation):
    r = copy.deepcopy(source)
    p = r["natal_planets_full"][0]
    a = next(a for a in r['aspects'] if a['point1'] == 'sun' and a['point2'] in ('moon', 'mercury', 'venus', 'mars', 'jupiter', 'saturn', 'uranus', 'neptune', 'pluto'))
    if mutation == "missing": r["natal_planets_full"] = [p for p in r["natal_planets_full"] if p['key'] != 'saturn']
    if mutation == "duplicate": r["natal_planets_full"].append(copy.deepcopy(p))
    if mutation == "nan": p['lon'] = float('nan')
    if mutation == "index": p['sign_idx'] = 0
    if mutation == "sign": p['sign'] = '白羊座'
    if mutation == "house_zero": p['house_p'] = 0
    if mutation == "house_bool": p['house_p'] = True
    if mutation == "whole_house": p['house_w'] = p['house_w'] % 12 + 1
    if mutation == "sect": r['sect'] = 'unknown'
    if mutation == "retrograde": p['retrograde'] = 'false'
    if mutation == "aspect_orb": a['orb'] += 1
    if mutation == "aspect_label": a['aspect'] = 'invalid'
    if mutation == "aspect_duplicate": r['aspects'].append(copy.deepcopy(a))
    if mutation == "house_row": r['house_ruler_chains']['placidus'][0]['house'] = 2
    if mutation == "fake_partial": r['layer_availability'] = {'placidus': {'status': 'unavailable'}}
    with pytest.raises(StructureInputError):
        build_structure_graph(r)


def test_normal_graph_and_old_source_are_preserved(source):
    original = copy.deepcopy(source)
    g = calculate_structure_graph(**BIRTH)
    assert g['status'] == 'ok'
    assert g['layer_availability'] == {}
    assert source == original
    assert g['dispositor']['traditional']['terminals'][0]['members'] == ['jupiter', 'mars', 'saturn', 'venus']
    assert sum(len(t['basin']) for t in g['dispositor']['modern']['terminals']) == 10
    assert len(g['houses']['placidus']) == len(g['houses']['whole_sign']) == 12
    assert g['interpretations'] == []


@pytest.mark.parametrize("lat,lng,month", [(69.6492, 18.9553, 6), (69.6492, 18.9553, 12),
                                         (78.2232, 15.6469, 1), (-77.8419, 166.6863, 6)])
def test_polar_graph_has_real_planets_without_fabricated_houses(lat, lng, month):
    g = calculate_structure_graph(year=2000, month=month, day=21, hour=12, minute=0, lat=lat, lng=lng)
    assert g['status'] == 'partial'
    assert len(g['nodes']) == 10
    assert all(n['house_p'] is None and n['house_w'] is None for n in g['nodes'])
    assert g['houses'] == {'placidus': [], 'whole_sign': []}
    assert g['axes'] == {}
    assert set(g['layer_availability']) == {'placidus', 'whole_sign', 'axes'}
    assert all(v['status'] == 'unavailable' for v in g['layer_availability'].values())
    assert g['aspects']['8']['edges']
    assert all(f & swe.FLG_SWIEPH for f in g['source_metadata']['ephemeris_flags'].values())
    json.dumps(g, allow_nan=False)


def test_partial_swiss_path_agrees_with_regular_planets(source):
    from services.location_resolver import LocationResolver
    from services.civil_time_resolver import CivilTimeResolver
    snap = LocationResolver().resolve(lat=BIRTH['lat'], lng=BIRTH['lng'])
    ctx = CivilTimeResolver().resolve(snap, 2000, 1, 1, 12, 0).context
    partial = _house_independent_source(ctx, "test of unavailable houses")
    expected = {p['key']: p for p in source['natal_planets_full']}
    for p in partial['natal_planets_full']:
        assert abs(p['lon'] - expected[p['key']]['lon']) < .000051
        assert p['retrograde'] == expected[p['key']]['retrograde']
    a = build_structure_graph(source)
    b = build_structure_graph(partial)
    assert a['dispositor'] == b['dispositor']
    for cutoff in ('6', '8', '10'):
        assert {e['id'] for e in a['aspects'][cutoff]['edges']} == {e['id'] for e in b['aspects'][cutoff]['edges']}
        assert {m['id'] for m in a['aspects'][cutoff]['motifs']} == {m['id'] for m in b['aspects'][cutoff]['motifs']}


def test_unrelated_compute_error_is_not_hidden(monkeypatch):
    from services import calculator
    def fail(*a, **kw):
        raise RuntimeError('unrelated failure')
    monkeypatch.setattr(calculator, 'compute', fail)
    with pytest.raises(RuntimeError, match='unrelated failure'):
        calculate_structure_graph(**BIRTH)


def test_ephemeris_fallback_is_not_silently_accepted(monkeypatch):
    from services.location_resolver import LocationResolver
    from services.civil_time_resolver import CivilTimeResolver
    from services.ephemeris_guard import EphemerisModeError
    snap = LocationResolver().resolve(lat=BIRTH['lat'], lng=BIRTH['lng'])
    ctx = CivilTimeResolver().resolve(snap, 2000, 1, 1, 12, 0).context
    original = swe.calc_ut
    def moshier(*args, **kwargs):
        values, flags = original(*args, **kwargs)
        return values, (flags & ~swe.FLG_SWIEPH) | swe.FLG_MOSEPH
    monkeypatch.setattr(swe, 'calc_ut', moshier)
    with pytest.raises(EphemerisModeError):
        _house_independent_source(ctx, 'test')


def test_dst_errors_and_fold_are_preserved():
    birth = dict(year=2024, month=11, day=3, hour=1, minute=30, lat=40.7128, lng=-74.006)
    with pytest.raises(BirthContextError) as exc:
        calculate_structure_graph(**birth)
    assert len(exc.value.candidates) == 2
    a = calculate_structure_graph(**birth, fold=0)
    b = calculate_structure_graph(**birth, fold=1)
    assert a['birth_context']['utc_offset'] == -4
    assert b['birth_context']['utc_offset'] == -5
    with pytest.raises(BirthContextError):
        calculate_structure_graph(**{**birth, 'month': 3, 'day': 10, 'hour': 2})


@pytest.mark.parametrize('bad', [True, '0', .5, 2])
def test_graph_fold_strictness(bad):
    with pytest.raises(ValueError, match='fold'):
        calculate_structure_graph(**BIRTH, fold=bad)
