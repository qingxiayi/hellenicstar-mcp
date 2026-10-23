"""Bounded numerical interval association over existing chart sources.

No new ephemeris, event interpretation or modification of legacy transit tools.
Roots use the existing scanner's bisection tolerances; moving charts are supplied
by the relationship timing adapter. Mesh and interval limits are engineering.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from itertools import product
import math

from services.planetary_aspect_scan import bisect, TIME_TOL, ANGLE_TOL, _stamp

MAX_WINDOW_DAYS = 31
STEP_DAYS = 0.25
DERIVATIVE_DAYS = 0.001


def window_settings(value, anchor):
    keys = {'window_start', 'window_end'} & value.keys()
    if not keys:
        return None
    if len(keys) != 2:
        raise ValueError('timing.window_start and window_end must be supplied together')
    from services.relationship_observation_timing import parse_instant
    start, end = (parse_instant(value[k], 'timing.'+k) for k in ('window_start', 'window_end'))
    days = (end-start).total_seconds()/86400
    if not 1/86400 <= days <= MAX_WINDOW_DAYS:
        raise ValueError(f'Timing window must span at least one second and at most {MAX_WINDOW_DAYS} days')
    if not start <= anchor < end:
        raise ValueError('Timing snapshot must fall within [window_start, window_end)')
    return dict(start=start.isoformat(), end=end.isoformat(), convention='start_inclusive_end_exclusive',
                max_days=MAX_WINDOW_DAYS, mesh_days=STEP_DAYS,
                mesh_midpoints_checked=True, relative_speed_station_split=True,
                numerical_time_tolerance_seconds=TIME_TOL*86400,
                angular_tolerance_degrees=ANGLE_TOL, provenance='ENGINE_DERIVED')


def _unique(times):
    result = []
    for t in sorted(times):
        if not result or t-result[-1] > TIME_TOL*2:
            result.append(t)
    return result


def _merge(intervals):
    result = []
    for lo, hi in sorted(intervals):
        if result and lo <= result[-1][1]+TIME_TOL:
            result[-1][1] = max(hi, result[-1][1])
        else:
            result.append([lo, hi])
    return result


def scan_curve(raw, velocity, lo, hi, thresholds, step=STEP_DAYS):
    """Unwrapped relative longitude, monotonic segments, exact/boundary roots.

