"""Bounded, factual reading views over existing timeline and natal results.

No ephemeris calls, importance weights, psychological themes or recursive natal
activation. Raw events and windows remain untouched. All references are local to
one complete response; projected/summary arrays must not be reindexed.
"""
from collections import defaultdict
from datetime import datetime

from services.natal_house_rulers import TRADITIONAL_RULERS, MODERN_RULERS, PLANET_ZH
from services.natal_structure_graph import DEFAULT_ASPECT_VIEW

VERSION = 'timeline-reading-1'
AXIS_PAIRS = {'asc': ('asc_dsc', 0), 'dsc': ('asc_dsc', 180),
              'mc': ('mc_ic', 0), 'ic': ('mc_ic', 180)}
AXIS_MEMBERS = {'asc_dsc': ['asc', 'dsc'], 'mc_ic': ['mc', 'ic']}


def policy():
    return dict(version=VERSION, provenance='project_defined_not_Forrest_algorithm',
                interval_semantics='start_inclusive_end_exclusive',
                natal_aspect_scope='existing_calculator_major_aspects_ten_planets',
                natal_aspect_orb_limit=DEFAULT_ASPECT_VIEW, natal_context_depth=1,
                house_systems=['placidus', 'whole_sign'],
                ruler_policies=['traditional', 'modern_replacement'],
                axis_equivalence='opposite_endpoints_same_moving_body_technique_geometry',
                exact_axis_group_tolerance_seconds=60,
                overlap_means='simultaneous_orb_membership_not_shared_psychological_theme',
                layering='reading_order_not_importance_ranking',
                precise_contacts='timing_markers_not_proven_event_triggers',
                fast_transits_included=False, recursive_activation=False,
                unique_life_theme_selected=False,
                raw_v3_resonances='retained_separate_not_axis_deduplicated')


def natal_context(natal):
    """Copy point facts once; expose only domicile's first house-to-ruler edge."""
    points = {}
    for row in natal['natal_planets_full']:
        key = row['key']
        if key not in PLANET_ZH:
            continue
        points[key] = dict(key=key, kind='planet', name=row['cn'], longitude=row['lon'],
                           sign=row['sign'], retrograde=row['retrograde'],
                           houses={'placidus': row['house_p'], 'whole_sign': row['house_w']},
                           ruled_houses={s: {'traditional': [], 'modern': []}
                                         for s in ('placidus', 'whole_sign')},
                           direct_aspect_indices=[])
    for key in AXIS_PAIRS:
        row = natal['axes'][key]
        points[key] = dict(key=key, kind='axis', longitude=row['lon'], sign=row['sign_zh'],
                           axis_pair=AXIS_PAIRS[key][0], direct_aspect_indices=[])
    houses = {}
    for system in ('placidus', 'whole_sign'):
        houses[system] = []
        for row in natal['house_ruler_chains'][system]:
            rulers = {'traditional': TRADITIONAL_RULERS[row['sign']],
                      'modern': MODERN_RULERS[row['sign']]}
            houses[system].append(dict(house=row['house'], longitude=row['cusp_lon'],
                                       sign_key=row['sign'], sign=row['sign_zh'], rulers=rulers))
            for scheme, ruler in rulers.items():
                points[ruler]['ruled_houses'][system][scheme].append(row['house'])
    aspects = []
    for row in natal['aspects']:
        a, b = row['point1'], row['point2']
        if (a not in PLANET_ZH or b not in PLANET_ZH or
                row['angle'] not in (0, 60, 90, 120, 180) or row['orb'] > DEFAULT_ASPECT_VIEW):
            continue
        a, b = sorted((a, b))
        aspects.append(dict(point_a=a, point_b=b, angle=row['angle'], orb=row['orb']))
    aspects.sort(key=lambda r: (r['point_a'], r['point_b'], r['angle']))
    for index, row in enumerate(aspects):
        row['index'] = index
        row['point_refs'] = [f'/natal_context/points/{p}' for p in (row['point_a'], row['point_b'])]
        for point in (row['point_a'], row['point_b']):
            points[point]['direct_aspect_indices'].append(index)
    return dict(points=points, aspects=aspects, house_cusps=houses,
                availability=dict(planet_aspects='available', axis_aspects='not_in_this_view'),
                role='natal_context_only_not_additional_timing_contacts')


