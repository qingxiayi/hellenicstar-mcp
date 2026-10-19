"""General geocentric apparent tropical longitude scan, using shared ephemeris IO.

Streaming monotonic segments: inspect relative-speed reversals before crossing
levels. This catches two roots around a station even with equal-sign endpoints.
Cycle IDs are query-local unwrapped directed-angle levels, not physical epochs.
"""
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import swisseph as swe
from services import transit_utils as tu

BODIES = {name: getattr(swe, name.upper()) for name in (
    'sun', 'moon', 'mercury', 'venus', 'mars', 'jupiter', 'saturn',
    'uranus', 'neptune', 'pluto', 'chiron', 'ceres', 'pallas', 'juno', 'vesta', 'pholus')}
BODIES.update(north_node=swe.MEAN_NODE, south_node=swe.MEAN_NODE,
              true_north_node=swe.TRUE_NODE, true_south_node=swe.TRUE_NODE,
              mean_apogee=swe.MEAN_APOG)
ALIASES = dict(zip(('太阳','月亮','水星','金星','火星','木星','土星','天王星','海王星','冥王星','凯龙星','北交点','南交点'),
                   ('sun','moon','mercury','venus','mars','jupiter','saturn','uranus','neptune','pluto','chiron','north_node','south_node')))
NAMES = {0:'合相',30:'半六合',45:'半刑',60:'六合',90:'刑',120:'拱',135:'补八分',150:'梅花',180:'冲'}
TIME_TOL = 0.05 / 86400
ANGLE_TOL = 1e-7


def canonical(name):
    key = ALIASES.get(name, name.strip().lower().replace(' ', '_').replace('-', '_'))
    if key not in BODIES:
        raise ValueError('Unsupported body: ' + name + '; supported: ' + ', '.join(BODIES))
    return key


def bisect(fn, lo, hi):
    a, b = fn(lo), fn(hi)
    if a == 0: return lo
    if b == 0: return hi
    if a * b > 0: raise ValueError('Root is not bracketed')
    while hi-lo > TIME_TOL:
        mid = (lo+hi)/2
        c = fn(mid)
        if c == 0: return mid
        if a*c <= 0: hi = mid
        else: lo, a = mid, c
    return (lo+hi)/2


def _stamp(jd, tz=None):
    dt = datetime(2000,1,1,12,tzinfo=timezone.utc) + timedelta(days=jd-2451545.0)
    return dt.astimezone(tz or timezone.utc).isoformat(timespec='milliseconds')


