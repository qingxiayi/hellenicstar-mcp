#!/usr/bin/env python3
"""Solar Return（太阳返照 / 日返盘）引擎 —— 纯新增，独立于本命盘引擎。

设计边界（重要）：
  - 不改动任何现有文件的现有逻辑。engine/natal_chart.py、services/calculator.py、
    compute()、/api/v1/calculate 一行不动。稳定的本命盘算法完全不受影响。
  - 只新增这一条独立计算路径。本命盘也在本模块内用同一套 swisseph 口径重算
    （不调 compute()），保证本命盘与日返盘逐项同口径、可直接叠加对比。

为什么不复用 compute()：
  compute()/calculate() 走「整数分钟民用时间」接口（engine 里 datetime(y,m,d,h,m)
  会丢掉秒）。日返盘的上升点对时间极敏感（地球每分钟自转 0.25°），丢 30 秒 = ASC 差
  ~0.125°，对不上真值。所以本模块在「精确 JD」上直接调 swisseph，不落到民用分钟。

口径与本命引擎逐项对齐：
  - 星历路径：services.ephemeris_guard.apply_ephe_path()（仓库内 ephe/，同源）
  - 交点：swe.MEAN_NODE（id 10）——本命引擎字段名叫 true，实际调用的是 MEAN_NODE
  - 凯龙：swe.CHIRON（id 15）
  - 宫位：swe.houses(jd, lat, lng, b'P' 普拉西度 / b'W' 整宫)
  - 行星 flag：FLG_SWIEPH | FLG_SPEED（用 speed<0 判逆行）
  - 相位容许度：分层。本命盘内部沿用本命引擎 10° 口径；日返盘内部用日返专属
    分层矩阵（不套本命 10°，也不砍成统一 3°）——见 NATAL_ASPECT_ORBS / SR_ASPECT_ORBS。
"""

from datetime import datetime, timezone

import swisseph as swe

from services.ephemeris_guard import apply_ephe_path
from services.jones_pattern import calculate_jones_pattern

apply_ephe_path()

# ── 常量（与本命引擎口径一致）──────────────────────────────────────────────
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

# 本命盘内部相位：统一收紧到 6°（合/冲/刑/三分/六分），梅花保持 3°。
# 原因：前端 result.wxml/result.js 只展示 orb ≤ 6° 的相位，若此处用 10°，
# _repeating_aspects 会把「前端看不见」的 6–10° 相位（如土天刑 orb~9°）判为
# 有相，导致日返重复相位与本命展示口径不一致。tests/test_solar_return.py
# 已断言 max(orb) <= 6.0。
NATAL_ASPECT_ORBS = {0: 6.0, 60: 6.0, 90: 6.0, 120: 6.0, 150: 3.0, 180: 6.0}
# 日返盘内部相位：分层容许度。依据 NotebookLM「日返与次限研究」/「Cycles of Light」
# 两库一致结论——Brian Clark 阶梯（合/冲 6°、刑 5°、三分 4°、六分 3°），Eshelman
# （1° 内最强、3–4° 强效、10° 只是部分相位理论边缘）、Lynn Bell 佐证。梅花资料未
# 形成统一标准，保守取 3°（工程选择）。不套本命 10°，也不砍成统一 3°。
SR_ASPECT_ORBS = {0: 6.0, 60: 3.0, 90: 5.0, 120: 4.0, 150: 3.0, 180: 6.0}
# 跨盘相位（日返行星 × 本命行星）：比较盘的核心读点。用紧容许度——研究一致认为
# 跨盘接触看的是「精确落点」，比单盘内部更严：合/冲/刑/三分 3°，六分 2°（软相位更保守）。
CROSS_ASPECT_ORBS = {0: 3.0, 90: 3.0, 120: 3.0, 180: 3.0, 60: 2.0}
ASPECT_ZH = {0: '合', 60: '六分', 90: '刑', 120: '三分', 150: '梅花', 180: '冲'}

