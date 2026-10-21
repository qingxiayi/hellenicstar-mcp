"""
希腊星智 · 计算服务层
封装所有占星引擎调用，返回纯 dict/bytes，与 Flask / HTTP 完全解耦
"""
import hashlib, sys, os

# 确保项目根目录在 sys.path 中（services/ 的子目录导入引擎模块）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fortuna_projection import project, placidus_house, whole_sign_house
from services.zodiac_constants import SIGN_RULER, SIGN_ZH, SIGN_MODERN_RULER
from services.natal_house_rulers import build_house_ruler_chains
from hellenistic import analyze, analyze_both, SIGN_CN, _dignity, STAGES, HOUSE_TYPE, PLANET_JOY, \
    SIGN_ELEMENT, TRIPLICITY, DAY_PLANETS, NIGHT_PLANETS, REVERSE_PK, NATURAL_MALEFICS

from services.geocoding import _log_geo_observation, GEO_OBSERVE_PREFIX

# 凶星定义（包含冥王星）
MALEFICS = {"火星", "土星", "冥王星"}

# 行星中文名
PLANET_CN = {
    "sun": "太阳", "moon": "月亮", "mercury": "水星", "venus": "金星",
    "mars": "火星", "jupiter": "木星", "saturn": "土星",
    "uranus": "天王星", "neptune": "海王星", "pluto": "冥王星"
}

# ── 缓存（LRU，最多 200 条，防内存泄漏）──────────────────────────────────
from collections import OrderedDict

_CACHE_MAX = 200

class _LRUCache:
    """简单 LRU dict，容量满时淘汰最久未访问的条目。"""
    def __init__(self, maxsize=_CACHE_MAX):
        self._d: OrderedDict = OrderedDict()
        self._max = maxsize

    def __contains__(self, key):
        return key in self._d

    def __getitem__(self, key):
        self._d.move_to_end(key)
        return self._d[key]

    def __setitem__(self, key, value):
        if key in self._d:
            self._d.move_to_end(key)
        self._d[key] = value
        if len(self._d) > self._max:
            self._d.popitem(last=False)   # 淘汰最旧

    def get(self, key, default=None):
        if key in self:
            return self[key]
        return default

_calc_cache = _LRUCache(200)  # {token: full_data_dict}

# ── 算法版本号：每次更新核心计算逻辑后 bump，让旧缓存全部失效 ──
# 已知 bump 时机：三分主星算法修正、宫位逻辑调整、评分体系变更等
#
# v2（2026-09-11）：修 CALC-001。Kerykeion 一直把星历路径改到它自带的
# kerykeion/sweph（缺行星与月亮文件），十大主行星请求 FLG_SWIEPH 却静默回退
# Moshier；services/ephemeris_guard.py 现在把我们的目录钉进查找列表。位置随之
# 变动，最大 0.403 角秒（月亮），度分显示看不出差别，但 v1 缓存里存的是 Moshier
# 结果，必须失效重算。
CALC_VERSION = "v2"




