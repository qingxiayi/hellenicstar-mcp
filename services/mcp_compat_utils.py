# -*- coding: utf-8 -*-
"""routes/geo.py —— 城市搜索与地名/时区展示标签。"""
import os
import re
import sqlite3


from services import rate_limit
from services.location_resolver import DEFAULT_DB_PATH, LocationResolver


# ── calculation ─────────────────────────────────────────────────────────────

_COUNTRY_LABELS = {
    "CN": "中国",
    "HK": "中国香港",
    "MO": "中国澳门",
    "TW": "中国台湾",
    "US": "美国",
    "GB": "英国",
    "FR": "法国",
    "DE": "德国",
    "IT": "意大利",
    "ES": "西班牙",
    "JP": "日本",
    "KR": "韩国",
    "SG": "新加坡",
    "AU": "澳大利亚",
    "CA": "加拿大",
    "MX": "墨西哥",
    "ID": "印度尼西亚",
    "RO": "罗马尼亚",
    "IN": "印度",
    "BR": "巴西",
    "UA": "乌克兰",
    "RU": "俄罗斯",
    "CI": "科特迪瓦",
    "PH": "菲律宾",
    "TR": "土耳其",
    "PL": "波兰",
    "AT": "奥地利",
    "CZ": "捷克",
    "IR": "伊朗",
    "PE": "秘鲁",
    "BE": "比利时",
    "GR": "希腊",
    "NL": "荷兰",
    "CH": "瑞士",
    "SE": "瑞典",
    "HU": "匈牙利",
    "HR": "克罗地亚",
    "CO": "哥伦比亚",
    "PT": "葡萄牙",
    "TH": "泰国",
    "AR": "阿根廷",
    "ZA": "南非",
    "FI": "芬兰",
    "NG": "尼日利亚",
    "VN": "越南",
    "PA": "巴拿马",
    "SK": "斯洛伐克",
    "NZ": "新西兰",
    "IL": "以色列",
    "MY": "马来西亚",
    "AM": "亚美尼亚",
    "NO": "挪威",
    "SI": "斯洛文尼亚",
    "MM": "缅甸",
    "PK": "巴基斯坦",
    "IE": "爱尔兰",
    "AO": "安哥拉",
    "HN": "洪都拉斯",
    "EC": "厄瓜多尔",
    "DK": "丹麦",
    "RS": "塞尔维亚",
    "MA": "摩洛哥",
    "PS": "巴勒斯坦",
    "AL": "阿尔巴尼亚",
    "VE": "委内瑞拉",
    "DZ": "阿尔及利亚",
    "KZ": "哈萨克斯坦",
    "GT": "危地马拉",
    "KH": "柬埔寨",
    "KE": "肯尼亚",
    "BG": "保加利亚",
    "MN": "蒙古",
    "TZ": "坦桑尼亚",
    "AF": "阿富汗",
    "YE": "也门",
    "CL": "智利",
    "BY": "白俄罗斯",
    "BA": "波黑",
    "SY": "叙利亚",
    "MK": "北马其顿",
    "TN": "突尼斯",
    "EG": "埃及",
    "ET": "埃塞俄比亚",
}


def _country_label(country_code):
    code = (country_code or "").upper()
    if not code:
        return ""
    # ISO 3166 覆盖远大于首期高频中文表。未翻译项保留代码用于精确辨认，
    # 但不要把裸代码伪装成可读国家名。
    return _COUNTRY_LABELS.get(code, f"其他国家/地区（{code}）")


# GeoNames 中国 admin1 代码 → 中文省名（来源 admin1CodesASCII.txt CN.*，已核）。
# 国内同名城（北京 / 安徽北京路 / 新疆新市）靠省份区分，光时区不够（大陆基本都 Asia/Shanghai）。
_CN_ADMIN1 = {
    "01": "安徽", "02": "浙江", "03": "江西", "04": "江苏", "05": "吉林",
    "06": "青海", "07": "福建", "08": "黑龙江", "09": "河南", "10": "河北",
    "11": "湖南", "12": "湖北", "13": "新疆", "14": "西藏", "15": "甘肃",
    "16": "广西", "18": "贵州", "19": "辽宁", "20": "内蒙古", "21": "宁夏",
    "22": "北京", "23": "上海", "24": "山西", "25": "山东", "26": "陕西",
    "28": "天津", "29": "云南", "30": "广东", "31": "海南", "32": "四川",
    "33": "重庆",
}

