"""Role indexing and separate resource dimensions; no importance/efficacy grades.

Version 2 replaces the unreleased v1 tier and resource-grade experiments.
"""
from collections import defaultdict
import copy


def _resolve(data, path):
    for key in path.strip('/').split('/'):
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data


def priority_decisions(data):
    roles = {a['planet']: [] for a in data['selection_audit']}
    profiles = {r['planet']: i for i, r in enumerate(data['priority_planets'])}

    def add(planet, kind, object_id, detail, ref):
        item = dict(kind=kind, object_id=object_id, detail=detail, source_ref=ref)
        if item not in roles[planet]:
            roles[planet].append(item)

    for i, terminal in enumerate(data['core_structures']):
        for p in terminal['members']:
            add(p, 'terminal_member', terminal['id'],
                dict(origins=terminal['numerator'], denominator=terminal['denominator']), f'/core_structures/{i}')
        for p in terminal['main_entries']:
            add(p, 'terminal_entry', terminal['id'], terminal['first_entry'][p], f'/core_structures/{i}')
    # Use every ten-origin path, including planets not selected for a profile.
    for terminal in data['scope_comparison']['ten']['terminals']:
        for p, path in terminal['paths'].items():
            if len(path['path']) > 1:
                ruler = path['path'][1]
                if ruler != p:
                    add(ruler, 'dispositor_of', p, dict(planet=p), '/scope_comparison/ten/terminals')
    for identity, evidence in data['evidence_index'].items():
        detail = evidence['detail']
        if evidence['family'] == 'identity':
            kind = {'identity:chart_ruler':'chart_ruler', 'identity:mc_ruler':'mc_ruler'}.get(identity, 'luminary')
            add(detail['planet'], kind, identity, detail, '/evidence_index/'+identity)
        elif evidence['family'] == 'reception':
            for p, other in ((detail['planet1'],detail['planet2']), (detail['planet2'],detail['planet1'])):
                add(p, 'mutual_reception_with', other, dict(planet=other, current_view=detail['current_view']), '/evidence_index/'+identity)
        elif identity == 'bridge:chart_ruler':
            add(detail['planet'], 'chart_ruler_dispositor', identity, detail, '/evidence_index/'+identity)
    for i, m in enumerate(data['priority_configurations']):
        for p in m['members']:
            add(p, 'configuration_role', m['id'], dict(roles=m['roles'][p]), f'/priority_configurations/{i}')
    for i, link in enumerate(data['house_ruler_links']):
        add(link['ruler'], 'house_ruler', f'{link["system"]}:{link["house"]}',
            dict(system=link['system'], house=link['house'], located_house=link['located_house']), f'/house_ruler_links/{i}')
    all_profiles = data.get('planet_profiles', {p:data['priority_planets'][i]['profile'] for p,i in profiles.items()})
    profile_paths = {p:'/planet_profiles/'+p if 'planet_profiles' in data else f'/priority_planets/{profiles[p]}/profile' for p in all_profiles}
    for p, profile in all_profiles.items():
        for j, contact in enumerate(profile['axis_contacts']):
            kind = 'axis_conjunction' if contact['angle'] in (0,180) else 'axis_aspect'
            add(p, kind, contact['id'], contact, profile_paths[p]+f'/axis_contacts/{j}')
    for i, edge in enumerate(data['priority_aspects']):
        for p in (edge['from'],edge['to']):
            add(p, 'tight_aspect_participant', edge['id'], dict(angle=edge['angle'],orb=edge['orb']), f'/priority_aspects/{i}')
    for p, profile in all_profiles.items():
        for j, c in enumerate(profile['resource_review']['candidates']):
            add(c['planet'], 'resource_connection', p,
                dict(connected_planet=p, route_kinds=sorted({r['kind'] for r in c['routes']})),
                profile_paths[p]+f'/resource_review/candidates/{j}')
    rows = []; groups = defaultdict(set)
    for p in sorted(roles):
        ordered = sorted(roles[p], key=lambda r:(r['kind'],r['object_id']))
        for role in ordered:
            groups[role['kind']].add(p)
        rows.append(dict(planet=p, roles=ordered, selected_for_profile=p in profiles,
            selected_as_focus=p in profiles, profile_ref=profile_paths.get(p)))
    return dict(version='natal-priority-policy-v4', rows=rows,
        role_groups={k:sorted(v) for k,v in sorted(groups.items())},
        policy=dict(order='planet and role identifiers only; not importance',
            ranking=None, state_effect='conditions do not remove or promote structural roles',
            coverage='all terminals and all ten planets; no largest-basin filter',
            selection='all ten profiles and roles survive; selected_for_profile refers only to the focal planet list',
            migration='v1 tier, domains and largest_basin_terminal_ids removed; use rows.roles and role_groups'))