# 传统七曜守护（按星座序 0=白羊..11=双鱼）——用于 ASC 守护星（解读焦点层）
RULER_BY_SIGN = ['mars', 'venus', 'mercury', 'moon', 'sun', 'mercury',
                 'venus', 'mars', 'jupiter', 'saturn', 'saturn', 'jupiter']

_SUN_DEG_PER_DAY = 360.0 / 365.2422   # 太阳平均每日黄经推进（找过境用的初猜）


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
    """圆周最小夹角，落在 [0,180]。"""
    d = abs(_norm(a) - _norm(b))
    return d if d <= 180 else 360 - d


def _house_of(lon, cusps):
    """给定 12 宫头经度（顺时针递增，可能跨 0°），定位 lon 落在第几宫（1-12）。"""
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


# ── 出生民用时间 → UTC 儒略日（走本命盘同一条解析链，绝不静默兜底）───────────
def _resolve_birth_jd(year, month, day, hour, minute,
                      lat=None, lng=None, location_id=None, fold=None):
    """把出生民用时间解析成精确 UTC 儒略日，口径与本命盘 compute() 完全一致：
      LocationResolver（坐标/location_id → tz_iana）→ CivilTimeResolver（DST fold/gap 分类）。
    非法时区 / 春拨空白（不存在的时刻）/ 秋拨歧义（未选 fold）一律抛 BirthContextError，
    由端点转结构化 4xx——绝不像旧版那样静默按 UTC 出一张错盘。

    抛 BirthContextError（复用本命引擎同一异常，端点用 _birth_context_error_response 兜）。
    """
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
    # 判据与本命盘 compute() 完全一致：有可用 context 且 NORMAL 或 AMBIGUOUS-已选fold → 放行；
    # NONEXISTENT / INVALID_TZ / AMBIGUOUS-未选fold(context=None,candidates两项) / INVALID_FOLD → 抛错。
    if res.context is not None and res.status in (
            ResolutionStatus.NORMAL, ResolutionStatus.AMBIGUOUS):
        ctx = res.context
    else:
        raise BirthContextError(res.status.value, res.message, res.candidates)

    ut = hour + minute / 60.0 - ctx.utc_offset     # 该民用时刻的 DST-含偏移（小时）
    return swe.julday(year, month, day, ut)


# ── 在任意精确 JD 上出一张盘（本命 / 日返共用同一套口径）────────────────────
def _chart_at(jd, lat, lng, hsys=b'P'):
    cusps, ascmc = swe.houses(jd, float(lat), float(lng), hsys)
    cusps = [_norm(c) for c in cusps[:12]]
    asc, mc = ascmc[0], ascmc[1]
    axes = {
        'ascendant': _point(asc),
        'midheaven': _point(mc),
        'descendant': _point(_norm(asc + 180)),
        'imum_coeli': _point(_norm(mc + 180)),
    }
    planets = {}
    for key, pid in PLANET_DEFS:
        data, _ = swe.calc_ut(jd, pid, _FLAGS)
        lon = _norm(data[0])
        planets[key] = _point(lon, retrograde=(data[3] < 0), speed=data[3],
                              house=_house_of(lon, cusps))
    node_data, _ = swe.calc_ut(jd, NODE_ID, _FLAGS)
    north = _norm(node_data[0])
    chiron_data, _ = swe.calc_ut(jd, CHIRON_ID, _FLAGS)
    special_points = {
        'true_north_lunar_node': _point(north, retrograde=(node_data[3] < 0),
                                        house=_house_of(north, cusps)),
        'true_south_lunar_node': _point(_norm(north + 180),
                                        retrograde=(node_data[3] < 0),
                                        house=_house_of(_norm(north + 180), cusps)),
        'chiron': _point(_norm(chiron_data[0]), retrograde=(chiron_data[3] < 0),
                         house=_house_of(_norm(chiron_data[0]), cusps)),
    }
    return {
        'planets': planets,
        'special_points': special_points,
        'houses': {'cusps': cusps},
        'axes': axes,
    }