# Province names in comma-separated birthplaces, aligned with GeoNames CN admin1.
_CN_ADMIN1_EN = {
    "01": "Anhui", "02": "Zhejiang", "03": "Jiangxi", "04": "Jiangsu",
    "05": "Jilin", "06": "Qinghai", "07": "Fujian", "08": "Heilongjiang",
    "09": "Henan", "10": "Hebei", "11": "Hunan", "12": "Hubei",
    "13": "Xinjiang", "14": "Tibet", "15": "Gansu", "16": "Guangxi",
    "18": "Guizhou", "19": "Liaoning", "20": "Inner Mongolia",
    "21": "Ningxia", "22": "Beijing", "23": "Shanghai", "24": "Shanxi",
    "25": "Shandong", "26": "Shaanxi", "28": "Tianjin", "29": "Yunnan",
    "30": "Guangdong", "31": "Hainan", "32": "Sichuan", "33": "Chongqing",
}


# 美国州代码（USPS 两字母）→ 中文州名，51 条（50 州 + DC）。
# 联邦制国家同名城市极多（如 Lexington 分布在 KY/NC/MA/MO），只靠国家名分不清，需州名消歧。
_US_ADMIN1 = {
    "AL": "阿拉巴马州", "AK": "阿拉斯加州", "AZ": "亚利桑那州", "AR": "阿肯色州",
    "CA": "加利福尼亚州", "CO": "科罗拉多州", "CT": "康涅狄格州", "DE": "特拉华州",
    "DC": "哥伦比亚特区", "FL": "佛罗里达州", "GA": "佐治亚州", "HI": "夏威夷州",
    "ID": "爱达荷州", "IL": "伊利诺伊州", "IN": "印第安纳州", "IA": "艾奥瓦州",
    "KS": "堪萨斯州", "KY": "肯塔基州", "LA": "路易斯安那州", "ME": "缅因州",
    "MD": "马里兰州", "MA": "马萨诸塞州", "MI": "密歇根州", "MN": "明尼苏达州",
    "MS": "密西西比州", "MO": "密苏里州", "MT": "蒙大拿州", "NE": "内布拉斯加州",
    "NV": "内华达州", "NH": "新罕布什尔州", "NJ": "新泽西州", "NM": "新墨西哥州",
    "NY": "纽约州", "NC": "北卡罗来纳州", "ND": "北达科他州", "OH": "俄亥俄州",
    "OK": "俄克拉何马州", "OR": "俄勒冈州", "PA": "宾夕法尼亚州", "RI": "罗得岛州",
    "SC": "南卡罗来纳州", "SD": "南达科他州", "TN": "田纳西州", "TX": "得克萨斯州",
    "UT": "犹他州", "VT": "佛蒙特州", "VA": "弗吉尼亚州", "WA": "华盛顿州",
    "WV": "西弗吉尼亚州", "WI": "威斯康星州", "WY": "怀俄明州",
}

_US_ADMIN1_EN = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}


