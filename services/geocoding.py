# -*- coding: utf-8 -*-
"""
services/geocoding.py
Nominatim (OpenStreetMap) geocoding 兜底服务

流程：
  1. 先查 SQLite 缓存表 city_geocache
  2. 未命中 → 调 Nominatim geocoding API
  3. 查到后写缓存 + 注入 NatalChartCalculator.CITY_COORDINATES
  4. 查不到 → 返回 None，上层报友好错误
"""

import sqlite3, time, os, logging, urllib.request, urllib.parse, json, re
from dataclasses import dataclass
from typing import Optional
from services.timezone_utils import normalize_timezone_for_coords

logger = logging.getLogger(__name__)
GEO_OBSERVE_PREFIX = "[geo_observe]"

# Standalone writable geocoding cache; never shares an authentication database.
DB_PATH = os.getenv("MCP_GEO_CACHE_PATH", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "geocache.db"
))

# 高德 Web 服务 Key（申请地址：https://lbs.amap.com/）
AMAP_KEY = os.getenv("AMAP_KEY", "")

_CN_CHAR = re.compile(r'[一-鿿]')

def _is_chinese(city: str) -> bool:
    return bool(_CN_CHAR.search(city))


@dataclass(frozen=True)
class AmapGeocodeResult:
    lat_wgs84: float
    lng_wgs84: float
    tz_iana: str
    province: str = ""
    city: str = ""
    district: str = ""
    adcode: str = ""


def _amap_text(value) -> str:
    """高德缺失字段可能是空字符串、空数组或 null，只接受真实文本。"""
    return value.strip() if isinstance(value, str) else ""


