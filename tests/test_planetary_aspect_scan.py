import asyncio
from collections import defaultdict
from datetime import datetime
import time

import pytest
from services.planetary_aspect_scan import scan

@pytest.mark.parametrize('a,b,start,end',[
 ('Pluto','Chiron','1960-01-01','2030-12-31'),
 ('Saturn','Uranus','2000-01-01','2040-12-31'),
 ('Jupiter','Saturn','1990-01-01','2030-12-31'),
 ('Mars','Saturn','2025-01-01','2026-12-31'),
 ('Moon','Saturn','2025-01-01','2025-12-31'),
])
def test_dense_mesh_agreement(a,b,start,end):
    result=scan(a,b,start,end)
    dense=scan(a,b,start,end,_step=0.03125 if a=='Moon' else 0.125)
    assert result['event_count']>0
    assert result['event_count']==dense['event_count']
    for x,y in zip(result['events'],dense['events']):
        assert x['aspect_degree']==y['aspect_degree']
        assert abs((datetime.fromisoformat(x['exact_datetime_utc'])-datetime.fromisoformat(y['exact_datetime_utc'])).total_seconds())<0.1
        assert abs(x['angular_difference']-x['aspect_degree'])<0.00002

def test_jupiter_saturn_2020():
    rows=scan('Jupiter','Saturn','2020-01-01','2020-12-31',[0])['events']
    assert len(rows)==1
    assert rows[0]['exact_datetime_utc'].startswith('2020-12-21T18:20:37')

def test_repeated_hits_and_summary():
    result=scan('Saturn','Uranus','2021-01-01','2021-12-31',[90])
    assert result['event_count']==3
    assert [r['hit_index'] for r in result['events']]==[1,2,3]
    assert len({r['cycle_group_id'] for r in result['events']})==1
    summary=scan('Saturn','Uranus','2021-01-01','2021-12-31',[90],output_precision='year_summary')
    assert summary['year_summary']==[{'year':2021,'aspects':[{'aspect_degree':90,'exact_count':3}]}]

def test_orb_windows_and_timezone():
    r=scan('Saturn','Uranus','2025-01-01','2040-12-31',[0,90,180],mode='orb_window',orb_deg=2,timezone_name='Asia/Shanghai')
    assert r['windows'] and r['events']
    assert sum(w['exact_count'] for w in r['windows'])==r['event_count']
    assert all(e['exact_datetime_local'].endswith('+08:00') for e in r['events'])
    for w in r['windows']:
        for field in ('enter_datetime_utc','exit_datetime_utc'):
            if w[field]:
                import swisseph as swe
                from services.transit_utils import body_position
                dt=datetime.fromisoformat(w[field]); jd=swe.julday(dt.year,dt.month,dt.day,dt.hour+dt.minute/60+dt.second/3600+dt.microsecond/3.6e9)
                x=body_position(swe.SATURN,jd)[0];y=body_position(swe.URANUS,jd)[0]
                assert abs(abs(abs((y-x+180)%360-180)-w['aspect_degree'])-2)<1e-5

def test_century():
    started=time.monotonic()
    r=scan('Pluto','Chiron','1960-01-01','2100-12-31')
    assert r['event_count']>20
    assert time.monotonic()-started<60

def test_station_double_root_and_tangent(monkeypatch):
    import services.planetary_aspect_scan as module
    import swisseph as swe
    base=swe.julday(2025,1,1,0)
    def fake(body,t):
        if body==swe.SUN:return 0.,0.
        u=t-base-0.1
        return (u*u-0.0004)%360,2*u
    monkeypatch.setattr(module.tu,'body_position',fake)
    r=scan('Sun','Mercury','2025-01-01','2025-01-01',[0])
    assert r['event_count']==2
    def tangent(body,t):
        if body==swe.SUN:return 0.,0.
        u=t-base-0.1
        return u*u,2*u
    monkeypatch.setattr(module.tu,'body_position',tangent)
    assert scan('Sun','Mercury','2025-01-01','2025-01-01',[0])['event_count']==1

@pytest.mark.parametrize('kwargs',[
 {'planet_b':'Sun'},{'aspects':[]},{'aspects':[float('nan')]},{'aspects':[181]},
 {'start_date':'1799-01-01'},{'orb_deg':0},{'timezone_name':'Bad/Zone'},
 {'planet_a':'north_node','planet_b':'south_node'},
])
def test_invalid(kwargs):
    args=dict(planet_a='Sun',planet_b='Moon',start_date='2025-01-01',end_date='2025-01-02')
    args.update(kwargs)
    with pytest.raises((ValueError,KeyError)):scan(**args)

def test_bodies():
    from services.planetary_aspect_scan import BODIES
    for body in BODIES:
        scan(body,'Saturn' if body!='saturn' else 'Sun','2025-01-01','2025-01-02')

def test_mcp_registration():
    import mcp_server
    r=asyncio.run(mcp_server.scan_planetary_aspects(planet_a='Jupiter',planet_b='Saturn',start_date='2020-01-01',end_date='2020-12-31',aspects=[0]))
    assert r['status']=='ok',r
    assert r['quality']['status']=='passed'
    caps=asyncio.run(mcp_server.get_capabilities())
    tool=next(t for t in caps['tools'] if t['name']=='scan_planetary_aspects')
    assert 'planet_a' in tool['input_schema']['properties']