def _split_us_state_query(query):
    """识别“城市 + 州”查询，返回 (城市部分, USPS 州代码)。

    GeoNames 的城市名称与 admin1 分列存储，直接搜 ``Princeton New Jersey``
    不会命中。这里统一支持英文州全名、USPS 代码和中文州名；只输入州名时
    返回该州人口靠前的城市。保留 New Jersy 这一常见拼写错误。
    """
    raw = (query or "").strip()
    if not raw:
        return raw, None
    aliases = {}
    for code, english in _US_ADMIN1_EN.items():
        aliases[english.lower()] = code
        aliases[_US_ADMIN1[code].lower()] = code
        aliases[_US_ADMIN1[code].removesuffix("州").lower()] = code
    aliases.update({"washington dc": "DC", "new jersy": "NJ", "新泽西": "NJ"})

    normalized = re.sub(r"\s+", " ", re.sub(r"[,，]+", " ", raw)).strip()
    lower = normalized.lower()
    for alias in sorted(aliases, key=len, reverse=True):
        code = aliases[alias]
        if lower == alias:
            return "", code
        if lower.endswith(" " + alias):
            return normalized[:-(len(alias) + 1)].strip(), code
        if lower.startswith(alias + " "):
            return normalized[len(alias) + 1:].strip(), code
        if raw.startswith(alias) and any("\u4e00" <= ch <= "\u9fff" for ch in alias):
            return raw[len(alias):].strip(), code
        if raw.endswith(alias) and any("\u4e00" <= ch <= "\u9fff" for ch in alias):
            return raw[:-len(alias)].strip(), code

    # 两字母州代码只在独立 token 中识别，避免把普通城市名的一部分误判成州。
    match = re.match(r"^(.*?)(?:\s+|,)([A-Za-z]{2})$", raw)
    if match and match.group(2).upper() in _US_ADMIN1:
        return match.group(1).rstrip(" ,，"), match.group(2).upper()
    return raw, None


# 常见英文国名 → ISO2，跟 _COUNTRY_LABELS 同一批国家代码，保持两边同步。
# 用于识别"City, Country"格式（历史人物出生地批量导入常见写法，如
# "Kesswil, Switzerland"）——之前只有 _split_us_state_query 认州名，
# 国名后缀完全没处理，离线库按整段字符串精确/前缀匹配，永远查不到。
_COUNTRY_NAME_TO_CODE = {
    "china": "CN", "中国": "CN", "hong kong": "HK", "macau": "MO", "macao": "MO", "taiwan": "TW",
    "usa": "US", "us": "US", "united states": "US", "united states of america": "US",
    "uk": "GB", "united kingdom": "GB", "great britain": "GB", "england": "GB",
    "france": "FR", "germany": "DE", "italy": "IT", "spain": "ES",
    "japan": "JP", "korea": "KR", "south korea": "KR", "singapore": "SG",
    "australia": "AU", "canada": "CA", "mexico": "MX", "indonesia": "ID",
    "romania": "RO", "india": "IN", "brazil": "BR", "ukraine": "UA",
    "russia": "RU", "ivory coast": "CI", "philippines": "PH", "turkey": "TR",
    "poland": "PL", "austria": "AT", "czech republic": "CZ", "czechia": "CZ",
    "iran": "IR", "peru": "PE", "belgium": "BE", "greece": "GR",
    "netherlands": "NL", "holland": "NL", "switzerland": "CH", "sweden": "SE",
    "hungary": "HU", "croatia": "HR", "colombia": "CO", "portugal": "PT",
    "thailand": "TH", "argentina": "AR", "south africa": "ZA", "finland": "FI",
    "nigeria": "NG", "vietnam": "VN", "panama": "PA", "slovakia": "SK",
    "new zealand": "NZ", "israel": "IL", "malaysia": "MY", "armenia": "AM",
    "norway": "NO", "slovenia": "SI", "myanmar": "MM", "burma": "MM",
    "pakistan": "PK", "ireland": "IE", "angola": "AO", "honduras": "HN",
    "ecuador": "EC", "denmark": "DK", "serbia": "RS", "morocco": "MA",
    "palestine": "PS", "albania": "AL", "venezuela": "VE", "algeria": "DZ",
    "kazakhstan": "KZ", "guatemala": "GT", "cambodia": "KH", "kenya": "KE",
    "bulgaria": "BG", "mongolia": "MN", "tanzania": "TZ", "afghanistan": "AF",
    "yemen": "YE", "chile": "CL", "belarus": "BY", "bosnia": "BA",
    "bosnia and herzegovina": "BA", "syria": "SY", "north macedonia": "MK",
    "macedonia": "MK", "tunisia": "TN", "egypt": "EG", "ethiopia": "ET",
}
_COUNTRY_NAME_TO_CODE.update({label.lower(): code for code, label in _COUNTRY_LABELS.items()})


