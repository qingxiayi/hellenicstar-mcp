"""Deterministic natal relations, with explicit unavailable layers.

Pure calculation infrastructure; mcp_structure_graph provides the MCP adapter.
Normal charts reuse calculator.compute; a failed Placidus preflight permits a
house-independent Swiss Ephemeris calculation without substituting a house system.
"""
import hashlib
import itertools
import json
import math
from services.natal_house_rulers import TRADITIONAL_RULERS, MODERN_RULERS, SIGN_KEYS, PLANET_ZH, trace_ruler_chain
from services.classical_engine import compute_essential_dignities, compute_receptions, compute_solar_state, compute_orientality
from versioning import get_version_info
TEN = tuple(PLANET_ZH)
SEVEN = TEN[:7]
DEFAULT_ASPECT_VIEW = 6


class StructureInputError(ValueError):
    """A source field is missing, invalid or contradicts another source field."""


def _require(condition, path):
    if not condition:
        raise StructureInputError(f"Invalid natal structure source: {path}")


def _number(value, path):
    _require(isinstance(value, (int, float)) and not isinstance(value, bool)
             and math.isfinite(value), path)
    return value


def validate_structure_source(source):
    """Fail before deriving relations; never silently overwrite duplicate bodies."""
    _require(isinstance(source, dict), "/")
    rows = source.get("natal_planets_full")
    _require(isinstance(rows, list), "/natal_planets_full")
    seen = set()
    for i, row in enumerate(rows):
        path = f"/natal_planets_full/{i}"
        _require(isinstance(row, dict), path)
        key = row.get("key")
        _require(isinstance(key, str) and key not in seen, path + "/key")
        seen.add(key)
    _require(set(TEN) <= seen, "/natal_planets_full: ten planets required")
    _require(source.get("sect") in ("日生人", "夜生人"), "/sect")
    _require(isinstance(source.get("birth_context"), dict), "/birth_context")
    availability = source.get("layer_availability", {})
    _require(isinstance(availability, dict), "/layer_availability")
    houses_missing = bool(availability)
    if houses_missing:
        _require(set(availability) == {"placidus", "whole_sign", "axes"},
                 "/layer_availability")
        _require(all(isinstance(v, dict) and v.get("status") == "unavailable"
                     and v.get("reason") == "placidus_calculation_failed"
                     for v in availability.values()), "/layer_availability/reason")
        _require(source.get("axes") == {}, "/axes")
    else:
        asc = _number((source.get("axes", {}).get("asc") or {}).get("lon"), "/axes/asc/lon")
        _require(0 <= asc < 360, "/axes/asc/lon")
    for i, row in enumerate(rows):
        if row["key"] not in TEN:
            continue
        path = f"/natal_planets_full/{i}"
        lon = _number(row.get("lon"), path + "/lon")
        _require(0 <= lon < 360, path + "/lon")
        idx = row.get("sign_idx")
        _require(type(idx) is int and idx == int(lon // 30), path + "/sign_idx")
        from services.classical_engine import SIGN_NAMES_ZH
        _require(row.get("sign") == SIGN_NAMES_ZH[idx], path + "/sign")
        _require(type(row.get("retrograde")) is bool, path + "/retrograde")
        _require(row.get("cn") == PLANET_ZH[row["key"]], path + "/cn")
        for field in ("house_p", "house_w"):
            house = row.get(field)
            _require(house is None if houses_missing else type(house) is int and 1 <= house <= 12,
                     path + "/" + field)
        if not houses_missing:
            _require(row["house_w"] == (idx - int(asc // 30)) % 12 + 1, path + "/house_w")
    raw = {row["key"]: row for row in rows}
    chains = source.get("house_ruler_chains")
    _require(isinstance(chains, dict), "/house_ruler_chains")
    for system in ("placidus", "whole_sign"):
        hs = chains.get(system)
        _require(isinstance(hs, list), f"/house_ruler_chains/{system}")
        if houses_missing:
            _require(hs == [], f"/house_ruler_chains/{system}")
            continue
        _require(len(hs) == 12, f"/house_ruler_chains/{system}")
        for i, row in enumerate(hs):
            path = f"/house_ruler_chains/{system}/{i}"
            _require(isinstance(row, dict) and type(row.get("house")) is int
                     and row["house"] == i + 1, path + "/house")
            lon = _number(row.get("cusp_lon"), path + "/cusp_lon")
            _require(0 <= lon < 360 and row.get("sign") == SIGN_KEYS[int(lon // 30)], path + "/sign")
    aspects = source.get("aspects")
    _require(isinstance(aspects, list), "/aspects")
    labels = {0: "合相", 60: "六分相", 90: "四分相", 120: "三分相", 150: "梅花相位", 180: "对分相"}
    seen_aspects = set()
    for i, row in enumerate(aspects):
        _require(isinstance(row, dict), f"/aspects/{i}")
        a, b = row.get("point1"), row.get("point2")
        if a not in TEN or b not in TEN:
            continue
        angle = row.get("angle")
        _require(type(angle) in (int, float) and angle in labels and a != b,
                 f"/aspects/{i}/angle")
        _require(row.get("aspect") == labels[angle], f"/aspects/{i}/aspect")
        identity = (tuple(sorted((a, b))), angle)
        _require(identity not in seen_aspects, f"/aspects/{i}: duplicate")
        seen_aspects.add(identity)
        orb = _number(row.get("orb"), f"/aspects/{i}/orb")
        separation = abs((raw[a]["lon"] - raw[b]["lon"] + 180) % 360 - 180)
        # calculator serializes longitudes to four decimal places.
        _require(orb >= 0 and abs(abs(separation - angle) - orb) <= 0.00012,
                 f"/aspects/{i}/orb")
    jones = source.get("jones_pattern")
    required = {"engine_version", "pattern_en", "pattern_zh", "confidence", "max_gap_deg",
                "occupied_signs", "high_focus_planet"}
    _require(isinstance(jones, dict) and required <= set(jones), "/jones_pattern")
    _require(isinstance(source.get("phase_patterns"), dict), "/phase_patterns")

def topology(planets, rulers):
    """Partition all origins by a canonical terminal cycle or self-dispositor."""
    next_planet = {
        key: rulers[SIGN_KEYS[int(value['longitude'] // 30)]]
        for key, value in planets.items()
    }
    paths, groups = {}, {}
    for key in planets:
        chain = trace_ruler_chain(key, planets, 0, rulers)
        if chain['status'] not in ('cycle', 'self'):
            raise StructureInputError(f"Incomplete dispositor chain: {key}")
        cycle = tuple(sorted(chain['cycle_planets']))
        paths[key] = {
            'path': [node['planet'] for node in chain['nodes']],
            'terminal': list(cycle), 'steps_to_terminal': chain['cycle_start'],
        }
        groups.setdefault(cycle, []).append(key)
    return {
        'edges': [{'id': f'd:{a}:{b}', 'from': a, 'to': b,
                   'depends_on': [f'lon:{a}'], 'rule': 'domicile'}
                  for a, b in next_planet.items()],
        'paths': paths,
        'terminals': [{'members': list(cycle), 'basin': origins,
                       'external_origins': [key for key in origins if key not in cycle],
                       'type': 'self' if len(cycle) == 1 else 'cycle'}
                      for cycle, origins in groups.items()],
        'direct_incoming': {
            key: [a for a, b in next_planet.items() if b == key and a != key]
            for key in planets
        },
    }


def motifs(edges):
    """Enumerate seven specified geometric templates over the ten planets."""
    lookup = {frozenset((edge['from'], edge['to'])): edge for edge in edges}
    result = []

    def add(kind, members, component_edges):
        result.append({
            'id': kind + ':' + ':'.join(sorted(members)), 'kind': kind,
            'members': list(members),
            'depends_on': sorted(edge['id'] for edge in component_edges),
            'max_orb': max(edge['orb'] for edge in component_edges),
        })

    triples = {
        (120, 120, 120): 'grand_trine', (60, 60, 120): 'minor_grand_trine',
        (60, 120, 180): 'wedge', (90, 90, 180): 't_square',
    }
    for members in itertools.combinations(TEN, 3):
        component_edges = [lookup.get(frozenset(pair))
                           for pair in itertools.combinations(members, 2)]
        if any(edge is None for edge in component_edges):
            continue
        kind = triples.get(tuple(sorted(edge['angle'] for edge in component_edges)))
        if kind:
            add(kind, members, component_edges)
    for members in itertools.combinations(TEN, 4):
        component_edges = [lookup.get(frozenset(pair))
                           for pair in itertools.combinations(members, 2)]
        if any(edge is None for edge in component_edges):
            continue
        angles = sorted(edge['angle'] for edge in component_edges)
        paired_oppositions = all(
            sum(edge['angle'] == 180 and key in (edge['from'], edge['to'])
                for edge in component_edges) == 1 for key in members
        )
        if angles == [60, 60, 120, 120, 180, 180] and paired_oppositions:
            add('mystic_rectangle', members, component_edges)
        if angles == [60, 60, 120, 120, 120, 180] and any(
            all(lookup[frozenset(pair)]['angle'] == 120
                for pair in itertools.combinations(triple, 2))
            for triple in itertools.combinations(members, 3)
        ):
            add('kite', members, component_edges)
        if angles == [90, 90, 90, 90, 180, 180] and paired_oppositions:
            add('grand_cross', members, component_edges)
    return result


def _aspect_layers(edges):
    layers = {}
    for cutoff in (6, 8, 10):
        selected = [edge for edge in edges if edge['orb'] <= cutoff]
        adjacent = {key: set() for key in TEN}
        for edge in selected:
            adjacent[edge['from']].add(edge['to'])
            adjacent[edge['to']].add(edge['from'])
        remaining, components = set(TEN), []
        while remaining:
            visited, stack = set(), [min(remaining)]
            while stack:
                key = stack.pop()
                if key in visited:
                    continue
                visited.add(key)
                stack.extend(adjacent[key] - visited)
            remaining -= visited
            components.append(sorted(visited))
        layers[str(cutoff)] = {
            'edges': selected, 'motifs': motifs(selected),
            'degree': {key: len(adjacent[key]) for key in TEN},
            'components': components, 'isolated': [key for key in TEN if not adjacent[key]],
            'rule': 'existing engine Ptolemaic aspect list filtered by orb <= cutoff; ten planets only',
        }
    return layers


def build_structure_graph(source):
    """Project validated calculator data into typed relations and dependencies."""
    validate_structure_source(source)
    raw = {row['key']: row for row in source['natal_planets_full']}
    planets = {
        key: {'longitude': raw[key]['lon'], 'sign': SIGN_KEYS[raw[key]['sign_idx']],
              'house': raw[key]['house_p']} for key in TEN
    }
    indices = {row['key']: i for i, row in enumerate(source['natal_planets_full'])}
    nodes = [{'id': key, **raw[key],
              'source_pointer': f'/natal_planets_full/{indices[key]}'} for key in TEN]
    facts = {f"lon:{node['id']}": {'value': node['lon'],
                                  'source_pointer': node['source_pointer'] + '/lon'}
             for node in nodes}
    edges = []
    for i, aspect in enumerate(source['aspects']):
        a, b = aspect.get('point1'), aspect.get('point2')
        if a in TEN and b in TEN and aspect['angle'] in (0, 60, 90, 120, 180):
            edges.append({
                'id': f"a:{':'.join(sorted((a, b)))}:{aspect['angle']}",
                'from': a, 'to': b, 'angle': aspect['angle'], 'orb': aspect['orb'],
                'aspect': aspect['aspect'], 'source_pointer': f'/aspects/{i}',
                'depends_on': [f'lon:{a}', f'lon:{b}'],
            })
    layers = _aspect_layers(edges)
    day = source['sect'] == '日生人'
    conditions = {
        key: {
            'essential': compute_essential_dignities(key, raw[key]['lon'], day),
            'retrograde': raw[key]['retrograde'],
            'solar': compute_solar_state(raw[key]['lon'], raw['sun']['lon']) if key != 'sun' else None,
            'orientality': compute_orientality(raw[key]['lon'], raw['sun']['lon']) if key != 'sun' else None,
            'source_facts': [f'lon:{key}', 'sect'],
            'rule': 'current classical_engine tables; essential_score is not importance',
        } for key in SEVEN
    }
    receptions = compute_receptions(raw, source['aspects'], day)
    for row in receptions['mutual_receptions']:
        a, b = row['planet1'], row['planet2']
        row['depends_on'] = [f'lon:{a}', f'lon:{b}', 'sect']
        row['domicile_cycle'] = (
            TRADITIONAL_RULERS[SIGN_KEYS[raw[a]['sign_idx']]] == b
            and TRADITIONAL_RULERS[SIGN_KEYS[raw[b]['sign_idx']]] == a
        )
    for row in receptions['receptions']:
        a, b = row['received_planet'], row['dignitor_planet']
        edge_id = next(edge['id'] for edge in edges if {edge['from'], edge['to']} == {a, b})
        row['depends_on'] = [f'lon:{a}', f'lon:{b}', 'sect', edge_id]
    houses = {}
    for system, field in [('placidus', 'house_p'), ('whole_sign', 'house_w')]:
        houses[system] = []
        for row in source['house_ruler_chains'][system]:
            house, sign = row['house'], row['sign']
            houses[system].append({
                'house': house, 'cusp_lon': row['cusp_lon'], 'sign': sign,
                'occupants': [key for key in TEN if raw[key][field] == house],
                'rulers': {policy: {'planet': rules[sign],
                                     'located_house': raw[rules[sign]][field]}
                           for policy, rules in [('traditional', TRADITIONAL_RULERS),
                                                 ('modern', MODERN_RULERS)]},
                'category': 'angular' if house in (1, 4, 7, 10) else
                            'succedent' if house in (2, 5, 8, 11) else 'cadent',
                'source_pointer': f'/house_ruler_chains/{system}/{house - 1}',
            })
    shared = []
    for a, b in itertools.combinations(layers[str(DEFAULT_ASPECT_VIEW)]['motifs'], 2):
        overlap = sorted(set(a['depends_on']) & set(b['depends_on']))
        if overlap:
            shared.append({'structures': [a['id'], b['id']], 'shared_aspect_edges': overlap})
    jones_keys = ('engine_version', 'pattern_en', 'pattern_zh', 'confidence',
                  'max_gap_deg', 'occupied_signs', 'high_focus_planet')
    from services.natal_jones_view import project_observation_details
    jones_facts = {key: source['jones_pattern'][key] for key in jones_keys}
    jones_facts['observation_details'] = project_observation_details(source['jones_pattern'])
    return {
        'schema_version': 'natal-structure-v1',
        'status': 'partial' if source.get('layer_availability') else 'ok',
        'birth_context': source['birth_context'],
        'settings': {
            'zodiac': 'tropical', 'location_assumption': 'See birth_context for resolved coordinates',
            'primary_aspect_view': DEFAULT_ASPECT_VIEW, 'scope': list(TEN),
            'house_systems': ['placidus', 'whole_sign'],
            'modern_rulership': 'replace Scorpio/Aquarius/Pisces with Pluto/Uranus/Neptune, not co-rulership',
            'motif_scope': 'ten planets; no axes, nodes, Chiron or lots',
            'reception_aspects': 'upstream engine list; selected degree-aspect membership is separate',
        },
        'engine': get_version_info(),
        'source_sha256': hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False,
                                                  allow_nan=False).encode()).hexdigest(),
        'nodes': nodes,
        'facts': {**facts, 'sect': {'value': source['sect'], 'source_pointer': '/sect'}},
        'dispositor': {'traditional': topology(planets, TRADITIONAL_RULERS),
                      'modern': topology(planets, MODERN_RULERS)},
        'aspects': layers, 'houses': houses, 'conditions': conditions, 'receptions': receptions,
        'jones': jones_facts, 'axes': source['axes'],
        'engine_additional_patterns': {
            'data': source['phase_patterns'],
            'note': 'Original engine rules and expanded point scope; kept separate from ten-planet graph; no psychological fields',
        },
        'dependencies': {
            'mutual_vs_cycle': [{'planets': [row['planet1'], row['planet2']],
                                'shared_domicile_cycle': row['domicile_cycle'],
                                'depends_on': row['depends_on']}
                               for row in receptions['mutual_receptions']],
            'motif_shared_edges': shared,
            'independence': 'No statistical or psychological independence inferred from distinct rules or shared inputs',
        },
        'layer_availability': source.get('layer_availability', {}), 'interpretations': [],
    }


def _house_independent_source(context, reason, include_supplementary=False):
    """Calculate ten planets at the resolved UTC instant; leave houses absent."""
    from types import SimpleNamespace
    import swisseph as swe
    from engine.natal_chart import NatalChartCalculator
    from services.classical_engine import SIGN_NAMES_ZH
    from services.ephemeris_guard import apply_ephe_path, EphemerisModeError
    from services.jones_pattern import calculate_jones_pattern

    apply_ephe_path()
    jd = context.julian_day_ut
    planets, flags_by_planet, positions = [], {}, {}
    sun_values = None
    for body, key in enumerate(TEN):
        values, flags = swe.calc_ut(jd, body, swe.FLG_SWIEPH | swe.FLG_SPEED)
        if not flags & swe.FLG_SWIEPH:
            raise EphemerisModeError(f"{key}: Swiss file ephemeris required")
        lon = values[0] % 360
        idx = int(lon // 30)
        planets.append({"key": key, "cn": PLANET_ZH[key], "lon": lon,
                        "sign": SIGN_NAMES_ZH[idx], "sign_idx": idx,
                        "house_p": None, "house_w": None,
                        "retrograde": values[3] < 0})
        flags_by_planet[key] = flags
        positions[key] = {"longitude": lon}
        if key == "sun":
            sun_values = values
    if include_supplementary:
        values, flags = swe.calc_ut(jd, swe.TRUE_NODE, swe.FLG_SWIEPH | swe.FLG_SPEED)
        if not flags & swe.FLG_SWIEPH:
            raise EphemerisModeError('true_node: Swiss file ephemeris required')
        for key, name, offset in (('north_node','北交点',0),('south_node','南交点',180)):
            lon=(values[0]+offset)%360; idx=int(lon//30)
            planets.append(dict(key=key,cn=name,lon=lon,sign=SIGN_NAMES_ZH[idx],sign_idx=idx,
                                house_p=None,house_w=None,retrograde=values[3]<0))
        flags_by_planet['true_node']=flags
    snap = context.snapshot
    # True solar altitude determines day/night even when Placidus fails.
    altitude = swe.azalt(jd, swe.ECL2HOR, (snap.lng_wgs84, snap.lat_wgs84, 0),
                         0, 0, sun_values[:3])[1]
    points = [(p["key"], SimpleNamespace(abs_pos=p["lon"])) for p in planets if p['key'] in TEN]
    aspects = NatalChartCalculator().calculate_aspects(points)
    if include_supplementary:
        extra = [(p['key'], SimpleNamespace(abs_pos=p['lon'])) for p in planets if p['key'] not in TEN]
        aspects += [a for a in NatalChartCalculator().calculate_aspects(points+extra)
                    if a['point1'] not in TEN or a['point2'] not in TEN]
    layers = {k: {"status": "unavailable", "reason": "placidus_calculation_failed",
                  "detail": reason} for k in ("placidus", "whole_sign", "axes")}
    return {
        "birth_context": {"lat": snap.lat_wgs84, "lng": snap.lng_wgs84,
                          "tz_iana": snap.tz_iana, "utc_offset": context.utc_offset,
                          "fold": context.fold, "civil_dt": context.civil_dt,
                          "location_id": snap.location_id, "source": snap.source},
        "natal_planets_full": planets, "aspects": aspects,
        "house_ruler_chains": {"placidus": [], "whole_sign": []},
        "axes": {}, "phase_patterns": {}, "layer_availability": layers,
        "sect": "日生人" if altitude >= 0 else "夜生人",
        "jones_pattern": calculate_jones_pattern(positions),
        "source_metadata": {"kind": "house_independent_swiss_ephemeris",
                            "julian_day_ut": jd, "utc_datetime": context.utc_datetime,
                            "ephemeris_flags": flags_by_planet,
                            "sect_rule": "true_solar_altitude_gte_zero",
                            "true_solar_altitude": altitude},
    }


def calculate_structure_graph(*, year, month, day, hour, minute, city="",
                              lat=None, lng=None, location_id=None, fold=None, name="",
                              include_supplementary=False):
    """Calculate a full or explicitly partial graph from an exact civil time.

    Invalid inputs raise ValueError (BirthContextError retains fold candidates).
    A Placidus error leaves all house/axis output unavailable, without substituting
    another house system. Other errors propagate rather than masking broken data.
    """
    import swisseph as swe
    from services.birth_input import validated_birth_values
    from services.calculator import compute, BirthContextError
    from services.civil_time_resolver import CivilTimeResolver, ResolutionStatus
    from services.ephemeris_guard import apply_ephe_path
    from services.location_resolver import LocationResolver, coordinate_location_id

    year, month, day, hour, minute = validated_birth_values(year, month, day, hour, minute)
    if fold is not None and (type(fold) is not int or fold not in (0, 1)):
        raise ValueError("fold must be integer 0 or 1")
    if (lat is None) != (lng is None):
        raise ValueError("lat and lng must be provided together")
    if lat is not None:
        coordinate_location_id(lat, lng)
    snapshot = LocationResolver().resolve(location_id=location_id, lat=lat, lng=lng, query=city)
    if snapshot is None:
        raise ValueError("Unable to resolve birthplace coordinates and timezone")
    resolved = CivilTimeResolver().resolve(snapshot, year, month, day, hour, minute, fold=fold)
    if resolved.context is None or resolved.status not in (ResolutionStatus.NORMAL, ResolutionStatus.AMBIGUOUS):
        raise BirthContextError(resolved.status.value, resolved.message, resolved.candidates)
    apply_ephe_path()
    try:
        swe.houses(resolved.context.julian_day_ut, snapshot.lat_wgs84, snapshot.lng_wgs84, b"P")
    except swe.Error as exc:
        source = _house_independent_source(resolved.context, str(exc), include_supplementary)
    else:
        source = compute(name, year, month, day, hour, minute, city,
                         lat=lat, lng=lng, location_id=location_id, fold=fold)
    graph = build_structure_graph(source)
    if include_supplementary:
        from services.natal_policy_context import extract_supplementary_source, validate_supplementary
        graph['supplementary_source'] = extract_supplementary_source(source)
        validate_supplementary(graph)
    graph["source_metadata"] = source.get("source_metadata", {"kind": "calculator.compute"})
    return graph

