"""Source-backed selection and bounded review routes over existing chart facts.

Routes explain where to look; only the original contacts establish cross geometry.
No recursive traversal, salience filter, psychological inference or extra ephemeris.
"""
from itertools import combinations

from services.relationship_charts import PLANETS

ELEMENTS = ('fire', 'earth', 'air', 'water')
CANONICAL = {'south_node': 'north_node', 'descendant': 'ascendant',
             'imum_coeli': 'midheaven'}


def route_provenance():
    locators = {
        'candidate_indicators': ('Chapter Two / The Natal Chart; Chapter Seven / summaries',
            'sign, house and aspects', 'natal indicators and current scenario; no inferred difficulty'),
        'candidate_communication': ('Chapter Three / Inner planets in synastry',
            'Mercury is very important in relationships.', 'communication entry in every relationship type'),
        'candidate_projection_houses': ('Chapter Three / House overlays',
            'planets that we have in the seventh and eighth houses', 'retain existing 7/8H candidates'),
        'candidate_projection_context': ('Chapter Two / What else can we project?',
            'We should look at any oppositions in the chart.', 'Saturn, twelfth-house planets and natal opposition endpoints are candidates, not actual projections'),
        'candidate_node_context': ('Chapter Three / Nodes',
            'If you have a planet on a Node in your personal chart', 'planet conjunct either natal node under the evaluated orb profile'),
        'candidate_house_context': ('Chapter Seven / Debbie Reynolds chart work',
            'Her fifth house is ruled by Aquarius', 'selected house ruler and existing natal aspects; no dynamic rulership propagation'),
        'candidate_natal_route': ('Chapter Three / Cross-aspects; Chapter Five / Chart work',
            'your experience is through your planet', 'typed one-hop context, including the roles of related natal points'),
        'candidate_first_house_venus': ('Chapter Three / House overlays / Taylor and Burton',
            'check the aspects to the Ascendant and the chart ruler', 'only Venus overlay in first house receives this specific context'),
        'candidate_overlay_context': ('Chapter Three / House overlays',
            'The house does not set off his Venus', 'target house context and same-source actual contacts remain distinct'),
        'candidate_comparisons': ('Chapter Three / Inner planets; Chapter Six / Tom and Katie; Chapter Seven / Simon and Garfunkel',
            'his Jupiter squares her Neptune and her Jupiter squares his Neptune', 'exact reciprocal contact pairs, same-planet natal contexts and Sun/Moon/Mercury element comparison; no similarity score'),
        'candidate_moon_venus': ('Chapter Two / Venus and Mars',
            'look to see if the Moon and Venus are in different elements', 'two natal contexts with their actual evaluated aspects'),
        'candidate_nodal_houses': ('Chapter Two / Planets in the seventh house',
            'When the Nodes are in the first and seventh houses', 'one nodal-axis candidate, both actual house and sign endpoints; no seventh-cusp rule for nodes'),
        'candidate_chart_ruler_seventh': ('Chapter Two / The Descendant sign',
            'If the ruling planet of the Ascendant is found in the seventh house', 'additional identity for selected chart ruler in actual seventh house'),
        'shared_natal_pairs': ('Chapter Four / Taylor and Burton; Chapter Eight / Case Study',
            'He’s Sun square Neptune and she’s Sun opposite Neptune', 'same unordered natal planet pair; preserve both actual aspect types and orbs, not a shared psychological theme'),
        'descendant_sign_correspondence': ('Chapter Eight / Case Study',
            'his Scorpio Descendant longing as she has Moon in Scorpio', 'exact sign equality with partner Sun through Pluto or Chiron; no prominence or attraction inferred'),
        'bounded_observation_complex': ('Chapter Three / Cross-aspects; Chapter Five / Chart work',
            'Moon–Pluto square to Mars', 'conjunction-pair neighborhoods and named-pattern conjunction satellites, including axis variants; grouping and stop rules are engineering decisions'),
    }
    result = {key: dict(concept_provenance='JG_EXPLICIT', operational_rule_provenance='ENGINE_DERIVED',
                        chapter=chapter, quote=quote, scope=scope)
              for key, (chapter, quote, scope) in locators.items()}
    result['candidate_route_policy'] = dict(concept_provenance='ENGINE_DERIVED',
        operational_rule_provenance='ENGINE_DECISION',
        scope='nonrecursive review paths; multiple reasons are not independent evidence or weights')
    return result


