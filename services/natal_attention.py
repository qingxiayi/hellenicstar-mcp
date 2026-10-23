"""Grouped reading view; role intersections are not an importance score.

Consumes the existing evidence audit. No ephemeris, dignity table, personal
case, inferred efficacy or forced number of foreground objects lives here.
"""
from services.natal_focus import FOCAL_ROLES

NETWORK_ROLES = FOCAL_ROLES | {'opposition_endpoint'}

ROLE_GROUPS = {
    'identity_anchor': 'identity',
    'main_external_entry': 'rulership',
    'chart_ruler_dispositor': 'rulership',
    'axis_conjunction': 'axis_contact',
    'maximal_configuration_focus': 'aspect_network',
}


def build_attention_layers(result):
    evidence = result['evidence_index']
    configurations = {m['id']: m for m in result['priority_configurations']}
    maximal_ids = set(result['focus_selection']['configuration_group_ids'])
    rows = []
    buckets = {key: [] for key in ('cross_focus', 'specific_focus', 'associated_context')}
    for audit in sorted(result['selection_audit'], key=lambda row: row['planet']):
        planet = audit['planet']
        groups = {}
        for rule in audit['focus_rules']:
            group = ROLE_GROUPS.get(rule['rule'])
            if group:
                groups.setdefault(group, set()).update(rule['evidence_ids'])
        # Preserve a role when its motif is represented by a larger motif.
        # Every facet belongs to one network group, never an extra vote.
        network = {}
        for identity, motif in sorted(configurations.items()):
            roles = sorted(set(motif['roles'].get(planet, [])) & NETWORK_ROLES)
            if not roles:
                continue
            owners = sorted(mid for mid in maximal_ids
                            if mid == identity or identity in configurations[mid]['contains'])
            network[identity] = dict(kind='configuration_role', evidence_id=identity,
                roles=roles, represented_by=owners,
                geometry_ids=sorted(set(motif['depends_on'])))
            groups.setdefault('aspect_network', set()).add(identity)
        # All selected tight edges remain corroborating facts, including those
        # represented by a motif. Edges alone still cannot select a planet.
        local_aspects = sorted({e['evidence_id'] for e in audit['candidate_evaluations']
                                if e['disposition'] == 'local_aspect'})
        for evaluation in audit['candidate_evaluations']:
            if evaluation['disposition'] not in ('local_aspect', 'contained_aspect'):
                continue
            identity = evaluation['evidence_id']
            network[identity] = dict(kind='tight_aspect', evidence_id=identity,
                roles=[], represented_by=sorted(set(evaluation.get('represented_by', []))),
                geometry_ids=[identity])
        tight_ids = {key for key, item in network.items() if item['kind'] == 'tight_aspect'}
        if groups and tight_ids:
            groups.setdefault('aspect_network', set()).update(tight_ids)
        groups = {key: sorted(value) for key, value in sorted(groups.items())}
        category = ('cross_focus' if len(groups) >= 2 else
                    'specific_focus' if groups else 'associated_context')
        buckets[category].append(planet)
        ids = sorted({identity for values in groups.values() for identity in values})
        assert all(identity in evidence for identity in ids)
        rows.append(dict(planet=planet, category=category, role_groups=groups,
            evidence_ids=ids, local_aspect_evidence_ids=local_aspects, legacy_selected=audit['selected'],
            aspect_network_evidence=[network[key] for key in sorted(network)],
            network_geometry_ids=sorted({edge for item in network.values() for edge in item['geometry_ids']}),
            reason=('multiple_role_groups' if len(groups) >= 2 else
                    'single_role_group' if groups else 'group_membership_or_context_only'),
            source_refs=[f'/planet_profiles/{planet}', '/selection_audit'],
            terminal_memberships=[t['id'] for t in result['core_structures'] if planet in t['members']],
            main_entry_for=[t['id'] for t in result['core_structures'] if planet in t['main_entries']],
            configuration_memberships=[m['id'] for m in result['priority_configurations'] if planet in m['members']]))

    structures = dict(
        terminals=[dict(id=t['id'], members=t['members'], main_entries=t['main_entries'],
                        numerator=t['numerator'], denominator=t['denominator'],
                        source_ref=f'/core_structures/{i}')
                   for i, t in enumerate(result['core_structures'])],
        configurations=[dict(id=m['id'], members=m['members'], roles=m['roles'],
                             contains=m['contains'], shared_with=m['shared_with'],
                             source_ref=f'/priority_configurations/{i}')
                        for i, m in enumerate(result['priority_configurations'])
                        if m['id'] in result['focus_selection']['configuration_group_ids']])
    return dict(version='natal-attention-v3', primary_structures=structures,
        **buckets, planet_audit=rows,
        availability=result['availability'],
        policy=dict(cross_focus_min_role_groups=2, role_groups=ROLE_GROUPS,
            configuration_roles=sorted(NETWORK_ROLES),
            local_aspect='All selected tight aspects, including contained edges, may corroborate an explicit role in one aspect_network group. Alone they remain context.',
            deduplication='Contained roles and edges remain traceable facets in one aspect_network group, with maximal representatives and unique geometry IDs. Cycle/reception synonyms and house-system repetitions do not create roles.',
            state_effect='None; conditions describe objects, never create focus roles.',
            order='Structures, role intersections, single-role entries, associated context; stable identifiers within each planet list, no total rank.',
            compatibility='v3 excludes Jones from natal role intersections. Jones roles remain in jones_view, not in a combined ranking. Render all structures and specific_focus, not cross_focus alone.',
            meaning='Cross-focus means distinct declared role groups, not independent evidence, better condition or psychological priority.',
            maximum_planets=None, score=None, recovered_report_formula=False),
        broad_cross_focus=len(buckets['cross_focus']) >= 8,
        empty_cross_focus=not buckets['cross_focus'])
