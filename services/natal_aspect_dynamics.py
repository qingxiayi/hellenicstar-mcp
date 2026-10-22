"""Bounded motion facts for natal aspect pairs; not a reception efficacy model."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import math

import swisseph as swe
from services.planetary_aspect_scan import BODIES, bisect, TIME_TOL, _stamp
from services.transit_utils import body_position
from services.ephemeris_guard import EphemerisModeError

ANGLE_TOL = 1e-6
SPEED_TOL = 1e-8
STEP = 0.125  # midpoint sampling gives 90-minute segments


def residual(a, b, target):
    return (b-a-target+180) % 360-180


def phase_at(a, b, va, vb, angle):
    targets = (angle,) if angle in (0,180) else (angle,360-angle)
    target = min(targets, key=lambda t: abs(residual(a,b,t)))
    error = residual(a,b,target)
    speed = vb-va
    status = ('exact' if abs(error) <= ANGLE_TOL else
              'relative_stationary' if abs(speed) <= SPEED_TOL else
              'applying' if error*speed < 0 else 'separating')
    return dict(status=status, directed_target=target, signed_error=error,
                relative_speed_deg_per_day=speed, speed_a=va, speed_b=vb)


def trace_pair(a, b, angle, start, days, position, step=STEP):
    """Follow the natal directed branch to its first exact hit, or bounded end.

    Split at relative-speed roots before seeking exact hits: a reversal can
    produce two roots even when both coarse endpoint errors have the same sign.
    Body stations and sign ingresses are facts, not automatic vetoes.
    """
    x,vx = position(a,start); y,vy = position(b,start)
    phase = phase_at(x,y,vx,vy,angle)
    target = phase['directed_target']
    error = lambda t: residual(position(a,t)[0],position(b,t)[0],target)
    velocity = lambda t: position(b,t)[1]-position(a,t)[1]
    events = []
    hit = start if phase['status']=='exact' else None
    end = start+days
    left = start

    def event(kind, time, **detail):
        if time <= start+TIME_TOL: return
        if not any(e['kind']==kind and e.get('body')==detail.get('body') and
                   abs(e['jd_ut']-time)<TIME_TOL*2 for e in events):
            events.append(dict(kind=kind,jd_ut=time,datetime_utc=_stamp(time),**detail))

    while left < end and hit is None:
        right = min(left+step,end)
        mid = (left+right)/2
        points = [left,mid,right]
        for lo,hi in ((left,mid),(mid,right)):
            v0,v1 = velocity(lo),velocity(hi)
            if v0*v1 < 0:
                root = bisect(velocity,lo,hi)
                points.append(root); event('relative_station',root)
            elif abs(v0) <= SPEED_TOL and velocity(lo-1e-5)*velocity(lo+1e-5)<0:
                event('relative_station',lo)
            for body in (a,b):
                l0,s0 = position(body,lo); l1,s1 = position(body,hi)
                cuts = [lo,hi]
                if s0*s1 < 0:
                    root = bisect(lambda t:position(body,t)[1],lo,hi)
                    cuts.append(root)
                    event('body_station',root,body=body,
                          direction_after='direct' if s1>0 else 'retrograde')
                elif abs(s0)<=SPEED_TOL and position(body,lo-1e-5)[1]*position(body,lo+1e-5)[1]<0:
                    event('body_station',lo,body=body,
                          direction_after='direct' if position(body,lo+1e-5)[1]>0 else 'retrograde')
                # Segment sign change may straddle 360 degrees; unwrap locally.
                cuts = sorted(cuts)
                for cl,ch in zip(cuts,cuts[1:]):
                    l0 = position(body,cl)[0]; l1 = position(body,ch)[0]
                    u1 = l0+(l1-l0+180)%360-180
                    if abs(u1-l0)<1e-12: continue
                    low,high = sorted((l0,u1))
                    for n in range(math.ceil(low/30), math.floor(high/30)+1):
                        boundary = n*30
                        fn = lambda t: l0+(position(body,t)[0]-l0+180)%360-180-boundary
                        if fn(cl)*fn(ch) <= 0:
                            root = bisect(fn,cl,ch)
                            # Touching a cusp at a station is not a sign change.
                            if int(position(body,root-1e-5)[0]//30)==int(position(body,root+1e-5)[0]//30): continue
                            event('sign_ingress',root,body=body,
                                  sign_after=(n if u1>l0 else n-1)%12)
        points = sorted(set(points))
        roots = []
        for lo,hi in zip(points,points[1:]):
            e0,e1 = error(lo),error(hi)
            if abs(e0)<=ANGLE_TOL: roots.append(lo)
            if abs(e1)<=ANGLE_TOL: roots.append(hi)
            # A wrap discontinuity is not an exact aspect.
            if e0*e1 < 0 and abs(e1-e0)<180:
                roots.append(bisect(error,lo,hi))
        if roots: hit = min(roots)
        left = right
    before = sorted((e for e in events if hit is None or e['jd_ut']<hit-TIME_TOL),
                    key=lambda e:(e['jd_ut'],e['kind'],e.get('body','')))
    reversals = [e for e in before if e['kind']=='relative_station']
    ingresses = [e for e in before if e['kind']=='sign_ingress']
    return dict(phase=phase, search=dict(status='exact_at_epoch' if hit==start else
        'exact_found' if hit is not None else 'not_found_in_window',
        horizon_days=days, start_utc=_stamp(start), end_utc=_stamp(end),
        first_exact_utc=_stamp(hit) if hit is not None else None,
        first_exact_jd_ut=hit, exact_residual_deg=error(hit) if hit is not None else None,
        events_before_exact_or_end=before,
        relative_station_before_exact=bool(reversals) if hit is not None else None,
        sign_change_before_exact=bool(ingresses) if hit is not None else None,
        current_application=('not_applying_at_epoch' if phase['status']!='applying' else
            'relative_reversal_before_exact' if reversals else
            'reached_exact' if hit is not None else 'unresolved_within_window')))


@lru_cache(maxsize=16)
def _compute(start, days, edges):
    @lru_cache(maxsize=20000)
    def position(body,t): return body_position(BODIES[body],t)
    rows = []
    for identity,a,b,angle in edges:
        phase = dict(status='unknown',reason='ephemeris_file_coverage_unavailable')
        try:
            x,vx=position(a,start); y,vy=position(b,start)
            phase=phase_at(x,y,vx,vy,angle)
            trace=trace_pair(a,b,angle,start,days,position)
            status='available'
        except (EphemerisModeError, swe.Error):
            # Preserve static graph and any verified epoch phase; do not silently
            # switch ephemerides or mistake incomplete searching for no hit.
            trace=dict(phase=phase,search=dict(status='unavailable',
                reason='ephemeris_file_coverage_unavailable',horizon_days=days,
                first_exact_utc=None,first_exact_jd_ut=None))
            status='partial' if phase['status']!='unknown' else 'unavailable'
        rows.append(dict(aspect_id=identity,planet_a=a,planet_b=b,angle=angle,status=status,**trace))
    return rows


def calculate_dynamics(graph, days=30, orb_view=8):
    import copy
    context = graph['birth_context']
    civil = datetime.fromisoformat(context['civil_dt'])
    utc = (civil-timedelta(hours=context['utc_offset'])).replace(tzinfo=timezone.utc)
    jd = swe.julday(utc.year,utc.month,utc.day,utc.hour+utc.minute/60+utc.second/3600)
    edges = tuple(sorted((e['id'],e['from'],e['to'],e['angle']) for e in graph['aspects'][str(orb_view)]['edges']))
    # Never mutate cached results through output references.
    rows = copy.deepcopy(_compute(jd,days,edges))
    status='available' if all(r['status']=='available' for r in rows) else 'unavailable' if all(r['status']=='unavailable' for r in rows) else 'partial'
    return dict(version='natal-aspect-dynamics-v1',status=status,epoch_utc=utc.isoformat(),rows=rows,
        method=dict(horizon_days=days,orb_view=orb_view,scan_step_days=STEP,
            midpoint_segments=True,root_time_tolerance_seconds=TIME_TOL*86400,
            exact_angle_tolerance_deg=ANGLE_TOL,relative_speed_tolerance=SPEED_TOL,
            ephemeris='Swiss Ephemeris file mode, apparent geocentric tropical longitude and speed',
            branch='nearest natal directed aspect branch, first hit in inclusive bounded window',
            time_basis='existing birth UTC offset to Julian UT convention',
            limitation='No third-body prohibition, transfer of light, or efficacy verdict. No hit in window is not impossibility.',
            source_refs=['/source_graph/birth_context','/source_graph/aspects/'+str(orb_view)]))
