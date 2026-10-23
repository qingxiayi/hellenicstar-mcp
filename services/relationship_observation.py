"""John Green observation v0.14: geometry once, two perspectives, bounded context.

No composite, ephemeris implementation, psychological flags or path enumeration.
Axis endpoints are equivalent representations of a single geometric contact.
"""
from copy import deepcopy
from itertools import combinations, product
import math

from services.relationship_charts import (
    PLANETS, AXES, DISPLAY_PLANETS, natal_from_summary, points, house_of,
    separation, valid_cusps,
)
from services.natal_house_rulers import TRADITIONAL_RULERS, MODERN_RULERS, SIGN_KEYS

VERSION = 'john-green-observation-v0.14'
RANKINGS = {
    'orb': 'min_direct_orb_asc_then_id',
    'relationship_indicators': 'target_relationship_role_first_then_min_direct_orb_asc_then_id',
    'natal_hard_aspects': 'natal_square_opposition_count_desc_then_min_direct_orb_asc_then_id',
}
QUESTIONS = {
    'partner_expectations': '你在寻找怎样的伴侣？你对关系有什么期待？',
    'love_experience': '你怎样体验爱一个人和被爱？',
    'wants_and_possibilities': '你想要的关系与现实中能够拥有的关系，有哪些相同或不同？',
}
PERSONAL = PLANETS[:5]
OUTER = ('uranus', 'neptune', 'pluto')
COUNTED = PLANETS[:7] + ('ascendant', 'midheaven')
OPPOSITES = {'north_node': 'south_node', 'ascendant': 'descendant',
             'midheaven': 'imum_coeli'}
CANONICAL = PLANETS + tuple(OPPOSITES)
ASPECT_NAMES = {0: 'conjunction', 60: 'sextile', 90: 'square',
                120: 'trine', 180: 'opposition', 30: 'semi_sextile',
                45: 'semi_square', 135: 'sesquiquadrate', 150: 'quincunx'}
SCENARIOS = {
    'love': {'points': ['moon', 'venus', 'mars', 'jupiter', 'saturn'],
             'houses': [5, 7, 8, 4], 'element_focus': 'complementarity'},
    'friendship': {'points': ['venus', 'mars', 'mercury', 'jupiter'],
                   'houses': [5, 11, 3], 'element_focus': 'similarity'},
    'work': {'points': ['sun', 'moon', 'mercury', 'mars', 'saturn'],
             'houses': [5, 6, 10, 11], 'element_focus': None},
    'family': {'points': ['sun', 'moon', 'mercury', 'saturn'],
               'houses': [3, 4, 5, 8, 10, 12], 'element_focus': None},
}


