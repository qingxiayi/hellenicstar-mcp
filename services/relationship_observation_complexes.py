"""Bounded review complexes, distinct from direct contacts and legacy motifs.

Conjunction pairs receive one layer of natal neighbors. Named patterns receive
only conjunction satellites. Neither layer is recursively expanded or merged.
"""
from itertools import combinations

from services.natal_structure_graph import motifs
from services.relationship_charts import PLANETS

AXIS_CANONICAL = {'south_node': 'north_node', 'descendant': 'ascendant',
                  'imum_coeli': 'midheaven'}


def canonical(point):
    return AXIS_CANONICAL.get(point, point)


def yods(edges, point_ids):
    lookup = {frozenset((e['from'], e['to'])): e for e in edges}
    result = []
    for members in combinations(point_ids, 3):
        rows = [lookup.get(frozenset(pair)) for pair in combinations(members, 2)]
        if any(e is None for e in rows) or sorted(e['angle'] for e in rows) != [60, 150, 150]:
            continue
        apex = next(p for p in members if all(e['angle'] == 150 for e in rows if p in (e['from'], e['to'])))
        result.append(dict(kind='yod', members=list(members), apex=apex,
                           depends_on=sorted(e['id'] for e in rows)))
    return result


def build_complexes(profiles, contacts, associations, settings):
    people = {}
    for who, profile in profiles.items():
        edges = profile['natal_aspects']
        edge_refs = {e['id']: f'/relationship_profiles/{who}/natal_aspects/{i}'
                     for i, e in enumerate(edges)}
        expanded, seeds = [], {}
        for e in edges:
            for v in e['endpoint_variants']:
                # An axis-equivalent sextile is not permission to use a sextile
                # pattern unless that angle's orb was explicitly configured.
                if str(v['angle']) not in settings['orbs'] or e['orb_degrees'] > settings['orbs'][str(v['angle'])]:
                    continue
                expanded.append(dict(id=e['id'], **{'from': v['first_point'], 'to': v['second_point']},
                                     angle=v['angle'], orb=e['orb_degrees']))
                if v['angle'] == 0 and {v['first_point'], v['second_point']} & set(PLANETS):
                    key = ('conjunction_pair', tuple(sorted((e['first_point'], e['second_point']))))
                    seed = seeds.setdefault(key, dict(core_aspect_ids=[e['id']], representations=[]))
                    seed['representations'].append(dict(kind='conjunction',
                        members=sorted((v['first_point'], v['second_point']))))
        patterns = motifs(expanded, point_ids=tuple(profile['points']))
        if {'60', '150'} <= settings['orbs'].keys():
            patterns += yods(expanded, tuple(profile['points']))
        for motif in patterns:
            members = tuple(sorted(canonical(p) for p in motif['members']))
            # One physical axis can never occupy two independent vertices.
            if len(set(members)) != len(members) or not set(members) & set(PLANETS):
                continue
            key = ('named_pattern', members)
            seed = seeds.setdefault(key, dict(core_aspect_ids=sorted(set(motif['depends_on'])), representations=[]))
            representation = dict(kind=motif['kind'], members=sorted(motif['members']))
            if motif['kind'] == 'yod':
                representation.update(apex=motif['apex'], rule_id='yod_context')
            seed['representations'].append(representation)
        rows = []
        for (kind, core), seed in sorted(seeds.items()):
            attached = {}
            for e in edges:
                ends = {e['first_point'], e['second_point']}
                if len(ends & set(core)) != 1:
                    continue
                if kind == 'named_pattern' and not any(v['angle'] == 0 for v in e['endpoint_variants']):
                    continue
                point = next(iter(ends - set(core)))
                row = attached.setdefault(point, dict(point=point, via_core_members=set(), natal_aspect_ids=[]))
                row['via_core_members'].update(ends & set(core))
                row['natal_aspect_ids'].append(e['id'])
            members = sorted(set(core) | set(attached))
            side, other = ('first', 'second') if who == 'a' else ('second', 'first')
            hits = [c for c in contacts if c[side + '_point'] in members]
            touched = {c[side + '_point'] for c in hits}
            for row in attached.values():
                row['via_core_members'] = sorted(row['via_core_members'])
                row['natal_aspect_ids'].sort()
                row['fact_refs'] = [edge_refs[i] for i in row['natal_aspect_ids']]
                row['relation'] = 'one_hop_neighbor' if kind == 'conjunction_pair' else 'conjunction_satellite'
            ids = sorted(set(seed['core_aspect_ids']))
            rows.append(dict(id=f'{who}:complex:{kind}:' + ':'.join(core), person=who,
                seed_type=kind, core_members=list(core), core_aspect_ids=ids,
                fact_refs=[edge_refs[i] for i in ids],
                representations=sorted(seed['representations'], key=lambda r: (r['kind'], r['members'])),
                attached_members=[attached[p] for p in sorted(attached)], members=members,
                member_refs=[f'/relationship_profiles/{who}/points/{p}' for p in members],
                legacy_configuration_ids=[c['id'] for c in associations['natal_configurations'][who]
                                          if set(c['depends_on']) == set(ids)],
                direct_core_members=sorted(touched & set(core)),
                direct_attached_members=sorted(touched - set(core)),
                associated_only_members=sorted(set(members) - touched),
                contact_ids=sorted(c['id'] for c in hits),
                source_groups=[dict(source_person='b' if who == 'a' else 'a', source_point=p,
                    contact_ids=sorted(c['id'] for c in hits if c[other + '_point'] == p),
                    core_contact_ids=sorted(c['id'] for c in hits
                        if c[other + '_point'] == p and c[side + '_point'] in core),
                    direct_members=sorted(c[side + '_point'] for c in hits if c[other + '_point'] == p))
                    for p in sorted({c[other + '_point'] for c in hits})],
                rule_id='bounded_observation_complex', whole_complex_activation_inferred=False))
        people[who] = rows
    return dict(status='computed', people=people,
        cross_contact_status='computed' if settings['mode'] == 'synastry' else 'not_computed',
        policy=dict(rule_id='bounded_observation_complex',
            seeds='conjunction_pairs_and_supported_named_patterns_with_axis_endpoint_variants',
            conjunction_pair_context='one_hop_from_original_pair_only',
            named_pattern_context='conjunction_satellites_of_original_core_only',
            attachment_depth=1, recursive_expansion=False, overlapping_complexes_merged=False,
            counts_are_additive=False, affects_contact_counts=False,
            axis_vertices='one_vertex_per_physical_axis; variants_are_representations',
            sextile_patterns_require_explicit_orb=True,
            yod_status='computed' if {'60', '150'} <= settings['orbs'].keys() else 'not_computed',
            unsupported=['unbounded_connected_components'],
            whole_complex_activation='not_inferred', ordering='stable_id_not_importance'))


