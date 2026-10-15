#!/usr/bin/env python3
"""Lunar Return（月亮返照 / 月返盘）引擎 —— 纯新增，独立于本命盘引擎。

设计边界：
  - 不改动任何现有文件的既有逻辑。engine/natal_chart.py、services/calculator.py 一行不动。
  - 在精确 JD 上通过 swisseph 计算，保持与日返盘、本命盘相同的高精度星历口径。
  - 居住地重置（Relocation）：根据指定居住地经纬度重新计算返照四轴与十二宫位。
  - 单盘层（13维度）、本命叠加层（6维度）与解读焦点（月度焦点、ASC守护星）。
"""

from datetime import date, datetime, timedelta, timezone
from calendar import monthrange
import swisseph as swe

from services.ephemeris_guard import apply_ephe_path
from services.jones_pattern import calculate_jones_pattern

apply_ephe_path()

# ── 常量（与本命引擎、日返引擎口径完全一致）────────────────────────────────
SIGNS_ZH = ['白羊', '金牛', '双子', '巨蟹', '狮子', '处女',
            '天秤', '天蝎', '射手', '摩羯', '水瓶', '双鱼']
ELEMENTS_ZH = ['火', '土', '风', '水', '火', '土', '风', '水',
               '火', '土', '风', '水']
ELEMENT_EN = {'火': 'fire', '土': 'earth', '风': 'air', '水': 'water'}

PLANET_DEFS = [
    ('sun', swe.SUN), ('moon', swe.MOON), ('mercury', swe.MERCURY),
    ('venus', swe.VENUS), ('mars', swe.MARS), ('jupiter', swe.JUPITER),
    ('saturn', swe.SATURN), ('uranus', swe.URANUS), ('neptune', swe.NEPTUNE),
    ('pluto', swe.PLUTO),
]
PLANET_ZH = {
    'sun': '太阳', 'moon': '月亮', 'mercury': '水星', 'venus': '金星',
    'mars': '火星', 'jupiter': '木星', 'saturn': '土星', 'uranus': '天王星',
    'neptune': '海王星', 'pluto': '冥王星',
}
NODE_ID = swe.MEAN_NODE
CHIRON_ID = swe.CHIRON
_FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED

NATAL_ASPECT_ORBS = {0: 6.0, 60: 6.0, 90: 6.0, 120: 6.0, 150: 3.0, 180: 6.0}
LR_ASPECT_ORBS = {0: 6.0, 60: 3.0, 90: 5.0, 120: 4.0, 150: 3.0, 180: 6.0}
CROSS_ASPECT_ORBS = {0: 3.0, 90: 3.0, 120: 3.0, 180: 3.0, 60: 2.0}
ASPECT_ZH = {0: '合', 60: '六分', 90: '刑', 120: '三分', 150: '梅花', 180: '冲'}

RULER_BY_SIGN = ['mars', 'venus', 'mercury', 'moon', 'sun', 'mercury',
                 'venus', 'mars', 'jupiter', 'saturn', 'saturn', 'jupiter']


# ── 基础几何 ──────────────────────────────────────────────────────────────
def _norm(a):
    return a % 360.0


