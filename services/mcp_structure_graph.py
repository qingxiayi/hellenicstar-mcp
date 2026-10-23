"""MCP adapter and bounded invariants for deterministic natal relations."""
import json
import math


def calculate_graph_data(**args):
    from services.natal_structure_graph import calculate_structure_graph, StructureInputError
    from services.mcp_natal import _input_error
    try:
        graph = calculate_structure_graph(**args)
    except StructureInputError:
        # Source corruption is a server validation failure, not a user's input error.
        return {'status': 'validation_failed', 'error': 'Natal source failed consistency checks.'}
    except ValueError as exc:
        return _input_error(exc)
    graph['completeness'] = 'partial' if graph['status'] == 'partial' else 'full'
    graph['status'] = 'ok'
    return graph


def validate_graph_output(d):
    """Check finite data, graph topology and geometry; not psychological claims."""
    from services.natal_structure_graph import TEN, SIGN_KEYS, TRADITIONAL_RULERS, MODERN_RULERS, topology, _aspect_layers
    from services.mcp_validation import require, longitude, house
    json.dumps(d, allow_nan=False)
    from services.natal_policy_context import validate_supplementary
    validate_supplementary(d)
    require(d['schema_version'] == 'natal-structure-v1', '/schema_version', 'known_graph_schema')
    require(d['completeness'] in ('full', 'partial'), '/completeness', 'explicit_completeness')
    require(d['interpretations'] == [], '/interpretations', 'calculation_only')
    require(len(d['nodes']) == 10 and {n['id'] for n in d['nodes']} == set(TEN), '/nodes', 'ten_unique_planets')
    planets = {}
    partial = d['completeness'] == 'partial'
    for n in d['nodes']:
        key = n['id']; longitude(n['lon'], '/nodes/lon')
        require(type(n['sign_idx']) is int and n['sign_idx'] == int(n['lon'] // 30), '/nodes/sign_idx', 'sign_matches_longitude')
        require(type(n['retrograde']) is bool, '/nodes/retrograde', 'boolean_motion')
        require(d['facts']['lon:'+key]['value'] == n['lon'], '/facts', 'facts_match_nodes')
        for f in ('house_p', 'house_w'):
            if partial:
                require(n[f] is None, '/nodes/'+f, 'unavailable_house_is_null')
            else:
                house(n[f], '/nodes/'+f)
        planets[key] = {'longitude': n['lon'], 'sign': SIGN_KEYS[n['sign_idx']], 'house': n['house_p']}
    for policy, rules in [('traditional', TRADITIONAL_RULERS), ('modern', MODERN_RULERS)]:
        require(d['dispositor'][policy] == topology(planets, rules), '/dispositor/'+policy, 'paths_cycles_basins_match_nodes')
    edges = d['aspects']['10']['edges']
    require(len({e['id'] for e in edges}) == len(edges), '/aspects', 'unique_edges')
    for e in edges:
        a,b=e['from'],e['to']
        require(a in planets and b in planets and a != b, '/aspects', 'valid_endpoints')
        require(e['angle'] in (0,60,90,120,180), '/aspects', 'supported_angle')
        sep=abs((planets[a]['longitude']-planets[b]['longitude']+180)%360-180)
        require(isinstance(e['orb'], (int,float)) and not isinstance(e['orb'],bool) and math.isfinite(e['orb']) and 0 <= e['orb'] <= 10 and abs(abs(sep-e['angle'])-e['orb']) <= .00012, '/aspects', 'orb_matches_geometry')
    require(d['aspects'] == _aspect_layers(edges), '/aspects', 'cutoffs_components_motifs_match_edges')
    if partial:
        require(d['axes'] == {} and d['houses'] == {'placidus': [], 'whole_sign': []}, '/houses', 'no_fabricated_houses')
        require(set(d['layer_availability']) == {'axes','placidus','whole_sign'} and all(v['status']=='unavailable' and v['reason']=='placidus_calculation_failed' for v in d['layer_availability'].values()), '/layer_availability', 'explicit_partial_reason')
    else:
        require(d['layer_availability'] == {}, '/layer_availability', 'full_layers_available')
        longitude(d['axes']['asc']['lon'], '/axes/asc/lon')
        nodes = {n['id']: n for n in d['nodes']}
        for system, field in [('placidus','house_p'), ('whole_sign','house_w')]:
            rows=d['houses'][system]
            require([r['house'] for r in rows] == list(range(1,13)), '/houses/'+system, 'twelve_ordered_houses')
            for row in rows:
                require(row['occupants'] == [k for k in TEN if nodes[k][field] == row['house']], '/houses', 'occupants_match_nodes')
