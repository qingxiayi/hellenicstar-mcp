"""Select review objects, without promoting every participant to a focal planet.

These are declared engineering rules, not recovered author weights. Families
are different structural descriptions, not statistically independent evidence.
"""

FOCAL_ROLES = {'apex', 'sextile_apex', 'mediator', 'sextile_vertex'}
CONVERGENCE_FAMILIES = 3


def select_focus(reasons, evidence, configurations):
    parents = {m['id']: sorted(n['id'] for n in configurations
                              if m['id'] in n['contains']) for m in configurations}
    maximal = {m['id']: m for m in configurations if not parents[m['id']]}
    aspect_roots = {}
    for mid, m in maximal.items():
        for edge in m['depends_on']:
            aspect_roots.setdefault(edge, []).append(mid)
    rows = {}
    for planet, matches in sorted(reasons.items()):
        evaluations = []
        direct = []
        families = {}
        for match in matches:
            identity = match['evidence_id']; e = evidence[identity]; detail = e['detail']
            family = e['family']; rule = None; owners = []
            disposition = 'context'
            if family == 'identity':
                rule = 'identity_anchor'
            elif family == 'dispositor':
                if identity.startswith('entry:'):
                    rule = 'main_external_entry'
                else:
                    disposition = 'group_member'; owners = [identity]
            elif family == 'angularity' and identity.startswith('axis:'):
                if detail['angle'] in (0, 180):
                    rule = 'axis_conjunction'
            elif family == 'configuration':
                owners = parents[identity] or [identity]
                if parents[identity]:
                    disposition = 'contained_structure'
                elif set(detail['roles'][planet]) & FOCAL_ROLES:
                    rule = 'maximal_configuration_focus'
                else:
                    disposition = 'group_member'
            elif family == 'aspect':
                owners = sorted(aspect_roots.get(identity, []))
                disposition = 'contained_aspect' if owners else 'local_aspect'
            if rule:
                direct.append(dict(rule=rule, evidence_ids=[identity]))
                disposition = 'direct_selection'
            # A child motif and its aspect edges cannot corroborate their parent.
            if disposition not in ('contained_structure', 'contained_aspect'):
                families.setdefault(family, []).append(identity)
            evaluations.append(dict(**match, disposition=disposition,
                                    represented_by=owners))
        qualifying = {k: sorted(v) for k, v in sorted(families.items())
                      if k != 'identity'}
        convergence = len(qualifying) >= CONVERGENCE_FAMILIES
        if convergence:
            direct.append(dict(rule='cross_family_convergence',
                evidence_ids=sorted({e for ids in qualifying.values() for e in ids})))
        selected = bool(direct)
        selection_ids = {eid for rule in direct for eid in rule['evidence_ids']}
        rows[planet] = dict(selected=selected, rules=direct,
            selection_reasons=[m for m in matches if m['evidence_id'] in selection_ids],
            candidate_evaluations=evaluations, structural_families=qualifying,
            reason='direct_anchor_or_convergence' if selected else
                   'represented_by_groups_or_local_relations' if matches else 'no_candidate_rule_matched')
    return rows, dict(version='natal-focus-v2',
        direct_rules=['identity_anchor', 'main_external_entry', 'axis_conjunction',
                      'maximal_configuration_focus'],
        convergence_min_families=CONVERGENCE_FAMILIES,
        convergence='Distinct descriptions, not independent votes; contained motifs and their aspect edges do not add families.',
        symmetric_structures='Retained as groups; no arbitrary focal member.',
        state_effect='No promotion from dignity, retrograde or adverse condition.',
        maximum_planets=None, ranking=None,
        limitation='A declared review policy, not validated psychological importance or a recovered report formula.')