def contact_key(row):
    """Physical contact identity; directed_angle is natal minus moving."""
    target = row['target']
    directed = row['directed_angle'] % 360
    if target in AXIS_PAIRS:
        family, shift = AXIS_PAIRS[target]
        return row['technique'], row['planet'], 'axis:' + family, (directed - shift) % 360
    return row['technique'], row['planet'], 'planet:' + target, directed


def target_refs(target_key):
    kind, name = target_key.split(':')
    return [f'/natal_context/points/{p}' for p in (AXIS_MEMBERS[name] if kind == 'axis' else [name])]


def reading_windows(windows):
    """Union overlapping equivalent endpoint rows, retaining disconnected visits."""
    buckets = defaultdict(list)
    for i, row in enumerate(windows):
        buckets[contact_key(row)].append((i, row))
    rows = []
    for key, values in sorted(buckets.items()):
        groups = []
        for i, row in sorted(values, key=lambda p: (p[1]['start_utc'], p[1]['end_utc'], p[0])):
            # Merely touching half-open intervals do not overlap.
            if groups and row['start_utc'] < groups[-1]['end_utc']:
                group = groups[-1]
                group['end_utc'] = max(group['end_utc'], row['end_utc'])
                group['window_indices'].append(i)
            else:
                groups.append(dict(start_utc=row['start_utc'], end_utc=row['end_utc'], window_indices=[i]))
        for group in groups:
            ids = sorted(group['window_indices'])
            group.update(technique=key[0], planet=key[1], target_key=key[2], directed_angle=key[3],
                         window_indices=ids,
                         exact_event_indices=sorted({j for i in ids for j in windows[i]['exact_event_indices']}),
                         natal_context_refs=target_refs(key[2]),
                         source_refs=[f'/aspect_windows/{i}' for i in ids],
                         rule_id='equivalent_axis_windows' if len(ids) > 1 else 'source_orb_window',
                         reason='同一移动星、同一技法、同一几何接触的轴点记录归并。' if len(ids) > 1 else '已有容许度区间；即使没有精确命中也保留。')
            rows.append(group)
    rows.sort(key=lambda r: (r['start_utc'], r['technique'], r['planet'], r['target_key'], r['directed_angle']))
    for i, row in enumerate(rows):
        row['index'] = i
    return rows


def concurrent_segments(windows):
    """Sweep all endpoints; every returned interval has one truly shared set."""
    changes = defaultdict(lambda: {'add': set(), 'remove': set()})
    for i, row in enumerate(windows):
        changes[row['start_utc']]['add'].add(i)
        changes[row['end_utc']]['remove'].add(i)
    active, rows = set(), []
    times = sorted(changes)
    for i, at in enumerate(times[:-1]):
        active.difference_update(changes[at]['remove'])
        active.update(changes[at]['add'])
        if len(active) < 2:
            continue
        rows.append(dict(index=len(rows), start_utc=at, end_utc=times[i + 1],
                         reading_window_indices=sorted(active),
                         rule_id='simultaneous_orb_membership',
                         reason='这些配置在此区间同时处于各自容许度内；未据此判断共同主题。'))
    return rows


def window_overlaps(windows, context):
    """Pairs only: no transitive components or inferred chain activation."""
    aspect_pairs = {(r['point_a'], r['point_b']): r['index'] for r in context['aspects']}
    rows = []
    for i, a in enumerate(windows):
        for j in range(i + 1, len(windows)):
            b = windows[j]
            start, end = max(a['start_utc'], b['start_utc']), min(a['end_utc'], b['end_utc'])
            if start >= end:
                continue
            same = a['target_key'] == b['target_key']
            pair = tuple(sorted((a['target_key'].removeprefix('planet:'), b['target_key'].removeprefix('planet:'))))
            aspect = aspect_pairs.get(pair) if all(w['target_key'].startswith('planet:') for w in (a, b)) else None
            if not same and aspect is None:
                continue
            rows.append(dict(index=len(rows), start_utc=start, end_utc=end,
                             reading_window_indices=[i, j],
                             rule_id='same_natal_target' if same else 'direct_natal_aspect',
                             natal_aspect_index=aspect,
                             different_techniques=a['technique'] != b['technique'],
                             source_refs=[f'/reading_windows/{i}', f'/reading_windows/{j}'] +
                                         ([] if same else [f'/natal_context/aspects/{aspect}']),
                             reason='同期触及同一本命点或同一轴线。' if same else '同期分别触及本命中有直接相位的两颗星；该本命相位仅作关联背景。'))
    return rows


