"""A reading order over existing facts, not another importance algorithm."""
from collections import defaultdict

FAMILIES = ('dispositor', 'identity', 'angularity', 'aspect',
            'configuration', 'house_ruler', 'reception')


def build_reading_layers(data):
    evidence = data['evidence_index']
    planets = {r['planet']: (i, r) for i, r in enumerate(data['priority_planets'])}
    configurations = data['priority_configurations']
    parents = {m['id']: sorted(n['id'] for n in configurations if m['id'] in n['contains'])
               for m in configurations}
    maximal = [m for m in configurations if not parents[m['id']]]
    matrix = []
    for audit in data['selection_audit']:
        planet = audit['planet']
        triggers = {r['evidence_id'] for r in audit['rules_matched']}
        related = set(triggers)
        for identity, e in evidence.items():
            detail = e['detail']
            if ((e['family'] == 'dispositor' and planet in detail.get('origins', [])) or
                (e['family'] == 'configuration' and planet in detail.get('members', [])) or
                (e['family'] == 'aspect' and planet in (detail.get('from'), detail.get('to'))) or
                (e['family'] == 'reception' and planet in (detail.get('planet1'), detail.get('planet2'))) or
                (e['family'] == 'house_ruler' and detail.get('ruler') == planet) or
                (e['family'] == 'angularity' and (detail.get('planet') == planet or planet in detail.get('members', [])))):
                related.add(identity)
        cells = {family: [] for family in FAMILIES}
        for identity in sorted(related):
            e = evidence[identity]
            cells[e['family']].append(dict(evidence_id=identity,
                usage='selection' if identity in triggers else 'context',
                synonym_group=e['synonym_group'], correlation_group=e.get('correlation_group')))
        matrix.append(dict(planet=planet, selected=audit['selected'], cells=cells,
            profile_ref=f'/priority_planets/{planets[planet][0]}/profile' if planet in planets else None,
            unavailable=audit['unknowns']))

    groups = defaultdict(list)
    for identity, e in evidence.items():
        groups[e['synonym_group']].append(identity)
    plan = dict(version='natal-reading-v2', order=['structural_backbone', 'identity_and_local',
                'complete_profiles', 'resource_checks'], score=None,
        structural_backbone=dict(
            terminal_refs=[f'/core_structures/{i}' for i in range(len(data['core_structures']))],
            maximal_configuration_ids=[m['id'] for m in maximal],
            configuration_expansion=[dict(id=m['id'], contained_ids=m['contains'], parent_ids=parents[m['id']],
                                         shared_with=m['shared_with']) for m in configurations]),
        identity_and_local=dict(
            identity_evidence_ids=sorted(k for k,e in evidence.items() if e['family']=='identity'),
            axis_contact_ids=sorted(k for k in evidence if k.startswith('axis:')),
            tight_aspect_ids=[a['id'] for a in data['priority_aspects']],
            configuration_roles=[dict(id=m['id'], roles=m['roles']) for m in configurations],
            house_relation_evidence_ids=sorted(k for k,e in evidence.items()
                if (e['family']=='house_ruler' and e['detail'].get('luminaries')) or k.startswith('concentration:'))),
        complete_profiles=[dict(planet=k, ref=f'/priority_planets/{i}/profile') for k,(i,_) in sorted(planets.items())],
        candidate_coverage=dict(selected=len(planets), total=len(matrix),
            all_selected=len(planets)==len(matrix), meaning='selected focal planets; grouped structures and local relations remain separate',
            candidate_count=sum(bool(r['selection_reasons']) for r in data['candidate_planets']),
            broad_selection=data['focus_selection']['broad_selection']),
        limitation='Order is an explicit project reading policy, not psychological importance. '
                   'All terminals survive; maximal means not contained in another detected configuration.')
    return dict(reading_plan=plan,
        evidence_matrix=dict(version='natal-evidence-matrix-v1', families=list(FAMILIES), rows=matrix,
            synonymous_groups={k:sorted(v) for k,v in sorted(groups.items()) if len(v)>1},
            independence='not_assumed; shared inputs, synonyms and containment are not extra independent votes'),
        resource_checks=_resource_checks(
            {p:(i,dict(profile=profile)) for i,(p,profile) in enumerate(data['planet_profiles'].items())},
            {p:'/planet_profiles/'+p for p in data['planet_profiles']}))