def settings_for(relationship_type='love', house_system='placidus', orb_profile='john_green',
                 ruler_profile='traditional', parental_house_mapping_profile='john_green',
                 sextile_orb_degrees=None, include_minor_aspects=False, include_timing=False,
                 mode='synastry', sort_by='orb', minor_orbs_degrees=None, relationship_context=None, timing=None):
    if mode not in ('synastry', 'natal'):
        raise ValueError('mode must be synastry or natal')
    if sort_by not in RANKINGS:
        raise ValueError('sort_by must be orb, relationship_indicators or natal_hard_aspects')
    if relationship_type not in SCENARIOS:
        raise ValueError('relationship_type must be love, friendship, work or family')
    if house_system != 'placidus' or orb_profile != 'john_green':
        raise ValueError('v0.14 supports placidus and john_green only')
    if ruler_profile not in ('traditional', 'modern'):
        raise ValueError('ruler_profile must be traditional or modern')
    if parental_house_mapping_profile not in ('john_green', 'reversed'):
        raise ValueError('parental_house_mapping_profile must be john_green or reversed')
    if sextile_orb_degrees is not None and (
        type(sextile_orb_degrees) not in (int, float) or not math.isfinite(sextile_orb_degrees)
        or not 0 <= sextile_orb_degrees <= 10
    ):
        raise ValueError('sextile_orb_degrees must be a finite number in [0, 10] or null')
    if type(include_minor_aspects) is not bool or type(include_timing) is not bool:
        raise ValueError('include flags must be boolean')
    from services.relationship_observation_timing import timing_settings
    from services.relationship_observation_contexts import context_settings, combined_scenario
    context = context_settings(relationship_context, relationship_type, SCENARIOS)
    timing_config = timing_settings(timing, include_timing, mode, context)
    minor_orbs = {} if minor_orbs_degrees is None else minor_orbs_degrees
    if not isinstance(minor_orbs, dict) or set(minor_orbs) - {'30', '45', '135', '150'}:
        raise ValueError('minor_orbs_degrees keys must be 30, 45, 135 or 150')
    if bool(minor_orbs) != include_minor_aspects:
        raise ValueError('include_minor_aspects requires explicit minor_orbs_degrees; orbs require the flag')
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 10 for v in minor_orbs.values()):
        raise ValueError('minor orbs must be finite numbers in [0, 10]; there is no author default')
    minor_orbs = {k: float(v) for k, v in sorted(minor_orbs.items())}
    # Direct Python calls may pass 5 while MCP validates it as 5.0. Freeze the
    # same JSON value before fingerprinting, so reference recomputation agrees.
    if sextile_orb_degrees is not None:
        sextile_orb_degrees = float(sextile_orb_degrees)
    orbs = {'0': 10., '90': 10., '120': 10., '180': 10.}
    if sextile_orb_degrees is not None:
        orbs['60'] = float(sextile_orb_degrees)
    orbs.update(minor_orbs)
    if minor_orbs:
        # Single geometric contact per point pair. Include all axis complements
        # when rejecting ambiguous overlapping windows rather than dropping a hit.
        windows = {}
        for angle, limit in orbs.items():
            for a in (int(angle), 180 - int(angle)):
                windows[a] = max(windows.get(a, 0), limit)
        if any(abs(a-b) <= windows[a] + windows[b] for a, b in combinations(windows, 2)):
            raise ValueError('Aspect orb windows overlap including axis complements; narrow explicit minor orbs')
    return dict(relationship_type=relationship_type, house_system=house_system,
                orb_profile=orb_profile, ruler_profile=ruler_profile,
                parental_house_mapping_profile=parental_house_mapping_profile,
                sextile_orb_degrees=sextile_orb_degrees,
                include_minor_aspects=include_minor_aspects, minor_orbs_degrees=minor_orbs, include_timing=include_timing, timing=timing_config,
                relationship_context=context,
                rule_version=VERSION, orbs=orbs, tight_orb_degrees=5.,
                personal_points=list(PERSONAL), element_counted_points=list(COUNTED),
                node_type='mean', natal_expansion_depth=1,
                reciprocity_source_points=[p for p in PLANETS if p != 'saturn'],
                mode=mode, sort_by=sort_by, ranking=RANKINGS[sort_by],
                ranking_provenance='ENGINE_DECISION',
                axis_policy='canonical_NN_ASC_MC_with_equivalent_endpoint_variants',
                scenario=combined_scenario(relationship_type, context, SCENARIOS))


