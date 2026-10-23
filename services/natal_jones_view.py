"""A parallel Jones observation view, never an input to natal focus selection.

Role geometry is supplied by the existing engine. These views share coordinates
and aspects; agreement is not a second independent vote or an efficacy claim.
"""
import copy
from services.natal_house_rulers import PLANET_ZH


CLASSIFICATION = ('family_en', 'family_zh', 'variant_en', 'is_variant', 'state',
                  'borderline', 'borderline_reasons', 'borderline_alternates',
                  'span_deg', 'high_focus_longitude')
GEOMETRY = ('midpoint_bowl', 'midpoint_loco', 'midpoint_bundle', 'cog_bowl',
            'crossing_point', 'group_axis')


def project_observation_details(upstream):
    """Whitelist factual role fields; exclude legacy interpretation prose."""
    return dict(
        classification={k: copy.deepcopy(upstream[k]) for k in CLASSIFICATION if k in upstream},
        roles=[{k: copy.deepcopy(role[k]) for k in
                ('planet_name', 'role_type', 'role_label', 'longitude', 'partners') if k in role}
               for role in upstream.get('key_roles', [])],
        roles_available='key_roles' in upstream,
        geometry={k: copy.deepcopy(upstream[k]) for k in GEOMETRY if k in upstream},
        core_opposition=copy.deepcopy(upstream.get('core_opposition')))


def _planet(name):
    return next((p for p, zh in PLANET_ZH.items() if name in (p, zh)), None)


def build_jones_view(graph, result):
    upstream = graph.get('jones') or {}
    details = upstream.get('observation_details') or {}
    raw_focus = upstream.get('high_focus_planet')
    focus = _planet(raw_focus)
    status = ('available' if focus else 'unrecognized_focus' if raw_focus else
              'no_focus_supplied' if upstream else 'unavailable')
    classification = {k: copy.deepcopy(v) for k, v in upstream.items()
                      if k != 'observation_details'}
    classification.update(copy.deepcopy(details.get('classification', {})))
    roles = []
    for i, raw in enumerate(details.get('roles', [])):
        p = _planet(raw.get('planet_name'))
        kind = raw.get('role_type')
        roles.append(dict(id=f'jones:role:{i}', planet=p, raw_planet=raw.get('planet_name'),
            role_type=kind, role_label=raw.get('role_label'), longitude=raw.get('longitude'),
            identity_status='recognized' if p else 'unrecognized',
            associated_members=[dict(planet=_planet(r.get('planet_name')), raw=copy.deepcopy(r))
                                for r in raw.get('partners', [])],
            source_refs=[f'/source_graph/jones/observation_details/roles/{i}']))
    # Old graph snapshots may carry only a focus label. Keep it separate from
    # complete roles, without fabricating a handle/leader or certainty state.
    role_planets = {r['planet'] for r in roles if r['planet']}
    observation_planets = role_planets | ({focus} if focus else set())
    # Consume the natal layer's normalized geometry, not the raw source list:
    # raw clients may duplicate, rename or reverse the same aspect edge.
    edges = {edge['id']: edge for profile in result['planet_profiles'].values()
             for edge in profile['aspects']}
    contacts = []
    for _, edge in sorted(edges.items()):
        incident = sorted(observation_planets & {edge['from'], edge['to']})
        if incident:
            contacts.append(dict(aspect=copy.deepcopy(edge), observation_endpoints=incident,
                role_ids=[r['id'] for r in roles if r['planet'] in incident],
                source_refs=['/source_graph/aspects/'+str(result['method']['config']['orb_view'])+'/edges']))
    core = copy.deepcopy(details.get('core_opposition'))
    if core:
        a, b = _planet(core.get('planet_name')), _planet(core.get('opposite_planet_name'))
        edge = next((c['aspect'] for c in contacts if c['aspect']['angle'] == 180
                     and {c['aspect']['from'], c['aspect']['to']} == {a, b}), None)
        core['members'] = [a, b]
        core['current_view'] = dict(orb_view=result['method']['config']['orb_view'],
                                  has_aspect=edge is not None, aspect=copy.deepcopy(edge))
    view = dict(version='natal-jones-view-v1', status='available' if upstream else 'unavailable',
        classification=classification,
        upstream_focus=dict(status=status, raw_value=raw_focus, planet=focus),
        roles_status='available' if details.get('roles_available') else 'not_supplied',
        observation_roles=roles, observation_planets=sorted(observation_planets),
        geometry=copy.deepcopy(details.get('geometry', {})), core_opposition=core,
        selected_orb_view=result['method']['config']['orb_view'], direct_contacts=contacts,
        method=dict(selection_effect='none', score=None, ranking=None,
            role_source='existing Jones engine; no roles inferred from interpretation text',
            aspect_policy='Direct contacts use the selected natal orb. Upstream core-opposition policy is disclosed separately; geometry thresholds are not aspect orbs.',
            independence='not_assumed; shared longitudes and aspects are not independent votes',
            unknowns='Missing roles or borderline metadata remain unspecified; they are not assumed absent or certain',
            limitation='Parallel shape perspective, not the report formula, a resource verdict or a unified importance ranking'))
    rows = []
    for audit in result['selection_audit']:
        p = audit['planet']
        rows.append(dict(planet=p,
            natal=dict(selected=audit['selected'], focus_rules=copy.deepcopy(audit['focus_rules']),
                terminal_memberships=[t['id'] for t in result['core_structures'] if p in t['members']],
                main_entry_for=[t['id'] for t in result['core_structures'] if p in t['main_entries']],
                source_refs=['/selection_audit', '/core_structures']),
            jones=dict(upstream_focus=p == focus,
                roles=[copy.deepcopy(r) for r in roles if r['planet'] == p],
                associated_role_ids=[r['id'] for r in roles
                                     if any(m['planet'] == p for m in r['associated_members'])],
                source_refs=['/jones_view']),
            shared_selected_contact_ids=[c['aspect']['id'] for c in contacts
                                         if p in (c['aspect']['from'], c['aspect']['to'])]))
    comparison = dict(version='natal-view-comparison-v1', rows=rows,
        method=dict(selection_effect='none', score=None, ranking=None,
            meaning='Side-by-side roles and existing contacts, not combined weights or independent confirmation',
            availability='Jones classification and uncertainty remain in jones_view; natal rules remain in focus_selection'))
    return view, comparison