# ── 1. 回归时刻：牛顿法（用太阳瞬时速度做精确导数）────────────────────────
def find_return_jd(natal_sun_lon, target_year, birth_month, birth_day, max_iter=40):
    """行运太阳精确回归本命太阳经度的 UTC 儒略日。收敛到 |diff|<1e-9°。"""
    target = _norm(natal_sun_lon)
    jd = swe.julday(target_year, birth_month, birth_day, 12.0)
    last = jd
    for _ in range(max_iter):
        res = swe.calc_ut(jd, swe.SUN, _FLAGS)
        diff = (res[0][0] - target + 180) % 360 - 180
        speed = res[0][3]
        if abs(diff) < 1e-9 or not speed:
            break
        last = jd
        jd -= diff / speed
        if abs(jd - last) > 3.0:
            jd = last - diff * (365.2422 / 360.0) * 0.5
    return jd


def _find_sun_crossing(target_lon, jd_start, jd_end):
    """[jd_start, jd_end] 内行运太阳首次到达 target_lon 的 JD（用于行运太阳过境）。
    太阳一年扫满 360°，窗口取一整年时每个经度必命中一次。"""
    target = _norm(target_lon)
    sun0 = swe.calc_ut(jd_start, swe.SUN, _FLAGS)[0][0]
    ahead = _norm(target - sun0)                 # 还要走多少度
    jd = jd_start + ahead / _SUN_DEG_PER_DAY     # 初猜
    for _ in range(40):
        res = swe.calc_ut(jd, swe.SUN, _FLAGS)
        diff = (res[0][0] - target + 180) % 360 - 180
        speed = res[0][3]
        if abs(diff) < 1e-7 or not speed:
            break
        jd -= diff / speed
    if jd < jd_start - 0.5 or jd > jd_end + 0.5:
        return None
    return jd


