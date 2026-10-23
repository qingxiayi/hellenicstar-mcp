"""Real MCP JSON round trips must not change numeric facts or references.

Synthetic births only. Node emulates the JSON.parse/stringify path used by JS
clients, where 3.0 becomes 3 without a user editing the reference.
"""
import asyncio
import copy
import json
import subprocess

import pytest

import mcp_server as m
from services.mcp_result_facts import fingerprint

BIRTH = dict(year=2000, month=1, day=1, hour=12, minute=0,
             location_id='coord:39.904200,116.407400')
PARTNER = {**BIRTH, 'year': 1998, 'month': 8, 'day': 2}


def js_roundtrip(value):
    return json.loads(subprocess.check_output(
        ['node', '-e', 'let s="";process.stdin.on("data",d=>s+=d);'
         'process.stdin.on("end",()=>process.stdout.write(JSON.stringify(JSON.parse(s))));'],
        input=json.dumps(value), text=True))


async def call(name, args):
    blocks = await m.mcp.call_tool(name, args)
    return json.loads(blocks[0].text)


@pytest.mark.parametrize('orb', [None, 8])
@pytest.mark.parametrize('detail', ['full', 'summary'])
def test_natal_reference_survives_actual_javascript_roundtrip(orb, detail):
    async def run():
        args = {**BIRTH, 'detail_level': detail}
        if orb is not None:
            args['orb_view'] = orb
        source = await call('calculate_natal_salience', args)
        assert source['status'] == 'ok'
        claims = [dict(quote='Schema', path='/schema_version', value=source['schema_version']),
                  dict(quote='Wrong schema', path='/schema_version', value='wrong'),
                  dict(quote='Orb', path='/settings/tight_orb', value=source['settings']['tight_orb']),
                  dict(quote='No bool coercion', path='/settings/include_mc_ruler', value=0)]
        for payload in (dict(reference=source['calculation_reference'], claims=claims),
                        js_roundtrip(dict(reference=source['calculation_reference'], claims=claims))):
            verified = await call('verify_calculation_claims', payload)
            assert verified.get('counts') == dict(supported=2, contradicted=2, unverified=0), verified
            assert verified['coverage']['independent_algorithm_verification'] is False
        tampered = js_roundtrip(source['calculation_reference'])
        tampered['input']['tight_orb'] = 2.5
        assert (await call('verify_calculation_claims', dict(reference=tampered, claims=claims)))['status'] == 'reference_mismatch'
    asyncio.run(run())


@pytest.mark.parametrize('detail', ['full', 'summary'])
def test_relationship_reference_and_human_note_survive_roundtrip(detail):
    async def run():
        source = await call('calculate_relationship_observation', dict(
            person_a=BIRTH, person_b=PARTNER, relationship_type='friendship',
            sextile_orb_degrees=5.0, detail_level=detail))
        assert source['status'] == 'ok', source
        ref = js_roundtrip(source['calculation_reference'])
        verified = await call('verify_calculation_claims', dict(reference=ref, claims=[
            dict(quote='Schema', path='/schema_version', value=source['schema_version']),
            dict(quote='Wrong', path='/schema_version', value='wrong')]))
        assert verified.get('counts') == dict(supported=1, contradicted=1, unverified=0), verified
        note = await call('prepare_relationship_observation_note', dict(
            reference=ref, person='a', statement='Synthetic caller statement.', author_role='client_report'))
        assert note['status'] == 'ok', note
        assert note['persisted'] is False and note['record']['is_calculation_fact'] is False
    asyncio.run(run())


def test_legacy_reference_still_verified_and_tampering_rejected():
    async def run():
        source = await call('calculate_natal_salience', BIRTH)
        ref = copy.deepcopy(source['calculation_reference'])
        ref['schema_version'] = 'calculation-reference-v1'
        ref['fingerprint'] = fingerprint(source, schema_version=ref['schema_version'])
        claims = [dict(quote='Schema', path='/schema_version', value=source['schema_version'])]
        verified = await call('verify_calculation_claims', dict(reference=ref, claims=claims))
        assert verified.get('counts', {}).get('supported') == 1, verified
        ref['fingerprint'] = '0' * 64
        assert (await call('verify_calculation_claims', dict(reference=ref, claims=claims)))['status'] == 'reference_mismatch'
    asyncio.run(run())


def test_numeric_canonicalization_does_not_round_or_coerce_non_numbers():
    from services.mcp_result_facts import exact_equal
    assert fingerprint({'v': [3., -0., {'a': 5.}]}) == fingerprint({'v': [3, 0, {'a': 5}]})
    assert exact_equal([3., {'a': 5.}], [3, {'a': 5}])
    for a, b in [(True, 1), (False, 0), ('3', 3), (3.000000000000001, 3),
                 (9007199254740993, 9007199254740992.)]:
        assert fingerprint({'v': a}) != fingerprint({'v': b})
        assert not exact_equal(a, b)
    with pytest.raises(ValueError):
        fingerprint({'v': float('nan')})
