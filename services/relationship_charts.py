"""Stateless relationship geometry over the existing compute() natal output.

Kerykeion supplies aspect geometry and circular means. Project policy supplies
orbs, labelled cusp validation, antipodal handling and evidence links. No scores,
psychological assertions, moving/fixed-planet conventions or new birth-time chain.
"""
from copy import deepcopy
from importlib.metadata import version
from itertools import combinations, product
from math import isfinite

from kerykeion.aspects.aspects_utils import get_aspect_from_two_points
from kerykeion.utilities import circular_mean

PLANETS = ('sun', 'moon', 'mercury', 'venus', 'mars', 'jupiter', 'saturn',
           'uranus', 'neptune', 'pluto', 'chiron')
# 南北交是月球轨道与黄道的真实交点，可以像行星一样直接取中点，不像福点/精神点
# 那样是从上升+日月推出的派生点（对派生点，"先取中点再推导"与"分别推导再取中点"
# 结果不同，那个歧义未决，因此仍不纳入）。
#
# 南交恒为北交的对点，两者同时参与判相会让每条交点相位重复出现一次
# （太阳合北交必然同时是太阳冲南交，同一几何事实数成两条）。因此沿用
# transit_natal.py 的既有口径：相位只遍历北交，南交照常显示位置与落宫。
NODES = ('north_node', 'south_node')
DISPLAY_PLANETS = PLANETS + NODES
ASPECT_EXCLUDED = frozenset(('south_node',))
AXES = ('ascendant', 'descendant', 'midheaven', 'imum_coeli')
HOUSE_PATTERN_SPECS = (
    {'id': 'fire_triplicity', 'kind': 'triangle', 'name': '火象宫位大三角',
     'houses': (1, 5, 9)},
    {'id': 'earth_triplicity', 'kind': 'triangle', 'name': '土象宫位大三角',
     'houses': (2, 6, 10)},
    {'id': 'air_triplicity', 'kind': 'triangle', 'name': '风象宫位大三角',
     'houses': (3, 7, 11)},
    {'id': 'water_triplicity', 'kind': 'triangle', 'name': '水象宫位大三角',
     'houses': (4, 8, 12)},
    {'id': 'cardinal_cross', 'kind': 'cross', 'name': '基本宫大十字',
     'houses': (1, 4, 7, 10)},
    {'id': 'fixed_cross', 'kind': 'cross', 'name': '固定宫大十字',
     'houses': (2, 5, 8, 11)},
    {'id': 'mutable_cross', 'kind': 'cross', 'name': '变动宫大十字',
     'houses': (3, 6, 9, 12)},
)
ASPECTS = ((0, 'conjunction'), (60, 'sextile'), (90, 'square'),
           (120, 'trine'), (180, 'opposition'))
# Greene, Relationships and How to Survive Them, Part One, p.29 in NLM edition.
# Internal composite/natal comparisons use the same explicit project preset.
ORB_PROFILES = {'greene': {0: 10., 60: 6., 90: 10., 120: 10., 180: 10.},
                'tight': {0: 3., 60: 3., 90: 3., 120: 3., 180: 3.}}
EPS = 1e-8