def point_ref(who, point):
    return f'/relationship_profiles/{who}/points/{point}'


def candidate_reasons(who, point, profile, settings):
    """A reason carries its own factual source; multiple reasons are not votes."""
    base = f'/relationship_profiles/{who}'
    pos = profile['points'][point]
    rows = []

    def add(role, rule, refs):
        rows.append(dict(id=role, role=role, rule_id=rule, fact_refs=refs))

    if point in settings['scenario']['points']:
        add('scenario_planet', 'candidate_indicators', [point_ref(who, point), '/settings/scenario/points'])
    if point == 'mercury':
        add('communication_indicator', 'candidate_communication', [point_ref(who, point)])
    if point == 'north_node' and {profile['points'][p]['house'] for p in ('north_node', 'south_node')} == {1, 7}:
        add('nodal_axis_first_seventh', 'candidate_nodal_houses',
            [point_ref(who, p) for p in ('north_node', 'south_node')])
    if profile['houses'][0]['ruler'] == point and pos['house'] == 7:
        add('chart_ruler_in_seventh', 'candidate_chart_ruler_seventh',
            [point_ref(who, point), base + '/houses/0', '/settings/ruler_profile'])
    if point in profile['projected_planets']:
        add('projection_house_planet', 'candidate_projection_houses',
            [point_ref(who, point), base + '/projected_planets'])
    if point in ('ascendant', 'descendant'):
        add('asc_dsc_axis', 'candidate_indicators', [point_ref(who, point)])
    if point in ('midheaven', 'imum_coeli'):
        add('parental_house_axis', 'candidate_indicators',
            [point_ref(who, point), '/settings/parental_house_mapping_profile'])
    parental = profile['parental_context']
    for parent in ('father', 'mother'):
        if point in parental[parent + '_points']:
            add(parent + '_indicator', 'candidate_indicators', [base + '/parental_context/' + parent + '_points'])
    for i, house in enumerate(profile['houses']):
        ref = f'{base}/houses/{i}'
        for relation, present in (('ruler', house['ruler'] == point), ('planet', point in house['planets'])):
            if not present:
                continue
            if house['house'] in settings['scenario']['houses']:
                add(f'scenario_house_{house["house"]}_{relation}', 'candidate_house_context',
                    [ref, '/settings/scenario/houses'])
            if house['house'] in (parental['father_house'], parental['mother_house']):
                add(f'parental_house_{house["house"]}_{relation}', 'candidate_indicators',
                    [ref, base + '/parental_context', '/settings/parental_house_mapping_profile'])
    if point in PLANETS:
        if pos['house'] == 12:
            add('projection_twelfth_candidate', 'candidate_projection_context', [point_ref(who, point)])
        if point == 'saturn':
            add('projection_saturn_candidate', 'candidate_projection_context', [point_ref(who, point)])
        opposition_refs, node_refs = [], []
        for i, edge in enumerate(profile['natal_aspects']):
            ends = {edge['first_point'], edge['second_point']}
            if point not in ends:
                continue
            if edge['angle'] == 180 and ends <= set(PLANETS):
                opposition_refs.append(f'{base}/natal_aspects/{i}')
            if 'north_node' in ends and edge['angle'] in (0, 180):
                node_refs.append(f'{base}/natal_aspects/{i}')
        if opposition_refs:
            add('projection_opposition_candidate', 'candidate_projection_context', opposition_refs)
        if node_refs:
            add('natal_node_conjunction_candidate', 'candidate_node_context', node_refs +
                [point_ref(who, 'north_node'), point_ref(who, 'south_node')])
    from services.relationship_observation_contexts import context_candidate_reasons
    rows.extend(context_candidate_reasons(who, point, profile, settings))
    return sorted(rows, key=lambda r: r['id'])


def is_relationship_role(role):
    """One classifier shared by the review lens and target-point sorting."""
    return role.startswith(('scenario_', 'projection_', 'context_')) or role in (
        'asc_dsc_axis', 'communication_indicator', 'natal_node_conjunction_candidate',
        'nodal_axis_first_seventh', 'chart_ruler_in_seventh')


