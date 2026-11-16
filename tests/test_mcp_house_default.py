import asyncio
import json

import pytest
import mcp_server as m
from services.mcp_result_facts import fingerprint, lookup

BIRTH = dict(year=1990, month=4, day=15, hour=18, minute=0, location_id='gn:2988507')


@pytest.mark.parametrize('setting', [{}, {'house_system': None}, {'house_system': ''}])
def test_unspecified_house_defaults_and_is_frozen_in_reference(setting):
    data = asyncio.run(m.calculate_natal_chart(**BIRTH, **setting))
    assert data['status'] == 'ok'
    assert data['settings']['house_system'] == 'placidus'
    assert data['fact_reference']['input']['house_system'] == 'placidus'
    assert data['house_system_notice']['house_system'] == 'placidus'
    assert '普拉西度' in data['house_system_notice']['message']
    assert fingerprint(data) == data['calculation_reference']['fingerprint']
    with pytest.raises(KeyError):
        lookup(data, '/house_system_notice/message')


def test_explicit_choice_survives_summary_and_recomputation():
    data = asyncio.run(m.calculate_natal_chart(**BIRTH, house_system='equal',
                                             detail_level='summary', include=['planets']))
    assert data['status'] == 'ok'
    assert data['house_system_notice']['house_system'] == 'equal'
    assert data['fact_reference']['input']['house_system'] == 'equal'
    verified = asyncio.run(m.verify_natal_claims(
        reference=m.NatalFactReference(**data['fact_reference']),
        claims=[m.NatalClaim(quote='太阳在白羊座', kind='sign', point='sun', value='白羊座')]))
    assert verified['claims'][0]['verdict'] == 'supported'


def test_lots_default_and_time_lord_method_are_disclosed_separately():
    lots = asyncio.run(m.calculate_lots(**BIRTH))
    assert lots['settings']['house_system'] == 'placidus'
    assert lots['house_system_notice']['house_system'] == 'placidus'
    lords = asyncio.run(m.calculate_time_lords(**BIRTH, as_of='2026-11-16'))
    assert lords['annual_profections']['house_system'] == 'whole_sign'
    assert lords['annual_profections']['natal_house_system'] == 'placidus'
    assert '年小限固定' in lords['house_system_notice']['method_note']


def test_render_discloses_same_house_as_validated_source(monkeypatch):
    monkeypatch.setattr(m, '_IMAGE_HTTP_ENABLED', False)
    rendered = asyncio.run(m.render_natal_chart(**BIRTH))
    data = rendered.structuredContent
    assert data['status'] == 'ok'
    assert data['house_system_notice']['house_system'] == 'placidus'
    assert data['calculation_source']['settings']['house_system'] == 'placidus'
    assert json.loads(rendered.content[0].text)['house_system_notice'] == data['house_system_notice']


def test_default_never_hides_other_missing_inputs_or_invalid_choice():
    missing = asyncio.run(m.calculate_natal_chart(year=1990))
    assert missing['status'] == 'needs_clarification'
    assert 'minute' in missing['required_fields']
    assert 'house_system' not in missing['required_fields']
    invalid = asyncio.run(m.calculate_natal_chart(**BIRTH, house_system='unknown'))
    assert invalid['status'] == 'invalid_input'
    assert 'house_system_notice' not in invalid
    unsupported = asyncio.run(m.calculate_classical_factors(**BIRTH, house_system='equal'))
    assert unsupported['status'] == 'invalid_input'