def longitude(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError('经度必须是有限数字')
    return float(value) % 360


def separation(a, b):
    return abs((a - b + 180) % 360 - 180)


def midpoint(a, b):
    """Never silently select one of two equally short antipodal midpoints."""
    a, b = longitude(a), longitude(b)
    if abs(separation(a, b) - 180) <= EPS:
        return {'longitude': None, 'status': 'ambiguous',
                'candidates': sorted([(a + 90) % 360, (a + 270) % 360])}
    return {'longitude': circular_mean(a, b) % 360, 'status': 'ok'}


def valid_cusps(cusps):
    if len(cusps) != 12 or any(c is None for c in cusps):
        return False
    widths = [(cusps[(i + 1) % 12] - c) % 360 for i, c in enumerate(cusps)]
    return (all(EPS < w < 180 for w in widths)
            and abs(sum(widths) - 360) < EPS
            and all(abs(separation(cusps[i], cusps[i + 6]) - 180) < EPS for i in range(6)))


def house_of(lon, cusps):
    # Exact cusps belong to the following house. No interpretive cusp orb.
    for i, start in enumerate(cusps):
        if (lon - start) % 360 < (cusps[(i + 1) % 12] - start) % 360:
            return i + 1
    raise ValueError('宫头不能构成完整宫位')


def natal_from_summary(summary, chart_id):
    """Public compute result, not private cache tokens or a second ephemeris call."""
    svg = summary['svg_data']
    planets = {key: {'longitude': longitude(svg['planets'][key]['lon'])}
               for key in DISPLAY_PLANETS if key in svg['planets']}
    if not all(key in planets for key in PLANETS[:10]):
        raise ValueError('本命盘缺少十大行星数据')
    cusps = [longitude(c) for c in svg['cusps']]
    if not valid_cusps(cusps):
        raise ValueError('本命宫头顺序或对宫关系无效')
    asc, mc = longitude(svg['asc_lon']), longitude(svg['mc_lon'])
    if separation(asc, cusps[0]) > EPS or separation(mc, cusps[9]) > EPS:
        raise ValueError('本命四轴与普拉西度宫头不一致')
    axes = dict(zip(AXES, [asc, (asc + 180) % 360, mc, (mc + 180) % 360]))
    return {'id': chart_id, 'name': summary.get('name', ''), 'planets': planets,
            'axes': {k: {'longitude': v} for k, v in axes.items()},
            'houses': {'system': 'placidus', 'status': 'ok', 'cusps': cusps},
            'birth_context': deepcopy(summary.get('birth_context', {})),
            'source_aspects': deepcopy(svg.get('aspects', [])),
            'missing_points': [p for p in DISPLAY_PLANETS if p not in planets]}


def points(chart):
    return {k: v['longitude'] for k, v in {**chart['planets'], **chart['axes']}.items()
            if v['longitude'] is not None}


def aspect_points(chart):
    """判相用的点集：显示集合减去恒为对点的南交，避免同一几何事实数两次。"""
    return {k: v for k, v in points(chart).items() if k not in ASPECT_EXCLUDED}


def aspects(first, second, profile, internal=False):
    settings = [{'degree': degree, 'name': name, 'orb': ORB_PROFILES[profile][degree]}
                for degree, name in ASPECTS]
    left, right = aspect_points(first), aspect_points(second)
    pairs = combinations(left, 2) if internal else product(left, right)
    rows = []
    for p1, p2 in pairs:
        # Internal axis-to-axis contacts are chart definitions, not distinct evidence.
        if internal and p1 in AXES and p2 in AXES:
            continue
        hit = get_aspect_from_two_points(settings, left[p1], right[p2])
        if hit['verdict']:
            angle = hit['aspect_degrees']
            rows.append({'id': f"{first['id']}:{p1}|{second['id']}:{p2}|{angle}",
                         'first_chart': first['id'], 'first_point': p1,
                         'second_chart': second['id'], 'second_point': p2,
                         'angle': angle, 'aspect': hit['name'], 'orb': hit['orbit'],
                         'orb_limit': ORB_PROFILES[profile][angle],
                         'tight_contact': hit['orbit'] <= 1., 'applying': None})
    return sorted(rows, key=lambda r: (r['orb'], r['id']))


def overlays(source, target):
    cusps = target['houses']['cusps']
    if target['houses']['status'] != 'ok':
        return []
    return [{'source_chart': source['id'], 'target_chart': target['id'],
             'point': p, 'house': house_of(lon, cusps)} for p, lon in points(source).items()]


def natal_house_patterns(first, second):
    """Return only complete A/B patterns formed from each natal chart's own houses.

    This is deliberately not aspect geometry.  Each planet stays in its owner's
    Placidus natal house; the two occupancy maps are merely laid over one another.
    Zodiac signs, degrees and axes do not participate.  Natal lunar nodes do
    participate as explicitly requested.  A pattern is returned only when every
    required house is occupied and both people contribute.
    """
    occupants = {house: [] for house in range(1, 13)}
    for chart in (first, second):
        own_houses = {row['point']: row['house'] for row in overlays(chart, chart)
                      if row['point'] in DISPLAY_PLANETS}
        for point in DISPLAY_PLANETS:
            house = own_houses.get(point)
            if house in occupants:
                occupants[house].append({'chart': chart['id'], 'point': point})

    rows = []
    for spec in HOUSE_PATTERN_SPECS:
        houses = [{'house': house, 'members': deepcopy(occupants[house])}
                  for house in spec['houses']]
        contributors = {member['chart'] for row in houses for member in row['members']}
        rows.append({
            'id': spec['id'],
            'kind': spec['kind'],
            'name': spec['name'],
            'houses': houses,
            # 四个三角与三个十字一律返回；complete 只是其中一个观察角度，
            # 不是显示的前提。此前只回传 complete 的那几个，读者无从知道
            # 其余结构长什么样、缺在哪一宫。
            'complete': all(row['members'] for row in houses) and {'a', 'b'} <= contributors,
            'contributors': sorted(contributors),
            'empty_houses': [row['house'] for row in houses if not row['members']],
        })
    return {
        'house_system': 'placidus',
        'rule': 'combined_own_natal_house_occupancy',
        'patterns': rows,
    }


def composite_chart(first, second):
    planets = {p: midpoint(first['planets'][p]['longitude'], second['planets'][p]['longitude'])
               for p in DISPLAY_PLANETS if p in first['planets'] and p in second['planets']}
    axes = {p: midpoint(first['axes'][p]['longitude'], second['axes'][p]['longitude']) for p in AXES}
    cusp_results = [midpoint(a, b) for a, b in zip(first['houses']['cusps'], second['houses']['cusps'])]
    cusps = [r['longitude'] for r in cusp_results]
    status = 'ok' if valid_cusps(cusps) else ('ambiguous' if None in cusps else 'invalid_order')
    # Do not sort/relabel houses. Even individually valid midpoints can cross.
    if status == 'ok' and any(separation(axes[p]['longitude'], cusps[i]) > EPS
                              for p, i in [('ascendant', 0), ('midheaven', 9)]):
        status = 'axis_mismatch'
    return {'id': 'composite', 'planets': planets, 'axes': axes,
            'missing_points': [p for p in DISPLAY_PLANETS if p not in planets],
            'houses': {'system': 'midpoint_of_placidus_cusps', 'status': status,
                       'cusps': cusps if status == 'ok' else None,
                       'raw_midpoints': cusp_results},
            'ambiguous_points': [k for k, v in {**planets, **axes}.items() if v['status'] != 'ok']}


def _links(rows, natal_aspects):
    """Join exact point identities, never infer a psychological condition."""
    out = []
    for row in rows:
        links = {}
        for side in ('first', 'second'):
            cid, point = row[f'{side}_chart'], row[f'{side}_point']
            if cid in natal_aspects:
                links[cid] = [a['id'] for a in natal_aspects[cid]
                              if point in (a['first_point'], a['second_point'])]
        out.append({'contact_id': row['id'], 'natal_aspect_ids': links})
    return out


def build_relationship_charts(first_summary, second_summary, orb_profile='greene'):
    if orb_profile not in ORB_PROFILES:
        raise ValueError('orb_profile 仅支持 greene 或 tight')
    first, second = natal_from_summary(first_summary, 'a'), natal_from_summary(second_summary, 'b')
    composite = composite_chart(first, second)
    charts = {'a': first, 'b': second, 'composite': composite}
    internal = {cid: aspects(chart, chart, orb_profile, internal=True) for cid, chart in charts.items()}
    for cid, chart in charts.items():
        chart['aspects'] = internal[cid]
        chart['point_houses'] = overlays(chart, chart)
    cross = aspects(first, second, orb_profile)
    ca, cb = aspects(composite, first, orb_profile), aspects(composite, second, orb_profile)
    # Same pair is a repeated geometric theme even if aspect angles differ.
    themes = {}
    for cid, rows in internal.items():
        for row in rows:
            if row['first_point'] in DISPLAY_PLANETS and row['second_point'] in DISPLAY_PLANETS:
                pair = tuple(sorted([row['first_point'], row['second_point']]))
                themes.setdefault(pair, {}).setdefault(cid, []).append(row['id'])
    repeated = [{'points': list(pair), 'aspects_by_chart': evidence}
                for pair, evidence in sorted(themes.items()) if len(evidence) >= 2]
    common = []
    for p in points(composite):
        a_hits = [r['id'] for r in ca if r['first_point'] == p and r['angle'] in (0, 180) and r['tight_contact']]
        b_hits = [r['id'] for r in cb if r['first_point'] == p and r['angle'] in (0, 180) and r['tight_contact']]
        if a_hits and b_hits:
            common.append({'composite_point': p, 'a_contact_ids': a_hits, 'b_contact_ids': b_hits})
    return {'schema_version': 1,
            'method': {'zodiac': 'tropical', 'natal_source': 'services.calculator.compute',
                       'composite': 'short_arc_midpoints_preserve_cusp_labels',
                       'orb_profile': orb_profile, 'orbs': ORB_PROFILES[orb_profile],
                       'geometry_library': 'kerykeion', 'library_version': version('kerykeion'),
                       'time_accuracy': 'exact_required', 'applying': 'not_defined_for_static_cross_charts',
                       'points': list(DISPLAY_PLANETS), 'axes': list(AXES),
                       'aspect_excluded_points': sorted(ASPECT_EXCLUDED),
                       'aspect_exclusion_reason': 'south_node_is_always_opposite_north_node'},
            'charts': charts,
            'natal_house_patterns': natal_house_patterns(first, second),
            'synastry': {'aspects': cross, 'a_in_b': overlays(first, second), 'b_in_a': overlays(second, first)},
            'composite_to_natal': {'a': {'aspects': ca, 'composite_in_natal': overlays(composite, first)},
                                   'b': {'aspects': cb, 'composite_in_natal': overlays(composite, second)}},
            'structure_links': _links(cross + ca + cb, {'a': internal['a'], 'b': internal['b']}),
            'repeated_pairs': repeated, 'common_contacts': common}
