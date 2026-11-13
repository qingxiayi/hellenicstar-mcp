"""Orb intervals for a moving longitude against fixed natal points.

Station knots split the sampling grid before solving boundary crossings, so an
orb visit that turns around without ever reaching exactitude is still included.
Search bounds are explicit: unknown entry/exit times are never invented.
"""
from __future__ import annotations

from functools import lru_cache

from services import transit_utils
from services.secondary_progressions import PLANET_DEFS, PROG_TO_NATAL_ORBS
from services.solar_arc_engine import TROPICAL_YEAR_DAYS, MAX_SUPPORTED_AGE
from services.transit_natal import ORBS, _group_for

WINDOW_TOLERANCE_DAYS = 1 / 1440
TRANSIT_PADDING_DAYS = 400
SECONDARY_PADDING_DAYS = 3 * TROPICAL_YEAR_DAYS


def _signed(lon, target):
    return (lon - target + 180) % 360 - 180


def _bisect(fn, left, right):
    fl = fn(left)
    if fl == 0:
        return left
    if fn(right) == 0:
        return right
    while right - left > WINDOW_TOLERANCE_DAYS / 8:
        mid = (left + right) / 2
        fm = fn(mid)
        if fm == 0:
            return mid
        if fl * fm <= 0:
            right = mid
        else:
            left, fl = mid, fm
    return (left + right) / 2


def motion_grid(position, lo, hi, step):
    """Sample in civil JD; position returns longitude and civil-day speed."""
    times = [lo]
    while times[-1] < hi:
        times.append(min(times[-1] + step, hi))
    stations = []
    for a, b in zip(times, times[1:]):
        sa, sb = position(a)[1], position(b)[1]
        if sa * sb < 0:
            stations.append(_bisect(lambda jd: position(jd)[1], a, b))
    times = sorted(set(times + stations))
    return times, [position(t)[0] for t in times]


def orb_intervals(position, times, longitudes, target, orb):
    """Connected positive-duration visits inside one directed aspect band.

    All grid steps are short enough to have <180 degrees motion. A tangency
    from outside touching only the boundary is not a positive-duration visit.
    """
    # Retain turning points even for a boundary tangency without a sign change.
    cuts = [times[0], times[-1]]
    for i in range(1, len(times) - 1):
        if _signed(longitudes[i], longitudes[i - 1]) * _signed(longitudes[i + 1], longitudes[i]) <= 0:
            cuts.append(times[i])
    for boundary in ((target - orb) % 360, (target + orb) % 360):
        for i, (a, b) in enumerate(zip(times, times[1:])):
            fa, fb = _signed(longitudes[i], boundary), _signed(longitudes[i + 1], boundary)
            if fa == 0:
                cuts.append(a)
            if fb == 0:
                cuts.append(b)
            if fa * fb < 0 and abs(fa - fb) < 180:
                cuts.append(_bisect(lambda jd: _signed(position(jd)[0], boundary), a, b))
    cuts = sorted(set(cuts))
    intervals = []
    for a, b in zip(cuts, cuts[1:]):
        if abs(_signed(position((a + b) / 2)[0], target)) <= orb:
            if intervals and intervals[-1][1] == a:
                intervals[-1] = (intervals[-1][0], b)
            else:
                intervals.append((a, b))
    return intervals


def compute_aspect_windows(snapshot, lo, hi, events, transit_planets, utc_text):
    """Return clipped intervals plus actual entry/exit when found in search."""
    bodies = dict(PLANET_DEFS)
    targets = {key: point.longitude for key, point in snapshot.planets.items() if key in bodies}
    targets.update(snapshot.axes)
    birth_jd = snapshot.birth_jd_ut
    rows = []
    hits = {}
    for event in events:
        source = event['source']
        if event['nature'] in ('axis_contact', 'exact_aspect'):
            key = (event['technique'], source['planet'], source['target'], source['angle'])
            hits.setdefault(key, []).append(event)

    for technique, planets in (('transits', transit_planets), ('secondary_progressions', tuple(bodies))):
        progressed = technique == 'secondary_progressions'
        padding = SECONDARY_PADDING_DAYS if progressed else TRANSIT_PADDING_DAYS
        search_lo = max(birth_jd, lo - padding)
        search_hi = min(birth_jd + MAX_SUPPORTED_AGE * TROPICAL_YEAR_DAYS, hi + padding)
        for planet in planets:
            body = bodies[planet]

            @lru_cache(maxsize=None)
            def position(jd):
                ephe_jd = birth_jd + (jd - birth_jd) / TROPICAL_YEAR_DAYS if progressed else jd
                lon, speed = transit_utils.body_position(body, ephe_jd)
                return lon, speed / TROPICAL_YEAR_DAYS if progressed else speed

            step = 7 if progressed and planet != 'moon' else 1
            times, lons = motion_grid(position, search_lo, search_hi, step)
            for target, longitude in targets.items():
                axis = target in snapshot.axes
                angles = (0, 90, 180) if progressed else ((0,) if axis else (0, 60, 90, 120, 180))
                for angle in angles:
                    orb = PROG_TO_NATAL_ORBS[angle] if progressed else ORBS[_group_for(planet)]['axis' if axis else angle]
                    for directed in ((angle, 360 - angle) if angle not in (0, 180) else (angle,)):
                        # Transit engine defines directed_angle as natal minus moving.
                        center = (longitude - directed) % 360
                        for a, b in orb_intervals(position, times, lons, center, orb):
                            if b <= lo or a >= hi:
                                continue
                            start, end = max(a, lo), min(b, hi)
                            entry = None if a == search_lo else utc_text(a)
                            exit_at = None if b == search_hi else utc_text(b)
                            included_hits = [e for e in hits.get((technique, planet, target, angle), [])
                                             if utc_text(start) <= e['exact_utc'] < utc_text(end)]
                            rows.append({
                                'technique': technique, 'planet': planet, 'target': target,
                                'focus': f"{'axis' if axis else 'planet'}:{target}",
                                'angle': angle, 'directed_angle': directed, 'orb_limit': orb,
                                'start_utc': utc_text(start), 'end_utc': utc_text(end),
                                'orb_entry_utc': entry, 'orb_exit_utc': exit_at,
                                'entry_status': 'found' if entry else ('birth_limit' if search_lo == birth_jd else 'search_limit'),
                                'exit_status': 'found' if exit_at else 'search_limit',
                                'continues_before_query': a < lo,
                                'continues_after_query': b > hi,
                                'exact_event_indices': [e['index'] for e in included_hits],
                            })
    rows.sort(key=lambda r: (r['start_utc'], r['technique'], r['planet'], r['target'], r['directed_angle']))
    return rows