def _ensure_cache_table():
    """建缓存表（幂等）"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS city_geocache (
            city       TEXT PRIMARY KEY,
            lat        REAL NOT NULL,
            lng        REAL NOT NULL,
            timezone   TEXT NOT NULL DEFAULT 'Asia/Shanghai',
            source     TEXT NOT NULL DEFAULT 'nominatim',
            created_at INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


_table_ready = False

def _init():
    global _table_ready
    if not _table_ready:
        _ensure_cache_table()
        _table_ready = True


def _log_geo_observation(event: str, city: str, success: bool = True,
                         lat=None, lng=None, tz=None, source=None, detail=None):
    """记录地理解析旁路日志，不参与计算决策。"""
    payload = {
        "event": event,
        "city": city,
        "success": success,
    }
    if lat is not None:
        payload["lat"] = lat
    if lng is not None:
        payload["lng"] = lng
    if tz is not None:
        payload["timezone"] = tz
    if source is not None:
        payload["source"] = source
    if detail is not None:
        payload["detail"] = detail
    logger.info("%s %s", GEO_OBSERVE_PREFIX, json.dumps(payload, ensure_ascii=False, sort_keys=True))


def lookup_cache_entry(city: str):
    """从 SQLite 缓存查坐标和来源，返回 (lat, lng, tz, source) 或 None"""
    _init()
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        row = conn.execute(
            "SELECT lat, lng, timezone, source FROM city_geocache WHERE city=?", (city,)
        ).fetchone()
        conn.close()
        if not row:
            return None
        lat, lng, tz, source = row
        return lat, lng, normalize_timezone_for_coords(lat, lng, tz), source
    except Exception as e:
        logger.warning(f"geocache 读取失败: {e}")
        return None


def lookup_cache(city: str):
    """从 SQLite 缓存查坐标，返回 (lat, lng, tz) 或 None"""
    entry = lookup_cache_entry(city)
    return entry[:3] if entry else None


def write_cache(city: str, lat: float, lng: float, tz: str = "Asia/Shanghai", source: str = "nominatim",
                 country: Optional[str] = None):
    """写入 SQLite 缓存，返回归一化后实际写入的 tz——调用方要用这个值覆盖自己的
    局部变量，否则本次请求返回的 tz 是归一前的原始值，只有下次缓存命中才会更正
    （新疆/西藏这类 Asia/Urumqi→Asia/Shanghai 归一就吃这个亏）。"""
    _init()
    tz = normalize_timezone_for_coords(lat, lng, tz, country=country)
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute(
            "INSERT OR REPLACE INTO city_geocache (city, lat, lng, timezone, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (city, lat, lng, tz, source, int(time.time()))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"geocache 写入失败: {e}")
    return tz


_timezone_finder = None


def _get_timezone_finder():
    """Lazily create and reuse the heavy timezonefinder instance.

    location_resolver.py 有自己的同款单例，但这里不能直接 import 它——
    location_resolver.py 反过来要 import 本文件的 AMAP_KEY/_amap_geocode/
    _is_chinese，互相 import 会成环。两份小函数各自维护比拆共享模块简单。
    """
    global _timezone_finder
    if _timezone_finder is None:
        from timezonefinder import TimezoneFinder
        _timezone_finder = TimezoneFinder()
    return _timezone_finder


def _amap_geocode(city: str):
    """
    调高德 Geocoding API，返回 AmapGeocodeResult 或 None。
    仅用于中文城市名；高德返回 GCJ-02，转换为 WGS-84 后返回。
    """
    if not AMAP_KEY:
        return None
    params = urllib.parse.urlencode({
        "address": city,
        "key": AMAP_KEY,
        "output": "JSON",
    })
    url = f"https://restapi.amap.com/v3/geocode/geo?{params}"
    try:
        import ssl
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "hellenic-star/1.0"})
        with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
            data = json.loads(resp.read().decode())
        geocodes = data.get("geocodes") or []
        if not geocodes or geocodes[0].get("location") in ("", None):
            return None
        geocode = geocodes[0]
        loc = geocode["location"]          # "lng,lat"
        gcj_lng, gcj_lat = map(float, loc.split(","))
        from services.gcj2wgs import gcj2wgs
        wgs_lat, wgs_lng = gcj2wgs(gcj_lat, gcj_lng)
        province = _amap_text(geocode.get("province"))
        adcode = _amap_text(geocode.get("adcode"))
        try:
            tz = _get_timezone_finder().timezone_at(lat=wgs_lat, lng=wgs_lng)
        except Exception:
            tz = None
        if not tz:
            # timezonefinder 未装/异常/坐标落在多边形外：退回按高德 adcode（省级行政区码，
            # 71/81/82=台/港/澳，权威字段）判断，不再无条件默认 Asia/Shanghai——旧逻辑连
            # 香港澳门失败都会被判成上海，外国地址被高德命中时也会被误判成大陆时区。
            # adcode 都拿不到时明确返回 None，交给调用方报错，不猜。
            if adcode.startswith("71") or "台湾" in province or "臺灣" in province:
                tz = "Asia/Taipei"
            elif adcode.startswith("81") or "香港" in province:
                tz = "Asia/Hong_Kong"
            elif adcode.startswith("82") or "澳门" in province or "澳門" in province:
                tz = "Asia/Macau"
            elif adcode:
                tz = "Asia/Shanghai"  # 有效大陆省级行政区码，统一北京时间
            else:
                logger.warning(f"高德 geocoding 无法确定时区且无 adcode：{city}")
                return None
        return AmapGeocodeResult(
            lat_wgs84=wgs_lat,
            lng_wgs84=wgs_lng,
            tz_iana=tz,
            province=province,
            city=_amap_text(geocode.get("city")),
            district=_amap_text(geocode.get("district")),
            adcode=_amap_text(geocode.get("adcode")),
        )
    except Exception as e:
        logger.warning(f"高德 geocoding 请求失败: {e}")
        return None


def _nominatim_geocode(city: str):
    """
    调 OpenStreetMap Nominatim geocoding API，返回 (lat, lng, country_code) 或 None
    免费、无需 Key、支持境外服务器访问
    文档：https://nominatim.org/release-docs/develop/api/Search/
    """
    params = urllib.parse.urlencode({
        "q": city,
        "format": "json",
        "limit": 1,
        "accept-language": "zh",
        "countrycodes": "",   # 不限国家，支持全球地名
        "addressdetails": 1,
    })
    url = f"https://nominatim.openstreetmap.org/search?{params}"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "hellenic-star-astro/1.0 (contact: qingxiayi@gmail.com)"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())

        if not data:
            logger.info(f"Nominatim 未找到城市: {city}")
            return None

        country_code = (data[0].get("address") or {}).get("country_code")
        country_code = country_code.upper() if country_code else None
        return float(data[0]["lat"]), float(data[0]["lon"]), country_code

    except Exception as e:
        logger.warning(f"Nominatim geocoding 请求失败: {e}")
        return None


def _guess_timezone(lat: float, lng: float) -> str:
    """
    根据经纬度推断时区（粗估，覆盖常用情况）
    中国大陆全部用 Asia/Shanghai；境外按经度段估
    """
    # 日本、韩国的经纬度框落在中国大陆框内，必须先判窄框，否则永远被中国框吃掉
    # 日本
    if 24 <= lat <= 46 and 122 <= lng <= 146:
        return "Asia/Tokyo"
    # 韩国
    if 33 <= lat <= 39 and 124 <= lng <= 132:
        return "Asia/Seoul"
    # 中国大陆范围
    if 18 <= lat <= 54 and 73 <= lng <= 135:
        return "Asia/Shanghai"
    # 台湾/香港/澳门
    if 20 <= lat <= 26 and 113 <= lng <= 122:
        return "Asia/Shanghai"
    # 东南亚 UTC+7
    if -10 <= lat <= 28 and 97 <= lng <= 108:
        return "Asia/Bangkok"
    # 东南亚 UTC+8
    if -10 <= lat <= 28 and 108 <= lng <= 120:
        return "Asia/Singapore"
    # 印度
    if 6 <= lat <= 36 and 68 <= lng <= 98:
        return "Asia/Kolkata"
    # 中东
    if 12 <= lat <= 42 and 35 <= lng <= 63:
        return "Asia/Dubai"
    # 英国/爱尔兰（经度 -10 ~ 2）
    if 35 <= lat <= 72 and -10 <= lng <= 2:
        return "Europe/London"
    # 欧洲西部大陆（法国/西班牙/荷兰等，经度 2 ~ 15）
    if 35 <= lat <= 72 and 2 < lng <= 15:
        return "Europe/Paris"
    # 欧洲中部（德国/波兰/东欧等，经度 15 ~ 35）
    if 35 <= lat <= 72 and 15 < lng <= 35:
        return "Europe/Berlin"
    # 美国东部
    if 25 <= lat <= 50 and -85 <= lng <= -65:
        return "America/New_York"
    # 美国西部
    if 25 <= lat <= 50 and -125 <= lng <= -105:
        return "America/Los_Angeles"
    # 澳大利亚东部
    if -40 <= lat <= -10 and 140 <= lng <= 155:
        return "Australia/Sydney"
    return "UTC"


def resolve_city(city: str):
    """
    对外接口：查城市坐标。
    返回 (lat, lng, tz_str) 或 None。
    同时注入 NatalChartCalculator.CITY_COORDINATES 供本次请求使用。

    查询顺序：
      1. geocache（已查过的直接命中）
      2. GeoNames 离线库（精确坐标 + IANA 时区）
      3. Nominatim API + timezonefinder（兜底）
    """
    city = city.strip()

    # 1. 查缓存
    cached = lookup_cache_entry(city)
    if cached:
        lat, lng, tz, source = cached
        _inject(city, lat, lng)
        logger.info(f"geocache 命中: {city} → ({lat}, {lng})")
        _log_geo_observation(
            "resolve_city",
            city,
            lat=lat,
            lng=lng,
            tz=tz,
            source=f"cache:{source or 'unknown'}",
        )
        return lat, lng, tz

    # 2. GeoNames 离线库
    try:
        from services.geonames_lookup import lookup as geonames_lookup
        result = geonames_lookup(city)
        if result:
            lat, lng, tz = result
            tz = write_cache(city, lat, lng, tz, source="geonames")
            _inject(city, lat, lng)
            logger.info(f"GeoNames 命中: {city} → ({lat}, {lng}), tz={tz}")
            _log_geo_observation("resolve_city", city, lat=lat, lng=lng, tz=tz, source="geonames")
            return lat, lng, tz
    except Exception as e:
        logger.warning(f"GeoNames 查询失败: {e}")

    # 3. 高德 API（仅中文城市名，GCJ-02 → WGS-84）
    if _is_chinese(city):
        result = _amap_geocode(city)
        if result:
            lat, lng, tz = result.lat_wgs84, result.lng_wgs84, result.tz_iana
            tz = write_cache(city, lat, lng, tz, source="amap")
            _inject(city, lat, lng)
            logger.info(f"高德 geocoding: {city} → ({lat}, {lng}), tz={tz}")
            _log_geo_observation("resolve_city", city, lat=lat, lng=lng, tz=tz, source="amap")
            return lat, lng, tz

    # 4. Nominatim + timezonefinder 兜底
    result = _nominatim_geocode(city)
    if result is None:
        _log_geo_observation("resolve_city", city, success=False, source="nominatim", detail="not_found")
        return None

    lat, lng, country_code = result
    try:
        from timezonefinder import TimezoneFinder
        tz = TimezoneFinder().timezone_at(lat=lat, lng=lng) or "UTC"
    except Exception:
        tz = _guess_timezone(lat, lng)

    tz = write_cache(city, lat, lng, tz, source="nominatim", country=country_code)
    _inject(city, lat, lng)
    logger.info(f"Nominatim geocoding: {city} → ({lat}, {lng}), tz={tz}")
    _log_geo_observation("resolve_city", city, lat=lat, lng=lng, tz=tz, source="nominatim")
    return lat, lng, tz


def _inject(city: str, lat: float, lng: float):
    """
    注入到所有已加载的 NatalChartCalculator.CITY_COORDINATES（幂等）。
    用 sys.modules 遍历，防止 engine/natal_chart.py 因 sys.path 差异被双重加载
    导致注入的类和引擎用的类不是同一个对象。
    """
    import sys
    injected = False
    for mod_name, mod in list(sys.modules.items()):
        if mod is None:
            continue
        cls = getattr(mod, 'NatalChartCalculator', None)
        if cls is not None and hasattr(cls, 'CITY_COORDINATES'):
            if city not in cls.CITY_COORDINATES:
                cls.CITY_COORDINATES[city] = (lat, lng)
            injected = True
    # 兜底：确保至少注入过一次（模块尚未加载时）
    if not injected:
        try:
            from engine.natal_chart import NatalChartCalculator
            if city not in NatalChartCalculator.CITY_COORDINATES:
                NatalChartCalculator.CITY_COORDINATES[city] = (lat, lng)
        except Exception:
            pass