def _split_country_query(query):
    """识别"City, Country"格式，返回 (城市部分, ISO2代码)。

    只在原文本带逗号时才尝试——避免把"New Chile"这种双词城市名误判成国名后缀。
    US 州名优先由 _split_us_state_query 处理，这里只处理它没命中的情况
    （调用方保证：仅当 us_state 为空时才调用本函数）。
    """
    raw = (query or "").strip()
    if not raw or ("," not in raw and "，" not in raw):
        return raw, None
    normalized = re.sub(r"\s+", " ", re.sub(r"[,，]+", " ", raw)).strip()
    lower = normalized.lower()
    parts = re.split(r"[,，]", raw)
    for name in sorted(_COUNTRY_NAME_TO_CODE, key=len, reverse=True):
        code = _COUNTRY_NAME_TO_CODE[name]
        if len(parts) > 1 and parts[-1].strip().lower() == name:
            return ",".join(parts[:-1]).strip(), code
        if lower == name:
            return "", code
        if lower.endswith(" " + name):
            return normalized[:-(len(name) + 1)].strip(), code
        if lower.startswith(name + " "):
            return normalized[len(name) + 1:].strip(), code
    return raw, None


def _normalize_city_search_term(query):
    """Normalize common Saint abbreviations and separators for GeoNames lookup.

    GeoNames stores many French place names in the canonical ``Saint-X`` form,
    while historical records commonly use ``St.X``, ``St. X`` or ``St X``.
    Normalize the spelling rule itself rather than special-casing any one city.
    """
    raw = re.sub(r"\s+", " ", (query or "").strip())
    match = re.match(r"^(?:st\.?|saint)[\s.-]+(.+)$", raw, flags=re.IGNORECASE)
    if not match:
        return raw
    remainder = match.group(1).strip(" .-")
    return f"Saint-{remainder}" if remainder else raw


def _split_region_query(query, country_code):
    """Parse City, Region, Country; return a verified admin1 code when known."""
    if not country_code:
        return query, None, None
    parts = re.split(r"[,，]", query)
    if len(parts) != 2:
        return query, None, None
    city, region = (part.strip() for part in parts)
    if not city or not region:
        return query, None, None
    if country_code == "CN":
        for code, name in _CN_ADMIN1.items():
            aliases = {name, name + "省", _CN_ADMIN1_EN[code].lower()}
            if region.lower() in aliases:
                return city, code, None
    elif country_code == "US":
        aliases = {name.lower(): code for code, name in _US_ADMIN1_EN.items()}
        aliases.update({name.lower(): code for code, name in _US_ADMIN1.items()})
        aliases.update({code.lower(): code for code in _US_ADMIN1})
        code = aliases.get(region.lower())
        if code:
            return city, code, None
    # Other countries' admin1 names are absent from location.db. Return city +
    # country candidates, but explicitly mark that the region was not verified.
    return city, None, region


