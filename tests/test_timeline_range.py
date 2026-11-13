"""Rolling-year bounds, real calculation clipping and reference round trips."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import pytest
from services.timeline_synthesis import resolve_timeline_range, compute_timeline_synthesis

CTX = dict(civil_dt='1990-04-15T18:00:00', tz_iana='Europe/Paris', fold=0)
BIRTH = dict(year=1990, month=4, day=15, hour=18, minute=0, location_id='gn:2988507')

@pytest.mark.parametrize('start,years,end', [('2026-11-13',1,'2027-11-13'),('2026-11-13',3,'2029-11-13'),('2028-02-29',1,'2029-02-28')])
def test_anniversaries_are_civil_years_not_fixed_day_counts(start,years,end):
    lo,hi,s=resolve_timeline_range(CTX,start_date=start,span_years=years)
    assert lo.date().isoformat()==start and hi.date().isoformat()==end
    assert s['mode']=='rolling_years' and s['end_date_exclusive']==end
    assert s['start_utc']==lo.astimezone(timezone.utc).isoformat().replace('+00:00','Z')


def test_daylight_saving_and_missing_midnight_boundaries():
    lo,hi,_=resolve_timeline_range(CTX,start_date='2026-03-29')
    assert (hi.astimezone(timezone.utc)-lo.astimezone(timezone.utc)).total_seconds()==365*86400-3600
    sao=dict(CTX,tz_iana='America/Sao_Paulo')
    lo,_,s=resolve_timeline_range(sao,start_date='2018-11-04')
    assert lo.isoformat()=='2018-11-04T01:00:00-02:00'
    assert s['requested_start_date']=='2018-11-04'
    with pytest.raises(ValueError,match='不存在'):
        resolve_timeline_range(dict(CTX,tz_iana='Pacific/Apia'),start_date='2011-12-30')


def test_calendar_mode_and_birth_clipping_preserved():
    lo,hi,s=resolve_timeline_range(CTX,target_year=2026,span_years=1)
    assert (lo.isoformat(),hi.isoformat())==('2026-01-01T00:00:00+01:00','2027-01-01T00:00:00+01:00')
    lo,_,s=resolve_timeline_range(CTX,target_year=1990)
    assert lo.isoformat()=='1990-04-15T18:00:00+02:00' and s['clipped_to_birth']


@pytest.mark.parametrize('args', [dict(start_date='today'),dict(start_date='20261113'),dict(start_date='2026-02-30'),dict(start_date='2026-11-13T00:00:00Z'),dict(start_date='1899-11-13'),dict(start_date='2026-11-13',target_year=2026),dict(start_date='2026-11-13',span_years=4),dict(start_date='2026-11-13',span_years=True),dict(start_date='1980-01-01'),dict(start_date='2090-11-13')])
def test_invalid_ranges_rejected(args):
    with pytest.raises(ValueError): resolve_timeline_range(CTX,**args)


@pytest.fixture(scope='module')
def rolling():
    import mcp_server as m
    return asyncio.run(m.calculate_timeline_synthesis(**BIRTH,start_date='2026-11-13',span_years=1))


def test_rolling_output_uses_real_start_and_preserves_period_context(rolling):
    from services.mcp_natal import _compute_source
    d=rolling
    assert d['status']=='ok' and d['quality']['status']=='passed'
    assert d['settings']['target_year'] is None
    lo='2026-11-12T23:00:00Z';hi='2027-11-12T23:00:00Z'
    assert d['progressed_context']['as_of_utc']==lo
    assert all(lo<=e['exact_utc']<hi for e in d['events'])
    assert all(lo<=w['start_utc']<w['end_utc']<=hi for w in d['aspect_windows'])
    assert all(lo<=p['exact_utc']<hi for p in d['progressed_context']['phase_transitions'])
    active=[e for e in d['events'] if e['nature']=='period_active']
    assert {e['technique'] for e in active}=={'firdaria','zodiacal_releasing'}
    assert all(e['exact_utc']==lo for e in active)
    birth=dict(BIRTH,fold=0)
    natal=_compute_source(**BIRTH,house_system='placidus',fold=None)
    wide=compute_timeline_synthesis(natal,birth,2026,2)
    # Query-root grids may differ by sub-minute rounding, so compare identity
    # and dates, then independently verify the endpoints above.
    def identities(rows):
        return {(e['technique'],e['nature'],e['date'],e['focus'],e['source'].get('planet'),e['source'].get('angle')) for e in rows if e['weight']=='exact' and lo<=e['exact_utc']<hi}
    assert identities(d['events'])==identities(wide['events'])
    assert d['progressed_context']['phase_at_start']!=wide['progressed_context']['phase_at_start']


def test_mcp_ranges_discovery_selective_reading_and_reference(rolling):
    import mcp_server as m
    from services.mcp_result_facts import CalculationReference, CalculationClaim
    async def check():
        defs=await m.mcp.list_tools()
        definition=next(t for t in defs if t.name=='calculate_timeline_synthesis')
        assert 'start_date' in definition.inputSchema['properties']
        selected=await m.calculate_timeline_synthesis(**BIRTH,start_date='2026-11-13',include=['reading_layers'])
        assert selected['calculation_reference']==rolling['calculation_reference']
        assert selected['settings']['query_range']==rolling['settings']['query_range']
        verified=await m.verify_calculation_claims(reference=CalculationReference(**rolling['calculation_reference']),claims=[CalculationClaim(quote='起点',path='/settings/query_range/start_utc',value='2026-11-12T23:00:00Z')])
        assert verified['counts']==dict(supported=1,contradicted=0,unverified=0)
        mixed=await m.calculate_timeline_synthesis(**BIRTH,target_year=2026,start_date='2026-11-13')
        assert mixed['status']=='invalid_input'
    asyncio.run(check())


@pytest.mark.parametrize('field',['range','event','background'])
def test_contract_rejects_outside_or_stale_calendar_data(rolling,field):
    from services.mcp_validation import validate_output
    d=deepcopy(rolling)
    if field=='range': d['settings']['query_range']['end_date_exclusive']='2027-01-01'
    elif field=='event': d['events'][0]['exact_utc']='2026-01-01T00:00:00Z'
    else: d['progressed_context']['as_of_utc']='2026-01-01T00:00:00Z'
    assert validate_output('calculate_timeline_synthesis',d,dict(BIRTH,start_date='2026-11-13',span_years=1))