def scan(planet_a, planet_b, start_date, end_date, aspects=None, mode='exact',
         orb_deg=1.0, output_precision='exact_datetime', timezone_name=None, *, _step=None):
    a, b = canonical(planet_a), canonical(planet_b)
    if a == b or {a,b} in ({'north_node','south_node'}, {'true_north_node','true_south_node'}):
        raise ValueError('Identical bodies or opposite nodes have a constant separation, not discrete exact events')
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if start.isoformat()!=start_date or end.isoformat()!=end_date:
        raise ValueError('Dates must use YYYY-MM-DD')
    if start > end or start.year < 1800 or end.year > 2399 or (end-start).days > 200*366:
        raise ValueError('Require ordered dates within 1800–2399, at most 200 years per request')
    angles = [0,60,90,120,180] if aspects is None else aspects
    if not angles or len(angles)>32 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=180 for v in angles):
        raise ValueError('aspects must contain 1–32 finite angles in [0,180]')
    angles = sorted(set(float(v) for v in angles))
    if mode not in ('exact','orb_window') or output_precision not in ('exact_datetime','date','year_summary'):
        raise ValueError('Invalid mode or output_precision')
    if type(orb_deg) not in (int,float) or not math.isfinite(orb_deg) or not 0<orb_deg<30:
        raise ValueError('orb_deg must be finite and between 0 and 30 (exclusive)')
    tz = ZoneInfo(timezone_name) if timezone_name else None
    lo = swe.julday(start.year,start.month,start.day,0)
    stop = end+timedelta(days=1)
    hi = swe.julday(stop.year,stop.month,stop.day,0)
    @lru_cache(maxsize=4096)
    def pos(t):
        x, vx = tu.body_position(BODIES[a],t)
        y, vy = tu.body_position(BODIES[b],t)
        if a in ('south_node','true_south_node'): x=(x+180)%360
        if b in ('south_node','true_south_node'): y=(y+180)%360
        return x,y,vx,vy
    def raw(t):
        x,y,_,_=pos(t)
        return (y-x)%360
    def velocity(t):
        _,_,vx,vy=pos(t)
        return vy-vx
    # 3-hour Moon mesh; 12-hour mesh otherwise; midpoint halves these.
    # Relative-speed roots split stations before exact/orb levels are searched.
    step = _step or (0.125 if 'moon' in (a,b) else 0.5)
    targets = [(angle,direction) for angle in angles for direction in
               ((angle,) if angle in (0,180) else (angle,360-angle))]
    roots = defaultdict(list)
    boundaries = defaultdict(list)
    first = raw(lo)
    previous = first
    t = lo
    sample_count=0
    while t < hi:
        right=min(t+step,hi)
        mid=(t+right)/2
        points=[t,mid,right]
        for left,r in ((t,mid),(mid,right)):
            if velocity(left)*velocity(r)<0:
                points.append(bisect(velocity,left,r))
        points=sorted(set(points))
        for left,r in zip(points,points[1:]):
            r0=raw(left)
            u0=previous
            u1=u0+(raw(r)-r0+180)%360-180
            low,high=sorted((u0,u1))
            def unwrapped(q): return u0+(raw(q)-r0+180)%360-180
            for angle,direction in targets:
                offsets=(0,) if mode=='exact' else (-orb_deg,0,orb_deg)
                for offset in offsets:
                    k0=math.ceil((low-direction-offset-ANGLE_TOL)/360)
                    k1=math.floor((high-direction-offset+ANGLE_TOL)/360)
                    for k in range(k0,k1+1):
                        level=direction+360*k+offset
                        f0,f1=u0-level,u1-level
                        if f0*f1<=0:
                            root=bisect(lambda q:unwrapped(q)-level,left,r)
                        elif abs(f0)<=ANGLE_TOL: root=left
                        elif abs(f1)<=ANGLE_TOL: root=r
                        else: continue
                        if root>=hi: continue
                        key=(angle,direction,k)
                        bucket=roots[key] if offset==0 else boundaries[angle]
                        if offset==0:
                            if not bucket or abs(root-bucket[-1])>TIME_TOL*2: bucket.append(root)
                        else: bucket.append(root)
            previous=u1
            sample_count+=1
        t=right
    events=[]
    for (angle,direction,k),times in roots.items():
        for index,exact in enumerate(times,1):
            x,y,vx,vy=pos(exact)
            event=dict(planet_a=a,planet_b=b,aspect_degree=angle,aspect_name=NAMES.get(angle,str(angle)+'°'),
                       exact_datetime_utc=_stamp(exact),longitude_a=x,longitude_b=y,
                       angular_difference=abs((y-x+180)%360-180),applying_or_separating='exact',
                       hit_index=index,cycle_group_id=f'{a}:{b}:{direction:g}:{k}',
                       retrograde_a=vx<0,retrograde_b=vy<0)
            if tz: event['exact_datetime_local']=_stamp(exact,tz)
            events.append((exact,event))
    events.sort(key=lambda row:(row[0],row[1]['aspect_degree']))
    windows=[]
    if mode=='orb_window':
        for angle in angles:
            cuts=[lo]+sorted(set(boundaries[angle]))+[hi]
            active=None
            for left,r in zip(cuts,cuts[1:]):
                if r-left<TIME_TOL: continue
                x,y,_,_=pos((left+r)/2)
                inside=abs(abs((y-x+180)%360-180)-angle)<=orb_deg
                if inside:
                    if active is None: active=[left,r]
                    else: active[1]=r
                elif active is not None:
                    windows.append((angle,*active)); active=None
            if active is not None: windows.append((angle,*active))
    def display(event):
        event=dict(event)
        if output_precision=='date':
            event['exact_date_utc']=event.pop('exact_datetime_utc')[:10]
            if tz: event['exact_date_local']=event.pop('exact_datetime_local')[:10]
        return event
    output=dict(status='ok',planet_a=a,planet_b=b,event_count=len(events),events=[],windows=[],year_summary=[],
                settings=dict(start_date=start_date,end_date=end_date,range_convention='UTC inclusive dates; end next midnight exclusive',
                              aspects=angles,mode=mode,orb_deg=orb_deg,output_precision=output_precision,timezone=timezone_name,
                              zodiac='tropical',center='geocentric',position='apparent',nodes='mean unless explicitly true',
                              solver_time_tolerance_seconds=0.05,cycle_group_scope='query-local directed unwrapped target; hit_index starts within query',
                              scan_step_days=step,segments=sample_count))
    if output_precision=='year_summary':
        summary=defaultdict(lambda:defaultdict(int))
        for _,event in events:
            stamp=event.get('exact_datetime_local',event['exact_datetime_utc'])
            summary[int(stamp[:4])][event['aspect_degree']]+=1
        output['year_summary']=[dict(year=year,aspects=[dict(aspect_degree=angle,exact_count=count) for angle,count in sorted(counts.items())]) for year,counts in sorted(summary.items())]
    else: output['events']=[display(event) for _,event in events]
    for angle,left,r in sorted(windows,key=lambda row:row[1]):
        window=dict(aspect_degree=angle,enter_datetime_utc=None if left==lo else _stamp(left),
                    exit_datetime_utc=None if r==hi else _stamp(r),start_truncated=left==lo,end_truncated=r==hi,
                    clipped_start_utc=_stamp(left),clipped_end_utc=_stamp(r),
                    exact_count=sum(left<=t<=r and e['aspect_degree']==angle for t,e in events))
        if tz:
            window.update(enter_datetime_local=None if left==lo else _stamp(left,tz),exit_datetime_local=None if r==hi else _stamp(r,tz))
        if output_precision=='date':
            window={key.replace('_datetime_','_date_'):value[:10] if isinstance(value,str) and ('datetime' in key or key.startswith('clipped_')) else value for key,value in window.items()}
        output['windows'].append(window)
    return output
