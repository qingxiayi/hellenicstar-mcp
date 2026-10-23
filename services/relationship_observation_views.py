"""Explain observation choices and fold containment without scoring or new facts."""
from services.relationship_charts import PLANETS
from services.relationship_observation_routes import is_relationship_role

PERSONAL = frozenset(PLANETS[:5])
OUTER = frozenset(('uranus', 'neptune', 'pluto'))


def point_roles(person, point, profile, settings):
    from services.relationship_observation_routes import candidate_reasons
    return dict(person=person, point=point,
                roles=[r['role'] for r in candidate_reasons(person, point, profile, settings)])


def build_review(profiles, contacts, clusters, associations, settings):
    """Reason dimensions are overlapping lenses, not votes or inferred problems."""
    by_id = {c['id']: c for c in contacts}
    entries = []
    for cluster in clusters:
        hits = [by_id[i] for i in cluster['contact_ids']]
        endpoint_roles = {}
        relationship_ids, parental_ids, inner_outer_ids = [], [], []
        for c in hits:
            roles = []
            for side in ('first', 'second'):
                who, point = c[side + '_person'], c[side + '_point']
                row = point_roles(who, point, profiles[who], settings)
                endpoint_roles[(who, point)] = row
                roles.extend(row['roles'])
            if any(is_relationship_role(r) for r in roles):
                relationship_ids.append(c['id'])
            if any(r.startswith(('father_', 'mother_', 'parental_')) for r in roles):
                parental_ids.append(c['id'])
            p, q = c['first_point'], c['second_point']
            if (p in PERSONAL and q in OUTER) or (q in PERSONAL and p in OUTER):
                inner_outer_ids.append(c['id'])
        entries.append(dict(cluster_id=cluster['id'], person=cluster['target_person'],
            point=cluster['target_point'], contact_ids=list(cluster['contact_ids']),
            endpoint_roles=[endpoint_roles[k] for k in sorted(endpoint_roles)],
            reasons=dict(
                relationship_indicators=dict(contact_ids=relationship_ids, rule_id='review_indicators'),
                parental_indicators=dict(contact_ids=parental_ids, rule_id='review_indicators'),
                inner_outer_contacts=dict(contact_ids=inner_outer_ids, rule_id='review_inner_outer'),
                tight_contacts=dict(contact_ids=[c['id'] for c in hits if c['tight_contact']],
                    threshold_degrees=settings['tight_orb_degrees'], rule_id='review_tightness'),
                wider_contacts=dict(contact_ids=[c['id'] for c in hits if not c['tight_contact']],
                    rule_id='review_tightness'),
                natal_structure=dict(configuration_ids=list(cluster['configuration_ids']),
                    local_edge_ids=list(cluster['local_natal_context']['edge_ids']), rule_id='network')),
            natal_background_ref=cluster['natal_background_ref']))
    by_cluster = {r['cluster_id']: r for r in entries}
    configuration_entries = []
    for activation in associations['configuration_activations']:
        entry_ids = [activation['person'] + ':' + p for p in activation['direct_members']]
        reason_contacts = {}
        for key in ('relationship_indicators', 'parental_indicators', 'inner_outer_contacts', 'tight_contacts', 'wider_contacts'):
            reason_contacts[key] = sorted({i for entry_id in entry_ids
                for i in by_cluster[entry_id]['reasons'][key]['contact_ids']})
        configuration_entries.append(dict(configuration_id=activation['configuration_id'],
            activation_id=activation['id'], person=activation['person'], review_cluster_ids=entry_ids,
            contact_ids=list(activation['contact_ids']), reason_contact_ids=reason_contacts))
    lenses = {}
    for who in profiles:
        rows = [r for r in entries if r['person'] == who]
        lenses[who] = {key: [r['cluster_id'] for r in rows if r['reasons'][key]['contact_ids']]
                       for key in ('relationship_indicators', 'parental_indicators', 'inner_outer_contacts', 'tight_contacts')}
        lenses[who]['natal_structure'] = [r['cluster_id'] for r in rows if
            r['reasons']['natal_structure']['configuration_ids'] or r['reasons']['natal_structure']['local_edge_ids']]
    return dict(status='computed' if settings['mode'] == 'synastry' else 'not_computed',
        reason='requested_mode', entries=entries, configuration_entries=configuration_entries, lenses=lenses,
        policy=dict(rule_id='review_policy', score=None, cross_dimension_order=None,
            within_lens_order='existing_cluster_order', overlapping_reasons_are_independent=False,
            actual_life_difficulty='not_inferred', client_priority='not_supplied',
            natal_selection_is_not_client_priority=True,
            overlays='separate_context_not_aspect_evidence'))


def build_structure_display(associations):
    """Fold strict containment only. Partial overlap never merges identities."""
    configs = {c['id']: c for rows in associations['natal_configurations'].values() for c in rows}
    ancestors = {key: sorted(p['id'] for p in configs.values() if key in p['contains']) for key in configs}
    # Multiple maximal parents are retained instead of arbitrarily assigning ownership.
    roots = {key: [p for p in parents if not ancestors[p]] for key, parents in ancestors.items()}
    activations = {a['configuration_id']: a for a in associations['configuration_activations']}
    people = {}
    for who, rows in associations['natal_configurations'].items():
        people[who] = dict(
            top_level_configuration_ids=[r['id'] for r in rows if not ancestors[r['id']]],
            top_level_activation_ids=[activations[r['id']]['id'] for r in rows
                                      if not ancestors[r['id']] and r['id'] in activations],
            folded_configurations=[dict(configuration_id=r['id'], parent_configuration_ids=roots[r['id']],
                activation_id=activations[r['id']]['id'] if r['id'] in activations else None)
                for r in rows if ancestors[r['id']]])
    bridges = associations['configuration_bridges']
    bridge_map = {(b['a_configuration_id'], b['b_configuration_id']): b for b in bridges}
    folded, top = [], []
    for b in bridges:
        a, other = b['a_configuration_id'], b['b_configuration_id']
        parents = []
        for pa in roots[a] or [a]:
            for pb in roots[other] or [other]:
                parent = bridge_map.get((pa, pb))
                if parent and parent['id'] != b['id'] and set(b['contact_ids']) <= set(parent['contact_ids']):
                    parents.append(parent['id'])
        if parents:
            folded.append(dict(bridge_id=b['id'], parent_bridge_ids=sorted(set(parents))))
        else:
            top.append(b['id'])
    return dict(people=people, top_level_bridge_ids=top, folded_bridges=folded,
        policy=dict(rule_id='containment_display', ordering='stable_id_not_importance',
            partial_overlap='keep_separate', folding='strict_edge_containment',
            all_raw_rows_retained=True, counts_are_additive=False, affects_contacts=False))
