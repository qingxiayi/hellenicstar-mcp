"""Analytic roots, station reversals, clipping, references and real MCP windows."""
from copy import deepcopy
from datetime import datetime
import json

import pytest

from services.relationship_observation import calculate_observation_data, settings_for
from services.relationship_observation_windows import scan_curve, scan_timing_window, endpoint_overlaps, TIME_TOL
from tests.test_relationship_observation import BIRTH, PARTNER, geometry
from tests.test_relationship_observation_timing import config, synthetic, sources
from tests.test_relationship_observation_v010 import lookup


def window_config(**changes):
    cfg=config()
    cfg.update(at='2020-06-01T12:00:00Z',window_start='2020-06-01T00:00:00Z',window_end='2020-06-02T00:00:00Z')
    cfg.update(changes)
    return cfg


@pytest.mark.parametrize('change',[
    {'window_start':None}, {'window_end':'2020-06-02'},
    {'window_start':'2020-06-01T00:00:00'}, {'window_end':'2020-06-01T00:00:00Z'},
    {'window_end':'2020-07-03T00:00:00Z'}, {'window_end':'2020-06-01T00:00:00.001Z'},
    {'at':'2020-06-02T00:00:00Z'}, {'at':'2020-05-31T23:59:59Z'},
])
def test_invalid_window_settings(change):
    with pytest.raises(ValueError):settings_for(include_timing=True,timing=window_config(**change))


def test_window_needs_both_endpoints():
    cfg=window_config();cfg.pop('window_end')
    with pytest.raises(ValueError):settings_for(include_timing=True,timing=cfg)


def test_wraparound_exact_entry_exit_and_mirror_trine():
    r=scan_curve(lambda t:(359+2*t)%360,lambda t:2,0,2,{0:0.5})[0]
    assert r['exact']==pytest.approx([0.5])
    assert r['windows'][0]==pytest.approx([0.25,0.75])
    assert scan_curve(lambda t:(239+t)%360,lambda t:1,0,2,{120:0})[120]['exact']==pytest.approx([1])


def test_station_splits_two_roots_despite_same_sign_mesh_endpoints():
    r=scan_curve(lambda t:((t-.1)**2-.0004)%360,lambda t:2*(t-.1),0,.25,{0:.0001})[0]
    assert r['exact']==pytest.approx([.08,.12],abs=TIME_TOL)
    assert len(r['windows'])==2
    for a,b in r['windows']:
        for t in (a,b):assert abs(abs((t-.1)**2-.0004)-.0001)<1e-8


def test_exact_tangent_and_orb_boundary_touch_without_positive_duration():
    tangent=scan_curve(lambda t:((t-.1)**2)%360,lambda t:2*(t-.1),0,.25,{0:.001})[0]
    assert tangent['exact']==pytest.approx([.1],abs=TIME_TOL)
    boundary=scan_curve(lambda t:((t-.1)**2+.001)%360,lambda t:2*(t-.1),0,.25,{0:.001})[0]
    assert boundary['exact']==[] and boundary['windows']==[]
    assert boundary['boundaries']==pytest.approx([.1],abs=TIME_TOL)


def test_clipped_window_and_constant_exact_not_repeated_events():
    r=scan_curve(lambda t:.2,lambda t:0,0,1,{0:1})[0]
    assert r['windows']==[[0,1]] and not r['exact']
    r=scan_curve(lambda t:0,lambda t:0,0,1,{0:0})[0]
    assert r['constant_exact']==[[0,1]] and not r['exact'] and not r['windows']


def test_adjacent_windows_own_start_not_end_exact_hit():
    left=scan_curve(lambda t:(t-1)%360,lambda t:1,0,1,{0:0})
    right=scan_curve(lambda t:(t-1)%360,lambda t:1,1,2,{0:0})
    assert not left and right[0]['exact']==[1]


def test_same_transit_and_real_overlap_required_not_just_hits_somewhere():
    obs={'contacts':[dict(first_point='sun',second_point='moon')]}
    def row(who,point,body,start,end):
        return dict(first=dict(kind='transit',point=body),second=dict(kind='natal',person=who,point=point),
                    windows=[dict(start_jd_ut=start,end_jd_ut=end)])
    a=row('a','sun','saturn',2451545,2451546)
    b=row('b','moon','jupiter',2451545,2451546)
    assert not endpoint_overlaps(obs,[a,b])
    b['first']['point']='saturn';b['windows']=[dict(start_jd_ut=2451546,end_jd_ut=2451547)]
    assert not endpoint_overlaps(obs,[a,b])
    b['windows']=[dict(start_jd_ut=2451545.5,end_jd_ut=2451547)]
    hit=endpoint_overlaps(obs,[a,b])[0]['same_transit_overlaps'][0]
    assert hit['transit_point']=='saturn'
    assert hit['a_timing_contact_ref'].endswith('/0') and hit['b_timing_contact_ref'].endswith('/1')