def _resource_checks(planets, profile_paths=None):
    profile_paths = profile_paths or {p:f"/priority_planets/{i}/profile" for p,(i,_) in planets.items()}
    topics = {}

    def add(identity, kind, affected, fact, ref):
        if identity not in topics:
            topics[identity] = dict(id=identity, kind=kind, affected_planets=sorted(affected),
                fact=fact, source_refs=[], verdict=None)
        if ref not in topics[identity]['source_refs']:
            topics[identity]['source_refs'].append(ref)

    for p, (i, row) in sorted(planets.items()):
        profile = row['profile']; base=profile_paths[p]
        condition = profile['condition']
        if condition:
            for flag in ('detriment', 'fall', 'peregrine'):
                if condition['essential'][flag]:
                    add(f'state:{p}:{flag}', 'essential_condition', [p], dict(flag=flag,value=True),
                        base+'/condition/essential/'+flag)
            solar = condition.get('solar') or {}
            if solar.get('state') in ('combust','under_beams'):
                add(f'state:{p}:solar', 'solar_condition', [p], solar, base+'/condition/solar')
        if profile['retrograde']:
            add(f'state:{p}:retrograde', 'motion', [p], dict(retrograde=True), base+'/retrograde')
        for system, house in profile['houses'].items():
            if house in (6,8,12):
                add(f'house:{p}:{system}:located:{house}', 'house_association', [p],
                    dict(system=system, house=house, association='located'),base+'/houses/'+system)
            for j, link in enumerate(profile['house_ruler_links'][system]):
                if link['house'] in (6,8,12):
                    add(f'house:{p}:{system}:rules:{link["house"]}', 'house_association', [p],
                        dict(system=system,house=link['house'],association='rules'),
                        base+f'/house_ruler_links/{system}/{j}')
        for j, edge in enumerate(profile['aspects']):
            if edge['angle'] in (90,180):
                add('geometry:'+edge['id'], 'square_or_opposition', [edge['from'],edge['to']],
                    dict(aspect_id=edge['id'],angle=edge['angle'],orb=edge['orb']),base+f'/aspects/{j}')

    for topic in topics.values():
        affected=topic['affected_planets']; connections=defaultdict(list)
        for endpoint in affected:
            if endpoint not in planets:
                continue
            i,row=planets[endpoint]
            for j,candidate in enumerate(row['profile']['resource_review']['candidates']):
                if candidate['planet'] in affected:
                    continue  # A participant is not a third-party connection to its own aspect.
                connections[candidate['planet']].append(dict(endpoint=endpoint,
                    candidate_ref=profile_paths[endpoint]+f'/resource_review/candidates/{j}'))
        topic['candidate_connections']=[dict(planet=p,connections=links,
            coverage='all_affected' if len(links)==len(affected) else 'some_affected',
            relevance='structural_connection_only; ability_to_address_this_condition_not_evaluated')
            for p,links in sorted(connections.items())]
        topic['unavailable_endpoint_profiles']=[p for p in affected if p not in planets]
        topic['status']='connections_for_review' if connections else 'no_external_connection_in_current_policy'
    return dict(version='natal-resource-checks-v1', topics=[topics[k] for k in sorted(topics)],
        limitation='These are condition and geometry review topics, not diagnoses. Connections '
                   'do not show that a condition is remedied. Shared counterpart across two endpoints '
                   'is not a new configuration or independent proof. No connection is not no resources.',
        coverage={p:dict(condition=row['profile']['condition_availability'],
                        houses={k:'available' if v is not None else 'unavailable' for k,v in row['profile']['houses'].items()})
                  for p,(_,row) in sorted(planets.items())})