# ── 单盘层维度（只依赖日返盘自身）────────────────────────────────────────
def _moon_phase(sun_lon, moon_lon):
    elong = _norm(moon_lon - sun_lon)
    names = ['新月', '上蛾眉', '上弦', '盈凸', '满月', '亏凸', '下弦', '残月']
    idx = int(elong // 45) % 8
    return {'elongation': elong, 'phase_num': idx + 1, 'phase_name': names[idx]}


def _aspects(planets):
    """日返盘内部：十大行星两两主要相位（口径 = 日返专属分层 SR_ASPECT_ORBS）。"""
    keys = [k for k, _ in PLANET_DEFS]
    out = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            sep = _angular_sep(planets[keys[i]]['longitude'], planets[keys[j]]['longitude'])
            for angle, orb_max in SR_ASPECT_ORBS.items():
                orb = abs(sep - angle)
                if orb <= orb_max:
                    out.append({'point1': keys[i], 'point2': keys[j],
                                'angle': angle, 'aspect': ASPECT_ZH[angle], 'orb': orb})
                    break
    return out


def _angular_planets(planets, axes, orb=8.0):
    """合四轴（±orb）的行星 → [{planet, axis, orb, house, strength}]。
    Lynn Bell：合四轴放到 8°，但 3° 内才是核心；strength 标 core(≤3°)/extended，
    前端不会把 7.9° 合轴和 0.2° 合轴显示成同等强度。"""
    out = []
    axis_lons = {'asc': axes['ascendant']['longitude'], 'dsc': axes['descendant']['longitude'],
                 'mc': axes['midheaven']['longitude'], 'ic': axes['imum_coeli']['longitude']}
    for key, _ in PLANET_DEFS:
        plon = planets[key]['longitude']
        best = None
        for axname, alon in axis_lons.items():
            sep = _angular_sep(plon, alon)
            if sep <= orb and (best is None or sep < best[1]):
                best = (axname, sep)
        if best:
            out.append({'planet': key, 'axis': best[0], 'orb': best[1],
                        'house': planets[key]['house'],
                        'strength': 'core' if best[1] <= 3.0 else 'extended'})
    return out


def _intercepted_signs(cusps):
    """截夺星座：不作为任何宫头星座、被整个包含在某宫内的星座 → [{house, sign}]。"""
    cusp_signs = {_sign_index(c) for c in cusps}
    out = []
    for s in range(12):
        if s not in cusp_signs:
            mid = s * 30 + 15
            out.append({'house': _house_of(mid, cusps), 'sign': SIGNS_ZH[s], 'sign_index': s})
    return out


def _elements(planets):
    counts = {'fire': 0, 'earth': 0, 'air': 0, 'water': 0}
    for key, _ in PLANET_DEFS:
        counts[ELEMENT_EN[ELEMENTS_ZH[planets[key]['sign_index']]]] += 1
    missing = [e for e, c in counts.items() if c == 0]
    return {'counts': counts, 'missing': missing}


def _unaspected_planets(aspects):
    aspected = set()
    for a in aspects:
        aspected.add(a['point1'])
        aspected.add(a['point2'])
    return [k for k, _ in PLANET_DEFS if k not in aspected]


# ── 叠加层维度（日返盘 × 本命盘）──────────────────────────────────────────
def _planets_in_houses(source_planets, target_cusps):
    return [{'planet': k, 'house': _house_of(source_planets[k]['longitude'], target_cusps)}
            for k, _ in PLANET_DEFS]


def _angle_contacts(sr_axes, natal_planets, orb=3.0):
    """日返四轴合本命行星（±orb）→ [{axis, natal_planet, orb}]。"""
    out = []
    for axname, key in (('asc', 'ascendant'), ('dsc', 'descendant'),
                        ('mc', 'midheaven'), ('ic', 'imum_coeli')):
        alon = sr_axes[key]['longitude']
        for pk, _ in PLANET_DEFS:
            sep = _angular_sep(alon, natal_planets[pk]['longitude'])
            if sep <= orb:
                out.append({'axis': axname, 'natal_planet': pk, 'orb': sep})
    return out


def _degree_contacts(sr_planets, natal_planets, natal_axes, orb=3.0):
    """日返行星合本命行星/四轴（±orb）→ [{sr_planet, natal_point, orb}]。
    Lynn Bell 同度数接触取 3°；输出精确 orb，由前端突出 1° 以内的最强接触。

    日返太阳合本命太阳必然排除：日返的定义就是「太阳回到本命度数的那一刻」，
    这一对必然重合（残差只是找返照时刻算法的精度余量，不是占星发现），当成
    「接触」列出没有信息量，无条件跳过，不看 orb 大小。"""
    natal_points = {k: natal_planets[k]['longitude'] for k, _ in PLANET_DEFS}
    for axname, key in (('asc', 'ascendant'), ('mc', 'midheaven')):
        natal_points[axname] = natal_axes[key]['longitude']
    out = []
    for sk, _ in PLANET_DEFS:
        sp = sr_planets[sk]
        slon = sp['longitude']
        speed = sp.get('speed')
        for nk, nlon in natal_points.items():
            if sk == 'sun' and nk == 'sun':
                continue
            sep = _angular_sep(slon, nlon)
            if sep <= orb:
                out.append({'sr_planet': sk, 'natal_point': nk, 'orb': sep,
                            'applying': _applying(slon, speed, nlon, 0)})
    return out


def _cross_aspects(sr_planets, natal_planets):
    """跨盘相位：日返每颗行星 × 本命每颗行星的主要相位（比较盘中心相位网）。
    口径 = CROSS_ASPECT_ORBS（紧）。日返太阳合本命太阳是日返定义本身，不作为
    有区分度的跨盘相位输出。→ [{sr_planet, natal_planet, angle, aspect, orb,
    applying}]。

    入相/出相与本命盘同一口径（engine/natal_chart.py）：前瞻一小步，看容许度
    是收窄还是拉开。跨盘的区别在于只有日返行星在动——本命盘是出生瞬间的定格，
    不参与运动，所以相对速度就是日返行星自己的速度。"""
    out = []
    for sk, _ in PLANET_DEFS:
        sp = sr_planets[sk]
        slon = sp['longitude']
        speed = sp.get('speed')
        for nk, _2 in PLANET_DEFS:
            if sk == 'sun' and nk == 'sun':
                continue
            nlon = natal_planets[nk]['longitude']
            hit = _pair_aspect(slon, nlon, CROSS_ASPECT_ORBS)
            if hit:
                out.append({'sr_planet': sk, 'natal_planet': nk,
                            'angle': hit[0], 'aspect': ASPECT_ZH[hit[0]],
                            'orb': hit[1],
                            'applying': _applying(slon, speed, nlon, hit[0])})
    return out


# 前瞻步长（天）：与 engine/natal_chart.py 的 dt=0.001 一致，约 1.44 分钟。
_APPLYING_DT = 0.001
_ORB_EPSILON = 1e-6


def _applying(moving_lon, speed, fixed_lon, angle):
    """跨盘相位的入相/出相：True=入相，False=出相，None=方向不明。

    只有 moving_lon（日返行星）在动，fixed_lon（本命点）静止。速度缺失或
    几乎为零时返回 None，不猜方向——宁可不显示，也不给错误的结论。"""
    if speed is None or abs(speed) <= 1e-9:
        return None
    now_orb = abs(_angular_sep(moving_lon, fixed_lon) - angle)
    later_lon = _norm(moving_lon + speed * _APPLYING_DT)
    later_orb = abs(_angular_sep(later_lon, fixed_lon) - angle)
    if abs(later_orb - now_orb) < _ORB_EPSILON:
        return None
    return later_orb < now_orb


def _pair_aspect(lon_a, lon_b, orbs):
    """两点在给定容许度矩阵 orbs 下是否成主要相位 → (angle, orb) 或 None。"""
    sep = _angular_sep(lon_a, lon_b)
    for angle, orb_max in orbs.items():
        orb = abs(sep - angle)
        if orb <= orb_max:
            return angle, orb
    return None


def _repeating_aspects(natal_planets, sr_planets):
    """本命有相位的行星对，在日返里也成相位 → [{pair, natal_aspect, sr_aspect, change}]。
    不要求相位类型相同（重现的是「这对行星又互动」，不是同一个相位）。两端各用各的
    容许度：本命端用 6° 口径（对齐前端展示），日返端用日返分层矩阵。"""
    keys = [k for k, _ in PLANET_DEFS]
    out = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            n = _pair_aspect(natal_planets[a]['longitude'], natal_planets[b]['longitude'],
                             NATAL_ASPECT_ORBS)
            s = _pair_aspect(sr_planets[a]['longitude'], sr_planets[b]['longitude'],
                             SR_ASPECT_ORBS)
            if n and s:
                out.append({
                    'pair': [a, b],
                    'natal_aspect': {'angle': n[0], 'name': ASPECT_ZH[n[0]], 'orb': n[1]},
                    'sr_aspect': {'angle': s[0], 'name': ASPECT_ZH[s[0]], 'orb': s[1]},
                    'change': 'same' if n[0] == s[0] else 'different',
                })
    return out


# ── 时间轴维度 ────────────────────────────────────────────────────────────
def _moon_progressions(sr_moon_lon, sr_planets, sr_cusps, orb=1.0):
    """日返月亮 +1°/月 × 12，逐月检查是否合日返行星/宫头（±orb）。"""
    out = []
    targets = [(k, sr_planets[k]['longitude']) for k, _ in PLANET_DEFS if k != 'moon']
    targets += [(f'cusp{i + 1}', sr_cusps[i]) for i in range(12)]
    for m in range(1, 13):
        plon = _norm(sr_moon_lon + m * 1.0)
        hits = [{'target': name, 'orb': _angular_sep(plon, tlon)}
                for name, tlon in targets if _angular_sep(plon, tlon) <= orb]
        if hits:
            out.append({'month': m, 'moon_lon': plon, 'hits': hits})
    return out


def _sun_transits(sr_jd, sr_planets, sr_axes):
    """日返后一年里，行运太阳过境（精确合）日返四轴/行星 → [{target, date, lon}]。
    对每个目标经度解出太阳到达的确切日期（不做粗糙月采样，避免漏过）。"""
    jd_end = sr_jd + 366.0
    targets = [(k, sr_planets[k]['longitude']) for k, _ in PLANET_DEFS if k != 'sun']
    targets += [('asc', sr_axes['ascendant']['longitude']),
                ('mc', sr_axes['midheaven']['longitude']),
                ('dsc', sr_axes['descendant']['longitude']),
                ('ic', sr_axes['imum_coeli']['longitude'])]
    out = []
    for name, tlon in targets:
        jd = _find_sun_crossing(tlon, sr_jd, jd_end)
        if jd is not None:
            out.append({'target': name, 'longitude': tlon, 'date': _jd_to_utc_str(jd)})
    out.sort(key=lambda x: x['date'])
    return out


def _metonic_cycle(sr_moon_lon, natal_moon_lon, orb=3.0):
    sep = _angular_sep(sr_moon_lon, natal_moon_lon)
    return {'is_return': sep <= orb, 'orb': sep}


def _saturn_return(sr_saturn_lon, natal_saturn_lon, orb=2.0):
    sep = _angular_sep(sr_saturn_lon, natal_saturn_lon)
    return {'is_return': sep <= orb, 'orb': sep}


def _moon_element_cycle(natal_sun_lon, birth_month, birth_day, target_year, this_sign,
                         this_element, max_lookback=5):
    """SR 月亮跨年连续同元素追踪——依据 NotebookLM「Cycles of Light」/「日返与次限
    研究」两库一致结论（Lynn Bell + Brian Clark）：SR 月亮每年前进约一个三分相，
    平均在同一元素停留 2-3 年（偶尔 4 年），不该孤立看单独一年，要看这几年是
    「一个系列」——月亮首次进入某元素那年是「新篇章开启」，中间年份是「主题
    深化」，元素即将改变前的最后一年是「系列收尾」。同一元素跨年时星座本身
    通常不同（每年前进约一个三分相，在同一元素的 2-3 个星座间循环），所以
    星座要逐年标，不能只标元素。

    只需查前一年、后一年（各一次 find_return_jd + 一次月亮经度，不用算全盘），
    向前最多回溯 max_lookback 年数出这是系列第几年——2-4 年的真实场景只要
    1-3 次回溯就会撞到元素不同而停下，足够便宜。
    """
    def sign_and_element_at(year):
        jd = find_return_jd(natal_sun_lon, year, birth_month, birth_day)
        moon_lon = swe.calc_ut(jd, swe.MOON, _FLAGS)[0][0]
        return _sign_zh(moon_lon), ELEMENTS_ZH[_sign_index(moon_lon)]

    prev_sign, prev_element = sign_and_element_at(target_year - 1)
    next_sign, next_element = sign_and_element_at(target_year + 1)

    run_length_before = 0
    for back in range(1, max_lookback + 1):
        if (prev_element if back == 1 else sign_and_element_at(target_year - back)[1]) == this_element:
            run_length_before += 1
        else:
            break
    position_in_run = run_length_before + 1
    continues_next_year = next_element == this_element

    if position_in_run == 1:
        stage = 'opening' if continues_next_year else 'single'
    else:
        stage = 'continuing' if continues_next_year else 'closing'

    return {
        'sign': this_sign,
        'prev_sign': prev_sign, 'prev_element': prev_element,
        'next_sign': next_sign, 'next_element': next_element,
        'element': this_element,
        'position_in_run': position_in_run,
        'stage': stage,  # 'opening' | 'continuing' | 'closing' | 'single'
    }


# ── 解读焦点维度 ──────────────────────────────────────────────────────────
def _asc_ruler(sr_asc_lon, sr_planets):
    ruler_key = RULER_BY_SIGN[_sign_index(sr_asc_lon)]
    rp = sr_planets[ruler_key]
    return {'planet': ruler_key, 'planet_zh': PLANET_ZH[ruler_key],
            'sign': rp['sign'], 'house': rp['house'], 'retrograde': rp['retrograde']}


def _annual_focus(sr_asc_lon, natal_cusps, asc_ruler):
    return {'sr_asc_in_natal_house': _house_of(sr_asc_lon, natal_cusps),
            'asc_ruler': asc_ruler}


# ── 时间格式化 ────────────────────────────────────────────────────────────
def _jd_to_utc_dt(jd):
    y, m, d, ut = swe.revjul(jd)
    hh = int(ut)
    mm = int((ut - hh) * 60)
    ss = int(round((((ut - hh) * 60) - mm) * 60))
    if ss >= 60:
        ss -= 60
        mm += 1
    if mm >= 60:
        mm -= 60
        hh += 1
    return datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc)