def _ctx_token(name, ctx):
    """计算缓存指纹（plan §4.3）：完全决定一张盘的稳定字段。
    含 name + location_id + 坐标 + tz_iana + 民用时刻 + fold —— 下拉选 / 打字 / 案例
    重算只要解析到同一 ctx 就同 token 命中；裸坐标 location_id 为空时靠坐标+tz 区分，
    根治旧 token 以裸 city 串入 key 的混淆。"""
    s = ctx.snapshot
    raw = (f"{CALC_VERSION}|{name}|{s.location_id}|{s.lat_wgs84:.4f}|{s.lng_wgs84:.4f}"
           f"|{s.tz_iana}|{s.version}|{ctx.civil_dt}|{ctx.utc_offset}|{ctx.fold}")
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _jpl_chiron(data, ctx, asc_lon):
    """凯龙兜底：引擎 swe.CHIRON 不可用（默认星历路径缺 seas_18.se1 小行星星历）时，
    用 JPL Horizons 补算。关键（plan §5.4）：用 ctx.julian_day_ut —— 与主盘同一个 UTC
    瞬间，删旧「再推时区 + utc_offset=8 兜底」。astroquery 缺失则静默跳过（凯龙非阻塞）。"""
    try:
        from astroquery.jplhorizons import Horizons
        from astropy.time import Time
    except Exception:
        return
    try:
        t = Time(ctx.julian_day_ut, format='jd')
        eph = Horizons(id='2060', location='500', epochs=t.jd).ephemerides()
        chiron_lon = float(eph['ObsEclLon'][0])
        eph2 = Horizons(id='2060', location='500', epochs=t.jd + 1).ephemerides()
        chiron_retrograde = float(eph2['ObsEclLon'][0]) < chiron_lon

        zodiac_names = ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sgr","Cap","Aqu","Pis"]
        zodiac_cn = ["白羊座","金牛座","双子座","巨蟹座","狮子座","处女座","天秤座","天蝎座","射手座","摩羯座","水瓶座","双鱼座"]
        sign_idx = int(chiron_lon // 30)
        house = int(((chiron_lon - asc_lon) % 360) // 30) + 1
        data["special_points"]["chiron"] = {
            "sign": zodiac_names[sign_idx],
            "sign_zh": zodiac_cn[sign_idx],
            "position": chiron_lon - sign_idx * 30,
            "longitude": chiron_lon,
            "retrograde": chiron_retrograde,
            "house": house,
        }
        _zh = {"sun":"太阳","moon":"月亮","mercury":"水星","venus":"金星","mars":"火星","jupiter":"木星","saturn":"土星","uranus":"天王星","neptune":"海王星","pluto":"冥王星","true_north_lunar_node":"北交点","true_south_lunar_node":"南交点","part_of_fortune":"福点","part_of_spirit":"精神点"}
        _phase_defs = [(0,8,"合相"),(60,6,"六分相"),(90,7,"四分相"),(120,8,"三分相"),(180,8,"对分相"),(150,3,"梅花相位")]
        _chiron_aspects = []
        def _collect(items):
            for _k, _v in items:
                _lon = _v.get("longitude") if isinstance(_v, dict) else None
                if _lon is None or _k == "chiron":
                    continue
                _diff = abs(chiron_lon - _lon)
                if _diff > 180:
                    _diff = 360 - _diff
                for _ang, _orb, _nm in _phase_defs:
                    _o = abs(_diff - _ang)
                    if _o <= _orb:
                        _chiron_aspects.append({"point1": _k, "point1_zh": _zh.get(_k,_k), "point2": "chiron", "point2_zh": "凯龙星", "aspect": _nm, "angle": _ang, "orb": round(_o,2), "exact_diff": round(_diff,2), "involves_axis": False})
        _collect(data["planets"].items())
        _collect(data.get("special_points", {}).items())
        if _chiron_aspects:
            data.setdefault("aspects", []).extend(_chiron_aspects)
    except Exception as e:
        print(f"Warning: JPL Chiron query failed: {e}")


# ═══════════════════════════════════════════
#  核心计算
# ═══════════════════════════════════════════

def _dedup_aspects(aspects):
    """去重相位列表：同一对天体同一相位角只保留 orb 最小的一条，并过滤 orb > 10°"""
    seen = {}
    for a in aspects:
        if a.get("orb", 99) > 10:
            continue
        # 用排序后的天体对 + 相位角作为唯一 key，消除 (A,B) / (B,A) 重复
        key = (tuple(sorted([a.get("point1", ""), a.get("point2", "")])), a.get("angle", 0))
        if key not in seen or a.get("orb", 99) < seen[key].get("orb", 99):
            seen[key] = a
    return sorted(seen.values(), key=lambda x: x.get("orb", 99))


class BirthContextError(ValueError):
    """compute 前置的出生瞬间解析需用户决策/失败：携带结构化 status + candidates，
    供 API 层分流 HTTP（ambiguous→409 带候选 / nonexistent·invalid_tz→422 /
    invalid_fold→400）。继承 ValueError：老 catch 点仍能兜底 400，不会漏成 500。"""

    def __init__(self, status, message, candidates=()):
        super().__init__(message)
        self.status = status          # ResolutionStatus 值字符串
        self.status_message = message
        self.candidates = tuple(candidates)   # tuple[ResolvedBirthContext]


def compute(name, year, month, day, hour, minute, city, lat=None, lng=None, tz=None,
            location_id=None, fold=None):
    """
    完整计算本命盘 + 古典评分 + 福点盘。
    返回 MCP 计算和渲染所需数据，不生成解读或课程作业。
    location_id / fold: 新解析链入参（下拉签发的 canonical id / 秋拨歧义所选 fold）。
    tz: 旧形参，保留兼容旧调用方但已忽略——时区现由 resolver 单一来源决定（plan §5.4）。
    """
    from services.birth_input import validated_birth_values
    year, month, day, hour, minute = validated_birth_values(
        year, month, day, hour, minute)

    # ── 单一解析链（plan §2/§5.4）：LocationResolver → CivilTimeResolver → ctx ──
    # 旧链已删：normalize_timezone_for_coords / CITY_COORDINATES 进程级注入 /
    # resolve_city 双轮 / _geo_tz_override 类属性写清 / 凯龙 utc_offset=8 兜底。
    from services.location_resolver import LocationResolver
    from services.civil_time_resolver import CivilTimeResolver, ResolutionStatus

    snapshot = LocationResolver().resolve(
        location_id=location_id,
        lat=float(lat) if lat is not None else None,
        lng=float(lng) if lng is not None else None,
        query=city,
    )
    if snapshot is None:
        raise ValueError(
            f"无法解析地点「{city or location_id or ''}」的坐标/时区，"
            f"请从下拉列表选择城市后重试。"
        )

    res = CivilTimeResolver().resolve(snapshot, year, month, day, hour, minute, fold=fold)
    if res.context is not None and res.status in (
        ResolutionStatus.NORMAL, ResolutionStatus.AMBIGUOUS
    ):
        ctx = res.context
    else:
        # NONEXISTENT / INVALID_TZ / AMBIGUOUS-未选 fold / INVALID_FOLD：显式报错，
        # 绝不静默兜底或替用户选 fold。携带 status + candidates 供 API 层分流。
        raise BirthContextError(res.status.value, res.message, res.candidates)

    token = _ctx_token(name, ctx)

    cache_hit = token in _calc_cache
    if not cache_hit:
        # 一次引擎调用出全量（行星/宫位/四轴/交点/凯龙/福点·精神点/日月食/相位/格局），
        # swisseph 与 kerykeion 同喂 ctx 的同一个 UTC 瞬间（plan §5.3）。
        from services.engine_adapter import calc_from_context
        data = calc_from_context(ctx, name=name, city=city,
                                 country_code=snapshot.country_code or "CN")
        lunations = data.get("lunations", {})

        r_pla, r_ws = analyze_both(data, name)
        cusps = data["houses"]["cusps"]
        asc_lon = cusps[0]

        fof_lon = data["special_points"]["part_of_fortune"]["longitude"]
        pos_lon = data["special_points"]["part_of_spirit"]["longitude"]
        fof_np, mapping_p, cared_p = project(data, placidus_house, cusps)
        fof_nw, mapping_w, cared_w = project(data, whole_sign_house, asc_lon)

        # 凯龙兜底：引擎 swe.CHIRON 不可用时用 JPL（ctx 同一 UTC 瞬间，plan §5.4）
        if "chiron" not in data.get("special_points", {}):
            _jpl_chiron(data, ctx, asc_lon)

        
        # 重新检测相位格局（凯龙星已通过JPL加入special_points）
        try:
            from adapter import _enhance_with_patterns
            from services.engine_adapter import strip_axis_patterns
            if "chiron" in data.get("special_points", {}):
                enhanced = _enhance_with_patterns(data)
                if enhanced:
                    data["patterns"] = enhanced.get("patterns", data.get("patterns", {}))
                    # 重检走的是 adapter 原始输出，四轴过滤要跟主路径同口径，
                    # 否则「有 JPL 凯龙的盘」会比别的盘多出含上升点的格局。
                    if isinstance(data["patterns"], dict) and "phase_patterns_enhanced" in data["patterns"]:
                        data["patterns"]["phase_patterns_enhanced"] = strip_axis_patterns(
                            data["patterns"]["phase_patterns_enhanced"]
                        )
        except Exception as recheck_err:
            pass  # 格局重检失败不阻塞主流程
        
        # 构建凶星检查用的行星数据（双制分开）
        natal_planets_p = []
        natal_planets_w = []
        for pk, pv in data["planets"].items():
            if pk in ("chiron", "siris", "north_node", "south_node", "hyponym"):
                continue
            planet_cn = PLANET_CN.get(pk, pk)
            planet_lon = pv["longitude"]
            sign_cn = pv.get("sign_zh", "")
            # Placidus 宫位
            house_p = pv.get("house", 1)
            # WholeSign 宫位: ASC星座=1宫, 依次
            asc_si = int(asc_lon // 30) % 12
            si = int(planet_lon // 30) % 12
            house_w = (si - asc_si + 12) % 12 + 1
            natal_planets_p.append((planet_cn, str(house_p), sign_cn, pk))
            natal_planets_w.append((planet_cn, str(house_w), sign_cn, pk))
        
        _calc_cache[token] = {
            "name": name, "year": year, "month": month,
            "day": day, "hour": hour, "minute": minute, "city": city,
            "data": data, "r_pla": r_pla, "r_ws": r_ws,
            "cusps": cusps, "asc_lon": asc_lon,
            "fof_lon": fof_lon, "pos_lon": pos_lon,
            "fof_np": fof_np, "mapping_p": mapping_p, "cared_p": cared_p,
            "fof_nw": fof_nw, "mapping_w": mapping_w, "cared_w": cared_w,
            "natal_planets_p": natal_planets_p,
            "natal_planets_w": natal_planets_w,
            "lunations": lunations,
        }

    full = _calc_cache[token]
    if cache_hit:
        # 埋点改用新链单一真相 ctx/snapshot（退役 _get_timezone_for_city 旧 tz 源）
        try:
            _log_geo_observation(
                "compute_result",
                city.strip(),
                lat=snapshot.lat_wgs84,
                lng=snapshot.lng_wgs84,
                tz=snapshot.tz_iana,
                source="cache",
            )
        except Exception:
            pass
    # 出生上下文真值：坐标/时区/UTC 偏移只有 snapshot+ctx 这一个来源，
    # 挂在 full 上供 _build_summary 输出给前端头部展示，前端不得自行推算。
    # 写在缓存命中判断之外，因为缓存里存的是引擎结果，ctx/snapshot 每次调用都新解析。
    full["birth_context"] = {
        "lat": snapshot.lat_wgs84,
        "lng": snapshot.lng_wgs84,
        "tz_iana": snapshot.tz_iana,
        "utc_offset": ctx.utc_offset,
        "fold": ctx.fold,
        "civil_dt": ctx.civil_dt,
        "location_id": snapshot.location_id,
        "source": snapshot.source,
    }
    return _build_summary(full, token)


def _build_natal_planets_full(data, asc_lon, cusps, fof_lon=None, pos_lon=None):
    """构建用于前端渲染星图的行星完整数据"""
    result = []
    planets_data = data.get("planets", {})
    special_data = data.get("special_points", {})
    # 主要行星映射
    PLANET_KEYS = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"]
    # 特殊星体
    SPECIAL_KEYS = {
        "true_north_lunar_node": "north_node",  # 北交点
        "true_south_lunar_node": "south_node",  # 南交点
        "chiron": "chiron"  # 凯龙星
    }
    
    for pk in PLANET_KEYS:
        p = planets_data.get(pk)
        if not p:
            continue
        lon = p.get("longitude", 0)
        sign_idx = int(lon // 30)
        deg = int(lon % 30)
        sign = p.get("sign", "")
        planet_cn = PLANET_CN.get(pk, pk)
        sign_cn = SIGN_CN.get(sign, sign)
        retrograde = p.get("retrograde", False)
        
        # 普拉西度制宫位
        house_p = p.get("house", 1)
        
        # 整宫制宫位：用星座序号差，避免经度差跨边界导致的宫位偏移
        # 与 natal_planets_w 保持一致
        asc_si  = int(asc_lon // 30) % 12
        planet_si = int(lon // 30) % 12
        house_w = (planet_si - asc_si + 12) % 12 + 1
        
        result.append({
            "key": pk,
            "cn": planet_cn,
            "lon": round(lon, 4),
            "sign": sign_cn,
            "sign_idx": sign_idx,
            "deg": deg,
            "house_p": house_p,
            "house_w": house_w,
            "retrograde": retrograde
        })
    
    # 添加轴点
    axes = data.get("axes", {})
    asc_data = axes.get("ascendant", {})
    mc_data = axes.get("midheaven", {})
    
    asc_lon_val = asc_data.get("longitude", 0)
    asc_sign_idx = int(asc_lon_val // 30)
    asc_sign = asc_data.get("sign", "")
    asc_sign_cn = SIGN_CN.get(asc_sign, asc_sign)
    asc_deg = int(asc_lon_val % 30)
    
    result.append({
        "key": "asc",
        "cn": "上升",
        "lon": round(asc_lon_val, 4),
        "sign": asc_sign_cn,
        "sign_idx": asc_sign_idx,
        "deg": asc_deg,
        "house_p": 1,
        "house_w": 1,
        "retrograde": False
    })
    
    mc_lon = mc_data.get("longitude", 0)
    mc_sign_idx = int(mc_lon // 30)
    mc_sign = mc_data.get("sign", "")
    mc_sign_cn = SIGN_CN.get(mc_sign, mc_sign)
    mc_deg = int(mc_lon % 30)
    mc_house_w = (int(mc_lon // 30) % 12 - int(asc_lon // 30) % 12 + 12) % 12 + 1
    
    result.append({
        "key": "mc",
        "cn": "天顶",
        "lon": round(mc_lon, 4),
        "sign": mc_sign_cn,
        "sign_idx": mc_sign_idx,
        "deg": mc_deg,
        "house_p": 10,
        "house_w": mc_house_w,
        "retrograde": False
    })
    
    # 添加精神点 (Pars Spiritus)
    if pos_lon is not None:
        pos_sign_idx = int(pos_lon // 30)
        pos_sign = ["白羊座","金牛座","双子座","巨蟹座","狮子座","处女座","天秤座","天蝎座","射手座","摩羯座","水瓶座","双鱼座"][pos_sign_idx]
        pos_deg = int(pos_lon % 30)
        pos_house_w = (int(pos_lon // 30) % 12 - int(asc_lon // 30) % 12 + 12) % 12 + 1
        pos_house_p = placidus_house(pos_lon, cusps)
        result.append({
            "key": "pars_spiritus",
            "cn": "精神点",
            "lon": round(pos_lon, 4),
            "sign": pos_sign,
            "sign_idx": pos_sign_idx,
            "deg": pos_deg,
            "house_p": pos_house_p,
            "house_w": pos_house_w,
            "retrograde": False
        })
    
    # 添加福点 (Pars Fortuna)
    if fof_lon is not None:
        fof_sign_idx = int(fof_lon // 30)
        fof_sign = ["白羊座","金牛座","双子座","巨蟹座","狮子座","处女座","天秤座","天蝎座","射手座","摩羯座","水瓶座","双鱼座"][fof_sign_idx]
        fof_deg = int(fof_lon % 30)
        fof_house_w = (int(fof_lon // 30) % 12 - int(asc_lon // 30) % 12 + 12) % 12 + 1
        fof_house_p = placidus_house(fof_lon, cusps)
        result.append({
            "key": "pars_fortuna",
            "cn": "福点",
            "lon": round(fof_lon, 4),
            "sign": fof_sign,
            "sign_idx": fof_sign_idx,
            "deg": fof_deg,
            "house_p": fof_house_p,
            "house_w": fof_house_w,
            "retrograde": False
        })
    
    # 添加凯龙星和南北交点
    SPECIAL_CN = {"chiron": "凯龙星", "north_node": "北交点", "south_node": "南交点"}
    for sk, dk in SPECIAL_KEYS.items():
        sp = special_data.get(sk)
        if not sp:
            continue
        lon = sp.get("longitude", 0)
        sign_idx = int(lon // 30)
        deg = int(lon % 30)
        sign = sp.get("sign", "")
        sign_cn = SIGN_CN.get(sign, sign)
        retrograde = sp.get("retrograde", False)
        # 整宫制宫位（星座序号差）
        house_w = (int(lon // 30) % 12 - int(asc_lon // 30) % 12 + 12) % 12 + 1
        # 普拉西度宫位（引擎已计算）
        house_p = sp.get("house", house_w)
        result.append({
            "key": dk,
            "cn": SPECIAL_CN.get(dk, dk),
            "lon": round(lon, 4),
            "sign": sign_cn,
            "sign_idx": sign_idx,
            "deg": deg,
            "house_p": house_p,
            "house_w": house_w,
            "retrograde": retrograde
        })
    
    return result

def _build_care_data(cared, mapping):
    """将 fortuna_projection 的 cared/mapping 转为前端格式"""
    import fortuna_projection as fp
    result = []
    for fc in fp.CARE_HOUSES:
        nh = mapping.get(fc, 0)
        entries = cared.get(fc, [])
        planets = [{"planet": pcn, "sign": s} for pcn, _, s, _ in entries]
        result.append({
            "fortune_house": fc,
            "natal_house": nh,
            "planets": planets,
            # 凶宫赦免检查
            "pardon": [{"planet": pcn, "house": nh, "desc": ""}
                       for pcn, nh2, _, _ in entries if nh2 in fp.MALEFIC_HOUSES],
            # 凶星检查
            "malefics": [{"planet": pcn, "house": nh}
                         for pcn, _, _, _ in entries if pcn in fp.MALEFIC_PLANETS],
        })
    return result


def _build_malefic_check(cared, mapping, natal_planets):
    """构建凶星检查数据"""
    import fortuna_projection as fp
    
    # 被照顾的本命宫集合（mapping 的值）
    protected_natal_houses = set(mapping.values())
    
    result = []
    for pcn, natal_house, sign, _ in natal_planets:
        if pcn not in MALEFICS:
            continue
        natal_house_num = int(natal_house) if isinstance(natal_house, int) else int(natal_house.replace("宫", ""))
        # 凶星是否被照顾：凶星所在的本命宫是否被照顾
        is_protected = natal_house_num in protected_natal_houses
        # 找到该凶星所在的福点盘宫位
        fortune_house = None
        for fc in fp.CARE_HOUSES:
            entries = cared.get(fc, [])
            if any(p == pcn for p, _, _, _ in entries):
                fortune_house = fc
                break
        
        result.append({
            "planet": pcn,
            "natal_house": natal_house_num,
            "sign": sign,
            "is_protected": is_protected,
            "fortune_house": fortune_house,
        })
    
    return result


def _build_lunation_data(lunations, data=None):
    """将 engine lunations 转为前端格式 {before: [...], after: [...]}
    每组：最接近的1个食相 + 最接近的1个非食相月相
    附加双宫制落入宫位"""
    SIGN_ORDER = {"白羊":0,"金牛":1,"双子":2,"巨蟹":3,"狮子":4,"处女":5,
                  "天秤":6,"天蝎":7,"射手":8,"摩羯":9,"水瓶":10,"双鱼":11}
    
    # 获取 Placidus cusps & Whole Sign ASC
    cusps = None
    asc_sign_idx = 0
    if data:
        houses = data.get("houses", {})
        cusps = houses.get("cusps")
        axes = data.get("axes", {})
        asc_sign_cn = axes.get("ascendant", {}).get("sign_zh", "白羊").replace("座", "")
        asc_sign_idx = SIGN_ORDER.get(asc_sign_cn, 0)
    
    def _lon(sign_cn, degree):
        return SIGN_ORDER.get(sign_cn, 0) * 30 + degree
    
    def _house_p(lon):
        if not cusps: return 0
        first = cusps[0]
        nc = [c + 360 if c < first else c for c in cusps]
        nc.append(nc[0] + 360)
        lo = lon % 360
        if lo < nc[0]: lo += 360
        for i in range(12):
            if nc[i] <= lo < nc[i+1]:
                return i + 1
        return 1
    
    def _house_w(sign_cn):
        si = SIGN_ORDER.get(sign_cn, 0)
        return (si - asc_sign_idx + 12) % 12 + 1
    
    def _enrich(events):
        for e in events:
            lon = _lon(e.get("sign_cn",""), e.get("degree",0))
            e["house_p"] = _house_p(lon)
            e["house_w"] = _house_w(e.get("sign_cn",""))
        return events
    
    all_events = lunations.get("all", [])
    
    def _pick_pair(events):
        eclipses = sorted([e for e in events if e.get("eclipse")], key=lambda x: abs(x["days"]))
        lunations_only = sorted([e for e in events if not e.get("eclipse")], key=lambda x: abs(x["days"]))
        result = []
        if eclipses: result.append(eclipses[0])
        if lunations_only: result.append(lunations_only[0])
        result.sort(key=lambda x: abs(x["days"]))
        return result
    
    before = [e for e in all_events if e.get("days", 0) < 0]
    after = [e for e in all_events if e.get("days", 0) > 0]
    return {
        "before": _enrich(_pick_pair(before)),
        "after": _enrich(_pick_pair(after)),
    }






def _build_summary(full, token):
    """构建 MCP 共用计算数据 — 双宫制，不含报告文案。"""
    r_pla = full["r_pla"]
    r_ws = full["r_ws"]
    data = full["data"]

    sect = r_pla.sect
    light_body = r_pla.luminaries  # "太阳" or "月亮"

    # ── 行星详情（按派系分组）──
    def _planet_dict(p, is_active_sect):
        is_light = p.planet_cn in ("太阳", "月亮")
        tags = []
        if is_light:
            # 太阳月亮只标注光体
            tags.append("光体")
        else:
            in_sect = (sect == "日生人") == (p.planet_cn in DAY_PLANETS.values())
            tag = "同党" if in_sect else "异党"
            tag += "吉星" if not p.is_malefic else "凶星"
            tags.append(tag)
            if p.hemisphere_isolated:
                tags.append("半球孤军")
            else:
                tags.append("半球喜乐")
            if p.in_joy:
                tags.append("喜乐")
            if p.dignity and p.dignity != "—":
                tags.append(p.dignity)
            else:
                tags.append("浮游")
        in_sect = (sect == "日生人") == (p.planet_cn in DAY_PLANETS.values())
        return {
            "planet_cn": p.planet_cn,
            "sign_cn": SIGN_CN.get(p.sign, p.sign),
            "house": p.house,
            "dignity": p.dignity,
            "tags": tags,
            "in_sect": in_sect,
            "is_malefic": p.is_malefic,
            "isolated": p.hemisphere_isolated,
            "in_joy": p.in_joy,
        }

    def _planet_scores(r):
        active = r.day_planets if sect == "日生人" else r.night_planets
        inactive = r.night_planets if sect == "日生人" else r.day_planets
        return {
            "active": [_planet_dict(p, True) for p in active],
            "inactive": [_planet_dict(p, False) for p in inactive],
            "active_label": ("日间派主星 · 得时" if sect == "日生人" else "夜间派主星 · 得时"),
            "inactive_label": ("夜间派主星 · 失时" if sect == "日生人" else "日间派主星 · 失时"),
        }

    # ── 三分主星阶段 ──
    def _tri_stages(r):
        STAGE_PREFIX = ["第一主星 ", "第二主星 ", "共管主星 "]
        result = []

        for i, t in enumerate(r.triplicity_lords):
            is_light = t.planet_cn in ("太阳", "月亮")
            tags = []
            if is_light:
                tags.append("光体")
            else:
                in_sect = (sect == "日生人") == (t.planet_cn in DAY_PLANETS.values())
                tag = "同党" if in_sect else "异党"
                tag += "吉星" if not (t.planet_cn in NATURAL_MALEFICS) else "凶星"
                tags.append(tag)
            if t.in_joy:
                tags.append("喜乐")
            if t.dignity and t.dignity != "—":
                tags.append(t.dignity)
            else:
                tags.append("浮游")
            entry = {
                "stage": STAGE_PREFIX[i] + t.stage,
                "stage_label": STAGES[i],
                "planet_cn": t.planet_cn,
                "sign_cn": SIGN_CN.get(t.sign, t.sign),
                "house": t.house,
                "dignity": t.dignity,
                "house_type": t.house_type,
                "tags": tags,
            }
            result.append(entry)
        return result

    # ── ASC 三分主星 ──
    def _asc_tri_stages(r):
        STAGE_PREFIX = ["第一主星 ", "第二主星 ", "共管主星 "]
        asc_sign = data["axes"]["ascendant"]["sign"]  # "Ari"
        elem = SIGN_ELEMENT[asc_sign]
        order = ["day", "night", "participating"] if sect == "日生人" else ["night", "day", "participating"]
        lord_names = [TRIPLICITY[elem][o] for o in order]
        cusps = data["houses"]["cusps"]
        asc_lon = cusps[0]

        if r.system == "whole_sign":
            hfn = lambda lon: whole_sign_house(lon, asc_lon)
        else:
            hfn = lambda lon: placidus_house(lon, cusps)

        stages = []
        for i, lord in enumerate(lord_names):
            pk = REVERSE_PK[lord]
            pi = data["planets"][pk]
            nh = hfn(pi["longitude"])
            is_light = lord in ("太阳", "月亮")
            tags = []
            if is_light:
                tags.append("光体")
            else:
                in_sect = (sect == "日生人") == (lord in DAY_PLANETS.values())
                tag = "同党" if in_sect else "异党"
                tag += "吉星" if lord not in NATURAL_MALEFICS else "凶星"
                tags.append(tag)
            # Check joy: need planet key for JOY lookup
            joy_nh = hfn(pi["longitude"])
            if joy_nh == PLANET_JOY.get(lord):
                tags.append("喜乐")
            dg = _dignity(lord, pi["sign"])
            if dg and dg != "—":
                tags.append(dg)
            else:
                tags.append("浮游")
            stages.append({
                "stage": STAGE_PREFIX[i] + STAGES[i],
                "planet_cn": lord,
                "sign_cn": SIGN_CN.get(pi["sign"], pi["sign"]),
                "house": nh,
                "dignity": dg,
                "house_type": HOUSE_TYPE.get(nh, ''),
                "tags": tags,
            })
        return stages

    # ── 派系标签（固定映射，与三阶段、宫制无关）──
    def _sect_labels():
        """七颗古典行星的派系标签：日间派（太阳/木星/土星）与夜间派（月亮/金星/火星）
        按生时派系标 得时/失时；水星中性，永远标"中性"。
        日生/夜生直接用引擎已算好的 sect 字段，不重算。"""
        day_birth = sect == "日生人"
        labels = {}
        for cn in DAY_PLANETS.values():      # 太阳、木星、土星
            labels[cn] = "得时" if day_birth else "失时"
        for cn in NIGHT_PLANETS.values():    # 月亮、金星、火星
            labels[cn] = "失时" if day_birth else "得时"
        labels["水星"] = "中性"
        return labels

    # ── 进阶补充：另一颗光体的三分主星 ──
    def _complement_luminary_tri_stages(r):
        """返回非主光体（夜生看太阳、日生看月亮）的三分主星。

        使用同一派系顺序读取另一颗光体所在星座的三分主星。
        """
        complement = "月亮" if light_body == "太阳" else "太阳"
        complement_key = "moon" if complement == "月亮" else "sun"
        complement_planet = data["planets"][complement_key]
        elem = SIGN_ELEMENT[complement_planet["sign"]]
        order = ["day", "night", "participating"] if sect == "日生人" else ["night", "day", "participating"]
        lord_names = [TRIPLICITY[elem][o] for o in order]
        cusps = data["houses"]["cusps"]
        asc_lon = cusps[0]
        STAGE_PREFIX = ["第一主星 ", "第二主星 ", "共管主星 "]

        if r.system == "whole_sign":
            hfn = lambda lon: whole_sign_house(lon, asc_lon)
        else:
            hfn = lambda lon: placidus_house(lon, cusps)

        stages = []
        for i, lord in enumerate(lord_names):
            pk = REVERSE_PK[lord]
            pi = data["planets"][pk]
            nh = hfn(pi["longitude"])
            is_light = lord in ("太阳", "月亮")
            tags = []
            if is_light:
                tags.append("光体")
            else:
                in_sect = (sect == "日生人") == (lord in DAY_PLANETS.values())
                tag = "同党" if in_sect else "异党"
                tag += "吉星" if lord not in NATURAL_MALEFICS else "凶星"
                tags.append(tag)
            if nh == PLANET_JOY.get(lord):
                tags.append("喜乐")
            dg = _dignity(lord, pi["sign"])
            if dg and dg != "—":
                tags.append(dg)
            else:
                tags.append("浮游")
            stages.append({
                "stage": STAGE_PREFIX[i] + STAGES[i],
                "planet_cn": lord,
                "sign_cn": SIGN_CN.get(pi["sign"], pi["sign"]),
                "house": nh,
                "dignity": dg,
                "house_type": HOUSE_TYPE.get(nh, ''),
                "tags": tags,
            })
        return {
            "luminary": complement,
            "sign_cn": SIGN_CN.get(complement_planet["sign"], complement_planet["sign"]),
            "element": elem,
            "stages": stages,
        }

    # ── 定位星位置（两宫制，支持多行星） ──
    def _get_planet_loc(ruler, data):
        """获取定位星在星盘中的位置，支持多行星
        古典单行星：火星双子座三宫
        现代多行星：木星白羊座一宫 / 海王星射手座九宫"""
        if not ruler:
            return None
        PLANET_KEY_MAP = {
            "太阳": "sun", "月亮": "moon", "水星": "mercury",
            "金星": "venus", "火星": "mars", "木星": "jupiter",
            "土星": "saturn", "天王星": "uranus", "海王星": "neptune",
            "冥王星": "pluto"
        }
        
        def get_single_loc(planet_name):
            planet_key = PLANET_KEY_MAP.get(planet_name)
            if not planet_key:
                return None
            planet_data = data.get("planets", {}).get(planet_key)
            if not planet_data:
                return None
            sign_zh = planet_data.get("sign_zh", "")
            house_p = planet_data.get("house", "")
            asc_lon = data["houses"]["cusps"][0]
            planet_lon = planet_data.get("longitude", 0)
            house_w = whole_sign_house(planet_lon, asc_lon)
            if sign_zh:
                return f"{planet_name} {sign_zh}{house_p}宫"
            return None
        
        if '/' in ruler:
            planets = [p.strip() for p in ruler.split('/')]
            locs = [get_single_loc(p) for p in planets]
            locs = [l for l in locs if l]
            return ' / '.join(locs) if locs else None
        else:
            # 单行星返回完整格式（包含行星名称）
            loc = get_single_loc(ruler)
            return loc

    # ── 整合 ──
    asc_sign = data["axes"]["ascendant"]["sign"]
    asc_lon = full["asc_lon"]
    cusps = full["cusps"]
    sect_short = "夜生人" if sect == "夜生人" else "日生人"

    _planet_dicts_pla = _planet_scores(r_pla)
    _planet_dicts_ws = _planet_scores(r_ws)
    _natal_planets = _build_natal_planets_full(data, asc_lon, cusps, full.get("fof_lon"), full.get("pos_lon"))
    _care_p = _build_care_data(full.get("cared_p", {}), full.get("mapping_p", {}))
    _care_w = _build_care_data(full.get("cared_w", {}), full.get("mapping_w", {}))
    _tri_pla = _tri_stages(r_pla)
    _tri_ws = _tri_stages(r_ws)
    _asc_pla = _asc_tri_stages(r_pla)
    _asc_ws = _asc_tri_stages(r_ws)
    _comp_pla = _complement_luminary_tri_stages(r_pla)
    _comp_ws = _complement_luminary_tri_stages(r_ws)
    from services.jones_pattern import calculate_jones_pattern
    _jones_pattern = calculate_jones_pattern(data.get("planets", {}))
    _house_ruler_chains = build_house_ruler_chains(
        data.get("planets", {}), cusps, asc_lon
    )

    return {
        "token": token,
        "name": full["name"],
        "year": full["year"], "month": full["month"], "day": full["day"],
        "hour": full["hour"], "minute": full["minute"], "city": full["city"],
        # 出生上下文（经纬度/IANA 时区/UTC 偏移/fold）：由解析链单一来源直出，
        # 供前端头部展示；无则为空 dict（旧缓存条目兼容）。
        "birth_context": full.get("birth_context", {}),
        "sect": sect,
        "light_body": light_body,
        "asc_sign_cn": SIGN_CN.get(asc_sign, asc_sign),
        "asc_elem": SIGN_ELEMENT.get(asc_sign, ""),
        "light_elem": r_pla.element,
        "asc_lon": asc_lon,
        "cusps": cusps,
        "fof_lon": full.get("fof_lon"),
        "pos_lon": full.get("pos_lon"),
        # 行星完整数据（用于前端渲染星图）
        "natal_planets_full": _build_natal_planets_full(data, asc_lon, cusps, full.get("fof_lon"), full.get("pos_lon")),
        # SVG 渲染原始数据（前端缓存，POST 回服务端换 SVG，无需服务端缓存）
        "svg_data": _extract_svg_data(full),
        "planet_scores": {
            "placidus": _planet_scores(r_pla),
            "whole_sign": _planet_scores(r_ws),
        },
        "sect_labels": {
            "placidus": _sect_labels(),
            "whole_sign": _sect_labels(),
        },
        "complement_luminary_tri_stages": {
            "placidus": _comp_pla,
            "whole_sign": _comp_ws,
        },
        "triplicity_stages": {
            "placidus": _tri_pla,
            "whole_sign": _tri_ws,
        },
        "asc_tri_stages": {
            "placidus": _asc_pla,
            "whole_sign": _asc_ws,
        },
        "asc_ruler": {
            "placidus": _asc_pla[0]["planet_cn"],
            "whole_sign": _asc_ws[0]["planet_cn"],
        },
        # 十二宫宫主星定位链，按基本/固定/变动三组十字分组：传统七曜与现代
        # 外行星并列，两条路径完全相同时自动去重。1 宫即命主星链（宫头星座
        # 在两种宫制下都等于上升星座），不再单列。
        "house_ruler_chains": _house_ruler_chains,
        # 保留旧字段兼容（其他标签页可能引用）
        "sun": f"{SIGN_CN[r_pla.sun_sign]} 第{r_pla.sun_house}宫",
        "asc": data["axes"]["ascendant"]["sign_zh"],
        "moon": f"{data['planets']['moon']['sign_zh']} 第{data['planets']['moon']['house']}宫",
        "triplicity_seq": " → ".join(r_pla.triplicity_seq),
        "fof_sign": SIGN_ZH.get(data["special_points"]["part_of_fortune"]["sign"], ""),
        "fof_house_p": full["fof_np"],
        "fof_house_w": full.get("fof_nw"),
        "fof_ruler": SIGN_RULER.get(data["special_points"]["part_of_fortune"]["sign"], ""),
        "fof_ruler_modern": SIGN_MODERN_RULER.get(data["special_points"]["part_of_fortune"]["sign"], ""),
        "pos_sign": SIGN_ZH.get(data["special_points"]["part_of_spirit"]["sign"], ""),
        "pos_house_p": placidus_house(full["pos_lon"], full["cusps"]),
        "pos_house_w": whole_sign_house(full["pos_lon"], full["asc_lon"]),
        "pos_ruler": SIGN_RULER.get(data["special_points"]["part_of_spirit"]["sign"], ""),
        "pos_ruler_modern": SIGN_MODERN_RULER.get(data["special_points"]["part_of_spirit"]["sign"], ""),
        # 福点定位星位置
        "fof_ruler_loc": _get_planet_loc(SIGN_RULER.get(data["special_points"]["part_of_fortune"]["sign"], ""), data),
        "fof_ruler_modern_loc": _get_planet_loc(SIGN_MODERN_RULER.get(data["special_points"]["part_of_fortune"]["sign"], ""), data) if SIGN_MODERN_RULER.get(data["special_points"]["part_of_fortune"]["sign"], "") != SIGN_RULER.get(data["special_points"]["part_of_fortune"]["sign"], "") else None,
        # 精神点定位星位置
        "pos_ruler_loc": _get_planet_loc(SIGN_RULER.get(data["special_points"]["part_of_spirit"]["sign"], ""), data),
        "pos_ruler_modern_loc": _get_planet_loc(SIGN_MODERN_RULER.get(data["special_points"]["part_of_spirit"]["sign"], ""), data) if SIGN_MODERN_RULER.get(data["special_points"]["part_of_spirit"]["sign"], "") != SIGN_RULER.get(data["special_points"]["part_of_spirit"]["sign"], "") else None,
        # 福点盘照顾宫位
        "fortune_care_p": _care_p,
        "fortune_care_w": _care_w,
        # 凶星检查
        "malefic_check_p": _build_malefic_check(full.get("cared_p", {}), full.get("mapping_p", {}), full.get("natal_planets_p", [])),
        "malefic_check_w": _build_malefic_check(full.get("cared_w", {}), full.get("mapping_w", {}), full.get("natal_planets_w", [])),
        # 日月食数据
        "lunation_data": _build_lunation_data(full.get("lunations", {}), full.get("data", {})),
        "axes": {
            "asc": {"sign_zh": data["axes"]["ascendant"]["sign_zh"], "lon": data["axes"]["ascendant"]["longitude"]},
            "dsc": {"sign_zh": data["axes"]["descendant"]["sign_zh"], "lon": data["axes"]["descendant"]["longitude"]},
            "mc": {"sign_zh": data["axes"]["midheaven"]["sign_zh"], "lon": data["axes"]["midheaven"]["longitude"]},
            "ic": {"sign_zh": data["axes"]["imum_coeli"]["sign_zh"], "lon": data["axes"]["imum_coeli"]["longitude"]},
        },
        "moon_phase": data.get("moon_phase"),
        "aspects": _dedup_aspects(data.get("aspects", [])),
        "phase_patterns": data.get("patterns", {}).get("phase_patterns_enhanced", {}),
        "jones_patterns": data.get("patterns", {}).get("jones_patterns", []),
        # 琼斯格局纯几何计算；不含 AI、心理或命运解读。
        "jones_pattern": _jones_pattern,
    }


# ═══════════════════════════════════════════
#  图表生成
# ═══════════════════════════════════════════

def _extract_svg_data(full):
    """从 full 数据提取 SVG 渲染所需的原始字段（纯函数，无缓存依赖）"""
    data = full["data"]
    
    # 行星数据
    planets = {}
    for pk, pv in data["planets"].items():
        planets[pk] = {"lon": pv["longitude"], "retrograde": pv.get("retrograde", False)}
    
    # 特殊点
    sp = data["special_points"]
    planets["fortune"] = {"lon": sp["part_of_fortune"]["longitude"], "retrograde": False}
    planets["spirit"] = {"lon": sp["part_of_spirit"]["longitude"], "retrograde": False}
    planets["north_node"] = {"lon": sp["true_north_lunar_node"]["longitude"], "retrograde": sp["true_north_lunar_node"]["retrograde"]}
    planets["south_node"] = {"lon": sp["true_south_lunar_node"]["longitude"], "retrograde": sp["true_south_lunar_node"]["retrograde"]}
    if "chiron" in sp:
        planets["chiron"] = {"lon": sp["chiron"]["longitude"], "retrograde": sp["chiron"].get("retrograde", False)}
    
    # 宫头
    cusps = list(data["houses"]["cusps"][:12])
    
    # 四轴
    asc_lon = data["axes"]["ascendant"]["longitude"]
    mc_lon = data["axes"]["midheaven"]["longitude"]
    
    # 相位（需要做 ID 映射：aspect数据用长名，SVG行星用短名）
    ID_MAP = {
        "true_north_lunar_node": "north_node",
        "true_south_lunar_node": "south_node",
        "part_of_fortune": "fortune",
        "part_of_spirit": "spirit",
        "chiron": "chiron",
        "ascendant": "ascendant",
        "midheaven": "midheaven",
        "descendant": "descendant",
        "imum_coeli": "imum_coeli",
    }
    aspects = []
    for a in data.get("aspects", []):
        p1 = a.get("point1", "")
        p2 = a.get("point2", "")
        if not p1 or not p2:
            continue
        aspects.append({
            "p1": ID_MAP.get(p1, p1), "p2": ID_MAP.get(p2, p2),
            "angle": a.get("angle", 0),
            "orb": a.get("orb", 0),
        })
    
    # 姓名和日期
    name = full.get("name", "")
    date_str = f"{full['year']}-{full['month']:02d}-{full['day']:02d} {full['hour']:02d}:{full['minute']:02d}"
    
    return {
        "planets": planets,
        "cusps": cusps,
        "asc_lon": asc_lon,
        "mc_lon": mc_lon,
        "aspects": aspects,
        "name": name,
        "date_str": date_str,
    }