# 常见 IANA 时区 → 用户能读懂的中文区域名。搜索请求没有出生日期，不能把
# 标准时偏移冒充出生当日实际偏移；实际偏移仍由 CivilTimeResolver 按
# IANA + 出生日期计算。
_TZ_DISPLAY = {
    "Asia/Shanghai": "北京时间",
    "Europe/Paris": "中欧时间",
    "America/Mexico_City": "北美中部时间",
    "Europe/Berlin": "中欧时间",
    "Europe/Rome": "中欧时间",
    "America/New_York": "北美东部时间",
    "Europe/Madrid": "中欧时间",
    "America/Chicago": "北美中部时间",
    "Europe/Bucharest": "东欧时间",
    "Asia/Kolkata": "印度时间",
    "Asia/Jakarta": "西印尼时间",
    "Europe/London": "格林尼治时间",
    "Africa/Abidjan": "格林尼治时间",
    "Europe/Kyiv": "东欧时间",
    "Asia/Manila": "菲律宾时间",
    "Europe/Istanbul": "土耳其时间",
    "Europe/Warsaw": "中欧时间",
    "America/Sao_Paulo": "巴西利亚时间",
    "Europe/Vienna": "中欧时间",
    "Europe/Moscow": "莫斯科时间",
    "Europe/Prague": "中欧时间",
    "Asia/Makassar": "中印尼时间",
    "Asia/Tehran": "伊朗时间",
    "America/Lima": "秘鲁时间",
    "Europe/Brussels": "中欧时间",
    "Asia/Tokyo": "日本时间",
    "America/Los_Angeles": "北美太平洋时间",
    "Europe/Athens": "东欧时间",
    "Europe/Amsterdam": "中欧时间",
    "Europe/Zurich": "中欧时间",
    "Australia/Sydney": "澳东时间",
    "Asia/Bangkok": "印支时间",
    "Europe/Stockholm": "中欧时间",
    "Europe/Budapest": "中欧时间",
    "Europe/Zagreb": "中欧时间",
    "America/Bogota": "哥伦比亚时间",
    "America/Toronto": "北美东部时间",
    "America/Denver": "北美山地时间",
    "America/Fortaleza": "巴西利亚时间",
    "Australia/Brisbane": "澳东时间",
    "Africa/Johannesburg": "南非时间",
    "Europe/Lisbon": "西欧时间",
    "Europe/Helsinki": "东欧时间",
    "Africa/Lagos": "西非时间",
    "Australia/Melbourne": "澳东时间",
    "America/Panama": "北美东部时间",
    "Asia/Jerusalem": "以色列时间",
    "Europe/Bratislava": "中欧时间",
    "America/Monterrey": "北美中部时间",
    "America/Mazatlan": "北美山地时间",
    "Pacific/Auckland": "新西兰时间",
    "Asia/Yekaterinburg": "叶卡捷琳堡时间",
    "Asia/Yerevan": "亚美尼亚时间",
    "Europe/Oslo": "中欧时间",
    "America/Edmonton": "北美山地时间",
    "Europe/Ljubljana": "中欧时间",
    "Asia/Kuala_Lumpur": "马来西亚时间",
    "Asia/Yangon": "缅甸时间",
    "Asia/Karachi": "巴基斯坦时间",
    "Europe/Belgrade": "中欧时间",
}


def _tz_display(tz_iana):
    """返回准确的区域名，不展示搜索阶段无法确定的固定 UTC 偏移。"""
    return _TZ_DISPLAY.get(tz_iana, tz_iana or "")


def _region_label(country_code, admin1):
    """下拉副行的地区名：中国给省份，美国给州名，其余国家给国家名。"""
    cc = (country_code or "").upper()
    if cc == "CN" and admin1 is not None:
        key = str(admin1).strip().zfill(2)
        prov = _CN_ADMIN1.get(key)
        if prov:
            return "中国 · " + prov
    if cc == "US" and admin1:
        state = _US_ADMIN1.get(str(admin1).strip().upper())
        if state:
            return "美国 · " + state
    return _country_label(cc)


def _administrative_region_label(*parts):
    """按上游行政层级生成展示文字；仅清洗和去重，不推断任何地名关系。"""
    labels = []
    for part in parts:
        label = part.strip() if isinstance(part, str) else ""
        if label and (not labels or labels[-1] != label):
            labels.append(label)
    return " · ".join(labels)


def _city_label(row):
    return row["name_zh"] or row["name_main"] or row["name_any"] or row["location_id"]


_DOMESTIC_CC = frozenset({"CN", "TW", "HK", "MO"})


def _is_query_chinese(s):
    return any("一" <= ch <= "鿿" for ch in (s or ""))