def _event_contact_key(event, points):
    source = event['source']
    # Secondary source longitude is the moving body's exact crossing longitude.
    directed = source.get('directed_angle')
    if directed is None:
        raw = (points[source['target']]['longitude'] - source['longitude']) % 360
        directed = min((0, 90, 180, 270, 360), key=lambda a: abs(raw - a)) % 360
    return contact_key(dict(technique=event['technique'], planet=source['planet'],
                            target=source['target'], directed_angle=directed))


def _seconds(text):
    return datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp()


def exact_contacts(events, windows, context):
    """Group equivalent axis hits only; minute tolerance covers secondary roots."""
    groups = []
    latest = {}
    for i, event in enumerate(events):
        if event['nature'] not in ('exact_aspect', 'axis_contact'):
            continue
        key = _event_contact_key(event, context['points'])
        previous = latest.get(key)
        if (key[2].startswith('axis:') and previous is not None and
                0 <= _seconds(event['exact_utc']) - _seconds(previous['start_utc']) <= 60 and
                event['source']['target'] not in previous['_endpoints']):
            previous['event_indices'].append(i)
            previous['_endpoints'].add(event['source']['target'])
            previous['end_utc'] = event['exact_utc']
        else:
            group = dict(technique=key[0], planet=key[1], target_key=key[2], directed_angle=key[3],
                         start_utc=event['exact_utc'], end_utc=event['exact_utc'], event_indices=[i],
                         _endpoints={event['source']['target']})
            groups.append(group)
            latest[key] = group
    for i, row in enumerate(groups):
        row.pop('_endpoints')
        times = [events[j]['exact_utc'] for j in row['event_indices']]
        row.update(index=i, natal_context_refs=target_refs(row['target_key']),
                   source_refs=[f'/events/{j}' for j in row['event_indices']],
                   matching_reading_window_indices=[w['index'] for w in windows if set(row['event_indices']) & set(w['exact_event_indices'])],
                   # All timestamps must lie inside the background interval.
                   concurrent_reading_window_indices=[w['index'] for w in windows if all(w['start_utc'] <= at < w['end_utc'] for at in times)],
                   rule_id='equivalent_axis_exact_contact' if len(times) > 1 else 'exact_contact',
                   reason='同一轴线接触的等价记录，只展示一次。' if len(times) > 1 else '精确接触时刻；与持续区间联读，不推断现实事件。')
    return groups


def reading_layers(events, windows, contacts):
    return dict(
        development_background=dict(
            title='发展背景与周期', rule_id='progressed_state_and_active_periods',
            progressed_context_ref='/progressed_context',
            progressed_ingress_event_indices=[i for i, e in enumerate(events) if e['technique'] == 'secondary_progressions' and e['nature'] == 'sign_ingress'],
            time_lord_event_indices=[i for i, e in enumerate(events) if e['technique'] in ('firdaria', 'zodiacal_releasing')],
            reason='先读次限日月与月相，以及已计算的法达和黄道释放周期；各技法含义分别保留。'),
        stage_configurations=dict(
            title='持续配置', rule_id='all_supported_orb_windows',
            reading_window_indices=list(range(len(windows))),
            overlap_ref='/window_overlaps', concurrent_segments_ref='/concurrent_segments',
            reason='所有已计算的持续区间，按起始时间排列；未按重要性筛选或评分。'),
        precise_contacts=dict(
            title='精确接触', rule_id='exact_contacts_linked_to_windows',
            exact_contact_indices=list(range(len(contacts))),
            reason='展开持续配置可查看各次精确接触；此层不含本版尚未计算的快速行运。'))