def build_routes(profiles, contacts, observation_paths, overlays, associations, settings, complexes, context_views):
    candidates, paths, point_path_ids, candidate_refs = {}, [], {}, {}
    by_pair = {(c['first_point'], c['second_point']): (i, c) for i, c in enumerate(contacts)}
    edge_refs = {who: {e['id']: f'/relationship_profiles/{who}/natal_aspects/{i}'
                      for i, e in enumerate(prof['natal_aspects'])} for who, prof in profiles.items()}

    def add_path(id_, kind, who, origin_ref, target_ref, fact_refs, **extra):
        paths.append(dict(id=id_, kind=kind, person=who, origin_ref=origin_ref,
                          target_ref=target_ref, fact_refs=fact_refs,
                          creates_direct_contact=False, **extra))
        return id_

    def canonical(point):
        return CANONICAL.get(point, point)

    def natal_edges(who, point):
        return [e for e in profiles[who]['natal_aspects']
                if canonical(point) in (e['first_point'], e['second_point'])]

    # Selection happens even in natal-only mode, before any partner is required.
    for who, prof in profiles.items():
        candidates[who] = []
        for point in prof['points']:
            reasons = candidate_reasons(who, point, prof, settings)
            if not reasons:
                continue
            candidate_refs[(who, point)] = f'/natal_observation_candidates/{who}/{len(candidates[who])}'
            hits = [p for p in observation_paths if p['target_person'] == who and
                    p['target_point'] == canonical(point)]
            candidates[who].append(dict(id=f'{who}:{point}', person=who, point=point,
                point_ref=point_ref(who, point), selection_reasons=reasons,
                contact_ids=sorted({p['contact_id'] for p in hits}),
                observation_path_ids=sorted(p['id'] for p in hits),
                configuration_ids=list(associations['configuration_memberships'][who][point]),
                review_path_ids=[], actual_projection='not_inferred',
                axis_endpoint_refs=([point_ref(who, p) for p in ('north_node', 'south_node')]
                                    if point == 'north_node' else [])))

    # A single static edge view per origin is shared by all its cross contacts.
    # Do not expand a neighbor again; fixed-axis variants remain explicit facts.
    for who, prof in profiles.items():
        for point in prof['points']:
            ids = point_path_ids[(who, point)] = []
            origin = point_ref(who, point)
            for edge in natal_edges(who, point):
                other = edge['second_point'] if edge['first_point'] == canonical(point) else edge['first_point']
                ids.append(add_path(f'natal:{who}:{point}:{edge["id"]}', 'natal_aspect_context', who,
                    origin, point_ref(who, other), [edge_refs[who][edge['id']]],
                    natal_aspect_id=edge['id'], canonical_origin_point=canonical(point),
                    target_point=other, target_candidate_ref=candidate_refs.get((who, other)),
                    rule_id='candidate_natal_route'))
            for i, config in enumerate(associations['natal_configurations'][who]):
                if point in config['members']:
                    ref = f'/natal_configurations/{who}/{i}'
                    ids.append(add_path(f'configuration:{who}:{point}:{config["id"]}', 'configuration_context',
                        who, origin, ref, [ref], configuration_id=config['id'],
                        rule_id='configuration_membership'))
            for i, complex_ in enumerate(complexes['people'][who]):
                if canonical(point) in complex_['core_members']:
                    ref = f'/observation_complexes/people/{who}/{i}'
                    ids.append(add_path(f'complex:{who}:{point}:{complex_["id"]}', 'complex_context',
                        who, origin, ref, [ref], complex_id=complex_['id'],
                        rule_id='bounded_observation_complex'))
        for i, house in enumerate(prof['houses']):
            ruler = house['ruler']
            ref = f'/relationship_profiles/{who}/houses/{i}'
            add_path(f'ruler:{who}:{house["house"]}', 'house_ruler_context', who,
                ref, point_ref(who, ruler), [ref, '/settings/ruler_profile'],
                target_point=ruler, target_candidate_ref=candidate_refs.get((who, ruler)),
                natal_context_path_ids=point_path_ids[(who, ruler)],
                rule_id='candidate_house_context')
        for i, house in enumerate(context_views['house_ruler_comparisons'][who]):
            for j, route in enumerate(house['routes']):
                ruler = route['point']
                ref = f'/house_ruler_comparisons/{who}/{i}/routes/{j}'
                add_path(f'parallel_ruler:{who}:{house["house"]}:{ruler}', 'parallel_house_ruler_context', who,
                    house['house_ref'], point_ref(who, ruler), [ref],
                    target_point=ruler, policies=route['policies'], selected=route['selected'],
                    natal_context_path_ids=point_path_ids[(who, ruler)], rule_id='parallel_ruler_context')
    for who, rows in candidates.items():
        for row in rows:
            row['review_path_ids'] = list(point_path_ids[(who, row['point'])]) + [
                p['id'] for p in paths if p['kind'] in ('house_ruler_context', 'parallel_house_ruler_context')
                and p['person'] == who and p['target_point'] == row['point']]

    contact_refs = {c['id']: f'/contacts/{i}' for i, c in enumerate(contacts)}
    for i, entry in enumerate(observation_paths):
        who, point = entry['target_person'], entry['target_point']
        add_path(f'direct:{entry["id"]}', 'direct_contact', who,
            point_ref(entry['source_person'], entry['source_point']), point_ref(who, point),
            [contact_refs[entry['contact_id']], f'/observation_paths/{i}'],
            contact_id=entry['contact_id'], source_person=entry['source_person'],
            target_point=point, target_candidate_ref=candidate_refs.get((who, point)),
            natal_context_path_ids=point_path_ids[(who, point)], rule_id='candidate_natal_route')

    overlay_contexts = []
    for i, overlay in enumerate(overlays):
        who, source, point = overlay['target_person'], overlay['source_person'], overlay['source_point']
        house = profiles[who]['houses'][overlay['house'] - 1]
        ref = f'/house_overlays/{i}'
        house_ref = f'/relationship_profiles/{who}/houses/{overlay["house"] - 1}'
        side = 'first' if source == 'a' else 'second'
        hit_ids = [c['id'] for c in contacts if c[side + '_point'] == canonical(point)]
        special = point == 'venus' and overlay['house'] == 1
        next_cusp = profiles[who]['houses'][overlay['house'] % 12]['cusp_longitude']
        row = dict(id=overlay['id'], overlay_ref=ref, source_person=source, target_person=who,
            source_point_ref=point_ref(source, point), target_house_ref=house_ref,
            target_occupant_refs=[point_ref(who, p) for p in house['planets']],
            target_ruler_ref=point_ref(who, house['ruler']),
            ruler_review_path_id=f'ruler:{who}:{overlay["house"]}',
            same_source_contact_ids=sorted(hit_ids),
            distance_to_next_target_cusp=(next_cusp - profiles[source]['points'][point]['longitude']) % 360,
            first_house_venus_context=(dict(ascendant_ref=point_ref(who, 'ascendant'),
                chart_ruler_ref=point_ref(who, house['ruler']),
                ascendant_review_path_ids=point_path_ids[(who, 'ascendant')],
                chart_ruler_review_path_ids=point_path_ids[(who, house['ruler'])],
                rule_id='candidate_first_house_venus') if special else None),
            rule_id='candidate_overlay_context')
        overlay_contexts.append(row)
        add_path(f'overlay:{overlay["id"]}', 'overlay_context', who,
            point_ref(source, point), house_ref, [ref],
            overlay_context_ref=f'/overlay_contexts/{i}', rule_id='candidate_overlay_context')

    def side_context(who, point):
        return dict(person=who, point=point, point_ref=point_ref(who, point),
                    candidate_ref=candidate_refs.get((who, point)),
                    natal_context_path_ids=point_path_ids[(who, point)])

    comparisons = dict(status='computed',
        cross_chart_status='computed' if settings['mode'] == 'synastry' else 'not_computed',
        reason='requested_mode', reciprocal_planet_pairs=[], same_planet_contexts=[],
        luminary_mercury_elements=[], moon_venus_natal=[], shared_natal_pairs=[],
        descendant_sign_correspondences=[], rule_id='candidate_comparisons')
    for who, prof in profiles.items():
        elems = {p: ELEMENTS[int(prof['points'][p]['longitude'] // 30) % 4] for p in ('moon', 'venus')}
        comparisons['moon_venus_natal'].append(dict(person=who, status='computed',
            moon=side_context(who, 'moon'), venus=side_context(who, 'venus'), elements=elems,
            same_element=elems['moon'] == elems['venus'],
            natal_aspect_ids=[e['id'] for e in natal_edges(who, 'moon')
                              if {e['first_point'], e['second_point']} == {'moon', 'venus'}],
            aspect_scope='evaluated_aspects_only', rule_id='candidate_moon_venus'))
    if settings['mode'] == 'synastry':
        comparisons['element_distribution'] = [dict(dimension=dimension, category=key,
            a_ref=f'/relationship_profiles/a/{dimension}/{key}', b_ref=f'/relationship_profiles/b/{dimension}/{key}',
            count_difference=profiles['a'][dimension][key]['count']-profiles['b'][dimension][key]['count'],
            psychological_lack='not_inferred')
            for dimension in ('element_balance', 'modality_balance') for key in profiles['a'][dimension]]
        planet_pairs = {who: {tuple(sorted((e['first_point'], e['second_point']))): e
                        for e in prof['natal_aspects']
                        if {e['first_point'], e['second_point']} <= set(PLANETS)}
                        for who, prof in profiles.items()}
        for pair in sorted(set(planet_pairs['a']) & set(planet_pairs['b'])):
            a, b = (planet_pairs[who][pair] for who in ('a', 'b'))
            hits = [(i, c) for i, c in enumerate(contacts)
                    if c['first_point'] in pair and c['second_point'] in pair]
            comparisons['shared_natal_pairs'].append(dict(id='shared_natal:' + ':'.join(pair),
                points=list(pair), a_natal_aspect_ref=edge_refs['a'][a['id']],
                b_natal_aspect_ref=edge_refs['b'][b['id']],
                a=[side_context('a', p) for p in pair], b=[side_context('b', p) for p in pair],
                same_aspect=a['angle'] == b['angle'],
                contact_ids=[c['id'] for _, c in hits], contact_refs=[f'/contacts/{i}' for i, _ in hits],
                shared_psychological_theme='not_inferred', rule_id='shared_natal_pairs'))
        for who, other in (('a', 'b'), ('b', 'a')):
            sign = profiles[who]['points']['descendant']['sign']
            for point in PLANETS:
                if profiles[other]['points'][point]['sign'] == sign:
                    comparisons['descendant_sign_correspondences'].append(dict(
                        id=f'{who}:descendant={other}:{point}:sign', person=who, partner=other,
                        partner_point=point, sign=sign, descendant_ref=point_ref(who, 'descendant'),
                        partner_point_ref=point_ref(other, point),
                        match_kind='exact_sign_equality', prominence='not_inferred', attraction='not_inferred',
                        creates_direct_contact=False, rule_id='descendant_sign_correspondence'))
        for p, q in combinations(sorted(PLANETS), 2):
            if (p, q) in by_pair and (q, p) in by_pair:
                hits = [by_pair[(p, q)], by_pair[(q, p)]]
                comparisons['reciprocal_planet_pairs'].append(dict(id=f'reciprocal:{p}:{q}', points=[p, q],
                    contact_ids=[c['id'] for _, c in hits], contact_refs=[f'/contacts/{i}' for i, _ in hits],
                    same_aspect=hits[0][1]['angle'] == hits[1][1]['angle']))
        for point in PLANETS:
            comparisons['same_planet_contexts'].append(dict(point=point,
                a=side_context('a', point), b=side_context('b', point),
                contact_ids=[by_pair[(point, point)][1]['id']] if (point, point) in by_pair else []))
        for point in ('sun', 'moon', 'mercury'):
            elems = {who: ELEMENTS[int(profiles[who]['points'][point]['longitude'] // 30) % 4]
                     for who in ('a', 'b')}
            comparisons['luminary_mercury_elements'].append(dict(point=point, elements=elems,
                same_element=elems['a'] == elems['b'],
                fact_refs=[point_ref(who, point) for who in ('a', 'b')]))
    return dict(natal_observation_candidates=candidates, review_paths=sorted(paths, key=lambda p: p['id']),
        overlay_contexts=overlay_contexts, observation_comparisons=comparisons,
        observation_route_policy=dict(rule_id='candidate_route_policy',
            paths_are='observation_routes_not_activation_propagation', natal_neighbor_depth=1,
            house_ruler_traversal='one_house_to_its_ruler_then_existing_natal_context',
            configuration_scope='legacy_templates_plus_separate_bounded_complex_context',
            candidates_require_cross_contact=False, selection_uses_natal_salience=False,
            projection_state='not_inferred', interpretation='not_computed',
            evidence_counts_are_additive=False, affects_contact_counts=False,
            aspect_scope='evaluated_aspects_only', order='stable_identifiers_not_importance'))
