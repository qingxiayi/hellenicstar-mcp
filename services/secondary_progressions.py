#!/usr/bin/env python3
"""Secondary Progressions（次限推进 / 二次推运）引擎 —— 纯新增，独立于本命盘引擎。

设计依据与天文学口径：
  - 一日一年象征法则（Day-for-a-Year / A Day for a Year）：
    地球自转一天（1天）象征地球公转一年（1回归年 = 365.2422天）。
    progressed_jd = birth_jd + age
  - 推进四轴（Progressed Angles）：默认 Naibod 平均弧，每岁推进 RAMC 0.98564733°。
    可选 solar_arc_in_ra，使用次限太阳与本命太阳的真实赤经差；两者不是同一种方法。
    由推进 RAMC 和出生地地理纬度计算推进上升点（ASC）和中天（MC）。
  - 相位系统：
    重点提供次限对本命（Progressed to Natal）相位（心理占星核心触发）
    与次限内部（Progressed to Progressed）相位。
"""

from datetime import date, datetime
import swisseph as swe

from services.ephemeris_guard import apply_ephe_path
from services.solar_arc_engine import TROPICAL_YEAR_DAYS, MAX_SUPPORTED_AGE

apply_ephe_path()

SIGNS_ZH = ['白羊', '金牛', '双子', '巨蟹', '狮子', '处女',
            '天秤', '天蝎', '射手', '摩羯', '水瓶', '双鱼']
ELEMENTS_ZH = ['火', '土', '风', '水', '火', '土', '风', '水',
               '火', '土', '风', '水']

PLANET_DEFS = [
    ('sun', swe.SUN), ('moon', swe.MOON), ('mercury', swe.MERCURY),
    ('venus', swe.VENUS), ('mars', swe.MARS), ('jupiter', swe.JUPITER),
    ('saturn', swe.SATURN), ('uranus', swe.URANUS), ('neptune', swe.NEPTUNE),
    ('pluto', swe.PLUTO),
]
PLANET_ZH = {
    'sun': '太阳', 'moon': '月亮', 'mercury': '水星', 'venus': '金星',
    'mars': '火星', 'jupiter': '木星', 'saturn': '土星', 'uranus': '天王星',
    'neptune': '海王星', 'pluto': '冥王星', 'chiron': '凯龙星',
    'mean_north_node': '平均北交点', 'mean_south_node': '平均南交点',
}
NODE_ID = swe.MEAN_NODE
CHIRON_ID = swe.CHIRON
_FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED
NAIBOD_ARC_DEG_PER_YEAR = 0.98564733

# 次限推运容许度（经典心理占星：次限行星对本命紧容许度 1.0°，合/冲可放宽至 1.5°）
PROG_TO_NATAL_ORBS = {0: 1.5, 60: 1.0, 90: 1.2, 120: 1.2, 150: 1.0, 180: 1.5}
PROG_INTERNAL_ORBS = {0: 1.5, 60: 1.0, 90: 1.2, 120: 1.2, 150: 1.0, 180: 1.5}
ASPECT_ZH = {0: '合', 60: '六分', 90: '刑', 120: '三分', 150: '梅花', 180: '冲'}


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


def _aspect_between(lon_a, lon_b, orb_matrix):
    d = _angular_sep(lon_a, lon_b)
    for angle, max_orb in orb_matrix.items():
        orb = abs(d - angle)
        if orb <= max_orb:
            return angle, orb
    return None, None


def _is_applying(moving_lon, speed, target_lon, target_angle):
    if speed is None:
        return None
    # 预测微小时间步长后的角度变化
    step_lon = moving_lon + speed * 0.01
    curr_diff = abs(_angular_sep(moving_lon, target_lon) - target_angle)
    next_diff = abs(_angular_sep(step_lon, target_lon) - target_angle)
    return next_diff < curr_diff