Public for deterministic analytic tests. Returns numeric intervals; this is a
finite numerical search, not a proof for arbitrary oscillatory input functions.
"""
    exact = {angle: [] for angle in thresholds}
    boundaries = {angle: [] for angle in thresholds}
    flats = {angle: [] for angle in thresholds}
    t, previous = lo, raw(lo)
    while t < hi:
        right = min(t+step, hi)
        mid = (t+right)/2
        cuts = [t, mid, right]
        for left, end in ((t, mid), (mid, right)):
            if velocity(left)*velocity(end) < 0:
                cuts.append(bisect(velocity, left, end))
        cuts = sorted(set(cuts))
        for left, end in zip(cuts, cuts[1:]):
            origin = raw(left)
            u0 = previous
            u1 = u0 + (raw(end)-origin+180) % 360-180
            low, high = sorted((u0, u1))
            def unwrapped(q):
                return u0 + (raw(q)-origin+180) % 360-180
            for angle, orb in thresholds.items():
                directions = (angle,) if angle in (0, 180) else (angle, 360-angle)
                for direction in directions:
                    for offset in ((0,) if orb == 0 else (-orb, 0, orb)):
                        k0 = math.ceil((low-direction-offset-ANGLE_TOL)/360)
                        k1 = math.floor((high-direction-offset+ANGLE_TOL)/360)
                        for k in range(k0, k1+1):
                            level = direction+offset+360*k
                            f0, f1 = u0-level, u1-level
                            if (abs(f0) < 1e-12 and abs(f1) < 1e-12
                                    and abs(velocity(left)) < 1e-12 and abs(velocity(end)) < 1e-12):
                                if offset == 0:
                                    flats[angle].append((left, end))
                                continue
                            if f0*f1 <= 0:
                                root = bisect(lambda q: unwrapped(q)-level, left, end)
                            elif abs(f0) <= ANGLE_TOL:
                                root = left
                            elif abs(f1) <= ANGLE_TOL:
                                root = end
                            else:
                                continue
                            # Normalize domain endpoints within numerical tolerance;
                            # adjacent windows must not both own an exact end hit.
                            if abs(root-hi) <= TIME_TOL and abs(unwrapped(hi)-level) <= ANGLE_TOL:
                                root = hi
                            if abs(root-lo) <= TIME_TOL and abs(unwrapped(lo)-level) <= ANGLE_TOL:
                                root = lo
                            if lo <= root < hi:
                                (exact if offset == 0 else boundaries)[angle].append(root)
            previous = u1
        t = right
    result = {}
    for angle, orb in thresholds.items():
        flat = _merge(flats[angle])
        roots = [t for t in _unique(exact[angle]) if not any(a-TIME_TOL <= t <= b+TIME_TOL for a, b in flat)]
        bounds = _unique(boundaries[angle])
        intervals = []
        if orb > 0:
            cuts = _unique([lo, *bounds, hi])
            for left, end in zip(cuts, cuts[1:]):
                separation = abs((raw((left+end)/2)+180) % 360-180)
                if abs(separation-angle) <= orb:
                    intervals.append((left, end))
            intervals = _merge(intervals)
        if roots or intervals or flat or bounds:
            result[angle] = dict(exact=roots, windows=intervals, constant_exact=flat, boundaries=bounds)
    return result


class ChartFrames:
    """Per-request caches; stable mesh frames are not evicted by root refinement."""
    def __init__(self, observation, births, lo, hi):
        self.observation, self.births, self.lo, self.hi = observation, births, lo, hi
        self.mesh = {}
        self.load = lru_cache(maxsize=512)(self._load)
        for i in range(math.ceil((hi-lo)/(STEP_DAYS/2))+1):
            t = min(lo+i*STEP_DAYS/2, hi)
            self.mesh[t] = self._state(t)

    def _load(self, jd):
        from services.relationship_observation_timing import calculate_timing_sources
        settings = deepcopy(self.observation['settings'])
        dt = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)+timedelta(days=jd-2451545)
        settings['timing']['at'] = dt.isoformat(timespec='microseconds')
        src = calculate_timing_sources(self.births, self.observation['birth_context'], settings)
        frame = {'transit': src['transit']['points']}
        for who in ('a', 'b'):
            frame[who+'_natal'] = self.observation['source_geometry'][who]['points']
            frame[who+'_progressed'] = src['progressed'][who]['points']
        return frame

    def _state(self, t):
        lo, hi = max(self.lo, t-DERIVATIVE_DAYS), min(self.hi, t+DERIVATIVE_DAYS)
        now, before, after = self.load(t), self.load(lo), self.load(hi)
        return {chart: {point: (lon, (after[chart][point]-before[chart][point]+180) % 360-180)
                        for point, lon in values.items()} for chart, values in now.items()}, hi-lo

    def state(self, t):
        return self.mesh[t] if t in self.mesh else self._state(t)

    def raw(self, left, p, right, q, t):
        if t in self.mesh:
            f, _ = self.mesh[t]
            return (f[right][q][0]-f[left][p][0]) % 360
        f = self.load(t)
        return (f[right][q]-f[left][p]) % 360

    def velocity(self, left, p, right, q, t):
        f, dt = self.state(t)
        return (f[right][q][1]-f[left][p][1])/dt


def _thresholds(orbs, p, q):
    from services.relationship_observation import OPPOSITES, ASPECT_NAMES
    return {angle: max(orbs[str(a)] for a in {angle, 180-angle}
                       if str(a) in orbs and (a == angle or p in OPPOSITES or q in OPPOSITES))
            for angle in ASPECT_NAMES if any(str(a) in orbs and (a == angle or p in OPPOSITES or q in OPPOSITES)
                                            for a in {angle, 180-angle})}


def scan_timing_window(observation, births, _step=STEP_DAYS):
    from services.civil_time_resolver import _julian_day_ut
    from services.relationship_observation import CANONICAL, OPPOSITES, ASPECT_NAMES, adjacent
    from services.relationship_observation_timing import timing_pairs
    cfg = observation['settings']['timing']
    if cfg is None or cfg['window'] is None:
        return dict(status='not_computed', reason='not_requested')
    win = cfg['window']
    lo, hi = (_julian_day_ut(datetime.fromisoformat(win[k])) for k in ('start', 'end'))
    frames = ChartFrames(observation, births, lo, hi)
    rows = []
    for left, right, orb_key in timing_pairs(cfg):
        first_points = tuple(p for p in CANONICAL if not (left == 'transit' and
            (p in ('ascendant', 'midheaven') or p in cfg['excluded_transit_points'])))
        for p, q in product(first_points, CANONICAL):
            thresholds = _thresholds(cfg[orb_key], p, q)
            raw = lambda t: frames.raw(left, p, right, q, t)
            vel = lambda t: frames.velocity(left, p, right, q, t)
            found = scan_curve(raw, vel, lo, hi, thresholds, _step)
            for angle, scan in found.items():
                variants = []
                for a, b in product((p, OPPOSITES[p]) if p in OPPOSITES else (p,),
                                    (q, OPPOSITES[q]) if q in OPPOSITES else (q,)):
                    equivalent = 180-angle if (a != p) != (b != q) else angle
                    variants.append(dict(first_point=a, second_point=b, angle=equivalent))
                def end_meta(chart, point):
                    kind = 'transit' if chart == 'transit' else chart.split('_')[1]
                    who = None if kind == 'transit' else chart[0]
                    return dict(chart=chart, kind=kind, person=who, point=point)
                exact = [dict(at_utc=_stamp(t), jd_ut=t,
                              residual_degrees=abs(abs((raw(t)+180) % 360-180)-angle)) for t in scan['exact']]
                windows = [dict(start_utc=_stamp(a), end_utc=_stamp(b), start_jd_ut=a, end_jd_ut=b,
                    start_clipped=a==lo, end_clipped=b==hi,
                    exact_event_indices=[i for i, t in enumerate(scan['exact']) if a-TIME_TOL <= t <= b+TIME_TOL])
                    for a, b in scan['windows']]
                row = dict(id=f'{left}:{p}|{right}:{q}|{angle}', first=end_meta(left, p), second=end_meta(right, q),
                    angle=angle, aspect=ASPECT_NAMES[angle], orb_limit=thresholds[angle],
                    orb_settings_ref='/settings/timing/'+orb_key, endpoint_variants=variants,
                    exact_events=exact, windows=windows,
                    constant_exact_intervals=[dict(start_utc=_stamp(a), end_utc=_stamp(b)) for a, b in scan['constant_exact']],
                    threshold_touch_times_utc=[_stamp(t) for t in scan['boundaries']],
                    rule_id='timing_window', natal_context_refs=[], partner_contact_refs=[],
                    core_complex_refs=[], context_complex_refs=[])
                if right.endswith('_natal'):
                    who = right[0]
                    prof = observation['relationship_profiles'][who]
                    ids = {e['id'] for e in adjacent(prof['natal_aspects'], q)}
                    row['natal_point_ref'] = f'/relationship_profiles/{who}/points/{q}'
                    row['natal_context_refs'] = [f'/relationship_profiles/{who}/natal_aspects/{i}'
                        for i, e in enumerate(prof['natal_aspects']) if e['id'] in ids]
                    side = 'first' if who == 'a' else 'second'
                    row['partner_contact_refs'] = ['/contacts/'+str(i) for i, c in enumerate(observation['contacts']) if c[side+'_point']==q]
                    for i, comp in enumerate(observation['observation_complexes']['people'][who]):
                        key = 'core_complex_refs' if q in comp['core_members'] else 'context_complex_refs'
                        if q in comp['members']:
                            row[key].append(f'/observation_complexes/people/{who}/{i}')
                rows.append(row)
    rows.sort(key=lambda r: r['id'])
    return dict(status='computed', contacts=rows, synastry_endpoint_overlaps=endpoint_overlaps(observation, rows),
        counts=dict(contact_series=len(rows), exact_events=sum(len(r['exact_events']) for r in rows),
                    orb_windows=sum(len(r['windows']) for r in rows)),
        policy=dict(rule_id='timing_window', scope='same_chart_pairs_as_requested_snapshot',
            all_point_pairs_considered=True, candidate_filter_from_snapshot=False,
            start_utc=win['start'], end_utc=win['end'], interval='[start,end)',
            mesh_days=_step, midpoint_and_relative_station_checks=True,
            time_tolerance_seconds=TIME_TOL*86400, angular_tolerance_degrees=ANGLE_TOL,
            derivative_days=DERIVATIVE_DAYS, numerical_search_not_formal_interval_proof=True,
            counts_are_additive=False, changes_static_contacts=False, whole_complex_activation_inferred=False,
            excluded_transit_points=cfg['excluded_transit_points'], predictions_generated=False,
            clipped_boundaries_are_not_actual_entry_or_exit=True))


def endpoint_overlaps(observation, rows):
    """Intersect actual windows of the SAME transit at both synastry endpoints."""
    by_point = {}
    for i, row in enumerate(rows):
        if row['first']['kind']=='transit' and row['second']['kind']=='natal':
            by_point.setdefault((row['second']['person'], row['second']['point']), []).append((i, row))
    result = []
    for i, contact in enumerate(observation['contacts']):
        a = by_point.get(('a', contact['first_point']), [])
        b = by_point.get(('b', contact['second_point']), [])
        overlaps = []
        for ai, ar in a:
            for bi, br in b:
                if ar['first']['point'] != br['first']['point']:
                    continue
                for aw in ar['windows']:
                    for bw in br['windows']:
                        lo = max(aw['start_jd_ut'], bw['start_jd_ut'])
                        hi = min(aw['end_jd_ut'], bw['end_jd_ut'])
                        if hi-lo > TIME_TOL:
                            overlaps.append(dict(transit_point=ar['first']['point'], start_utc=_stamp(lo), end_utc=_stamp(hi),
                                a_timing_contact_ref=f'/timing_observations/window_scan/contacts/{ai}',
                                b_timing_contact_ref=f'/timing_observations/window_scan/contacts/{bi}'))
        if overlaps:
            result.append(dict(contact_ref='/contacts/'+str(i), same_transit_overlaps=overlaps,
                               counts_are_additive=False))
    return result


def attach_window(observation, births):
    result = scan_timing_window(observation, births)
    observation['timing_observations']['window_scan'] = result
    observation['layer_availability']['timing_window'] = dict(status=result['status'],
        scope='explicit_bounded_numerical_search_only', reason='requested_window' if result['status']=='computed' else 'not_requested')
    if result['status']=='computed':
        view = observation['timing_observations']
        view['availability']['exact_pass_search'] = 'computed_for_requested_window'
        view['availability']['interval_presence_absence'] = 'numerically_searched_requested_window_only'
    return observation