def _search_city_options(query, limit=10):
    q = (query or "").strip()
    if not q:
        return []
    city_query, us_state = _split_us_state_query(q)
    country_code = None
    region_code = None
    unverified_region = None
    if not us_state:
        city_query, country_code = _split_country_query(city_query)
        city_query, region_code, unverified_region = _split_region_query(city_query, country_code)
    city_query = _normalize_city_search_term(city_query)

    resolver = LocationResolver()

    def _amap_fallback():
        """离线全 miss 时才打高德一次，省配额；结果带 amap: 合成 id，前端可提交。"""
        try:
            s = resolver.resolve(query=q)   # online=True → 触发高德兜底
        except Exception:
            s = None
        if not s:
            return []
        region = _administrative_region_label(
            s.province, s.prefecture, s.district
        ) or _country_label(s.country_code)
        return [{
            "location_id": s.location_id,
            "city": q,
            "country": _country_label(s.country_code),
            "country_code": s.country_code,
            "region": region,
            "admin1": s.admin1,
            "lat": s.lat_wgs84,
            "lng": s.lng_wgs84,
            "timezone": s.tz_iana,
            "tz_display": _tz_display(s.tz_iana),
        }]

    try:
        # 带州/国条件时必须由 SQL 同时约束 city + admin1/country，否则精确
        # 城市名会又按全球人口选到别的州/国（"London, Canada"精确匹配不加国家
        # 约束会选中人口更多的英国伦敦）。
        exact = None if (us_state or country_code) else resolver.resolve(query=city_query, online=False)
    except Exception:
        exact = None

    if not os.path.exists(DEFAULT_DB_PATH):
        return _amap_fallback()

    q_lower = city_query.lower()
    try:
        conn = sqlite3.connect(DEFAULT_DB_PATH, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=1")
        except sqlite3.Error:
            pass
        try:
            state_clause = " AND p.country_code = 'US' AND p.admin1 = ?" if us_state else ""
            country_clause = " AND p.country_code = ?" if country_code else ""
            region_clause = " AND p.admin1 = ?" if region_code else ""
            sql = """
                SELECT
                    p.location_id,
                    p.country_code,
                    p.lat_wgs84,
                    p.lng_wgs84,
                    p.tz_iana,
                    p.admin1,
                    p.population,
                    (
                        SELECT z.name
                        FROM place_names z
                        WHERE z.location_id = p.location_id AND z.lang = 'zh'
                        ORDER BY
                            CASE WHEN z.name_lower = ? THEN 0 ELSE 1 END,
                            z.is_preferred DESC,
                            length(z.name),
                            z.name
                        LIMIT 1
                    ) AS name_zh,
                    (
                        SELECT m.name
                        FROM place_names m
                        WHERE m.location_id = p.location_id AND m.lang = 'main'
                        ORDER BY m.is_preferred DESC, length(m.name), m.name
                        LIMIT 1
                    ) AS name_main,
                    (
                        SELECT a.name
                        FROM place_names a
                        WHERE a.location_id = p.location_id
                        ORDER BY a.is_preferred DESC, length(a.name), a.name
                        LIMIT 1
                    ) AS name_any,
                    MAX(CASE WHEN n.name_lower = ? THEN 1 ELSE 0 END) AS exact_match,
                    MAX(CASE WHEN n.name_lower LIKE ? THEN 1 ELSE 0 END) AS prefix_match
                FROM place_names n
                JOIN places p ON p.location_id = n.location_id
                WHERE n.name_lower >= ? AND n.name_lower < ?
                """ + state_clause + country_clause + region_clause + """
                GROUP BY p.location_id
                ORDER BY exact_match DESC, prefix_match DESC, p.population DESC
                LIMIT ?
                """
            # name_lower 已在构建期统一小写。用半开区间表达前缀，
            # 让 SQLite 真正走 idx_names_lower；`exact OR LIKE prefix%`
            # 在 650 万名称库上会退化成全表扫描。
            params = [q_lower, q_lower, q_lower + "%", q_lower, q_lower + "\uffff"]
            if us_state:
                params.append(us_state)
            elif country_code:
                params.append(country_code)
            if region_code:
                params.append(region_code)
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        rows = []

    options = []
    seen = set()
    if exact:
        seen.add(exact.location_id)
        options.append({
            "location_id": exact.location_id,
            "city": "",
            "country": _country_label(exact.country_code),
            "country_code": exact.country_code,
            "region": _region_label(exact.country_code, getattr(exact, "admin1", None)),
            "admin1": getattr(exact, "admin1", None),
            "lat": exact.lat_wgs84,
            "lng": exact.lng_wgs84,
            "timezone": exact.tz_iana,
            "tz_display": _tz_display(exact.tz_iana),
        })

    for row in rows:
        loc_id = row["location_id"]
        item = {
            "location_id": loc_id,
            "city": _city_label(row),
            "country": _country_label(row["country_code"]),
            "country_code": row["country_code"],
            "region": _region_label(row["country_code"], row["admin1"]),
            "admin1": row["admin1"],
            "lat": row["lat_wgs84"],
            "lng": row["lng_wgs84"],
            "timezone": row["tz_iana"],
            "tz_display": _tz_display(row["tz_iana"]),
        }
        if loc_id in seen:
            options[0]["city"] = item["city"]
            continue
        seen.add(loc_id)
        options.append(item)

    final = [item for item in options[:limit] if item["city"]]
    if unverified_region:
        for item in final:
            item["requested_region"] = unverified_region
            item["region_verified"] = False
    # 中文查询若离线无 CN/TW/HK/MO 域内命中，打一次高德补域内正解并前置（合并去重）。
    # 只前置"域内"结果：避免把离线里正确的外国同名城挤到高德的大陆音译之下。
    # 高德至多调用一次（amap 缓存本次结果，末尾复用，不重复打网络）。
    amap = None
    if not us_state and _is_query_chinese(q) and not any(
        (it.get("country_code") or "").upper() in _DOMESTIC_CC for it in final
    ):
        amap = _amap_fallback()
        domestic = [a for a in amap if (a.get("country_code") or "").upper() in _DOMESTIC_CC]
        if domestic:
            dom_ids = {a["location_id"] for a in domestic}
            return (domestic + [it for it in final if it["location_id"] not in dom_ids])[:limit]
    if final:
        return final
    if us_state:
        return []
    return amap if amap is not None else _amap_fallback()




# --- Common & Candidate Serialization ---
def _fold_label(ctx):
    hhmm = (ctx.civil_dt or '')[11:16]
    seq = '第一次' if ctx.fold == 0 else '第二次'
    off = ctx.utc_offset
    return f"{seq} {hhmm}（UTC{'+' if off >= 0 else '-'}{abs(off):g}）"

def _serialize_candidate(ctx):
    return {
        'fold': ctx.fold,
        'label': _fold_label(ctx),
        'utc_datetime': ctx.utc_datetime,
        'utc_offset': ctx.utc_offset,
    }

# --- SVG to PNG ---
import subprocess
import shutil
import logging

def _svg_to_png(svg, size):
    from services.zodiac_svg_outline import outline_zodiac_text
    svg = outline_zodiac_text(svg)
    log = logging.getLogger(__name__)
    rsvg = shutil.which('rsvg-convert')
    if not rsvg:
        log.error('rsvg-convert not found on PATH; install librsvg2-bin')
        return None
    try:
        proc = subprocess.run(
            [rsvg, '-w', str(size), '-h', str(size), '--format=png'],
            input=svg.encode('utf-8'),
            capture_output=True,
            timeout=30,
        )
    except (subprocess.SubprocessError, OSError) as e:
        log.error('rsvg-convert failed to run: %s', e)
        return None
    if proc.returncode != 0 or not proc.stdout:
        log.error(
            'rsvg-convert exit=%s stderr=%s',
            proc.returncode, proc.stderr.decode('utf-8', 'replace')[:500],
        )
        return None
    return proc.stdout

# --- Datetime Parsing ---
from datetime import datetime

def _parse_datetime_param(raw):
    if not raw or not isinstance(raw, str):
        raise ValueError('datetime 缺失或非法')
    text = raw.strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f'datetime 格式非法：{raw}，应为 ISO 8601（如 2026-08-18T13:22:00+08:00）')
    if dt.tzinfo is None:
        raise ValueError(
            f'datetime 必须带时区偏移：{raw}，应为 ISO 8601 带 offset'
            '（如 2026-08-18T13:22:00+08:00 或 2026-08-18T05:22:00Z）'
        )
    return dt

# --- Natal Axes ---
_AXIS_KEYMAP = {
    'ascendant': 'Asc',
    'midheaven': 'MC',
    'descendant': 'Dsc',
    'imum_coeli': 'IC',
}

def _natal_axes_from_data(data):
    axes = data.get('axes') or {}
    out = {}
    for eng_key, short in _AXIS_KEYMAP.items():
        node = axes.get(eng_key) or {}
        lon = node.get('longitude')
        if lon is None:
            raise ValueError('本命四轴缺失，无法计算土木流年')
        out[short] = float(lon)
    return out
