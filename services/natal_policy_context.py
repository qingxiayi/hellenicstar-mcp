"""Explicit scope and policy comparisons, without changing the default rules."""
import copy
import math
from services.natal_house_rulers import PLANET_ZH
from services.natal_resource_context import triplicity_context

TEN = tuple(PLANET_ZH)
NODE_IDS = ('north_node', 'south_node')
ALIASES = {'true_north_lunar_node': 'north_node', 'true_south_lunar_node': 'south_node'}


def extract_supplementary_source(source):
    """Project already calculated true nodes; do not re-run an ephemeris."""
    from engine.natal_chart import NatalChartCalculator
    points = {}
    for i, row in enumerate(source['natal_planets_full']):
        if row['key'] in NODE_IDS:
            points[row['key']] = dict(id=row['key'], longitude=row['lon'],
                houses=dict(placidus=row.get('house_p'), whole_sign=row.get('house_w')),
                upstream_source_pointer=f'/natal_planets_full/{i}')
    edges = {}
    for i, row in enumerate(source['aspects']):
        a, b = (ALIASES.get(row.get(key), row.get(key)) for key in ('point1', 'point2'))
        if a in NODE_IDS and b in TEN:
            a, b = b, a
        if a not in TEN or b not in NODE_IDS or row['angle'] not in (0,60,90,120,180):
            continue
        identity = f'node_aspect:{a}:{b}:{row["angle"]}'
        if identity in edges:
            raise ValueError('Duplicate upstream lunar-node aspect')
        edges[identity] = dict(id=identity, planet=a, node=b, angle=row['angle'],
            orb=row['orb'], upstream_source_pointer=f'/aspects/{i}')
    return dict(node_model='true', points=points, edges=[edges[k] for k in sorted(edges)],
        upstream_orbs={str(k):v for k,v in NatalChartCalculator.ASPECT_ORBS.items() if k in (0,60,90,120,180)})


def validate_supplementary(graph):
    from services.natal_structure_graph import StructureInputError
    raw = graph.get('supplementary_source')
    if raw is None:
        return
    def require(ok):
        if not ok:
            raise StructureInputError('Invalid supplementary lunar-node source')
    require(raw.get('node_model') == 'true')
    from engine.natal_chart import NatalChartCalculator
    require(raw['upstream_orbs'] == {str(k):v for k,v in NatalChartCalculator.ASPECT_ORBS.items()
                                   if k in (0,60,90,120,180)})
    points = raw['points']; require(set(points) == set(NODE_IDS))
    for key, p in points.items():
        v = p['longitude']
        require(p['id'] == key and type(v) in (int,float) and math.isfinite(v) and 0 <= v < 360)
        for h in p['houses'].values():
            require(h is None or type(h) is int and 1 <= h <= 12)
    require(abs((points['north_node']['longitude']-points['south_node']['longitude']) % 360-180) < .00012)
    nodes = {n['id']:n['lon'] for n in graph['nodes']}
    seen = set()
    for e in raw['edges']:
        require(e['planet'] in nodes and e['node'] in points and e['angle'] in (0,60,90,120,180))
        require(e['id'] == f'node_aspect:{e["planet"]}:{e["node"]}:{e["angle"]}' and e['id'] not in seen)
        seen.add(e['id'])
        sep = abs((nodes[e['planet']]-points[e['node']]['longitude']+180) % 360-180)
        require(type(e['orb']) in (int,float) and math.isfinite(e['orb']) and 0 <= e['orb'] <= 10
                and abs(abs(sep-e['angle'])-e['orb']) <= .00012)


def policy_context(graph, config, profiles):
    """Publish rule sensitivity separately; no alternate efficacy or salience score."""
    validate_supplementary(graph)
    raw = graph.get('supplementary_source')
    contacts = {}
    if raw:
        for e in raw['edges']:
            if e['orb'] > config['orb_view']:
                continue
            canonical_angle = e['angle'] if e['node']=='north_node' else 180-e['angle']
            identity=f'node_axis:{e["planet"]}:{canonical_angle}'
            row=contacts.setdefault(identity,dict(id=identity,planet=e['planet'],
                canonical_node='north_node',canonical_angle=canonical_angle,expressions=[],
                source_refs=['/source_graph/supplementary_source','/planet_profiles/'+e['planet']]))
            row['expressions'].append(copy.deepcopy(e))
    for row in contacts.values():
        row['expressions'].sort(key=lambda e:e['id'])
    supplementary=dict(status='available' if raw else 'not_supplied',node_model='true' if raw else None,
        points=copy.deepcopy(raw['points']) if raw else {},contacts=[contacts[k] for k in sorted(contacts)],
        orb_view=config['orb_view'],selection_effect='none',
        scope='True lunar-node axis contacts only; excluded from dispositor origins, ten-planet motifs and global point counts.',
        deduplication='North/south expressions of one planetary contact are grouped, not two independent facts.')
    dignity = {}
    for p, profile in sorted(profiles.items()):
        condition = profile['condition']
        if not condition:
            continue
        e=condition['essential']
        context=triplicity_context(p,profile['sign_idx'],condition)
        member=context['is_triplicity_ruler']
        other=any(e[k] for k in ('domicile','exaltation','term','face'))
        dignity[p]=dict(identity=dict(is_triplicity_ruler=member,sect_order=context['sect_order'],
                                     sect_priority=context['sect_priority'],order_status=context['order_status']),
            active_sect=dict(triplicity=e['triplicity'],peregrine=e['peregrine']),
            any_triplicity_member_sensitivity=dict(member=member,peregrine_if_membership_counted=not (other or member)),
            differs=(e['triplicity'] != member),
            difference_meaning='membership_and_dignity_credit_differ; not evidence of disagreement with a report',
            source_refs=['/planet_profiles/'+p+'/triplicity_context'])
    views={}
    for view in ('6','8','10'):
        layer=graph['aspects'][view]
        edge_ids=sorted({f'a:{":".join(sorted((e["from"],e["to"])))}:{int(e["angle"])}' for e in layer['edges']})
        motif_ids=sorted({m['kind']+':'+':'.join(sorted(m['members'])) for m in layer['motifs']})
        views[view]=dict(aspect_ids=edge_ids,configuration_ids=motif_ids,
            aspect_count=len(edge_ids),configuration_count=len(motif_ids))
    comparison=dict(version='natal-policy-context-v1',
        dignity=dict(active_policy='active_day_or_night_only',rows=dignity,
            sensitivity='Counting any of three rulers is a disclosed counterfactual, not a claim that a source author awards equal dignity to all three. Default dignity, receptions and focus remain unchanged.'),
        aspects=dict(selected_view=config['orb_view'],views=views,
            upstream_orbs=copy.deepcopy(raw['upstream_orbs']) if raw else None,
            rule='Views filter the upstream major-aspect list; they cannot recover omitted upstream edges.',
            report_policy='not_inferred_from_a_single_chart'),
        terminology=dict(detriment='opposite a domicile sign',fall='opposite an exaltation sign',
            rule='Separate flags; do not collapse both into one translated term.'),
        report_formula='unknown; no prescribed winner, resource efficacy or mandatory life sequence')
    return supplementary, comparison