def _sign_index(lon):
    return int(_norm(lon) // 30) % 12


def _sign_zh(lon):
    return SIGNS_ZH[_sign_index(lon)]


def _deg_in_sign(lon):
    return _norm(lon) % 30.0


def _angular_sep(a, b):
    d = abs(_norm(a) - _norm(b))
    return d if d <= 180 else 360 - d


def _house_of(lon, cusps):
    lon = _norm(lon)
    for i in range(12):
        start = _norm(cusps[i])
        end = _norm(cusps[(i + 1) % 12])
        span = _norm(end - start)
        offset = _norm(lon - start)
        if offset < span or span == 0:
            return i + 1
    return 12


def _point(lon, retrograde=False, speed=None, house=None):
    lon = _norm(lon)
    p = {
        'longitude': lon,
        'sign': _sign_zh(lon),
        'sign_index': _sign_index(lon),
        'deg_in_sign': _deg_in_sign(lon),
        'retrograde': bool(retrograde),
    }
    if speed is not None:
        p['speed'] = speed
    if house is not None:
        p['house'] = house
    return p


def _resolve_birth_jd(year, month, day, hour, minute,
                      lat=None, lng=None, location_id=None, fold=None):
    from services.location_resolver import LocationResolver
    from services.civil_time_resolver import CivilTimeResolver, ResolutionStatus
    from services.calculator import BirthContextError

    snapshot = LocationResolver().resolve(
        location_id=location_id or None,
        lat=lat, lng=lng,
    )
    if snapshot is None:
        raise BirthContextError('invalid_tz', '无法解析出生地时区，请核对出生地经纬度', None)

    res = CivilTimeResolver().resolve(snapshot, year, month, day, hour, minute, fold=fold)
    if res.context is not None and res.status in (
            ResolutionStatus.NORMAL, ResolutionStatus.AMBIGUOUS):
        ctx = res.context
    else:
        raise BirthContextError(res.status.value, res.message, res.candidates)

    ut = hour + minute / 60.0 - ctx.utc_offset
    return swe.julday(year, month, day, ut)


def _chart_at(jd, lat, lng, hsys=b'P'):
    apply_ephe_path()
    cusps, ascmc = swe.houses(jd, lat, lng, hsys)
    cusps = list(cusps)

    planets = {}
    for name, body_id in PLANET_DEFS:
        res = swe.calc_ut(jd, body_id, _FLAGS)
        lon = res[0][0]
        speed = res[0][3]
        planets[name] = _point(lon, retrograde=(speed < 0), speed=speed,
                               house=_house_of(lon, cusps))

    special_points = {}
    node_res = swe.calc_ut(jd, NODE_ID, _FLAGS)
    node_lon = node_res[0][0]
    special_points['mean_north_node'] = _point(node_lon, retrograde=(node_res[0][3] < 0), speed=node_res[0][3],
                                         house=_house_of(node_lon, cusps))
    special_points['mean_south_node'] = _point(_norm(node_lon + 180), retrograde=(node_res[0][3] < 0),
                                          house=_house_of(_norm(node_lon + 180), cusps))

    chiron_res = swe.calc_ut(jd, CHIRON_ID, _FLAGS)
    c_lon = chiron_res[0][0]
    special_points['chiron'] = _point(c_lon, retrograde=(chiron_res[0][3] < 0),
                                      speed=chiron_res[0][3], house=_house_of(c_lon, cusps))

    axes = {
        'ascendant': _point(ascmc[0]),
        'midheaven': _point(ascmc[1]),
        'descendant': _point(_norm(ascmc[0] + 180)),
        'imum_coeli': _point(_norm(ascmc[1] + 180)),
    }

    return {
        'planets': planets,
        'special_points': special_points,
        'houses': {'cusps': cusps},
        'axes': axes,
    }


# ── 1. 回归时刻：牛顿迭代法求解月亮返照 ─────────────────────────────────────
def find_lunar_return_jd(natal_moon_lon, target_year, target_month, target_day=None,
                         max_iter=40, tz_iana=None):
    """指定所在地民用月份内的月亮返照；同月两次时选最接近指定日或月中者。"""
    from zoneinfo import ZoneInfo
    zone = ZoneInfo(tz_iana) if tz_iana else timezone.utc
    target = _norm(natal_moon_lon)
    days = monthrange(target_year, target_month)[1]
    if target_day is not None:
        date(target_year, target_month, target_day)
    month_start = swe.julday(target_year, target_month, 1, 0.0)
    anchor = target_day if target_day is not None else (days + 1) / 2
    candidates = []
    for offset in range(-4, days + 5, 4):
        jd = month_start + offset + 0.5
        for _ in range(max_iter):
            res = swe.calc_ut(jd, swe.MOON, _FLAGS)
            diff = (res[0][0] - target + 180) % 360 - 180
            if abs(diff) < 1e-8:
                break
            jd -= diff / res[0][3]
        if abs(diff) >= 1e-7:
            continue
        local = _jd_to_utc_dt(jd).astimezone(zone)
        if ((local.year, local.month) == (target_year, target_month)
                and all(abs(jd - prev) > 1 for prev in candidates)):
            candidates.append(jd)
    if not candidates:
        raise ValueError('指定月份内没有月亮返照时刻')
    return min(candidates, key=lambda jd: abs(
        (_jd_to_utc_dt(jd).astimezone(zone).day - anchor)))


def _moon_phase(sun_lon, moon_lon):
    elong = _norm(moon_lon - sun_lon)
    names = ['新月', '娥眉月', '上弦月', '盈凸月', '满月', '亏凸月', '下弦月', '残月']
    idx = int(elong // 45) % 8
    return {'elongation': elong, 'phase_num': idx + 1, 'phase_name': names[idx]}


def _aspects(planets):
    keys = [k for k, _ in PLANET_DEFS]
    found = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            p1, p2 = keys[i], keys[j]
            d = _angular_sep(planets[p1]['longitude'], planets[p2]['longitude'])
            for angle, max_orb in LR_ASPECT_ORBS.items():
                orb = abs(d - angle)
                if orb <= max_orb:
                    found.append({
                        'point1': p1, 'point2': p2,
                        'point1_zh': PLANET_ZH[p1], 'point2_zh': PLANET_ZH[p2],
                        'aspect': ASPECT_ZH[angle], 'angle': angle,
                        'orb': round(orb, 4), 'max_orb': max_orb,
                    })
                    break
    return found


def _angular_planets(planets, axes, orb=8.0):
    axis_lons = {
        'asc': axes['ascendant']['longitude'],
        'mc': axes['midheaven']['longitude'],
        'dsc': axes['descendant']['longitude'],
        'ic': axes['imum_coeli']['longitude'],
    }
    hits = []
    for p, data in planets.items():
        lon = data['longitude']
        for ax, ax_lon in axis_lons.items():
            d = _angular_sep(lon, ax_lon)
            if d <= orb:
                hits.append({
                    'planet': p, 'planet_zh': PLANET_ZH[p],
                    'axis': ax, 'orb': round(d, 4),
                })
    return hits


def _intercepted_signs(cusps):
    house_signs = [_sign_index(c) for c in cusps]
    present = set(house_signs)
    intercepted = []
    for sign_idx in range(12):
        if sign_idx not in present:
            intercepted.append({
                'sign_index': sign_idx,
                'sign': SIGNS_ZH[sign_idx],
                'element': ELEMENTS_ZH[sign_idx],
            })
    return intercepted


def _elements(planets):
    counts = {'fire': 0, 'earth': 0, 'air': 0, 'water': 0}
    for p in planets.values():
        counts[ELEMENT_EN[ELEMENTS_ZH[p['sign_index']]]] += 1
    return counts


def _unaspected_planets(aspects):
    connected = set()
    for a in aspects:
        connected.add(a['point1'])
        connected.add(a['point2'])
    return [k for k, _ in PLANET_DEFS if k not in connected]


def _planets_in_houses(source_planets, target_cusps):
    return {k: _house_of(v['longitude'], target_cusps) for k, v in source_planets.items()}


def _angle_contacts(lr_axes, natal_planets, orb=3.0):
    hits = []
    for ax_key, ax_label in (('ascendant', 'ASC'), ('midheaven', 'MC')):
        ax_lon = lr_axes[ax_key]['longitude']
        for p_key, p_data in natal_planets.items():
            d = _angular_sep(ax_lon, p_data['longitude'])
            if d <= orb:
                hits.append({
                    'lr_axis': ax_label, 'natal_planet': p_key,
                    'natal_planet_zh': PLANET_ZH[p_key],
                    'aspect': '合', 'angle': 0, 'orb': round(d, 4),
                })
    return hits


def _degree_contacts(lr_planets, natal_planets, natal_axes, orb=3.0):
    targets = {**{f'p_{k}': (v['longitude'], PLANET_ZH[k]) for k, v in natal_planets.items()},
               'a_asc': (natal_axes['ascendant']['longitude'], '本命上升'),
               'a_mc': (natal_axes['midheaven']['longitude'], '本命中天')}
    hits = []
    for lr_p, lr_data in lr_planets.items():
        lr_lon = lr_data['longitude']
        for t_key, (t_lon, t_zh) in targets.items():
            d = _angular_sep(lr_lon, t_lon)
            if d <= orb:
                hits.append({
                    'lr_planet': lr_p, 'lr_planet_zh': PLANET_ZH[lr_p],
                    'natal_target': t_key, 'natal_target_zh': t_zh,
                    'aspect': '合', 'angle': 0, 'orb': round(d, 4),
                })
    return hits


def _cross_aspects(lr_planets, natal_planets):
    hits = []
    for lr_p, lr_data in lr_planets.items():
        lr_lon = lr_data['longitude']
        for nat_p, nat_data in natal_planets.items():
            nat_lon = nat_data['longitude']
            d = _angular_sep(lr_lon, nat_lon)
            for angle, max_orb in CROSS_ASPECT_ORBS.items():
                orb = abs(d - angle)
                if orb <= max_orb:
                    hits.append({
                        'lr_planet': lr_p, 'lr_planet_zh': PLANET_ZH[lr_p],
                        'natal_planet': nat_p, 'natal_planet_zh': PLANET_ZH[nat_p],
                        'aspect': ASPECT_ZH[angle], 'angle': angle,
                        'orb': round(orb, 4), 'max_orb': max_orb,
                    })
                    break
    return hits


def _pair_aspect(lon_a, lon_b, orbs):
    d = _angular_sep(lon_a, lon_b)
    for angle, max_orb in orbs.items():
        orb = abs(d - angle)
        if orb <= max_orb:
            return angle, orb
    return None, None


def _repeating_aspects(natal_planets, lr_planets):
    keys = [k for k, _ in PLANET_DEFS]
    hits = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            p1, p2 = keys[i], keys[j]
            nat_ang, nat_orb = _pair_aspect(
                natal_planets[p1]['longitude'], natal_planets[p2]['longitude'],
                NATAL_ASPECT_ORBS)
            if nat_ang is None:
                continue
            lr_ang, lr_orb = _pair_aspect(
                lr_planets[p1]['longitude'], lr_planets[p2]['longitude'],
                LR_ASPECT_ORBS)
            if lr_ang is None:
                continue
            hits.append({
                'point1': p1, 'point2': p2,
                'point1_zh': PLANET_ZH[p1], 'point2_zh': PLANET_ZH[p2],
                'natal_aspect': ASPECT_ZH[nat_ang], 'natal_angle': nat_ang,
                'natal_orb': round(nat_orb, 4),
                'lr_aspect': ASPECT_ZH[lr_ang], 'lr_angle': lr_ang,
                'lr_orb': round(lr_orb, 4),
                'same_aspect': bool(nat_ang == lr_ang),
            })
    return hits


def _asc_ruler(lr_asc_lon, lr_planets):
    ruler_key = RULER_BY_SIGN[_sign_index(lr_asc_lon)]
    rp = lr_planets[ruler_key]
    return {'planet': ruler_key, 'planet_zh': PLANET_ZH[ruler_key],
            'sign': rp['sign'], 'house': rp['house'], 'retrograde': rp['retrograde']}


def _monthly_focus(lr_asc_lon, natal_cusps, asc_ruler):
    return {'lr_asc_in_natal_house': _house_of(lr_asc_lon, natal_cusps),
            'asc_ruler': asc_ruler}


def _jd_to_utc_dt(jd):
    y, m, d, ut = swe.revjul(jd)
    return datetime(y, m, d, tzinfo=timezone.utc) + timedelta(seconds=round(ut * 3600))


def _jd_to_utc_str(jd):
    return _jd_to_utc_dt(jd).strftime('%Y-%m-%dT%H:%M:%SZ')


def _jd_to_local_str(jd, tz_iana):
    if not tz_iana:
        return None
    dt_utc = _jd_to_utc_dt(jd)
    try:
        from zoneinfo import ZoneInfo
        return dt_utc.astimezone(ZoneInfo(str(tz_iana))).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return None


# ── 主计算函数入口 ────────────────────────────────────────────────────────
def compute_lunar_return_full(birth_year, birth_month, birth_day, birth_hour, birth_minute,
                              birth_lat, birth_lng,
                              target_year, target_month, target_day=None,
                              residence_lat=None, residence_lng=None,
                              residence_tz=None, residence_city='', house_system='P',
                              birth_location_id=None, birth_fold=None):
    """计算完整的月亮返照盘（Lunar Return）。

    内部重算本命盘以保证同一高精度星历口径，并在精确返照时刻建立月返星盘与本命叠加。
    """
    hsys = b'W' if str(house_system).lower() in ('w', 'whole_sign') else b'P'

    natal_jd = _resolve_birth_jd(birth_year, birth_month, birth_day, birth_hour, birth_minute,
                                 lat=birth_lat, lng=birth_lng,
                                 location_id=birth_location_id, fold=birth_fold)
    natal = _chart_at(natal_jd, birth_lat, birth_lng, hsys)
    natal_moon_lon = natal['planets']['moon']['longitude']

    # 若未提供 residence 经纬度，默认以出生地为准
    r_lat = float(residence_lat if residence_lat is not None else birth_lat)
    r_lng = float(residence_lng if residence_lng is not None else birth_lng)

    lr_jd = find_lunar_return_jd(natal_moon_lon, target_year, target_month,
                                 target_day=target_day, tz_iana=residence_tz)
    lr = _chart_at(lr_jd, r_lat, r_lng, hsys)

    lr_planets = lr['planets']
    lr_axes = lr['axes']
    lr_cusps = lr['houses']['cusps']
    natal_planets = natal['planets']
    natal_cusps = natal['houses']['cusps']

    sun_lon = lr_planets['sun']['longitude']
    moon_lon = lr_planets['moon']['longitude']
    aspects = _aspects(lr_planets)
    asc_ruler = _asc_ruler(lr_axes['ascendant']['longitude'], lr_planets)

    return {
        'lr_jd': lr_jd,
        'lr_utc': _jd_to_utc_str(lr_jd),
        'lr_local': _jd_to_local_str(lr_jd, residence_tz),
        'natal_jd': natal_jd,
        'residence': {'lat': r_lat, 'lng': r_lng, 'tz': residence_tz, 'city': residence_city},
        'house_system': 'whole_sign' if hsys == b'W' else 'placidus',

        # 单盘层
        'single': {
            'planets': lr_planets,
            'special_points': lr['special_points'],
            'angles': lr_axes,
            'houses': lr['houses'],
            'moon_house': lr_planets['moon']['house'],
            'sun_house': lr_planets['sun']['house'],
            'sun': {'longitude': sun_lon, 'sign': _sign_zh(sun_lon),
                    'house': lr_planets['sun']['house'],
                    'element': ELEMENTS_ZH[_sign_index(sun_lon)]},
            'lunation_phase': _moon_phase(sun_lon, moon_lon),
            'retrograde_planets': [k for k, _ in PLANET_DEFS if lr_planets[k]['retrograde']],
            'angular_planets': _angular_planets(lr_planets, lr_axes),
            'jones_pattern': calculate_jones_pattern(
                {k: {'longitude': lr_planets[k]['longitude']} for k, _ in PLANET_DEFS}),
            'intercepted_signs': _intercepted_signs(lr_cusps),
            'elements': _elements(lr_planets),
            'unaspected_planets': _unaspected_planets(aspects),
            'aspects': aspects,
        },

        # 叠加层
        'overlay': {
            'lr_planets_in_natal_houses': _planets_in_houses(lr_planets, natal_cusps),
            'natal_planets_in_lr_houses': _planets_in_houses(natal_planets, lr_cusps),
            'angle_contacts': _angle_contacts(lr_axes, natal_planets),
            'degree_contacts': _degree_contacts(lr_planets, natal_planets, natal['axes']),
            'repeating_aspects': _repeating_aspects(natal_planets, lr_planets),
            'cross_aspects': _cross_aspects(lr_planets, natal_planets),
        },

        # 解读焦点
        'focus': {
            'asc_ruler': asc_ruler,
            'monthly_focus': _monthly_focus(lr_axes['ascendant']['longitude'], natal_cusps, asc_ruler),
        },

        'natal': {'planets': natal_planets, 'axes': natal['axes'],
                  'houses': natal['houses'], 'special_points': natal['special_points']},
    }