def build_complex_links(complexes, contacts, settings):
    """Factor memberships by unique contact; never materialize all complex pairs.

A core hit and a contact to an attached context member remain distinct. The
latter does not imply a direct contact to any core member or whole activation.
"""
    memberships = {}
    for who, rows in complexes['people'].items():
        index = memberships.setdefault(who, {})
        for i, row in enumerate(rows):
            ref = f'/observation_complexes/people/{who}/{i}'
            core = set(row['core_members'])
            for point in row['members']:
                slots = index.setdefault(point, {'core_complex_refs': [], 'context_complex_refs': []})
                slots['core_complex_refs' if point in core else 'context_complex_refs'].append(ref)
    rows = []
    if settings['mode'] == 'synastry':
        for i, contact in enumerate(contacts):
            a = memberships.get('a', {}).get(contact['first_point'])
            b = memberships.get('b', {}).get(contact['second_point'])
            if not a or not b:
                continue
            rows.append(dict(id='complex-link:' + contact['id'], contact_id=contact['id'],
                contact_ref=f'/contacts/{i}',
                a=dict(person='a', point=contact['first_point'], **a),
                b=dict(person='b', point=contact['second_point'], **b),
                rule_id='observation_complex_link', creates_direct_contact=False,
                whole_complex_activation_inferred=False))
    return dict(status='computed' if settings['mode'] == 'synastry' else 'not_computed',
        reason='requested_mode', links=rows,
        unique_linked_contact_count=len(rows),
        policy=dict(rule_id='observation_complex_link',
            representation='one_row_per_existing_contact_with_two_owner_membership_lists',
            counts_are_additive=False, all_complex_pairs_materialized=False,
            core_and_context_memberships_distinguished=True,
            context_membership_implies_core_hit=False,
            recursive_expansion=False, whole_complex_activation_inferred=False,
            axis_policy='canonical_points_with_contact_endpoint_variants_retained',
            scope='existing_bounded_complexes_only_including_axes_yods_and_conjunction_pairs'))