def compute_secondary_progressions(birth_year, birth_month, birth_day, birth_hour, birth_minute,
                                    birth_lat, birth_lng,
                                    age=None, as_of=None, house_system='P',
                                    angle_progression_method='naibod',
                                    birth_location_id=None, birth_fold=None):
    """计算完整次限推进星盘、推进四轴及对本命的相位。

    参数：
      - age: 事件年龄（岁），如 36.0
      - as_of: 事件日期（ISO 字符串 'YYYY-MM-DD'），若提供则自动由 (as_of - birth) 换算精确年龄
      - house_system: 'P' (Placidus) 或 'W' (Whole Sign)
    """
    hsys = b'W' if str(house_system).lower() in ('w', 'whole_sign') else b'P'

    natal_jd = _resolve_birth_jd(birth_year, birth_month, birth_day, birth_hour, birth_minute,
                                 lat=birth_lat, lng=birth_lng,
                                 location_id=birth_location_id, fold=birth_fold)
    natal = _chart_at(natal_jd, birth_lat, birth_lng, hsys)
    natal_planets = natal['planets']
    natal_special = natal['special_points']
    natal_axes = natal['axes']
    natal_cusps = natal['houses']['cusps']

    # 确定推进年龄与次限时间
    if age is not None:
        prog_age = float(age)
    elif as_of is not None:
        if isinstance(as_of, str):
            as_of_dt = datetime.fromisoformat(as_of)
        elif isinstance(as_of, (date, datetime)):
            as_of_dt = as_of
        else:
            raise ValueError(f"无法解析 as_of: {as_of}")
        as_of_jd = swe.julday(as_of_dt.year, as_of_dt.month, as_of_dt.day, 12.0)
        prog_age = (as_of_jd - natal_jd) / TROPICAL_YEAR_DAYS
    else:
        raise ValueError("需提供 age 或 as_of")

    if not (0.0 <= prog_age <= MAX_SUPPORTED_AGE):
        raise ValueError(f"次限年龄需在 0 到 {MAX_SUPPORTED_AGE} 之间（当前: {prog_age}）")

    prog_jd = natal_jd + prog_age

    # 1. 计算次限行星位置
    prog_planets = {}
    for name, body_id in PLANET_DEFS:
        res = swe.calc_ut(prog_jd, body_id, _FLAGS)
        lon = res[0][0]
        speed = res[0][3]
        prog_planets[name] = _point(lon, retrograde=(speed < 0), speed=speed)

    prog_special = {}
    node_res = swe.calc_ut(prog_jd, NODE_ID, _FLAGS)
    node_lon = node_res[0][0]
    prog_special['mean_north_node'] = _point(node_lon, retrograde=(node_res[0][3] < 0), speed=node_res[0][3])
    prog_special['mean_south_node'] = _point(_norm(node_lon + 180), retrograde=(node_res[0][3] < 0))

    chiron_res = swe.calc_ut(prog_jd, CHIRON_ID, _FLAGS)
    c_lon = chiron_res[0][0]
    prog_special['chiron'] = _point(c_lon, retrograde=(chiron_res[0][3] < 0),
                                    speed=chiron_res[0][3])

    # 2. 推进四轴：Naibod 平均弧为默认；真实太阳赤经弧是显式可选口径。
    if angle_progression_method == 'naibod':
        ra_arc = prog_age * NAIBOD_ARC_DEG_PER_YEAR
    elif angle_progression_method == 'solar_arc_in_ra':
        sun_nat_ra = swe.calc_ut(natal_jd, swe.SUN, swe.FLG_SWIEPH | swe.FLG_EQUATORIAL)[0][0]
        sun_prg_ra = swe.calc_ut(prog_jd, swe.SUN, swe.FLG_SWIEPH | swe.FLG_EQUATORIAL)[0][0]
        ra_arc = (sun_prg_ra - sun_nat_ra) % 360.0
    else:
        raise ValueError('angle_progression_method 需为 naibod 或 solar_arc_in_ra')

    armc_nat = (swe.sidtime(natal_jd) * 15.0 + birth_lng) % 360.0
    armc_prog = (armc_nat + ra_arc) % 360.0
    eps_prog = swe.calc_ut(prog_jd, swe.ECL_NUT)[0][0]

    prog_cusps, prog_ascmc = swe.houses_armc(armc_prog, birth_lat, eps_prog, hsys)
    prog_cusps = list(prog_cusps)

    prog_axes = {
        'ascendant': _point(prog_ascmc[0]),
        'midheaven': _point(prog_ascmc[1]),
        'descendant': _point(_norm(prog_ascmc[0] + 180)),
        'imum_coeli': _point(_norm(prog_ascmc[1] + 180)),
    }

    # 补齐落宫：次限星落次限宫 与 次限星落本命宫
    for p_name, p_data in prog_planets.items():
        p_data['house'] = _house_of(p_data['longitude'], prog_cusps)
        p_data['natal_house'] = _house_of(p_data['longitude'], natal_cusps)

    for p_name, p_data in prog_special.items():
        p_data['house'] = _house_of(p_data['longitude'], prog_cusps)
        p_data['natal_house'] = _house_of(p_data['longitude'], natal_cusps)

    # 3. 计算次限对本命相位（Progressed to Natal Aspects）
    all_prog_points = {**prog_planets, **prog_special, **prog_axes}
    all_natal_points = {**natal_planets, **natal_special, **natal_axes}

    prog_to_natal_aspects = []
    for prg_key, prg_p in all_prog_points.items():
        prg_lon = prg_p['longitude']
        prg_speed = prg_p.get('speed')
        for nat_key, nat_p in all_natal_points.items():
            nat_lon = nat_p['longitude']
            ang, orb = _aspect_between(prg_lon, nat_lon, PROG_TO_NATAL_ORBS)
            if ang is not None:
                app = _is_applying(prg_lon, prg_speed, nat_lon, ang)
                prog_to_natal_aspects.append({
                    'progressed_point': prg_key,
                    'progressed_point_zh': PLANET_ZH.get(prg_key, prg_key),
                    'natal_point': nat_key,
                    'natal_point_zh': PLANET_ZH.get(nat_key, nat_key),
                    'aspect': ASPECT_ZH[ang],
                    'angle': ang,
                    'orb': round(orb, 4),
                    'applying': app,
                })

    # 4. 次限月相（Rudhyar 8 阶段）
    sun_lon = prog_planets['sun']['longitude']
    moon_lon = prog_planets['moon']['longitude']
    elong = (moon_lon - sun_lon) % 360.0
    phase_names = ['新月', '娥眉月', '上弦月', '盈凸月', '满月', '亏凸月', '下弦月', '残月']
    phase_idx = int(elong // 45.0) % 8
    progress_pct = round((elong % 45.0) / 45.0 * 100, 1)

    # 5. 次限星盘与星历对应时刻
    prog_y, prog_m, prog_d, prog_ut = swe.revjul(prog_jd)
    prog_ephemeris_date = f"{prog_y:04d}-{prog_m:02d}-{prog_d:02d} UT {prog_ut:.2f}"

    return {
        'age': round(prog_age, 4),
        'progressed_jd': prog_jd,
        'progressed_ephemeris_date': prog_ephemeris_date,
        'angle_progression_method': angle_progression_method,
        'house_system': 'whole_sign' if hsys == b'W' else 'placidus',
        'progressed_chart': {
            'planets': prog_planets,
            'special_points': prog_special,
            'axes': prog_axes,
            'houses': {'cusps': prog_cusps},
            'lunation_phase': {
                'elongation': round(elong, 4),
                'phase_num': phase_idx + 1,
                'phase_name': phase_names[phase_idx],
                'progress_pct': progress_pct,
            },
        },
        'progressed_to_natal_aspects': prog_to_natal_aspects,
        'natal': {
            'planets': natal_planets,
            'special_points': natal_special,
            'axes': natal_axes,
            'houses': natal['houses'],
        },
    }