def test_scan_considers_contacts_absent_at_snapshot(monkeypatch):
    import services.relationship_observation_windows as mod
    cfg=window_config(at='2020-06-01T00:00:00Z',window_end='2020-06-04T00:00:00Z')
    src=sources();src['transit']['points']['saturn']=4
    obs=synthetic(cfg=cfg,source=src,a=geometry(sun=0))
    ident='transit:saturn|a_natal:sun|0'
    assert not any(c['id']==ident for c in obs['timing_observations']['contacts'])
    class Frames:
        def __init__(self,observation,births,lo,hi):
            self.lo=lo
            self.charts={'transit':src['transit']['points']}
            for who in ('a','b'):
                self.charts[who+'_natal']=observation['source_geometry'][who]['points']
                self.charts[who+'_progressed']=src['progressed'][who]['points']
        def lon(self,c,p,t):return self.charts[c][p]-(2*(t-self.lo) if (c,p)==('transit','saturn') else 0)
        def raw(self,l,p,r,q,t):return (self.lon(r,q,t)-self.lon(l,p,t))%360
        def velocity(self,l,p,r,q,t):return (-2 if (r,q)==('transit','saturn') else 0)-(-2 if (l,p)==('transit','saturn') else 0)
    monkeypatch.setattr(mod,'ChartFrames',Frames)
    scan=scan_timing_window(obs,{})
    row=next(c for c in scan['contacts'] if c['id']==ident)
    assert len(row['exact_events'])==1 and row['exact_events'][0]['at_utc'].startswith('2020-06-03T00:00:00')
    assert row['windows'][0]['start_utc'].startswith('2020-06-02T12:00:00')
    assert row['partner_contact_refs']
    assert len({c['id'] for c in scan['contacts']})==len(scan['contacts'])


@pytest.fixture(scope='module')
def real():
    args=dict(person_a=BIRTH,person_b=PARTNER,include_timing=True,timing=window_config())
    r=calculate_observation_data(**args)
    assert r['status']=='ok',r
    return args,r


def test_real_references_residuals_and_default_compatibility(real):
    args,r=real
    plain=calculate_observation_data(person_a=BIRTH,person_b=PARTNER)
    for k in ('contacts','counts','observation_paths','activation_clusters','house_overlays'):
        assert r[k]==plain[k]
    window=r['timing_observations']['window_scan']
    assert window['status']=='computed' and window['contacts']
    assert r['layer_availability']['timing_window']['status']=='computed'
    exact=[e for row in window['contacts'] for e in row['exact_events']]
    assert exact
    assert all(e['residual_degrees']<0.00002 for e in exact)
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if k.endswith('_ref'):assert lookup(r,v) is not None
                if k.endswith('_refs'):
                    for ref in v:assert lookup(r,ref) is not None
                walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(window)


def test_real_dense_mesh_agrees_on_events_and_intervals(real):
    args,r=real
    normal=r['timing_observations']['window_scan']
    dense=scan_timing_window(r,{'a':BIRTH,'b':PARTNER},_step=.125)
    assert [c['id'] for c in normal['contacts']]==[c['id'] for c in dense['contacts']]
    for a,b in zip(normal['contacts'],dense['contacts']):
        assert len(a['windows'])==len(b['windows'])
        assert len(a['exact_events'])==len(b['exact_events'])
        for x,y in zip(a['exact_events'],b['exact_events']):
            assert abs(x['jd_ut']-y['jd_ut'])<2*TIME_TOL
        for x,y in zip(a['windows'],b['windows']):
            assert abs(x['start_jd_ut']-y['start_jd_ut'])<2*TIME_TOL
            assert abs(x['end_jd_ut']-y['end_jd_ut'])<2*TIME_TOL


def test_checked_recomputation_rejects_window_tampering(real):
    import mcp_server
    from services.mcp_result_facts import checked_result,verify_calculation_claims_data
    args,r=real
    checked=checked_result('calculate_relationship_observation',r,args)
    assert checked['status']=='ok',checked
    v=verify_calculation_claims_data(checked['calculation_reference'],[
        dict(quote='window',path='/timing_observations/window_scan/status',value='computed'),
        dict(quote='No snapshot filter',path='/timing_observations/window_scan/policy/candidate_filter_from_snapshot',value=False)])
    assert v['counts']['supported']==2,v
    bad=deepcopy(r);bad['timing_observations']['window_scan']['contacts'][0]['windows'][0]['start_jd_ut']+=0.1
    assert checked_result('calculate_relationship_observation',bad,args)['status']=='validation_failed'


def test_out_of_birth_range_fails_and_window_is_opt_in(monkeypatch):
    import services.relationship_observation_windows as mod
    cfg=window_config(at='2000-01-01T12:00:00Z',window_start='1999-12-31T00:00:00Z',window_end='2000-01-02T00:00:00Z')
    assert calculate_observation_data(person_a=BIRTH,person_b=PARTNER,include_timing=True,timing=cfg)['status']=='invalid_input'
    monkeypatch.setattr(mod,'ChartFrames',lambda *a:pytest.fail('disabled interval must not build frames'))
    r=calculate_observation_data(person_a=BIRTH,person_b=PARTNER,include_timing=True,timing=config())
    assert r['timing_observations']['window_scan']['status']=='not_computed'
