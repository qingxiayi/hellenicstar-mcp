"""Bounded configuration membership and background from the existing natal engine.

Membership is not a new contact, and background identities never propagate hits.
"""
from copy import deepcopy

from services.relationship_charts import PLANETS
from services.natal_structure_graph import motifs

SUPPORTED = ['grand_trine', 'minor_grand_trine', 'wedge', 't_square',
             'kite', 'mystic_rectangle', 'grand_cross']


def configurations(profile, person):
    edges = [dict(id=e['id'], **{'from': e['first_point'], 'to': e['second_point']},
                  angle=e['angle'], orb=e['orb_degrees'])
             for e in profile['natal_aspects']
             if e['first_point'] in PLANETS and e['second_point'] in PLANETS]
    rows = motifs(edges, point_ids=PLANETS)  # Includes Chiron; never fixed axis opposites.
    for row in rows:
        row['id'] = person + ':' + row['id']
        row['person'] = person
        row['members'].sort()
        row['rule_id'] = 'configuration_membership'
    for row in rows:
        row['contains'] = sorted(other['id'] for other in rows
                                 if set(other['depends_on']) < set(row['depends_on']))
        row['overlaps'] = sorted(other['id'] for other in rows if other != row and
                                set(other['members']) & set(row['members']))
    return sorted(rows, key=lambda r: r['id'])


def natal_background(graph, settings):
    """Reuse static salience selection; do not run dynamics or another ephemeris."""
    if graph is None:
        return dict(status='not_computed', reason='natal_source_graph_not_supplied', points={})
    from services.natal_salience import build_salience
    result = build_salience(graph, dict(rulership=settings['ruler_profile']))
    audit = {r['planet']: r for r in result['selection_audit']}
    points = {}
    for point, p in result['planet_profiles'].items():
        points[point] = dict(chart_ruler=p['chart_ruler'],
            selected_as_natal_priority=audit[point]['selected'],
            focus_rules=audit[point]['focus_rules'],
            selection_reasons=audit[point]['rules_matched'],
            natal_configuration_roles=p['configurations'],
            dispositor_path=p['path'], mutual_receptions=p['receptions'],
            jones_roles=[r for r in result['jones_view']['observation_roles'] if r['planet'] == point],
            jones_upstream_focus=result['jones_view']['upstream_focus']['planet'] == point,
            contact_effect='none', rule_id='natal_background')
    # Evidence references are local to this embedded context; preserve the natal
    # engine's /source_graph pointers via the embedded source_graph member.
    return dict(status='computed', schema_version=result['schema_version'],
        settings=result['method']['config'], focus_policy=result['focus_selection']['policy'],
        scope='static_natal_background_only', dynamics_status='not_computed',
        longitude_precision='existing natal source rounds planets to 4 decimals; relationship geometry is unrounded',
        relationship_orbs_applied=False, evidence_index=result['evidence_index'],
        reference_scope='source_refs resolve within this natal background object',
        core_structures=result['core_structures'],
        priority_configurations=result['priority_configurations'], points=points,
        source_graph=deepcopy(graph), rule_id='natal_background')


def associate(profiles, contacts, paths, clusters, graphs, settings):
    configs = {who: configurations(prof, who) for who, prof in profiles.items()}
    backgrounds = {who: natal_background(graphs.get(who), settings) for who in profiles}
    memberships = {who: {p: [c['id'] for c in rows if p in c['members']]
                         for p in profiles[who]['points']} for who, rows in configs.items()}
    for path in paths:
        path['target_configuration_ids'] = memberships[path['target_person']][path['target_point']]
        path['source_configuration_ids'] = memberships[path['source_person']][path['source_point']]
    for cluster in clusters:
        who, point = cluster['target_person'], cluster['target_point']
        cluster['configuration_ids'] = memberships[who][point]
        cluster['natal_background_ref'] = (f'/natal_backgrounds/{who}/points/{point}'
            if point in backgrounds[who]['points'] else None)
    activations = []
    for who, rows in configs.items():
        side = 'first' if who == 'a' else 'second'
        other = 'second' if who == 'a' else 'first'
        for config in rows:
            hits = [c for c in contacts if c[side + '_point'] in config['members']]
            if not hits:
                continue
            touched = sorted({c[side + '_point'] for c in hits})
            ids = sorted({c['id'] for c in hits})
            activations.append(dict(id='activation:' + config['id'], person=who,
                configuration_id=config['id'], direct_members=touched,
                associated_only_members=sorted(set(config['members']) - set(touched)),
                contact_ids=ids, direct_contact_count=len(ids),
                observation_path_ids=[i + '->' + who for i in ids],
                source_groups=[dict(source_point=p,
                    contact_ids=sorted(c['id'] for c in hits if c[other + '_point'] == p),
                    direct_members=sorted({c[side + '_point'] for c in hits if c[other + '_point'] == p}))
                    for p in sorted({c[other + '_point'] for c in hits})],
                rule_id='configuration_membership'))
    links = {}
    for contact in contacts:
        for a in memberships['a'][contact['first_point']]:
            for b in memberships['b'][contact['second_point']]:
                links.setdefault((a, b), set()).add(contact['id'])
    bridges = [dict(id=a + '<->' + b, a_configuration_id=a, b_configuration_id=b,
                    contact_ids=sorted(ids), direct_contact_count=len(ids),
                    rule_id='configuration_bridge') for (a, b), ids in sorted(links.items())]
    return dict(natal_configurations=configs, configuration_memberships=memberships,
                configuration_activations=activations, configuration_bridges=bridges,
                natal_backgrounds=backgrounds)
