"""Selected-system natal positions, independent of dual-system method reports."""
from copy import deepcopy

from services.calculator import (
    _LRUCache, _ctx_token, _dedup_aspects, _extract_svg_data, _jpl_chiron,
    resolve_birth_context, PLANET_CN, SIGN_CN,
)
from services.engine_adapter import calc_from_context
from services.house_systems import calculate_houses

_CACHE = _LRUCache(200)


def calculate_positions(year, month, day, hour, minute, location_id, house_system, fold=None):
    ctx = resolve_birth_context(year, month, day, hour, minute, location_id=location_id, fold=fold)
    snap = ctx.snapshot
    key = (_ctx_token('', ctx), house_system)
    cached = _CACHE.get(key)
    if cached is not None:
        return deepcopy(cached)
    # Preflight returns domain errors before the legacy engine's error envelope.
    frame = calculate_houses(ctx.julian_day_ut, snap.lat_wgs84, snap.lng_wgs84, house_system)
    data = calc_from_context(ctx, country_code=snap.country_code or 'CN', house_system=house_system)
    if 'chiron' not in data.get('special_points', {}):
        _jpl_chiron(data, ctx, frame.ascmc[0])
    rows = []
    sources = [(key, PLANET_CN[key], p) for key, p in data['planets'].items() if key in PLANET_CN]
    special = data['special_points']
    for source, key, label in (
        ('part_of_spirit', 'pars_spiritus', '精神点'),
        ('part_of_fortune', 'pars_fortuna', '福点'),
        ('true_north_lunar_node', 'north_node', '北交点'),
        ('true_south_lunar_node', 'south_node', '南交点'),
        ('chiron', 'chiron', '凯龙星'),
    ):
        if source in special:
            sources.append((key, label, special[source]))
    for key_name, label, point in sources:
        lon = point['longitude']
        rows.append(dict(key=key_name, cn=label, lon=round(lon, 4),
                         sign=SIGN_CN.get(point['sign'], point['sign']),
                         house=frame.house_of(lon), retrograde=point.get('retrograde', False)))
    axes = {short: {'sign_zh': data['axes'][long]['sign_zh'], 'lon': data['axes'][long]['longitude']}
            for short, long in (('asc', 'ascendant'), ('dsc', 'descendant'),
                                ('mc', 'midheaven'), ('ic', 'imum_coeli'))}
    from services.natal_house_rulers import build_selected_house_ruler_chains
    from hellenistic import sect_from_horizon
    result = {
        'house_system': house_system,
        'sect': sect_from_horizon(data['planets']['sun']['longitude'], frame.ascmc[0]),
        'planet_longitudes': {k: v['longitude'] for k, v in data['planets'].items()},
        'moon_phase': data.get('moon_phase'),
        'phase_patterns': data.get('patterns', {}).get('phase_patterns_enhanced', {}),
        'birth_context': dict(lat=snap.lat_wgs84, lng=snap.lng_wgs84,
                              tz_iana=snap.tz_iana, utc_offset=ctx.utc_offset, fold=ctx.fold,
                              civil_dt=ctx.civil_dt, location_id=snap.location_id, source=snap.source),
        'asc_lon': frame.ascmc[0], 'cusps': list(frame.cusps), 'axes': axes,
        'natal_planets_full': rows, 'aspects': _dedup_aspects(data.get('aspects', [])),
        'svg_data': _extract_svg_data(dict(data=data, name='', year=year, month=month, day=day, hour=hour, minute=minute)),
        'house_ruler_chains': build_selected_house_ruler_chains(data['planets'], frame),
    }
    _CACHE[key] = deepcopy(result)
    return result
