"""Workshop additions: self-first geometry, sorting, and non-factual human notes."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from services.relationship_observation import calculate_observation_data, settings_for, VERSION
from services.mcp_result_facts import checked_result, verify_calculation_claims_data

BIRTH = dict(year=2000, month=1, day=1, hour=12, minute=0, location_id='coord:39.904200,116.407400')
PARTNER = {**BIRTH, 'year': 1995, 'month': 5, 'day': 12}


@pytest.mark.parametrize('two_people', [False, True])
def test_natal_mode_requires_no_partner_or_cross_contacts(two_people):
    import mcp_server  # populate verification registry
    args = dict(person_a=BIRTH, mode='natal')
    if two_people:
        args['person_b'] = PARTNER
    raw = calculate_observation_data(**args)
    result = checked_result('calculate_relationship_observation', raw, args)
    assert result['status'] == 'ok', result
    assert set(result['relationship_profiles']) == ({'a', 'b'} if two_people else {'a'})
    for field in ('contacts', 'observation_paths', 'activation_clusters', 'house_overlays'):
        assert result[field] == []
    assert result['saturn_reciprocity']['value'] is None
    assert result['layer_availability']['synastry']['status'] == 'not_computed'
    assert len(result['natal_observation_entries']['a']) == 17
    assert all(e['activation_cluster_ids'] == [] for e in result['natal_observation_entries']['a'])
    checked = verify_calculation_claims_data(result['calculation_reference'], [dict(
        quote='source version', path='/schema_version', value=VERSION)])
    assert checked['counts']['supported'] == 1
    paired = calculate_observation_data(person_a=BIRTH, person_b=PARTNER)
    assert paired['relationship_profiles']['a'] == result['relationship_profiles']['a']


def test_sorting_only_reorders_clusters_and_retains_all_geometry():
    args = dict(person_a=BIRTH, person_b=PARTNER)
    results = {sort: calculate_observation_data(**args, sort_by=sort) for sort in
               ('orb', 'relationship_indicators', 'natal_hard_aspects')}
    base = results['orb']
    assert [(c['min_direct_orb_degrees'], c['id']) for c in base['activation_clusters']] == sorted(
        (c['min_direct_orb_degrees'], c['id']) for c in base['activation_clusters'])
    for sort, r in results.items():
        assert r['contacts'] == base['contacts'] and r['counts'] == base['counts']
        assert r['relationship_profiles'] == base['relationship_profiles']
        assert {c['id']: c for c in r['activation_clusters']} == {c['id']: c for c in base['activation_clusters']}
        if sort == 'relationship_indicators':
            keys = [(-int(c['observation_context']['target_relationship_indicator']), c['min_direct_orb_degrees'], c['id'])
                    for c in r['activation_clusters']]
            assert keys == sorted(keys)
    with pytest.raises(ValueError):
        settings_for(sort_by='psychological_importance')


def test_notes_do_not_become_facts_or_change_fingerprint():
    import mcp_server
    from services.relationship_observation_notes import prepare_note
    args = dict(person_a=BIRTH, mode='natal')
    r = checked_result('calculate_relationship_observation', calculate_observation_data(**args), args)
    before = deepcopy(r)
    note_args = dict(reference=r['calculation_reference'], person='a', statement='我希望彼此能坦诚沟通。',
                     author_role='client_report', point='venus', question_id='partner_expectations')
    note = prepare_note(**note_args)
    assert note['status'] == 'ok' and note['persisted'] is False
    assert note['record']['statement'] == note_args['statement']
    assert note['record']['statement_verification'] == 'not_verified'
    assert note['record']['is_calculation_fact'] is False
    assert 'calculation_reference' not in note
    assert r == before
    for update in (dict(person='b'), dict(statement=' '), dict(point='invented'), dict(question_id='diagnosis')):
        assert prepare_note(**{**note_args, **update})['status'] == 'invalid_input'
    tampered = deepcopy(r['calculation_reference']); tampered['fingerprint'] = '0' * 64
    assert prepare_note(**{**note_args, 'reference': tampered})['status'] == 'invalid_reference'
    wrong = deepcopy(r['calculation_reference']); wrong['tool'] = 'calculate_natal_chart'
    assert prepare_note(**{**note_args, 'reference': wrong})['status'] == 'invalid_reference'


def test_stdio_self_first_notes_and_legacy_pair_requirements():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    async def run():
        params = StdioServerParameters(command=sys.executable,
            args=[str(Path(__file__).resolve().parents[1] / 'mcp_server.py')])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                async def call(name, args):
                    out = await s.call_tool(name, args)
                    assert not out.isError, out
                    return json.loads(out.content[0].text)
                r = await call('calculate_relationship_observation', dict(person_a=BIRTH, mode='natal'))
                assert r['status'] == 'ok', r
                v = await call('verify_calculation_claims', dict(reference=r['calculation_reference'], claims=[
                    dict(quote='mode', path='/settings/mode', value='natal')]))
                assert v['counts']['supported'] == 1
                note = await call('prepare_relationship_observation_note', dict(reference=r['calculation_reference'],
                    person='a', statement='咨询者记录：待进一步询问。', author_role='practitioner_note'))
                assert note['status'] == 'ok' and note['persisted'] is False
                assert 'calculation_reference' not in note and 'quality' not in note
                bad_note = await call('prepare_relationship_observation_note', dict(reference=r['calculation_reference'],
                    person='b', statement='unavailable person', author_role='client_report'))
                assert bad_note['status'] == 'invalid_input'
                for tool in ('calculate_relationship_observation', 'calculate_relationship_charts'):
                    missing = await call(tool, dict(person_a=BIRTH))
                    assert missing['status'] == 'needs_clarification'
                    assert 'person_b.hour' in missing['required_fields']
                short = await call('calculate_relationship_observation', dict(person_a=BIRTH, mode='natal',
                    detail_level='summary', include=['natal_observation_entries']))
                assert short['layer_availability']['synastry']['status'] == 'not_computed'
    asyncio.run(run())
