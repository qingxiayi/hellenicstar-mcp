"""Analytic motion oracles, independent roots, and real MCP contract checks."""
import asyncio
import copy
import pytest
from services.natal_aspect_dynamics import phase_at, trace_pair as _trace_pair, calculate_dynamics
from services.natal_relation_facts import reception_facts
from services.mcp_salience import calculate_salience_data
from services.natal_salience import normalize_config


def trace_pair(a,b,angle,start,days,position,**kwargs):
    # Analytic time is days since J2000, not Julian day zero (outside datetime).
    epoch=2451545.
    out=_trace_pair(a,b,angle,epoch+start,days,lambda body,jd:position(body,jd-epoch),**kwargs)
    hit=out['search']['first_exact_jd_ut']
    if hit is not None: out['search']['first_exact_jd_ut']=hit-epoch
    return out


@pytest.mark.parametrize('args,status',[
    ((0,59,0,1,60),'applying'),((0,61,0,1,60),'separating'),
    ((359,1,0,-1,0),'applying'),((0,301,0,-1,60),'applying'),
    ((0,179,1,0,180),'separating'),((0,60,0,1,60),'exact'),
    ((0,61,1,1,60),'relative_stationary')])
def test_signed_relative_motion(args,status):
    assert phase_at(*args)['status']==status
    a,b,va,vb,angle=args
    assert phase_at(b,a,vb,va,angle)['status']==status


def test_initially_applying_then_reverses_before_exact():
    def pos(body,t):
        return (0,0) if body=='a' else (59+t-t*t,1-2*t)
    out=trace_pair('a','b',60,0,2,pos)
    assert out['phase']['status']=='applying'
    assert out['search']['status']=='not_found_in_window'
    assert out['search']['current_application']=='relative_reversal_before_exact'
    assert {e['kind'] for e in out['search']['events_before_exact_or_end']} >= {'relative_station','body_station'}


@pytest.mark.parametrize('offset,expected',[(.01,.4),(0,.5)])
def test_two_crossings_or_tangent_inside_same_sign_endpoints(offset,expected):
    def pos(body,t):
        return (0,0) if body=='a' else (60+(t-.5)**2-offset,2*(t-.5))
    out=trace_pair('a','b',60,0,1,pos,step=1)
    assert out['search']['first_exact_jd_ut']==pytest.approx(expected,abs=1e-5)


def test_wrap_discontinuity_is_not_a_false_exact_hit():
    def pos(body,t): return (0,0) if body=='a' else ((179+2*t)%360,2)
    out=trace_pair('a','b',0,0,1,pos)
    assert out['search']['status']=='not_found_in_window'


def test_sign_change_precedes_exact_and_station_does_not_mean_failure():
    def pos(body,t):
        return ((29+2*t)%360,2) if body=='a' else ((93+t*t)%360,2*t)
    # residual = 4 - 2t + t^2: closest at t=1, never exact in window.
    out=trace_pair('a','b',60,0,2,pos)
    assert any(e['kind']=='sign_ingress' and e['body']=='a' for e in out['search']['events_before_exact_or_end'])
    assert out['search']['sign_change_before_exact'] is None


def test_exact_at_birth_has_no_future_events():
    out=trace_pair('a','b',60,0,1,lambda b,t:(0,0) if b=='a' else (60+t,1))
    assert out['search']['status']=='exact_at_epoch'
    assert out['search']['events_before_exact_or_end']==[]


def test_station_inside_segment_exposes_two_sign_crossings():
    def pos(body,t):
        return (200,0) if body=='a' else ((30.001-(t-.03)**2)%360,-2*(t-.03))
    out=trace_pair('a','b',0,0,.125,pos)
    # One crossing is before epoch, the return ingress must still be recorded.
    assert any(e['kind']=='sign_ingress' for e in out['search']['events_before_exact_or_end'])