def provenance():
    """Short locators into the supplied book; no edition-dependent page keys."""
    from services.relationship_observation_routes import route_provenance
    from services.relationship_observation_contexts import context_provenance
    from services.relationship_observation_lenses import lens_provenance
    from services.relationship_observation_timing import timing_provenance
    return {
        **route_provenance(),
        **context_provenance(),
        **lens_provenance(),
        **timing_provenance(),
        'element_count': dict(concept_provenance='JG_PREFERENCE',
            operational_rule_provenance='ENGINE_DECISION', chapter='Chapter Two',
            quote='I tend to count the planets out to Saturn and the Ascendant and Midheaven.'),
        'network': dict(concept_provenance='JG_EXPLICIT',
            operational_rule_provenance='ENGINE_DERIVED', chapter='Chapter 5 – Cookbook Astrology',
            quote="we can’t ignore that those are in orb to the other planets"),
        'cross_orbs': dict(concept_provenance='JG_PREFERENCE',
            operational_rule_provenance='ENGINE_DECISION', chapter='Chapter Three',
            quote='I use 10˚ orbs for conjunctions, oppositions, squares and trines'),
        'seventh_cusp': dict(concept_provenance='JG_EXPLICIT',
            operational_rule_provenance='ENGINE_DECISION', chapter='Chapter Two',
            quote='within 5˚ of the cusp of the seventh house'),
        'reciprocity': dict(concept_provenance='JG_EXPLICIT',
            operational_rule_provenance='ENGINE_DECISION', chapter='Chapter Three – Synastry / Saturn and Chiron',
            quote='don’t themselves have their Saturn aspected by the other'),
        'scenario': dict(concept_provenance='JG_EXPLICIT',
            operational_rule_provenance='ENGINE_DECISION', chapter='Chapter Seven',
            quote='Synastry with work colleagues and bosses'),
        'aggregation': dict(concept_provenance='ENGINE_DERIVED',
            operational_rule_provenance='ENGINE_DECISION'),
        'configuration_membership': dict(concept_provenance='JG_EXPLICIT',
            operational_rule_provenance='ENGINE_DERIVED', chapter='Chapter 5 – Cookbook Astrology',
            quote='it is Saturn setting off a very important T-square',
            scope='bounded templates over Sun through Pluto plus Chiron; not a connected component'),
        'observation_complex_link': dict(concept_provenance='JG_EXPLICIT',
            operational_rule_provenance='ENGINE_DERIVED',
            chapter='Chapter Seven / Fisher and Reynolds; Chapter Six / Tom and Katie',
            scope='actual contacts and two owner bounded-complex membership lists; core and attached context separate; no pair product, additional evidence or whole activation'),
        'configuration_bridge': dict(concept_provenance='JG_EXPLICIT',
            operational_rule_provenance='ENGINE_DERIVED', chapter='Chapter Seven – Synastry with family members',
            quote='Debbie’s Venus, Moon and Neptune T-square triggers Carrie’s Moon, Saturn and Pluto T-square',
            scope='group actual contacts by memberships; no additional contact or reaction inferred'),
        'natal_background': dict(concept_provenance='ENGINE_DERIVED',
            operational_rule_provenance='ENGINE_DECISION',
            scope='reuse natal salience with its own disclosed policy; no activation propagation'),
        'review_indicators': dict(concept_provenance='JG_EXPLICIT',
            operational_rule_provenance='ENGINE_DERIVED', chapter='Chapter 5 – Cross-aspect pointers',
            quote='Examine closely any cross-aspects that involve relationship or parental indicators in each chart.'),
        'review_inner_outer': dict(concept_provenance='JG_EXPLICIT',
            operational_rule_provenance='ENGINE_DECISION', chapter='Chapter 5 – Cross-aspect pointers',
            scope='Sun/Moon/Mercury/Venus/Mars versus Uranus/Neptune/Pluto; both directions'),
        'review_tightness': dict(concept_provenance='JG_EXPLICIT',
            operational_rule_provenance='ENGINE_DECISION', chapter='Chapter Three – Inner planets in synastry',
            scope='5 degree focus threshold; wider contacts retained, no inferred life importance'),
        'review_policy': dict(concept_provenance='JG_DERIVED',
            operational_rule_provenance='ENGINE_DERIVED', chapter='Chapter Three – Cross-aspects',
            scope='parallel reasons and lenses; no total weights, no automatic client-priority inference'),
        'containment_display': dict(concept_provenance='ENGINE_DERIVED',
            operational_rule_provenance='ENGINE_DECISION',
            scope='fold strict containment, preserve partial overlaps and every raw evidence row'),
        'workshop_observation': dict(concept_provenance='SOURCE_SUPPORTED',
            operational_rule_provenance='ENGINE_DECISION',
            title="It’s not them, it’s you!", section='Natal Chart - Questions to Explore',
            quote='How do you experience love and being loved?',
            scope='observation prompts only; no attachment or IFS mapping'),
        'source': dict(title='Do You Love Me? The Astrology of Relationships',
                       author='John Green', rule_version=VERSION,
                       edition='user-supplied PDF; edition unspecified'),
    }


def geometry_from_summary(summary, who):
    chart = natal_from_summary(summary, who)
    return {'points': points(chart), 'cusps': chart['houses']['cusps']}


def validate_geometry(g):
    required = set(DISPLAY_PLANETS + AXES)
    if set(g['points']) != required:
        raise ValueError('Observation requires all planets, Chiron, both nodes and four angles')
    values = list(g['points'].values()) + list(g['cusps'])
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v < 360 for v in values):
        raise ValueError('Source longitudes must be finite degrees in [0, 360)')
    if not valid_cusps(g['cusps']):
        raise ValueError('Placidus cusps unavailable or invalid; no replacement houses inferred')
    for a, b in OPPOSITES.items():
        if abs(separation(g['points'][a], g['points'][b]) - 180) > 1e-6:
            raise ValueError('Source axis endpoints must be opposite')
    for p, i in [('ascendant', 0), ('midheaven', 9)]:
        if separation(g['points'][p], g['cusps'][i]) > 1e-6:
            raise ValueError('Source angles must match Placidus cusps')


