"""Childbirth is a second context for existing geometry, not extra evidence."""


def childbirth_view(observation, timing):
    cfg = observation['settings']['timing']
    event = cfg['event_context']
    if event is None:
        return dict(status='not_computed', reason='childbirth_event_not_requested')
    parent, child = event['parent_person'], event['child_person']
    birth_points = observation['source_geometry'][child]['points']
    transit_points = timing['sources']['transit']['points']
    residuals = {p: abs((lon-birth_points[p]+180) % 360-180) for p, lon in transit_points.items()}
    if not residuals or max(residuals.values()) > 1e-7:
        raise ValueError('Childbirth transit positions disagree with the child natal source')
    child_side, parent_side = ('first', 'second') if child == 'a' else ('second', 'first')
    static_index = {}
    for i, row in enumerate(observation['contacts']):
        key = (row[child_side+'_point'], row[parent_side+'_point'], row['angle'])
        static_index.setdefault(key, []).append('/contacts/'+str(i))
    parent_entries = {row['point']: '/timing_observations/natal_point_entries/'+str(i)
                      for i, row in enumerate(timing['natal_point_entries']) if row['person'] == parent}
    rows = []
    for i, contact in enumerate(timing['contacts']):
        if contact['first_kind'] != 'transit' or contact['second_kind'] != 'natal' or contact['second_owner'] != parent:
            continue
        p, q = contact['first_point'], contact['second_point']
        refs = static_index.get((p, q, contact['angle']), [])
        core, context = [], []
        for j, comp in enumerate(observation['observation_complexes']['people'][parent]):
            if q in comp['members']:
                (core if q in comp['core_members'] else context).append(f'/observation_complexes/people/{parent}/{j}')
        rows.append(dict(timing_contact_ref=f'/timing_observations/contacts/{i}',
            child_natal_point_ref=f'/source_geometry/{child}/points/{p}',
            parent_natal_point_ref=f'/source_geometry/{parent}/points/{q}',
            parent_natal_entry_ref=parent_entries[q], static_contact_refs=refs,
            static_match='same_geometry_existing_contact' if refs else 'not_present_under_static_aspect_policy',
            core_complex_refs=core, context_complex_refs=context,
            independent_evidence_added=False, rule_id='childbirth_observation'))
    return dict(status='computed', parent_person=parent, child_person=child, at_utc=cfg['at'],
        child_birth_context_ref=event['birth_context_ref'], contacts=rows,
        counts=dict(parental_transit_contacts=len(rows)),
        source_agreement=dict(max_residual_degrees=max(residuals.values()), tolerance_degrees=1e-7,
                              checked_points=sorted(residuals), rule_provenance='ENGINE_DERIVED'),
        policy=dict(rule_id='childbirth_observation', role_origin='caller_supplied_not_inferred',
            event_time_source='resolved_child_birth', child_axes_are_not_transiting_planets=True,
            static_and_timing_orbs_remain_separate=True, counts_are_additive=False,
            whole_complex_activation_inferred=False, parent_gender_inferred=False,
            pregnancy_or_parenthood_experience_inferred=False,
            birth_input_historical_accuracy_independently_verified=False))
