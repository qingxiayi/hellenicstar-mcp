"""Auditable structural candidate routes and condition facts, without interpretation.

These review routes are a project policy, not a reconstruction of an unknown
report formula. Dignity tables are shared with the existing classical engine.
"""
import copy
from services.classical_engine import DOROTHEAN_TRIPLICITY


def triplicity_context(planet, sign_idx, condition):
    if not condition:
        return dict(status='classical_conditions_not_defined_for_outer_planets')
    roles = dict(zip(('day', 'night', 'participating'), DOROTHEAN_TRIPLICITY[sign_idx]))
    essential = condition['essential']
    active = essential.get('active_triplicity_lord')
    sect_role=next((role for role in ('day','night') if roles[role]==active),None)
    order=([roles['day'],roles['night'],roles['participating']] if sect_role=='day' else
           [roles['night'],roles['day'],roles['participating']] if sect_role=='night' else None)
    member=planet in roles.values()
    priority=order.index(planet)+1 if order and member else None
    return dict(status='available', version='triplicity-context-v2', rulers=roles,
                planet_roles=[role for role, ruler in roles.items() if ruler == planet],
                is_triplicity_ruler=member, sect_order=order, sect_priority=priority,
                order_status='available' if order else 'unknown_sect',
                active_lord=active, active_sect_role=sect_role,
                counted_by_engine=essential['triplicity'],
                counting_reason=('primary_ruler_in_current_sect' if priority==1 else
                                 'secondary_ruler_not_counted_by_active_only_policy' if priority==2 else
                                 'participating_ruler_not_counted_by_active_only_policy' if priority==3 else
                                 'not_a_ruler_of_this_triplicity' if not member else 'unknown_sect'),
                peregrine_under_active_policy=essential.get('peregrine'),
                meaning='Ruler identity, sect priority and dignity credit are separate. '
                        'Uncredited does not mean non-member; peregrine is scoped to the active dignity policy, '
                        'not absence of all relationships or resources.',
                policy='active_day_or_night_only; participating and other-sect roles are disclosed, not scored')


def condition_context(profile):
    """Keep house availability and state dimensions separate, without grading."""
    houses = {}
    for system, house in profile['houses'].items():
        ruled = sorted(r['house'] for r in profile['house_ruler_links'][system])
        houses[system] = dict(
            located_house=house, ruled_houses=ruled,
            category=None if house is None else 'angular' if house in (1,4,7,10)
                     else 'succedent' if house in (2,5,8,11) else 'cadent',
            in_6_8_12=None if house is None else house in (6,8,12),
            rules_6_8_12=None if house is None else sorted(set(ruled) & {6,8,12}),
            availability='unavailable' if house is None else 'available')
    condition = profile['condition']
    return dict(houses=houses, essential=copy.deepcopy(condition['essential']) if condition else None,
        triplicity_context=copy.deepcopy(profile.get('triplicity_context')),
        retrograde=profile['retrograde'], solar=copy.deepcopy(condition.get('solar')) if condition else None,
        axis_contacts=copy.deepcopy(profile['axis_contacts']),
        availability=profile['condition_availability'], aggregation=None)


def resource_review(planet, profiles, reception_rows=()):
    """Group direct review routes by counterpart; retain limitations and sources."""
    profile = profiles[planet]
    candidates = {}

    def add(other, kind, detail, refs):
        if other == planet:
            return  # Self rulership is not an external resource.
        candidates.setdefault(other, []).append(dict(kind=kind, detail=detail, source_refs=refs))

    add(profile['dispositor']['planet'], 'dispositor', profile['path'],
        ['/source_graph/dispositor'])
    for reception in profile['receptions']:
        other = next(p for p in (reception['planet1'], reception['planet2']) if p != planet)
        add(other, 'mutual_reception', reception,
            ['/source_graph/receptions/mutual_receptions'])
    for i, relation in enumerate(reception_rows):
        if planet in (relation['host'], relation['guest']) and relation['meets_dignity_threshold']:
            other = relation['guest'] if planet == relation['host'] else relation['host']
            add(other, 'dignity_relation', relation, [f'/reception_facts/rows/{i}'])
    for edge in profile['aspects']:
        if edge['angle'] in (0, 60, 90, 120, 180):
            other = edge['to'] if edge['from'] == planet else edge['from']
            kind = 'sextile_or_trine' if edge['angle'] in (60,120) else 'conjunction' if edge['angle'] == 0 else 'square_or_opposition'
            add(other, kind, edge, [
                '/source_graph/aspects'])
    for configuration in profile['configurations']:
        for other, counterpart in sorted(profiles.items()):
            match = next((m for m in counterpart['configurations'] if m['id'] == configuration['id']), None)
            if match:
                add(other, 'shared_configuration', dict(id=configuration['id'],
                    target_roles=configuration['roles'], counterpart_roles=match['roles']),
                    ['/priority_configurations'])

    result = []
    for other, routes in sorted(candidates.items()):
        # Snapshot only factual fields: no recursive resource reviews or ratings.
        counterpart = profiles[other]
        state = {key: copy.deepcopy(counterpart[key]) for key in (
            'condition', 'condition_availability', 'triplicity_context',
            'retrograde', 'houses', 'house_ruler_links', 'aspects', 'path',
            'axis_contacts', 'source_refs')}
        state['condition_context'] = condition_context(counterpart)
        result.append(dict(planet=other, routes=routes, counterpart_state=state,
                           assessment='not_evaluated'))
    return dict(policy_version='structural-candidates-v2', candidates=result,
                intrinsic=dict(planet=planet, condition_context=condition_context(profile),
                    configurations=copy.deepcopy(profile['configurations']),
                    source_refs=profile['source_refs'], assessment='facts_only'),
                status='candidates_only' if result else 'no_matching_review_route',
                verdict=None,
                limitation='Dispositor, dignity relations, all current Ptolemaic contacts and shared configurations; intrinsic facts are separate. '
                'Overlapping routes are not independent proofs. No efficacy, support verdict or ranking inferred; '
                'absence of a route does not mean absence of resources.')