def test_four_policies_preserve_facts_and_distinguish_unknown_from_false():
    nodes={'sun':{'lon':1.,'sign_idx':0},'mars':{'lon':149.,'sign_idx':4}}
    results={p:reception_facts(nodes,[],'日生人',8,policy=p) for p in
             ('dignity_only','sign_aspect','degree_aspect','applying_degree_aspect')}
    assert [next(r for r in x['rows'] if r['host']=='mars')['policy_evaluation']['meets'] for x in results.values()]==[True,True,False,False]
    edge={'id':'x','from':'sun','to':'mars','angle':120,'orb':1}
    unknown=reception_facts(nodes,[edge],'日生人',8,policy='applying_degree_aspect')
    assert next(r for r in unknown['rows'] if r['host']=='mars')['policy_evaluation']['meets'] is None
    dynamic={'rows':[{'aspect_id':'x','phase':{'status':'separating'}}]}
    evaluated=reception_facts(nodes,[edge],'日生人',8,dynamic,'applying_degree_aspect')
    assert next(r for r in evaluated['rows'] if r['host']=='mars')['policy_evaluation']['meets'] is False


@pytest.mark.parametrize('value',[True,0,91,1.5,'30'])
def test_bounded_horizon_validation(value):
    with pytest.raises(ValueError): normalize_config({'dynamics_days':value})


def test_real_ephemeris_phase_and_roots_and_no_cache_mutation():
    from services.transit_utils import body_position
    from services.planetary_aspect_scan import BODIES
    d=calculate_salience_data(year=2000,month=1,day=1,hour=12,minute=0,location_id='coord:39.904200,116.407400')
    motion=d['aspect_dynamics']
    assert motion['status']=='available'
    assert {r['aspect_id'] for r in motion['rows']}=={e['id'] for e in d['source_graph']['aspects']['6']['edges']}
    for row in motion['rows']:
        hit=row['search']['first_exact_jd_ut']
        if hit:
            a=body_position(BODIES[row['planet_a']],hit)[0]
            b=body_position(BODIES[row['planet_b']],hit)[0]
            assert abs(abs((b-a+180)%360-180)-row['angle']) < 1e-5
    reference=copy.deepcopy(motion)
    motion['rows'][0]['phase']['status']='tampered'
    assert calculate_dynamics(d['source_graph'])==reference


def test_missing_future_ephemeris_keeps_epoch_phase_and_never_reports_no_hit(monkeypatch):
    from services import natal_aspect_dynamics as module
    from services.ephemeris_guard import EphemerisModeError
    def missing_future(body,jd):
        if jd>2451545.1: raise EphemerisModeError('test coverage boundary')
        return (0,0) if body==module.BODIES['sun'] else (59,1)
    monkeypatch.setattr(module,'body_position',missing_future)
    module._compute.cache_clear()
    try:
        row=module._compute(2451545.,1,(('test','sun','moon',60),))[0]
        assert row['status']=='partial' and row['phase']['status']=='applying'
        assert row['search']['status']=='unavailable'
    finally: module._compute.cache_clear()


def test_real_mcp_new_policy_fields_verify_and_tamper_rejected():
    import mcp_server as m
    from services.mcp_result_facts import checked_result
    async def run():
        args=dict(year=2000,month=1,day=1,hour=12,minute=0,location_id='coord:39.904200,116.407400',
                  reception_policy='applying_degree_aspect',dynamics_days=10)
        d=await m.calculate_natal_salience(**args)
        assert d['status']=='ok',d
        path='/aspect_dynamics/rows/0/phase/status'
        r=await m.verify_calculation_claims(reference=m.CalculationReference(**d['calculation_reference']),
            claims=[m.CalculationClaim(quote='phase',path=path,value=d['aspect_dynamics']['rows'][0]['phase']['status'])])
        assert r['claims'][0]['verdict']=='supported'
        d['aspect_dynamics']['rows'][0]['phase']['status']='tampered'
        assert checked_result('calculate_natal_salience',d,args)['status']=='validation_failed'
    asyncio.run(run())