def derive_reading_views(events, windows, context):
    grouped = reading_windows(windows)
    contacts = exact_contacts(events, grouped, context)
    overlaps = window_overlaps(grouped, context)
    segments = concurrent_segments(grouped)
    return dict(reading_windows=grouped, exact_contacts=contacts,
                window_overlaps=overlaps, concurrent_segments=segments,
                reading_layers=reading_layers(events, grouped, contacts),
                reading_counts=dict(reading_windows=len(grouped), exact_contacts=len(contacts),
                                    window_overlaps=len(overlaps), concurrent_segments=len(segments)))


def build_reading_views(natal, events, windows):
    context = natal_context(natal)
    return dict(natal_context=context, **derive_reading_views(events, windows, context))


def validate_reading_views(data, require):
    """Validate self-contained facts and exact derivation/reference membership.

    Rebuilding the small projection catches omitted/altered links; it is not an
    independent proof of the astronomical engines or of interpretation.
    """
    from math import isfinite
    context = data['natal_context']
    points = context['points']
    require(set(points) == set(PLANET_ZH) | set(AXIS_PAIRS), '/natal_context/points', 'complete_natal_point_scope')
    for key, point in points.items():
        lon = point['longitude']
        require(type(lon) in (int, float) and isfinite(lon) and 0 <= lon < 360,
                f'/natal_context/points/{key}', 'valid_natal_longitude')
    for anchor, opposite in (('asc', 'dsc'), ('mc', 'ic')):
        delta = (points[opposite]['longitude'] - points[anchor]['longitude']) % 360
        require(abs(delta - 180) < 1e-6, '/natal_context/points', 'axis_endpoints_opposite')
    for system in ('placidus', 'whole_sign'):
        rows = context['house_cusps'][system]
        require([r['house'] for r in rows] == list(range(1, 13)), '/natal_context/house_cusps', 'twelve_ordered_houses')
        for row in rows:
            from services.natal_house_rulers import SIGN_KEYS
            require(row['sign_key'] in {SIGN_KEYS[int(((row['longitude'] + delta) % 360) // 30)] for delta in (-.000051, 0, .000051)}
                    and row['rulers'] == {'traditional': TRADITIONAL_RULERS[row['sign_key']], 'modern': MODERN_RULERS[row['sign_key']]},
                    '/natal_context/house_cusps', 'direct_domicile_rulers_match_cusp_sign')
        for key in PLANET_ZH:
            point = points[key]
            require(type(point['houses'][system]) is int and 1 <= point['houses'][system] <= 12,
                    '/natal_context/points', 'valid_house_placement')
            expected = {scheme: [r['house'] for r in rows if r['rulers'][scheme] == key]
                        for scheme in ('traditional', 'modern')}
            require(point['ruled_houses'][system] == expected, '/natal_context/points', 'ruled_houses_match_cusps')
    seen = set()
    for i, row in enumerate(context['aspects']):
        a, b = row['point_a'], row['point_b']
        pair = (a, b)
        require(a in PLANET_ZH and b in PLANET_ZH and a < b and pair not in seen,
                '/natal_context/aspects', 'unique_ten_planet_aspects')
        seen.add(pair)
        separation = abs((points[a]['longitude'] - points[b]['longitude'] + 180) % 360 - 180)
        require(row['index'] == i and row['angle'] in (0, 60, 90, 120, 180)
                and 0 <= row['orb'] <= DEFAULT_ASPECT_VIEW
                and abs(abs(separation - row['angle']) - row['orb']) <= .00012,
                '/natal_context/aspects', 'natal_aspect_geometry_and_orb')
        require(row['point_refs'] == [f'/natal_context/points/{a}', f'/natal_context/points/{b}'],
                '/natal_context/aspects', 'natal_point_references')
    for key, point in points.items():
        require(point['direct_aspect_indices'] == [i for i, r in enumerate(context['aspects']) if key in (r['point_a'], r['point_b'])],
                '/natal_context/points', 'direct_natal_edges_only')
    require(data['settings']['reading_policy'] == policy(), '/settings/reading_policy', 'declared_reading_policy')
    expected = derive_reading_views(data['events'], data['aspect_windows'], context)
    for key, value in expected.items():
        require(data[key] == value, '/' + key, 'reading_view_matches_source_membership_and_rule')
