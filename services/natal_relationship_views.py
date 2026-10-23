"""Purpose-specific views of existing relationships; no efficacy or new rules.

The complete legacy candidate pool remains unchanged. States are returned once
and referenced by both endpoints so a selected view is self-contained.
"""
import copy
import json
import math

from services.natal_resource_context import condition_context


VERSION = 'natal-relationship-views-v1'
GROUPS = ('host_of_target', 'guest_of_target', 'exchange', 'degree_contact',
          'shared_configuration', 'unclassified')
ASPECT_KINDS = {'conjunction': (0,), 'sextile_or_trine': (60, 120),
                'square_or_opposition': (90, 180)}


def classify_routes(target, other, routes, orb_view):
    """Classify direction and geometry without using condition as a veto."""
    groups = set()
    for route in routes:
        kind, detail = route['kind'], route['detail']
        if kind == 'dispositor':
            groups.add('host_of_target')
        elif kind == 'dignity_relation':
            if {detail['host'], detail['guest']} != {target, other}:
                raise ValueError('Dignity route endpoints do not match relationship')
            groups.add('host_of_target' if detail['guest'] == target else 'guest_of_target')
        elif kind == 'mutual_reception':
            groups.add('exchange')
        elif kind in ASPECT_KINDS:
            orb = detail['orb']
            if (type(orb) not in (int, float) or not math.isfinite(orb)
                    or not 0 <= orb <= orb_view or detail['angle'] not in ASPECT_KINDS[kind]):
                raise ValueError('Degree contact is outside the selected aspect view')
            groups.add('degree_contact')
        elif kind == 'shared_configuration':
            groups.add('shared_configuration')
        else:
            groups.add('unclassified')
    if not groups:
        groups.add('unclassified')
    return [name for name in GROUPS if name in groups]


def build_relationship_views(result):
    profiles = result['planet_profiles']
    orb_view = result['method']['config']['orb_view']
    dynamics = result['aspect_dynamics']
    motions = {row['aspect_id']: (i, row) for i, row in enumerate(dynamics.get('rows', []))}
    states = {}
    for planet, profile in sorted(profiles.items()):
        states[planet] = copy.deepcopy({k: v for k, v in profile.items() if k != 'resource_review'})
        states[planet]['condition_context'] = condition_context(profile)
    planets = {}
    for target, profile in sorted(profiles.items()):
        # Deduplicate only this new view, never the original relation records.
        by_planet = {}
        for candidate in profile['resource_review']['candidates']:
            by_planet.setdefault(candidate['planet'], []).extend(candidate['routes'])
        groups = {name: [] for name in GROUPS}
        relations = {}
        for other, original_routes in sorted(by_planet.items()):
            routes = [json.loads(key) for key in sorted({
                json.dumps(r, sort_keys=True, ensure_ascii=False, allow_nan=False)
                for r in original_routes})]
            membership = classify_routes(target, other, routes, orb_view)
            for name in membership:
                groups[name].append(other)
            contacts = []
            for route in routes:
                if route['kind'] not in ASPECT_KINDS:
                    continue
                edge = route['detail']
                motion = motions.get(edge['id'])
                contacts.append(dict(aspect=copy.deepcopy(edge),
                    phase=copy.deepcopy(motion[1]['phase']) if motion else dict(
                        status='unknown', reason='motion data not supplied for this contact'),
                    search=copy.deepcopy(motion[1]['search']) if motion else dict(status='not_supplied'),
                    source_refs=copy.deepcopy(route['source_refs']) + (
                        [f'/aspect_dynamics/rows/{motion[0]}'] if motion else [])))
            directions = [copy.deepcopy(r) for r in result['reception_facts']['rows']
                          if {r['host'], r['guest']} == {target, other}]
            relations[other] = dict(target=target, counterpart=other, groups=membership,
                target_state_ref=f'/relationship_views/states/{target}',
                counterpart_state_ref=f'/relationship_views/states/{other}',
                routes=routes, degree_contacts=contacts, dignity_directions=directions,
                source_refs=[f'/planet_profiles/{target}/resource_review/candidates',
                             f'/planet_profiles/{target}', f'/planet_profiles/{other}'],
                efficacy='not_evaluated')
        dependency = sorted(set(groups['host_of_target']) | set(groups['exchange']))
        direct = groups['degree_contact']
        planets[target] = dict(target_state_ref=f'/relationship_views/states/{target}',
            dependency_review=dependency, direct_aspect_review=direct,
            context_review=sorted(set(relations) - set(dependency) - set(direct)),
            all_associations=sorted(relations), groups=groups, relations=relations)
    return dict(version=VERSION, orb_view=orb_view, states=states, planets=planets,
        availability=dict(dignity=result['reception_facts']['availability'], dynamics=dynamics['status']),
        method=dict(
            dependency_review='host_of_target union exchange; dispositor/dignity dependency and mutual exchange are labelled separately',
            direct_aspect_review='existing selected-view major degree contacts only, including squares and oppositions',
            context_review='all remaining associations; no relationship is deleted',
            state_storage='complete factual profiles without recursive resource_review; both endpoint refs resolve inside this layer',
            ordering='stable planet identifiers, not strength or independent support votes',
            unknown_routes='preserved under unclassified',
            selection_effect='none', efficacy='not_evaluated',
            limitation='View partition only, not a remedy or report formula. Mutual exchange does not prove strict reception, '
                       'and applying motion does not prove unimpeded perfection or mitigation. '
                       'An empty list does not establish absence of resources.'))
