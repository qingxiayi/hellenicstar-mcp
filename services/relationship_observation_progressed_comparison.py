"""Compare natal and progressed synastry under one explicit aspect policy.

This is a selected-time comparison, not a search for first appearance, loss or
duration. Baseline rows re-evaluate existing natal geometry, adding no evidence.
"""
from collections import Counter


def progressed_synastry_comparison(observation, timing):
    from services.relationship_observation import contacts_between
    cfg = observation['settings']['timing']
    if not cfg['include_progressed_synastry']:
        return dict(status='not_computed', reason='progressed_synastry_not_requested')
    base = '/timing_observations/progressed_synastry_comparison'
    orb_ref = '/settings/timing/progression_orbs_degrees'
    baseline = contacts_between(observation['source_geometry']['a']['points'],
        observation['source_geometry']['b']['points'], 'a_natal', 'b_natal',
        dict(orbs=cfg['progression_orbs_degrees'], tight_orb_degrees=0))
    for c in baseline:
        c.pop('tight_contact'); c.pop('generational_contact')
        c.update(first_point_ref='/source_geometry/a/points/'+c['first_point'],
                 second_point_ref='/source_geometry/b/points/'+c['second_point'],
                 orb_settings_ref=orb_ref, rule_id='progressed_synastry_comparison',
                 independent_evidence_added=False)
    def key(c):
        return (c['first_point'], c['second_point'])
    natal_index = {key(c): (i, c) for i, c in enumerate(baseline)}
    progressed_index = {key(c): (i, c) for i, c in enumerate(timing['contacts'])
        if c['first_kind'] == c['second_kind'] == 'progressed'
        and (c['first_owner'], c['second_owner']) == ('a', 'b')}
    static_index = {}
    for i, c in enumerate(observation['contacts']):
        static_index.setdefault(key(c), []).append('/contacts/'+str(i))
    same_nodes = observation['settings']['node_type'] == cfg['node_type']
    rows = []
    for pair in sorted(natal_index.keys() | progressed_index.keys()):
        ni, nc = natal_index.get(pair, (None, None))
        pi, pc = progressed_index.get(pair, (None, None))
        comparable = same_nodes or 'north_node' not in pair
        if not comparable:
            state = 'not_comparable_node_conventions'
        elif nc is None:
            state = 'progressed_only'
        elif pc is None:
            state = 'natal_only'
        else:
            state = 'same_aspect' if nc['angle'] == pc['angle'] else 'different_aspect'
        rows.append(dict(id='progressed-compare:a:'+pair[0]+'|b:'+pair[1],
            a_point=pair[0], b_point=pair[1], comparable=comparable, state=state,
            **({} if ni is None else dict(natal_comparison_contact_ref=base+'/natal_comparison_contacts/'+str(ni))),
            **({} if pi is None else dict(progressed_contact_ref='/timing_observations/contacts/'+str(pi))),
            existing_static_contact_refs=static_index.get(pair, []),
            natal_geometry_refs=['/source_geometry/'+who+'/points/'+p for who, p in zip(('a', 'b'), pair)],
            progressed_geometry_refs=['/timing_observations/sources/progressed/'+who+'/points/'+p
                                      for who, p in zip(('a', 'b'), pair)],
            rule_id='progressed_synastry_comparison', independent_evidence_added=False))
    states = Counter(r['state'] for r in rows)
    return dict(status='computed', at_utc=cfg['at'], natal_comparison_contacts=baseline, entries=rows,
        counts=dict(point_pairs=len(rows), by_state={s: states[s] for s in
            ('same_aspect', 'different_aspect', 'natal_only', 'progressed_only', 'not_comparable_node_conventions')}),
        policy=dict(rule_id='progressed_synastry_comparison', orb_settings_ref=orb_ref,
            natal_and_progressed_use_same_orbs=True, original_static_orbs_unchanged=True,
            existing_static_reference_scope='same_point_pair_context_only_not_comparison_baseline',
            baseline_geometry='existing_natal_points_rechecked_no_new_ephemeris',
            natal_node_type=observation['settings']['node_type'], progressed_node_type=cfg['node_type'],
            node_mismatches='not_classified_as_aspect_change', axis_equivalents_share_one_pair=True,
            absent_from_both='omitted_not_an_aspect_change', comparison_scope='selected_snapshot_only',
            first_appearance_or_duration_inferred=False, progressed_internal_patterns='not_computed',
            counts_are_additive=False, affects_contact_counts=False,
            strength_or_relationship_outcome_inferred=False))
