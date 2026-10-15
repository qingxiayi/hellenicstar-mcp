#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/geonames_lookup.py

城市地理解析服务：城市名 → (lat, lng, tz_str)

查询顺序：
  L1: 中文名桥接表 → GeoNames 英文名直查
  L2: GeoNames 别名直查
  L3: GeoNames 英文名模糊查（LIKE）
  L4: Nominatim API + timezonefinder
  L5: 返回 None

返回值统一为 (lat, lng, tz_str) 或 None
"""

import os
import sqlite3
import logging
import urllib.request
import urllib.parse
import json

from services.timezone_utils import normalize_search_timezone, normalize_timezone_for_coords

logger = logging.getLogger(__name__)

# ── 路径配置 ──────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEONAMES_DB = os.path.join(_BASE, "data", "geonames.db")

# ── 中文城市名 → GeoNames 英文名桥接表 ──────────────────────
# 覆盖 timezone_mapping 里所有中文名，以及用户常见输入
# 格式：中文名: GeoNames 里的 name 字段值（精确匹配）
CN_TO_EN = {
    # 日本
    "东京": "Tokyo", "大阪": "Osaka", "京都": "Kyoto",
    "横滨": "Yokohama", "名古屋": "Nagoya", "札幌": "Sapporo",
    "福冈": "Fukuoka", "神户": "Kobe", "广岛": "Hiroshima",
    # 韩国
    "首尔": "Seoul", "釜山": "Busan", "仁川": "Incheon",
    "大邱": "Daegu", "光州": "Gwangju",
    # 东南亚
    "新加坡": "Singapore",
    "曼谷": "Bangkok", "芭提雅": "Pattaya", "普吉": "Phuket",
    "清迈": "Chiang Mai",
    "吉隆坡": "Kuala Lumpur", "槟城": "George Town",
    "雅加达": "Jakarta", "巴厘岛": "Denpasar",
    "马尼拉": "Manila", "宿雾": "Cebu City",
    "胡志明": "Ho Chi Minh City", "河内": "Hanoi",
    "金边": "Phnom Penh", "暹粒": "Siem Reap",
    "仰光": "Yangon", "万象": "Vientiane",
    # 南亚
    "孟买": "Mumbai", "德里": "Delhi", "新德里": "New Delhi",
    "班加罗尔": "Bengaluru", "金奈": "Chennai",
    "海德拉巴": "Hyderabad", "加尔各答": "Kolkata",
    "卡拉奇": "Karachi",
    # 中东
    "迪拜": "Dubai", "阿布扎比": "Abu Dhabi",
    "多哈": "Doha", "利雅得": "Riyadh",
    "科威特": "Kuwait City", "马斯喀特": "Muscat",
    "伊斯坦布尔": "Istanbul", "安卡拉": "Ankara",
    "特拉维夫": "Tel Aviv", "耶路撒冷": "Jerusalem",
    "德黑兰": "Tehran", "巴格达": "Baghdad",
    "贝鲁特": "Beirut", "安曼": "Amman",
    # 欧洲
    "伦敦": "London", "曼彻斯特": "Manchester",
    "爱丁堡": "Edinburgh", "伯明翰": "Birmingham",
    "格拉斯哥": "Glasgow", "利物浦": "Liverpool",
    "都柏林": "Dublin",
    "巴黎": "Paris", "马赛": "Marseille",
    "里昂": "Lyon", "尼斯": "Nice", "波尔多": "Bordeaux",
    "柏林": "Berlin", "慕尼黑": "Munich",
    "法兰克福": "Frankfurt am Main", "汉堡": "Hamburg",
    "科隆": "Cologne", "斯图加特": "Stuttgart",
    "阿姆斯特丹": "Amsterdam", "鹿特丹": "Rotterdam",
    "布鲁塞尔": "Brussels",
    "维也纳": "Vienna", "萨尔茨堡": "Salzburg",
    "苏黎世": "Zurich", "日内瓦": "Geneva", "伯尔尼": "Bern",
    "罗马": "Rome", "米兰": "Milan",
    "佛罗伦萨": "Florence", "威尼斯": "Venice",
    "那不勒斯": "Naples", "都灵": "Turin",
    "马德里": "Madrid", "巴塞罗那": "Barcelona",
    "塞维利亚": "Seville", "瓦伦西亚": "Valencia",
    "里斯本": "Lisbon", "波尔图": "Porto",
    "雅典": "Athens", "塞萨洛尼基": "Thessaloniki",
    "斯德哥尔摩": "Stockholm", "哥本哈根": "Copenhagen",
    "奥斯陆": "Oslo", "赫尔辛基": "Helsinki",
    "雷克雅未克": "Reykjavik",
    "华沙": "Warsaw", "克拉科夫": "Kraków",
    "布拉格": "Prague", "布达佩斯": "Budapest",
    "布加勒斯特": "Bucharest", "索菲亚": "Sofia",
    "贝尔格莱德": "Belgrade", "萨格勒布": "Zagreb",
    "莫斯科": "Moscow", "圣彼得堡": "Saint Petersburg",
    "基辅": "Kyiv", "明斯克": "Minsk",
    # 北美
    "纽约": "New York City",
    "波士顿": "Boston", "华盛顿": "Washington",
    "费城": "Philadelphia", "迈阿密": "Miami",
    "亚特兰大": "Atlanta", "底特律": "Detroit",
    "芝加哥": "Chicago", "休斯顿": "Houston",
    "达拉斯": "Dallas", "圣安东尼奥": "San Antonio",
    "丹佛": "Denver", "凤凰城": "Phoenix",
    "洛杉矶": "Los Angeles", "旧金山": "San Francisco",
    "西雅图": "Seattle", "拉斯维加斯": "Las Vegas",
    "波特兰": "Portland", "圣迭戈": "San Diego",
    "多伦多": "Toronto", "蒙特利尔": "Montreal",
    "温哥华": "Vancouver", "卡尔加里": "Calgary",
    "渥太华": "Ottawa",
    "墨西哥城": "Mexico City", "坎昆": "Cancún",
    # 南美
    "圣保罗": "São Paulo", "里约热内卢": "Rio de Janeiro",
    "布宜诺斯艾利斯": "Buenos Aires",
    "利马": "Lima", "圣地亚哥": "Santiago",
    "波哥大": "Bogotá", "加拉加斯": "Caracas",
    "基多": "Quito", "蒙得维的亚": "Montevideo",
    # 大洋洲
    "悉尼": "Sydney", "墨尔本": "Melbourne",
    "布里斯班": "Brisbane", "珀斯": "Perth",
    "阿德莱德": "Adelaide", "堪培拉": "Canberra",
    "奥克兰": "Auckland", "惠灵顿": "Wellington",
    # 非洲
    "开罗": "Cairo", "亚历山大": "Alexandria",
    "约翰内斯堡": "Johannesburg", "开普敦": "Cape Town",
    "内罗毕": "Nairobi", "拉各斯": "Lagos",
    "卡萨布兰卡": "Casablanca", "突尼斯": "Tunis",
    "达喀尔": "Dakar", "阿克拉": "Accra",
    "亚的斯亚贝巴": "Addis Ababa",
}


def _get_conn():
    if not os.path.exists(GEONAMES_DB):
        return None
    try:
        conn = sqlite3.connect(GEONAMES_DB, timeout=5)
        conn.execute("PRAGMA query_only=1")
        return conn
    except Exception as e:
        logger.warning(f"GeoNames DB 连接失败: {e}")
        return None


def _query_by_name(conn, name: str):
    """按英文名精确查，取人口最多的"""
    return conn.execute(
        "SELECT latitude, longitude, timezone, country FROM geonames_cities "
        "WHERE name=? ORDER BY population DESC LIMIT 1", (name,)
    ).fetchone()


def _query_by_alias(conn, alias: str):
    """按别名查，取人口最多的"""
    return conn.execute(
        """SELECT c.latitude, c.longitude, c.timezone, c.country
           FROM geonames_aliases a
           JOIN geonames_cities c ON a.geonameid = c.geonameid
           WHERE a.alias = ?
           ORDER BY c.population DESC LIMIT 1""", (alias,)
    ).fetchone()


def _query_by_name_fuzzy(conn, name: str):
    """英文名前缀模糊查，处理"New York"→"New York City"这类情况"""
    return conn.execute(
        "SELECT latitude, longitude, timezone, country FROM geonames_cities "
        "WHERE name LIKE ? ORDER BY population DESC LIMIT 1",
        (name + "%",)
    ).fetchone()


def _format_row(row):
    lat, lng, tz, country = row
    return lat, lng, normalize_search_timezone(country, tz)


def _nominatim(city: str):
    """Nominatim 兜底，返回 (lat, lng, country_code) 或 None"""
    params = urllib.parse.urlencode({
        "q": city, "format": "json", "limit": 1,
        "accept-language": "zh", "countrycodes": "", "addressdetails": 1,
    })
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "hellenic-star-astro/1.0 (contact: qingxiayi@gmail.com)"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        if data:
            country_code = (data[0].get("address") or {}).get("country_code")
            country_code = country_code.upper() if country_code else None
            return float(data[0]["lat"]), float(data[0]["lon"]), country_code
    except Exception as e:
        logger.warning(f"Nominatim 查询失败: {e}")
    return None


def _tz_from_coords(lat: float, lng: float) -> str:
    """经纬度 → IANA 时区，用 timezonefinder"""
    try:
        from timezonefinder import TimezoneFinder
        tf = TimezoneFinder()
        tz = tf.timezone_at(lat=lat, lng=lng)
        return tz or "UTC"
    except Exception as e:
        logger.warning(f"timezonefinder 失败: {e}")
        return "UTC"


def lookup(city: str):
    """
    主入口：城市名 → (lat, lng, tz_str) 或 None

    source 记录走了哪条路径（供调试）
    """
    city = city.strip()
    conn = _get_conn()

    if conn:
        try:
            # L1: 中文名桥接 → 英文名精确查
            en_name = CN_TO_EN.get(city)
            if en_name:
                row = _query_by_name(conn, en_name)
                if row:
                    logger.info(f"GeoNames L1(桥接): {city}→{en_name} tz={row[2]}")
                    return _format_row(row)

            # L2: 别名精确查（上海、伦敦等有中文别名的城市）
            row = _query_by_alias(conn, city)
            if row:
                logger.info(f"GeoNames L2(别名): {city} tz={row[2]}")
                return _format_row(row)

            # L3: 英文名精确查（用户直接输入英文）
            row = _query_by_name(conn, city)
            if row:
                logger.info(f"GeoNames L3(英文精确): {city} tz={row[2]}")
                return _format_row(row)

            # L4: 英文名前缀模糊查
            row = _query_by_name_fuzzy(conn, city)
            if row:
                logger.info(f"GeoNames L4(模糊): {city} tz={row[2]}")
                return _format_row(row)

        except Exception as e:
            logger.warning(f"GeoNames 查询异常: {e}")
        finally:
            conn.close()

    # L5: Nominatim + timezonefinder
    result = _nominatim(city)
    if result:
        lat, lng, country_code = result
        tz = normalize_timezone_for_coords(lat, lng, _tz_from_coords(lat, lng), country=country_code)
        logger.info(f"Nominatim+TF: {city} ({lat},{lng}) country={country_code} tz={tz}")
        return lat, lng, tz

    logger.warning(f"所有路径均未找到城市: {city}")
    return None