def contacts_between(left, right, first_person, second_person, settings, internal=False, first_points=None):
    rows = []
    pairs = combinations(CANONICAL, 2) if internal else product(
        CANONICAL if first_points is None else first_points, CANONICAL)
    for p, q in pairs:
        if internal and p in AXES and q in AXES:
            continue  # No internal angle-to-angle chart definitions as evidence.
        sep = separation(left[p], right[q])
        # An axis trine can be the other endpoint's sextile, and vice versa.
        # Keep these equivalent representations without inventing a sextile orb.
        for angle in ASPECT_NAMES:
            evaluated = [a for a in (angle, 180 - angle) if str(a) in settings['orbs']
                         and (a == angle or p in OPPOSITES or q in OPPOSITES)]
            if not evaluated:
                continue
            limit = max(settings['orbs'][str(a)] for a in evaluated)
            orb = abs(sep - angle)
            if orb > limit:
                continue
            variants = []
            for a, b in product((p, OPPOSITES[p]) if p in OPPOSITES else (p,),
                                (q, OPPOSITES[q]) if q in OPPOSITES else (q,)):
                equivalent_angle = 180 - angle if (a != p) != (b != q) else angle
                variants.append(dict(first_point=a, second_point=b, angle=equivalent_angle,
                                     aspect=ASPECT_NAMES[equivalent_angle],
                                     separation_degrees=separation(left[a], right[b]),
                                     representation='canonical' if (a, b) == (p, q) else 'axis_equivalent'))
            rows.append(dict(id=f'{first_person}:{p}|{second_person}:{q}|{angle}',
                first_person=first_person, first_point=p, second_person=second_person,
                second_point=q, aspect=ASPECT_NAMES[angle], angle=angle,
                separation_degrees=sep, orb_degrees=orb, orb_limit=limit,
                tight_contact=orb <= settings['tight_orb_degrees'], applying=None,
                evaluated_angles=sorted(set(a for a in evaluated if orb <= settings['orbs'][str(a)])),
                canonical_angle_enabled=str(angle) in settings['orbs'] and orb <= settings['orbs'][str(angle)],
                generational_contact=p == q and p in OUTER + ('saturn', 'chiron'),
                endpoint_variants=variants, rule_id='minor_orbs' if angle in (30, 45, 135, 150) else 'cross_orbs'))
    return sorted(rows, key=lambda r: (r['orb_degrees'], r['id']))


def adjacent(edges, point):
    canonical = next((a for a, b in OPPOSITES.items() if b == point), point)
    return [e for e in edges if canonical in (e['first_point'], e['second_point'])]