def _jd_to_utc_str(jd):
    return _jd_to_utc_dt(jd).strftime('%Y-%m-%dT%H:%M:%SZ')


def _jd_to_local_str(jd, tz_iana):
    if not tz_iana:
        return None
    dt_utc = _jd_to_utc_dt(jd)
    try:
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from backports.zoneinfo import ZoneInfo
        return dt_utc.astimezone(ZoneInfo(str(tz_iana))).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return None


# ── 地基版：只出日返盘本体（保留给基础端点/测试）──────────────────────────
def compute_solar_return(natal_sun_lon, target_year, birth_month, birth_day,
                         residence_lat, residence_lng,
                         residence_tz=None, residence_city='', house_system='P'):
    """只算日返盘本体（不含本命叠加）。地基阶段用，输出对齐 /calculate 字段口径。"""
    hsys = b'W' if str(house_system).upper() == 'W' else b'P'
    jd = find_return_jd(natal_sun_lon, target_year, birth_month, birth_day)
    chart = _chart_at(jd, residence_lat, residence_lng, hsys)
    sun_lon = chart['planets']['sun']['longitude']
    moon_lon = chart['planets']['moon']['longitude']
    return {
        'sr_jd': jd,
        'sr_utc': _jd_to_utc_str(jd),
        'sr_local': _jd_to_local_str(jd, residence_tz),
        'residence': {'lat': float(residence_lat), 'lng': float(residence_lng),
                      'tz': residence_tz, 'city': residence_city},
        'house_system': 'whole_sign' if hsys == b'W' else 'placidus',
        'planets': chart['planets'],
        'special_points': chart['special_points'],
        'houses': chart['houses'],
        'axes': chart['axes'],
        'sun_house': chart['planets']['sun']['house'],
        'moon': {'longitude': moon_lon, 'sign': _sign_zh(moon_lon),
                 'house': chart['planets']['moon']['house'],
                 'element': ELEMENTS_ZH[_sign_index(moon_lon)]},
        'lunation_phase': _moon_phase(sun_lon, moon_lon),
        'aspects': _aspects(chart['planets']),
        'jones_pattern': calculate_jones_pattern(
            {k: {'longitude': chart['planets'][k]['longitude']} for k, _ in PLANET_DEFS}),
    }


