"""Separate dignity direction, sign geometry and selected degree-aspect facts.

Uses the existing classical engine's tables and threshold; no efficacy policy.
No instantaneous longitude data are treated as proof of future perfection.
"""
from services.classical_engine import _dignities_given_by
from services.natal_structure_graph import SEVEN


POLICIES = ('dignity_only', 'sign_aspect', 'degree_aspect', 'applying_degree_aspect')


def reception_facts(nodes, aspects, sect, orb_view, dynamics=None, policy='dignity_only'):
    if policy not in POLICIES:
        raise ValueError('Unknown reception policy')
    motion = {r['aspect_id']:(i,r) for i,r in enumerate((dynamics or {}).get('rows',[]))}
    rows = []
    known_sect = sect in ('日生人', '夜生人')
    if known_sect:
        for guest in sorted(set(nodes) & set(SEVEN)):
            for host in sorted(set(nodes) & set(SEVEN) - {guest}):
                dignities = _dignities_given_by(host, nodes[guest]['lon'], sect == '日生人')
                if not dignities:
                    continue
                strong = sum(major for _, major in dignities)
                minor = len(dignities) - strong
                delta = abs(nodes[guest]['sign_idx'] - nodes[host]['sign_idx'])
                distance = min(delta, 12-delta)
                separation = abs((nodes[guest]['lon']-nodes[host]['lon']+180) % 360-180)
                edge = next((e for e in aspects if {e['from'], e['to']} == {guest, host}), None)
                dynamic = motion.get(edge['id']) if edge else None
                phase = dict(dynamic[1]['phase'],source_ref=f'/aspect_dynamics/rows/{dynamic[0]}/phase') if dynamic else dict(
                    status='unknown' if edge else 'not_applicable',
                    reason='motion data not supplied' if edge else 'no aspect in selected view')
                checks = dict(dignity=strong >= 1 or minor >= 2,
                    sign_aspect=distance in (0,2,3,4,6),degree_aspect=edge is not None,
                    applying=phase['status']=='applying' if phase['status'] not in ('unknown','not_applicable') else None)
                required = {'dignity_only':['dignity'],'sign_aspect':['dignity','sign_aspect'],
                    'degree_aspect':['dignity','degree_aspect'],
                    'applying_degree_aspect':['dignity','degree_aspect','applying']}[policy]
                result = False if any(checks[k] is False for k in required) else None if any(checks[k] is None for k in required) else True
                rows.append(dict(
                    id=f'dignity:{host}:receives:{guest}', host=host, guest=guest,
                    bases=[dict(dignity=name, major=major) for name, major in dignities],
                    meets_dignity_threshold=strong >= 1 or minor >= 2,
                    sign_geometry=dict(distance=distance, same_sign=distance == 0,
                        ptolemaic_angle={0:0, 2:60, 3:90, 4:120, 6:180}.get(distance),
                        aversion=distance in (1, 5)),
                    degree_geometry=dict(separation=separation,
                        deviations={str(a):abs(separation-a) for a in (0,60,90,120,180)}),
                    current_view=dict(orb_view=orb_view, has_aspect=edge is not None,
                        aspect_id=edge['id'] if edge else None,
                        angle=edge['angle'] if edge else None, orb=edge['orb'] if edge else None),
                    phase=phase,
                    motion_ref=f'/aspect_dynamics/rows/{dynamic[0]}' if dynamic else None,
                    policy_evaluation=dict(policy=policy,checks=checks,required=required,meets=result,
                        failed=[k for k in required if checks[k] is False],unknown=[k for k in required if checks[k] is None]),
                    source_refs=['/source_graph/facts/lon:'+guest, '/source_graph/facts/lon:'+host,
                                 '/source_graph/facts/sect', '/source_graph/aspects/'+str(orb_view)],
                    depends_on=['lon:'+guest, 'lon:'+host, 'sect']))
    by_pair = {(r['host'], r['guest']):r for r in rows}
    for row in rows:
        reverse = by_pair.get((row['guest'], row['host']))
        row['reverse_id'] = reverse['id'] if reverse else None
        row['mutual_dignity_threshold'] = bool(row['meets_dignity_threshold'] and reverse and reverse['meets_dignity_threshold'])
    return dict(version='reception-facts-v2', rows=rows,
        availability='available' if known_sect else 'unavailable_sect',
        method=dict(scope=list(SEVEN), direction='host holds dignities at guest longitude',
            dignity_threshold='existing classical_engine: at least one major or two minor dignities',
            triplicity='active day or night lord only',
            aspect='selected upstream degree-aspect view; sign geometry reported independently',
            selection_policy=policy, policies=list(POLICIES),
            phase='relative longitude speed; exact is distinct from applying', efficacy='not evaluated',
            ordering='guest then host identifiers; not quality or strength'))