def profile(g, who, settings):
    ps, cusps = g['points'], g['cusps']
    edges = contacts_between(ps, ps, who, who, settings, internal=True)
    positions = {}
    for p, lon in ps.items():
        house = house_of(lon, cusps)
        distance = (cusps[house % 12] - lon) % 360
        near = p in PLANETS and house == 6 and distance <= 5
        positions[p] = dict(longitude=lon, sign=SIGN_KEYS[int(lon // 30)], house=house,
                            distance_to_next_cusp=distance, seventh_cusp_effect=near,
                            effective_seventh_house=p in PLANETS and (house == 7 or near))
    elements = {k: [] for k in ('fire', 'earth', 'air', 'water')}
    modalities = {k: [] for k in ('cardinal', 'fixed', 'mutable')}
    for p in COUNTED:
        idx = int(ps[p] // 30)
        elements[list(elements)[idx % 4]].append(p)
        modalities[list(modalities)[idx % 3]].append(p)
    rulers = TRADITIONAL_RULERS if settings['ruler_profile'] == 'traditional' else MODERN_RULERS
    houses = []
    for i, cusp in enumerate(cusps, 1):
        ruler = rulers[SIGN_KEYS[int(cusp // 30)]]
        houses.append(dict(house=i, cusp_longitude=cusp, cusp_sign=SIGN_KEYS[int(cusp // 30)],
            ruler=ruler, ruler_sign=positions[ruler]['sign'], ruler_house=positions[ruler]['house'],
            ruler_natal_aspect_ids=[e['id'] for e in adjacent(edges, ruler)],
            planets=[p for p in PLANETS if positions[p]['house'] == i]))
    projected = [p for p in PLANETS if positions[p]['house'] == 8 or positions[p]['effective_seventh_house']]
    father, mother = (4, 10) if settings['parental_house_mapping_profile'] == 'john_green' else (10, 4)
    outer = {p: dict(personal_natal_aspect_ids=[e['id'] for e in adjacent(edges, p)
                   if e['first_point'] in PERSONAL or e['second_point'] in PERSONAL]) for p in OUTER}
    for row in outer.values():
        row['has_personal_planet_natal_aspects'] = bool(row['personal_natal_aspect_ids'])
        row['scope'] = 'evaluated_aspects_only'
    return dict(points=positions, natal_aspects=edges, houses=houses,
        element_balance={k: dict(count=len(v), points=v, singleton=len(v) == 1) for k, v in elements.items()},
        modality_balance={k: dict(count=len(v), points=v, singleton=len(v) == 1) for k, v in modalities.items()},
        saturn_element=list(elements)[int(ps['saturn'] // 30) % 4],
        moon_venus_different_elements=int(ps['moon'] // 30) % 4 != int(ps['venus'] // 30) % 4,
        projected_planets=projected, outer_planet_contexts=outer,
        parental_context=dict(father_points=['sun', 'saturn', 'mars'], mother_points=['moon', 'venus'],
            father_house=father, mother_house=mother,
            sun_moon_natal_aspect_ids=[e['id'] for e in edges if {e['first_point'], e['second_point']} == {'sun', 'moon'}],
            luminary_contact_ids=[e['id'] for e in edges
                if (e['first_point'] in ('sun', 'moon') and e['second_point'] in OUTER + ('saturn', 'chiron'))],
            ruler_4_10_aspect_ids=[e['id'] for e in edges if {e['first_point'], e['second_point']} == {houses[3]['ruler'], houses[9]['ruler']}],
            same_parental_house_ruler=houses[3]['ruler'] == houses[9]['ruler']))


def build_observation(source_geometry, birth_context, settings, natal_graphs=None, timing_sources=None):
    from services.relationship_observation_routes import candidate_reasons, is_relationship_role
    people = tuple(source_geometry)
    if 'a' not in people or set(people) - {'a', 'b'} or (settings['mode'] == 'synastry' and 'b' not in people):
        raise ValueError('person_a is required; synastry also requires person_b')
    for who in people:
        validate_geometry(source_geometry[who])
    profiles = {who: profile(source_geometry[who], who, settings) for who in people}
    contacts = (contacts_between(source_geometry['a']['points'], source_geometry['b']['points'], 'a', 'b', settings)
                if settings['mode'] == 'synastry' else [])
    paths, clusters, overlays, projected, groups = [], [], [], [], []
    for target, source in ((('a', 'b'), ('b', 'a')) if settings['mode'] == 'synastry' else ()):
        target_side = 'first' if target == 'a' else 'second'
        source_side = 'second' if target == 'a' else 'first'
        prof = profiles[target]
        for contact in contacts:
            point = contact[target_side + '_point']
            paths.append(dict(id=contact['id'] + '->' + target, contact_id=contact['id'],
                source_person=source, source_point=contact[source_side + '_point'],
                target_person=target, target_point=point,
                natal_context_edge_ids=[e['id'] for e in adjacent(prof['natal_aspects'], point)]))
        for point in CANONICAL:
            direct = [c for c in contacts if c[target_side + '_point'] == point]
            if not direct:
                continue
            natal = adjacent(prof['natal_aspects'], point)
            neighbors = sorted({p for e in natal for p in (e['first_point'], e['second_point'])} - {point})
            context = dict(rules_as_houses=[h['house'] for h in prof['houses'] if h['ruler'] == point],
                scenario_indicator=point in settings['scenario']['points'],
                target_relationship_indicator=any(is_relationship_role(r['role'])
                    for r in candidate_reasons(target, point, prof, settings)),
                parental_indicator=point in ('sun', 'moon', 'saturn', 'mars', 'venus'),
                projected_planet=point in prof['projected_planets'],
                nodal_axis=point == 'north_node', angle_axis=point in ('ascendant', 'midheaven'))
            clusters.append(dict(id=f'{target}:{point}', target_person=target, target_point=point,
                contact_ids=[c['id'] for c in direct],
                observation_path_ids=[c['id'] + '->' + target for c in direct],
                local_natal_context=dict(edge_ids=[e['id'] for e in natal], neighbors=neighbors, depth=1),
                observation_context=context,
                direct_contact_count=len(direct), natal_context_edge_count=len(natal),
                unique_source_point_count=len({c[source_side + '_point'] for c in direct}),
                natal_hard_aspect_count=sum(e['angle'] in (90, 180) for e in natal),
                min_direct_orb_degrees=min(c['orb_degrees'] for c in direct)))
        for p, lon in source_geometry[source]['points'].items():
            h = house_of(lon, source_geometry[target]['cusps'])
            row = dict(id=f'{source}:{p}->{target}:house:{h}', source_person=source, source_point=p,
                target_person=target, house=h, scenario_house=h in settings['scenario']['houses'],
                target_natal_planet_count=len(prof['houses'][h - 1]['planets']),
                parental_house=h in (4, 10), outer_in_twelfth=p in OUTER and h == 12)
            overlays.append(row)
            if p in profiles[source]['projected_planets']:
                projected.append(dict(overlay_id=row['id'], source_natal_house=profiles[source]['points'][p]['house'],
                                      seventh_cusp_effect=profiles[source]['points'][p]['seventh_cusp_effect']))
        for point in CANONICAL:
            hits = [c for c in contacts if c[source_side + '_point'] == point]
            targets = sorted({c[target_side + '_point'] for c in hits})
            if len(targets) > 1:
                groups.append(dict(id=f'{source}:{point}->{target}', source_person=source, source_point=point,
                    target_person=target, contact_ids=[c['id'] for c in hits],
                    cluster_ids=[f'{target}:{p}' for p in targets],
                    linking_natal_edge_ids=[e['id'] for e in prof['natal_aspects']
                        if e['first_point'] in targets and e['second_point'] in targets]))
    def sort_key(c):
        prefix = (() if settings['sort_by'] == 'orb' else
                  (-int(c['observation_context']['target_relationship_indicator']),) if settings['sort_by'] == 'relationship_indicators'
                  else (-c['natal_hard_aspect_count'],))
        return (*prefix, c['min_direct_orb_degrees'], c['id'])
    clusters.sort(key=sort_key)
    saturn = {target: [p['contact_id'] for p in paths if p['target_person'] == target and p['target_point'] == 'saturn'
                      and p['source_point'] in settings['reciprocity_source_points']] for target in ('a', 'b')}
    reciprocity = 'both' if all(saturn.values()) else 'A_only' if saturn['a'] else 'B_only' if saturn['b'] else 'none'
    from services.relationship_natal_bridge import associate, SUPPORTED
    associations = associate(profiles, contacts, paths, clusters, natal_graphs or {}, settings)
    from services.relationship_observation_complexes import build_complexes, build_complex_links
    complexes = build_complexes(profiles, contacts, associations, settings)
    from services.relationship_observation_views import build_review, build_structure_display
    review = build_review(profiles, contacts, clusters, associations, settings)
    structure_display = build_structure_display(associations)
    unavailable = {k: dict(status='not_computed', reason='deferred_v0.14') for k in
                   ('seeking_carrier', 'natal_resonance', 'shared_themes', 'timing')}
    unavailable['configuration_membership'] = dict(status='computed', supported=SUPPORTED,
        points=list(PLANETS), excluded_points=list(OPPOSITES) + list(OPPOSITES.values()),
        unsupported=['yod', 'arbitrary_connected_component'],
        scope='evaluated_john_green_aspects_only; sextile-dependent patterns require explicit sextile orb',
        max_members=4, recursive_expansion=False)
    unavailable['natal_background'] = {
        who: dict(status=row['status'], scope='static_natal_background_only')
        for who, row in associations['natal_backgrounds'].items()}
    unavailable['configuration_bridges'] = dict(
        status='computed' if settings['mode'] == 'synastry' else 'not_computed',
        reason='requested_mode', counts_are_additive=False)
    unavailable.update({k: dict(status='not_computed', reason='rule_undefined') for k in
                        ('complementarity_matches', 'similarity_matches', 'element_lack_abundance')})
    unavailable['minor_aspects'] = dict(status='computed' if settings['include_minor_aspects'] else 'not_computed',
        reason='caller_defined_orbs' if settings['include_minor_aspects'] else 'orbs_unspecified',
        evaluated_angles=sorted(int(a) for a in settings['minor_orbs_degrees']),
        unconfigured_angles=sorted({30, 45, 135, 150} - {int(a) for a in settings['minor_orbs_degrees']}))
    unavailable['yod_context'] = dict(status='computed' if {'60', '150'} <= settings['orbs'].keys() else 'not_computed',
        reason='requires_explicit_sextile_and_quincunx_orbs', scope='observation_complexes_only')
    unavailable['sextile'] = dict(status='not_computed' if settings['sextile_orb_degrees'] is None else 'computed',
        reason='orb_unspecified_axis_equivalents_still_retained' if settings['sextile_orb_degrees'] is None else 'caller_defined_orb')
    unavailable['role_specific_indicators'] = dict(
        status='computed' if settings['relationship_context']['roles'] else 'not_computed',
        reason='caller_supplied_roles' if settings['relationship_context']['roles'] else 'relationship_roles_not_supplied',
        scope='supported_role_focal_entries; not_parent_birth_transits')
    unavailable['synastry'] = dict(status='computed' if settings['mode'] == 'synastry' else 'not_computed',
                                  reason='requested_mode')
    # Every natal point remains accessible, whether or not the partner touches it.
    natal_entries = {who: [dict(id=f'{who}:{point}', point=point,
        point_path=f'/relationship_profiles/{who}/points/{point}',
        natal_context_edge_ids=[e['id'] for e in adjacent(profiles[who]['natal_aspects'], point)],
        configuration_ids=associations['configuration_memberships'][who][point],
        natal_background_ref=(f'/natal_backgrounds/{who}/points/{point}'
            if point in associations['natal_backgrounds'][who]['points'] else None),
        activation_cluster_ids=[c['id'] for c in clusters if c['target_person'] == who and
            c['target_point'] == next((a for a, b in OPPOSITES.items() if b == point), point)])
        for point in DISPLAY_PLANETS + AXES] for who in people}
    from services.relationship_observation_routes import build_routes
    from services.relationship_observation_contexts import build_context_views
    context_views = build_context_views(profiles, contacts, settings)
    context_views['observation_complex_links'] = build_complex_links(complexes, contacts, settings)
    from services.relationship_observation_lenses import build_scenario_lenses
    context_views['scenario_observation_lenses'] = build_scenario_lenses(profiles, contacts, paths, overlays, settings)
    routes = build_routes(profiles, contacts, paths, overlays, associations, settings, complexes, context_views)
    unavailable['observation_routes'] = dict(status='computed',
        scope='selection_reasons_and_bounded_context_only; cross_views_require_synastry')
    unavailable['observation_complexes'] = dict(status='computed',
        scope='conjunction_pair_one_hop_context_and_named_pattern_conjunction_satellites; not_activation')
    unavailable['observation_complex_links'] = dict(status='computed' if settings['mode'] == 'synastry' else 'not_computed',
        reason='requested_mode', scope='factorized_existing_contacts_and_complex_memberships_not_new_evidence')
    unavailable['parallel_ruler_context'] = dict(status='computed', scope='background_only; selected_ruler_unchanged')
    unavailable['hemisphere_background'] = dict(status='computed', scope='Sun_through_Pluto_actual_houses')
    unavailable['scenario_observation_lenses'] = dict(status='computed',
        scope='four_scenario_and_ch2_projection_conditions; not_planet_filter_or_all_interpretations')
    unavailable['special_contact_views'] = dict(status='computed' if settings['mode'] == 'synastry' else 'not_computed',
        scope='parallel_lists_not_weights', reason='requested_mode')
    for key in ('shared_natal_pairs', 'descendant_sign_correspondences'):
        unavailable[key] = dict(status='computed' if settings['mode'] == 'synastry' else 'not_computed',
                                reason='requested_mode', scope='factual_comparison_only')
    result = dict(status='ok', schema_version=VERSION, completeness='partial',
        birth_context=deepcopy(birth_context), settings=deepcopy(settings), source_geometry=deepcopy(source_geometry),
        relationship_profiles=profiles, contacts=contacts, observation_paths=paths, **associations,
        observation_review=review, structure_display=structure_display, observation_complexes=complexes, **routes, **context_views,
        activation_clusters=clusters, source_contact_groups=groups, house_overlays=overlays,
        projected_planet_overlays=projected, saturn_reciprocity=dict(
            status='computed' if settings['mode'] == 'synastry' else 'not_computed',
            value=reciprocity if settings['mode'] == 'synastry' else None, contact_ids=saturn,
            scope='evaluated_aspects_only', rule_id='reciprocity'),
        natal_observation_entries=natal_entries,
        manual_observation_interface=dict(tool='prepare_relationship_observation_note',
            questions=[dict(id=k, prompt=v, rule_id='workshop_observation') for k, v in QUESTIONS.items()],
            storage='caller_owned', answers_inferred=False, statements_are_calculation_facts=False),
        nodal_contact_ids=[c['id'] for c in contacts if 'north_node' in (c['first_point'], c['second_point'])],
        nodal_bending_contact_ids=[c['id'] for c in contacts if c['angle'] == 90 and 'north_node' in (c['first_point'], c['second_point'])],
        angle_contact_ids=[c['id'] for c in contacts if any(p in AXES for p in (c['first_point'], c['second_point']))],
        counts=dict(unique_contacts=len(contacts), observation_paths=len(paths), activation_clusters=len(clusters)),
        layer_availability=unavailable, provenance=provenance(), interpretations=[])
    from services.relationship_observation_timing import build_timing_observations
    result['timing_observations'] = build_timing_observations(result, timing_sources)
    unavailable['timing'] = dict(status=result['timing_observations']['status'],
        reason='explicit_time_and_orbs' if settings['include_timing'] else 'not_requested',
        scope='selected_time_only; no_event_search_or_symbolic_carrier_matching')
    unavailable['timing_window'] = dict(status='not_computed', reason='not_requested_or_requires_source_calculation')
    birth_view = result['timing_observations'].get('childbirth_observation', {})
    unavailable['childbirth'] = dict(status=birth_view.get('status', 'not_computed'),
        reason='resolved_child_birth' if birth_view.get('status') == 'computed' else 'childbirth_event_not_requested')
    comparison = result['timing_observations'].get('progressed_synastry_comparison', {})
    unavailable['progressed_synastry_comparison'] = dict(status=comparison.get('status', 'not_computed'),
        reason='same_orb_selected_snapshot_comparison' if comparison.get('status') == 'computed' else 'not_requested')
    return result


def calculate_observation_data(*, person_a, person_b=None, **options):
    from services.mcp_natal import _compute_source, _input_error
    from services.calculator import BirthContextError
    from services.mcp_contract import ClarificationRequired
    try:
        settings = settings_for(**options)
        geometries, contexts, graphs = {}, {}, {}
        for who, birth in (('a', person_a), ('b', person_b)):
            if who == 'b' and birth is None and settings['mode'] == 'natal':
                continue
            try:
                if not isinstance(birth, dict):
                    raise ValueError(f'person_{who} requires exact birth data')
                summary = _compute_source(**{k: birth.get(k) for k in
                    ('year', 'month', 'day', 'hour', 'minute', 'location_id', 'fold')}, house_system='placidus')
                geometries[who] = geometry_from_summary(summary, who)
                contexts[who] = summary['birth_context']
                from services.natal_structure_graph import build_structure_graph
                graphs[who] = build_structure_graph(summary)
                graphs[who]['completeness'] = 'full'
            except BirthContextError as exc:
                exc.mcp_field_prefix = f'person_{who}.'
                raise
            except ClarificationRequired as exc:
                raise ClarificationRequired([f'person_{who}.{k}' for k in exc.response['required_fields']]) from None
            except RuntimeError as exc:
                # The legacy adapter wraps Swiss house errors in RuntimeError.
                # Recognize only that explicit failure; never hide other engine bugs.
                if not str(exc).startswith('引擎计算失败: swisseph.houses:'):
                    raise
                return dict(status='unavailable', failed_person=who,
                    error='Placidus houses could not be calculated; observation v0.14 requires houses and angles.',
                    layer_availability={f'{who}.houses_and_angles': {
                        'status': 'unavailable', 'reason': 'placidus_calculation_failed'}},
                    next_action='review_birth_data_or_use_house_independent_tool')
        from services.relationship_observation_timing import resolve_event_settings, verify_natal_node_sources
        from services.ephemeris_guard import EphemerisModeError
        import swisseph as swe
        try:
            verify_natal_node_sources(geometries, contexts)
        except (swe.Error, EphemerisModeError):
            return dict(status='unavailable', error='Natal nodes do not have a verified mean-node source; no replacement geometry returned.',
                        layer_availability={'nodes': dict(status='unavailable', reason='node_source_mismatch_or_unavailable')})
        settings = resolve_event_settings(settings, contexts)
        timing_sources = None
        if settings['include_timing']:
            from services.relationship_observation_timing import calculate_timing_sources
            from services.ephemeris_guard import EphemerisModeError
            import swisseph as swe
            try:
                timing_sources = calculate_timing_sources({'a': person_a, 'b': person_b}, contexts, settings)
            except (swe.Error, EphemerisModeError):
                return dict(status='unavailable', error='Timing source could not be calculated without ephemeris or house fallback.',
                    layer_availability={'timing': dict(status='unavailable', reason='timing_source_unavailable')})
        result = build_observation(geometries, contexts, settings, graphs, timing_sources)
        from services.relationship_observation_windows import attach_window
        if settings['include_timing']:
            try:
                return attach_window(result, {'a': person_a, 'b': person_b})
            except (swe.Error, EphemerisModeError):
                return dict(status='unavailable', error='Timing window source unavailable; no fallback results returned.',
                            layer_availability={'timing_window': dict(status='unavailable', reason='source_unavailable')})
        return attach_window(result, {})
    except (ValueError, BirthContextError) as exc:
        return _input_error(exc)


def validate_observation_output(data, args):
    """Rebuild bounded associations from supplied geometry; not independent ephemeris proof."""
    from services.mcp_validation import require, context
    options = {k: v for k, v in args.items() if k not in ('person_a', 'person_b')}
    settings = settings_for(**options)
    expected_people = {'a', 'b'} if args.get('person_b') is not None else {'a'}
    require(set(data['source_geometry']) == set(data['birth_context']) == expected_people,
            '/source_geometry', 'people_match_inputs')
    for who in expected_people:
        context(data['birth_context'][who], args.get('person_' + who) or {}, '/birth_context/' + who)
    from services.mcp_structure_graph import validate_graph_output
    graphs = {}
    for who in expected_people:
        graph = data['natal_backgrounds'][who]['source_graph']
        validate_graph_output(graph)
        require(graph['birth_context'] == data['birth_context'][who],
                '/natal_backgrounds/' + who, 'same_birth_context')
        require(all(n['lon'] == round(data['source_geometry'][who]['points'][n['id']], 4) for n in graph['nodes']),
                '/natal_backgrounds/' + who, 'same_planet_geometry')
        require(all(graph['axes'][short]['lon'] == data['source_geometry'][who]['points'][point]
                    for short, point in [('asc', 'ascendant'), ('mc', 'midheaven')]),
                '/natal_backgrounds/' + who, 'same_axis_geometry')
        graphs[who] = graph
    from services.relationship_observation_timing import resolve_event_settings, verify_natal_node_sources
    verify_natal_node_sources(data['source_geometry'], data['birth_context'])
    settings = resolve_event_settings(settings, data['birth_context'])
    timing_sources = None
    if settings['include_timing']:
        from services.relationship_observation_timing import calculate_timing_sources
        timing_sources = calculate_timing_sources(
            {who: args['person_'+who] for who in expected_people}, data['birth_context'], settings)
    expected = build_observation(data['source_geometry'], data['birth_context'], settings, graphs, timing_sources)
    from services.relationship_observation_windows import attach_window
    attach_window(expected, {who: args['person_'+who] for who in expected_people})
    import json
    require(json.dumps(data, sort_keys=True, allow_nan=False) == json.dumps(expected, sort_keys=True, allow_nan=False),
            '/', 'observation_geometry_associations_counts_and_rules_match')