# ── 完整版：本命盘 + 日返盘 + 24 维度（端点主入口）──────────────────────────
def compute_solar_return_full(birth_year, birth_month, birth_day, birth_hour, birth_minute,
                              birth_lat, birth_lng,
                              target_year, residence_lat, residence_lng,
                              residence_tz=None, residence_city='', house_system='P',
                              birth_location_id=None, birth_fold=None):
    """完整日返盘：内部重算本命盘（同口径），组装看板 24 维度。

    出生时区走本命盘同一条解析链（LocationResolver + CivilTimeResolver）：非法时区 /
    春拨空白 / 秋拨歧义抛 BirthContextError，绝不静默按 UTC 出错盘。日返盘在精确 JD
    上出，两盘同口径可直接叠加。返回按看板四层分组：single / overlay / timeline / focus。
    """
    hsys = b'W' if str(house_system).upper() == 'W' else b'P'

    # 本命盘（同口径重算）：出生时间走本命盘同一条解析链，非法/歧义/空白直接抛错
    natal_jd = _resolve_birth_jd(birth_year, birth_month, birth_day, birth_hour, birth_minute,
                                 lat=birth_lat, lng=birth_lng,
                                 location_id=birth_location_id, fold=birth_fold)
    natal = _chart_at(natal_jd, birth_lat, birth_lng, hsys)
    natal_sun_lon = natal['planets']['sun']['longitude']

    # 日返盘（精确 JD）
    sr_jd = find_return_jd(natal_sun_lon, target_year, birth_month, birth_day)
    sr = _chart_at(sr_jd, residence_lat, residence_lng, hsys)

    sr_planets = sr['planets']
    sr_axes = sr['axes']
    sr_cusps = sr['houses']['cusps']
    natal_planets = natal['planets']
    natal_cusps = natal['houses']['cusps']

    sun_lon = sr_planets['sun']['longitude']
    moon_lon = sr_planets['moon']['longitude']
    aspects = _aspects(sr_planets)
    asc_ruler = _asc_ruler(sr_axes['ascendant']['longitude'], sr_planets)

    return {
        'sr_jd': sr_jd,
        'sr_utc': _jd_to_utc_str(sr_jd),
        'sr_local': _jd_to_local_str(sr_jd, residence_tz),
        'natal_jd': natal_jd,
        'residence': {'lat': float(residence_lat), 'lng': float(residence_lng),
                      'tz': residence_tz, 'city': residence_city},
        'house_system': 'whole_sign' if hsys == b'W' else 'placidus',

        # ═══ 单盘层（13）═══
        'single': {
            'planets': sr_planets,                                              # 1
            'angles': sr_axes,                                                  # 2
            'houses': sr['houses'],                                             # 3
            'sun_house': sr_planets['sun']['house'],                            # 4
            'moon': {'longitude': moon_lon, 'sign': _sign_zh(moon_lon),         # 5
                     'house': sr_planets['moon']['house'],
                     'element': ELEMENTS_ZH[_sign_index(moon_lon)]},
            'lunation_phase': _moon_phase(sun_lon, moon_lon),                   # 6
            'retrograde_planets': [k for k, _ in PLANET_DEFS                    # 7
                                   if sr_planets[k]['retrograde']],
            'angular_planets': _angular_planets(sr_planets, sr_axes),          # 8
            'jones_pattern': calculate_jones_pattern(                          # 9
                {k: {'longitude': sr_planets[k]['longitude']} for k, _ in PLANET_DEFS}),
            'intercepted_signs': _intercepted_signs(sr_cusps),                 # 10
            'elements': _elements(sr_planets),                                 # 11
            'unaspected_planets': _unaspected_planets(aspects),               # 12
            'aspects': aspects,                                                # 13
        },

        # ═══ 叠加层（6）═══
        'overlay': {
            'sr_planets_in_natal_houses': _planets_in_houses(sr_planets, natal_cusps),   # 14
            'natal_planets_in_sr_houses': _planets_in_houses(natal_planets, sr_cusps),   # 15
            'angle_contacts': _angle_contacts(sr_axes, natal_planets),                   # 16
            'degree_contacts': _degree_contacts(sr_planets, natal_planets, natal['axes']),  # 17
            'repeating_aspects': _repeating_aspects(natal_planets, sr_planets),          # 18
            'cross_aspects': _cross_aspects(sr_planets, natal_planets),                  # 19 跨盘相位（比较盘中心）
        },

        # ═══ 时间轴（4+1）═══
        'timeline': {
            'moon_progressions': _moon_progressions(moon_lon, sr_planets, sr_cusps),     # 19
            'sun_transits': _sun_transits(sr_jd, sr_planets, sr_axes),                   # 20
            'metonic_cycle': _metonic_cycle(moon_lon, natal_planets['moon']['longitude']),  # 21
            'saturn_return': _saturn_return(sr_planets['saturn']['longitude'],           # 22
                                            natal_planets['saturn']['longitude']),
            'moon_element_cycle': _moon_element_cycle(                                   # 22b
                natal_sun_lon, birth_month, birth_day, target_year,
                _sign_zh(moon_lon), ELEMENTS_ZH[_sign_index(moon_lon)]),
        },

        # ═══ 解读焦点（2）═══
        'focus': {
            'asc_ruler': asc_ruler,                                             # 23
            'annual_focus': _annual_focus(sr_axes['ascendant']['longitude'],    # 24
                                          natal_cusps, asc_ruler),
        },

        # 本命盘（供前端叠加展示，可选）
        'natal': {'planets': natal_planets, 'axes': natal['axes'],
                  'houses': natal['houses'], 'special_points': natal['special_points']},
    }