def assess_resource(topic, candidate, data):
    connections = []
    snapshots = []
    state_refs = []
    affected = topic['affected_planets']
    for link in candidate['connections']:
        row = _resolve(data, link['candidate_ref'])
        governance = []
        soft = []
        receptions = []
        contacts = []
        dignity_relations = []
        configurations = []
        for i, route in enumerate(row['routes']):
            ref = link['candidate_ref']+f'/routes/{i}'
            if route['kind'] == 'dispositor':
                governance.append(dict(kind='dispositor', source_ref=ref))
            elif route['kind'] == 'mutual_reception':
                governance.append(dict(kind='mutual_reception', source_ref=ref))
                receptions.append(dict(current_view=route['detail']['current_view'],
                    upstream=route['detail'].get('upstream'), source_ref=ref))
            elif route['kind'] in ('sextile_or_trine', 'conjunction', 'square_or_opposition'):
                edge = route['detail']
                contact = dict(aspect_id=edge['id'],angle=edge['angle'],orb=edge['orb'],source_ref=ref)
                contacts.append(contact)
                if route['kind'] == 'sextile_or_trine': soft.append(contact)
            elif route['kind'] == 'dignity_relation':
                dignity_relations.append(dict(detail=route['detail'],source_ref=ref))
            elif route['kind'] == 'shared_configuration':
                configurations.append(dict(detail=route['detail'],source_ref=ref))
        connections.append(dict(endpoint=link['endpoint'], governance=governance,
            soft_aspects=soft, aspects=contacts, dignity_relations=dignity_relations,
            shared_configurations=configurations, mutual_receptions=receptions, source_ref=link['candidate_ref']))
        snapshots.append(row['counterpart_state'])
        state_refs.append(link['candidate_ref']+'/counterpart_state')
    if not snapshots:
        raise ValueError('Resource candidate has no source connection')
    if any(state != snapshots[0] for state in snapshots[1:]):
        raise ValueError('Conflicting counterpart snapshots')
    state = snapshots[0]
    condition = state.get('condition')
    hard = [dict(aspect=copy.deepcopy(e),
        relation_to_topic='touches_affected_planet' if {e['from'],e['to']} & set(affected) else 'elsewhere_in_chart')
        for e in state.get('aspects',[]) if e['angle'] in (90,180)]
    state_view = dict(
        essential=copy.deepcopy(condition['essential']) if condition else None,
        retrograde=state.get('retrograde'), solar=copy.deepcopy(condition.get('solar')) if condition else None,
        houses=copy.deepcopy(state.get('houses',{})),
        condition_context=copy.deepcopy(state.get('condition_context')),
        ruled_houses={k:[r['house'] for r in v] for k,v in state.get('house_ruler_links',{}).items()},
        hard_aspects=hard, source_refs=state_refs,
        availability=dict(essential='available' if condition else 'classical_condition_not_defined',
            solar='not_applicable' if candidate['planet']=='sun' else 'available' if condition and condition.get('solar') else 'unavailable',
            houses={k:'available' if v is not None else 'unavailable' for k,v in state.get('houses',{}).items()}),
        aggregation='none; dignity, motion, houses and other aspects do not grade the relationship')
    aspect_endpoints = sorted({c['endpoint'] for c in connections if c['aspects'] or
        any(r['current_view']['has_aspect'] for r in c['mutual_receptions'])})
    governance_endpoints = sorted({c['endpoint'] for c in connections if c['governance']})
    dignity_endpoints = sorted({c['endpoint'] for c in connections if c['dignity_relations']})
    configuration_endpoints = sorted({c['endpoint'] for c in connections if c['shared_configurations']})
    kind = topic['kind']
    if kind == 'essential_condition':
        status = 'governance_or_reception_context' if governance_endpoints else 'aspect_context_only' if aspect_endpoints else 'participant_connection_only'
        reason = 'Sign governance/reception and aspect contact are separate forms of context; neither changes essential dignity.'
    elif kind in ('square_or_opposition','soft_aspect_with_essential_condition'):
        status = 'two_endpoint_aspect_connection' if len(set(affected) & set(aspect_endpoints))==2 else 'one_endpoint_aspect_connection' if aspect_endpoints else 'governance_connection_only' if governance_endpoints else 'structural_connection_only'
        reason = 'Describes which endpoints are connected; it does not establish help, harm, resolution or a new configuration.'
    elif kind in ('motion','solar_condition','house_association'):
        status = 'background_connection_only'
        reason = 'The relationship supplies context; it does not change natal motion, solar state or house association.'
    else:
        status = 'no_topic_rule'
        reason = 'No declared applicability rule for this topic kind.'
    return dict(
        relationship=dict(status='established', coverage=candidate['coverage'],connections=connections,
            unavailable_endpoint_profiles=topic['unavailable_endpoint_profiles']),
        counterpart_state=state_view,
        applicability=dict(status=status, topic_kind=kind, governance_endpoints=governance_endpoints,
            aspect_endpoints=aspect_endpoints, reason=reason,
            dignity_endpoints=dignity_endpoints, configuration_endpoints=configuration_endpoints,
            coverage='partial' if topic['unavailable_endpoint_profiles'] else 'complete_for_listed_participants',
            ability_to_resolve_issue='not_established'),
        effective_remedy=None)


def resource_decisions(data):
    topics = []
    for index, topic in enumerate(data['resource_checks']['topics']):
        candidates = [dict(planet=c['planet'],
            connection_ref=f'/resource_checks/topics/{index}/candidate_connections/{j}',
            **assess_resource(topic,c,data)) for j,c in enumerate(topic['candidate_connections'])]
        topics.append(dict(id=topic['id'], topic_ref=f'/resource_checks/topics/{index}', candidates=candidates,
            status='dimensions_reported' if candidates else 'no_candidate_under_policy'))
    return dict(version='natal-resource-policy-v3',topics=topics,
        policy=dict(dimensions=['relationship','counterpart_state','applicability'],
            order='topic and planet identifier, no efficacy ranking',
            state_effect='counterpart conditions cannot invalidate existing relations or determine applicability',
            missing='missing data affect only the corresponding dimension; no global downgrade',
            migration='v1 support_candidate/conditional_candidate/insufficient_basis removed; no replacement global grade',
            interpretation='Explicit project context rules, not recovered report formula or effective remedy. '
                'No candidate under this policy is not no resources.'))


def build_decisions(data):
    return dict(priority_decisions=priority_decisions(data), resource_decisions=resource_decisions(data))
