# -*- coding: utf-8 -*-
"""
services/location_resolver.py —— LocationResolver 第一版。

把「城市/坐标 → 唯一坐标 + IANA 时区」这层从冻结引擎里剥出来。
本版只做三条路径（plan §2.1 的 1/2/3），**不含**在线高德兜底（第 4 条）与
CivilTimeResolver/EngineAdapter（另开块做）：

  1. location_id 命中    → 直接读 location.db（零网络快路径）
  2. query 字符串        → 离线 place_names 匹配，同名取人口最多
  3. (lat, lng) only     → timezonefinder 多边形算 tz_iana（懒导入）

全 miss 返回 None；**绝不静默兜底坐标/时区**（这正是要根治的旧病）。
时区只有一个来源：id/query 走库内 tz_iana 列；坐标-only 才用 timezonefinder 现算。
"""

import os
import math
import re
import sqlite3
from dataclasses import dataclass, replace
from typing import Optional

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.environ.get("MCP_LOCATION_DB_PATH", os.path.join(_BASE, "data", "location.db"))
_timezone_finder = None

# 中国大陆统一北京时间：IANA 把新疆划入 Asia/Urumqi(+6)，但中国全境官方民用时间
# 一律是北京时间(+8)——身份证/户口登记的出生时间皆按此。故把大陆的 Urumqi/Kashgar
# 归一到 Asia/Shanghai，与旧网页版行为一致（避免新疆用户整盘偏 2 小时）。
# 港(Asia/Hong_Kong)/澳(Asia/Macau)/台(Asia/Taipei)各有独立时区与历史夏令时，不在此列。
_CN_TZ_CANONICAL = {
    "Asia/Urumqi": "Asia/Shanghai",
    "Asia/Kashgar": "Asia/Shanghai",
}

_COORD_ID_PREFIX = "coord:"
_COORD_ID_RE = re.compile(r"^coord:(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$")


def coordinate_location_id(lat: float, lng: float) -> str:
    """Stable WGS84 location ID for the existing coordinate-only resolver path."""
    if isinstance(lat, bool) or isinstance(lng, bool):
        raise ValueError("经纬度必须是有限数字")
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        raise ValueError("经纬度必须是有限数字") from None
    if not math.isfinite(lat) or not math.isfinite(lng) or not -90 <= lat <= 90 or not -180 <= lng <= 180:
        raise ValueError("纬度需在 -90–90、经度需在 -180–180")
    return f"{_COORD_ID_PREFIX}{lat:.6f},{lng:.6f}"


def _canonical_cn_tz(tz_iana: Optional[str]) -> Optional[str]:
    """把中国大陆的非北京时区归一到 Asia/Shanghai（全国统一北京时间）。"""
    return _CN_TZ_CANONICAL.get(tz_iana, tz_iana)


def _amap_country_code(province: Optional[str], adcode: Optional[str]) -> str:
    """按高德行政字段判定国家/地区代码。adcode 前两位为省级码（权威）：
    71=台湾 / 81=香港 / 82=澳门；省名作兜底。其余大陆返回 CN。
    只查省级字段，避免"台州(浙江)""澳门路(某市)"误判。"""
    prov = province or ""
    code = (adcode or "").strip()
    if code.startswith("71") or "台湾" in prov or "臺灣" in prov:
        return "TW"
    if code.startswith("81") or "香港" in prov:
        return "HK"
    if code.startswith("82") or "澳门" in prov or "澳門" in prov:
        return "MO"
    return "CN"


# ── 高德在线兜底（第4条）的可写缓存：写 data/geocache.db，不碰只读的 location.db ──────
# location.db 是版本化、只读、随盘部署的离线主库；高德结果运行时落到 data/geocache.db
# 的 amap_cache 表（每地只查一次），并合成稳定 location_id 让下拉/案例重算能回查。
_AMAP_ID_PREFIX = "amap:"
_AMAP_TABLE = "amap_cache"
_AMAP_REGION_COLUMNS = {
    "province": "TEXT",
    "prefecture": "TEXT",
    "district": "TEXT",
    "adcode": "TEXT",
}


def _amap_db_path() -> str:
    from services.geocoding import DB_PATH  # 独立地理缓存
    return DB_PATH


def _amap_conn():
    import sqlite3 as _sq
    conn = _sq.connect(_amap_db_path(), timeout=5)
    conn.row_factory = _sq.Row
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS {_AMAP_TABLE} (
            location_id   TEXT PRIMARY KEY,
            query         TEXT,
            lat_wgs84     REAL NOT NULL,
            lng_wgs84     REAL NOT NULL,
            tz_iana       TEXT NOT NULL,
            country_code  TEXT NOT NULL DEFAULT 'CN',
            name          TEXT,
            created_at    INTEGER NOT NULL
        )"""
    )
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({_AMAP_TABLE})")}
    for column, column_type in _AMAP_REGION_COLUMNS.items():
        if column in existing:
            continue
        try:
            conn.execute(f"ALTER TABLE {_AMAP_TABLE} ADD COLUMN {column} {column_type}")
        except _sq.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    conn.commit()
    return conn


def _amap_cache_lookup(key: str) -> Optional["sqlite3.Row"]:
    """key 可为合成 location_id（amap:…）或原始 query，命中任一即返回。"""
    import sqlite3 as _sq
    try:
        conn = _amap_conn()
        try:
            return conn.execute(
                f"SELECT * FROM {_AMAP_TABLE} WHERE location_id = ? OR query = ? LIMIT 1",
                (key, key),
            ).fetchone()
        finally:
            conn.close()
    except _sq.Error:
        return None


def _amap_cache_write(location_id, query, lat, lng, tz, country_code, name,
                      province="", prefecture="", district="", adcode=""):
    import sqlite3 as _sq
    import time as _t
    try:
        conn = _amap_conn()
        try:
            conn.execute(
                f"INSERT OR REPLACE INTO {_AMAP_TABLE} "
                "(location_id, query, lat_wgs84, lng_wgs84, tz_iana, country_code, name, "
                "province, prefecture, district, adcode, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (location_id, query, lat, lng, tz, country_code, name,
                 province, prefecture, district, adcode, int(_t.time())),
            )
            conn.commit()
        finally:
            conn.close()
    except _sq.Error:
        pass


def migrate_amap_country_codes() -> int:
    """一次性迁移：把 amap_cache 里按 province/adcode 重推后不一致的 country_code
    就地更正（旧版无条件写 CN 的港澳台行）。幂等，返回更正行数。部署时跑一次。"""
    import sqlite3 as _sq
    fixed = 0
    try:
        conn = _amap_conn()
        try:
            rows = conn.execute(
                f"SELECT location_id, province, adcode, country_code FROM {_AMAP_TABLE}"
            ).fetchall()
            for row in rows:
                correct = _amap_country_code(row["province"], row["adcode"])
                if correct != (row["country_code"] or ""):
                    conn.execute(
                        f"UPDATE {_AMAP_TABLE} SET country_code = ? WHERE location_id = ?",
                        (correct, row["location_id"]),
                    )
                    fixed += 1
            conn.commit()
        finally:
            conn.close()
    except _sq.Error:
        pass
    return fixed


def _snapshot_from_amap_row(row) -> "LocationSnapshot":
    return LocationSnapshot(
        location_id=row["location_id"],
        lat_wgs84=row["lat_wgs84"],
        lng_wgs84=row["lng_wgs84"],
        tz_iana=_canonical_cn_tz(row["tz_iana"]),  # 新疆经高德也归一北京时间
        # 读时按 province/adcode 重推国家码：旧缓存里错写的 CN 也自愈成 TW/HK/MO
        country_code=_amap_country_code(row["province"], row["adcode"]),
        admin1=None,
        source="amap",
        datum="WGS84",
        version="amap-cache",
        province=row["province"] or "",
        prefecture=row["prefecture"] or "",
        district=row["district"] or "",
        adcode=row["adcode"] or "",
    )


def _amap_row_has_region(row) -> bool:
    return any((row[column] or "").strip() for column in _AMAP_REGION_COLUMNS)


def _get_timezone_finder():
    """Lazily create and reuse the heavy timezonefinder instance."""
    global _timezone_finder
    if _timezone_finder is None:
        try:
            from timezonefinder import TimezoneFinder
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "缺少 timezonefinder 依赖，无法根据裸坐标解析 IANA 时区；"
                "请安装 requirements.txt 后重试。"
            ) from exc
        _timezone_finder = TimezoneFinder()
    return _timezone_finder


@dataclass(frozen=True)
class LocationSnapshot:
    """单一坐标 + 时区真相。不可变。"""
    location_id: str
    lat_wgs84: float
    lng_wgs84: float
    tz_iana: str              # 永远 IANA 名（如 "Europe/Paris"），绝不是数字 offset
    country_code: str
    admin1: Optional[str]
    source: str               # "location_db" | "timezonefinder"
    datum: str                # "WGS84"
    version: str
    province: str = ""
    prefecture: str = ""
    district: str = ""
    adcode: str = ""


class LocationResolver:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path

    # ── 连接（只读）──────────────────────────────────────────
    def _conn(self) -> Optional[sqlite3.Connection]:
        if not os.path.exists(self.db_path):
            return None
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=1")
        except sqlite3.Error:
            pass
        return conn

    # ── 主入口 ───────────────────────────────────────────────
    def resolve(self, location_id: Optional[str] = None,
                lat: Optional[float] = None, lng: Optional[float] = None,
                query: Optional[str] = None,
                online: bool = True) -> Optional[LocationSnapshot]:
        """
        优先级：location_id > (lat,lng) > query离线 > query高德兜底(online)。
        注意 0 是合法坐标（伦敦本初子午线 lng=0），故用 is not None 判断。
        online=False 时跳过高德在线兜底（如 search-city 只想要离线快路径时）。
        """
        if location_id:
            return self._by_id(location_id)
        if lat is not None and lng is not None:
            return self._by_coords(float(lat), float(lng))
        if query and query.strip():
            q = query.strip()
            snap = self._by_query(q)
            if snap is not None:
                return snap
            # 第4条：离线 miss 的中文地名 → 高德在线兜底一次（plan §2.1）
            return self._by_amap(q) if online else None
        return None

    # ── 1. location_id 命中 ──────────────────────────────────
    def _by_id(self, location_id: str) -> Optional[LocationSnapshot]:
        if location_id.startswith(_COORD_ID_PREFIX):
            match = _COORD_ID_RE.fullmatch(location_id)
            if not match:
                return None
            try:
                key = coordinate_location_id(float(match[1]), float(match[2]))
            except ValueError:
                return None
            if key != location_id:
                return None
            snap = self._by_coords(float(match[1]), float(match[2]))
            return replace(snap, location_id=key) if snap else None
        # 高德合成 id（下拉选回 / 案例重算）→ 从 data/geocache.db 可写缓存回查
        if location_id.startswith(_AMAP_ID_PREFIX):
            row = _amap_cache_lookup(location_id)
            if not row:
                return None
            if not _amap_row_has_region(row):
                query = row["query"] or location_id[len(_AMAP_ID_PREFIX):]
                return self._by_amap(query)
            return _snapshot_from_amap_row(row)
        conn = self._conn()
        if conn is None:
            return None
        try:
            row = conn.execute(
                "SELECT * FROM places WHERE location_id = ?", (location_id,)
            ).fetchone()
        finally:
            conn.close()
        return self._snapshot_from_place(row) if row else None

    # ── 2. query 离线匹配 ────────────────────────────────────
    def _by_query(self, query: str) -> Optional[LocationSnapshot]:
        conn = self._conn()
        if conn is None:
            return None
        try:
            # place_names 大小写不敏感匹配 → 同名取「人口最多 + 优先名」
            row = conn.execute(
                """
                SELECT p.*
                FROM place_names n
                JOIN places p ON p.location_id = n.location_id
                WHERE n.name_lower = ?
                ORDER BY p.population DESC, n.is_preferred DESC
                LIMIT 1
                """,
                (query.lower(),),
            ).fetchone()
        finally:
            conn.close()
        return self._snapshot_from_place(row) if row else None

    # ── 3. (lat,lng) → timezonefinder ───────────────────────
    def _by_coords(self, lat: float, lng: float) -> Optional[LocationSnapshot]:
        tz = _get_timezone_finder().timezone_at(lat=lat, lng=lng)
        if not tz:
            return None
        tz = _canonical_cn_tz(tz)   # 大陆统一北京时间（新疆 Urumqi→Shanghai）
        version = self._meta("version") or "unknown"
        return LocationSnapshot(
            location_id="",          # 裸坐标无 canonical id
            lat_wgs84=lat,
            lng_wgs84=lng,
            tz_iana=tz,
            country_code="",
            admin1=None,
            source="timezonefinder",
            datum="WGS84",
            version=version,
        )

    # ── 4. 高德在线兜底（仅离线 miss 的中文地名）─────────────
    def _by_amap(self, query: str) -> Optional[LocationSnapshot]:
        """离线库没有的中文地名 → 高德 geocode 一次，结果落 data/geocache.db 缓存。

        坐标经 gcj2wgs 转 WGS-84（_amap_geocode 内部已转），时区用 timezonefinder
        现算后归一北京时间（_canonical_cn_tz）。合成稳定 location_id=`amap:<query>`，
        让下拉选回 / 案例重算可经 _by_id 回查。无 key / 非中文 / 太短 / miss → None，
        绝不静默兜底坐标（保持新链「全 miss 报错请重选」的不变量）。
        """
        from services.geocoding import AMAP_KEY, _amap_geocode, _is_chinese

        loc_id = _AMAP_ID_PREFIX + query
        cached = _amap_cache_lookup(loc_id)        # 每地只查一次
        if cached and _amap_row_has_region(cached):
            return _snapshot_from_amap_row(cached)

        if not AMAP_KEY or not _is_chinese(query) or len(query) < 2:
            return _snapshot_from_amap_row(cached) if cached else None

        result = _amap_geocode(query)
        if not result:
            return _snapshot_from_amap_row(cached) if cached else None
        tz = _canonical_cn_tz(result.tz_iana)
        cc = _amap_country_code(result.province, result.adcode)
        _amap_cache_write(
            loc_id, query, result.lat_wgs84, result.lng_wgs84, tz, cc, query,
            province=result.province,
            prefecture=result.city,
            district=result.district,
            adcode=result.adcode,
        )
        return LocationSnapshot(
            location_id=loc_id,
            lat_wgs84=result.lat_wgs84,
            lng_wgs84=result.lng_wgs84,
            tz_iana=tz,
            country_code=cc,
            admin1=None,
            source="amap",
            datum="WGS84",
            version="amap-cache",
            province=result.province,
            prefecture=result.city,
            district=result.district,
            adcode=result.adcode,
        )

    # ── 辅助 ─────────────────────────────────────────────────
    def _snapshot_from_place(self, row: sqlite3.Row) -> LocationSnapshot:
        return LocationSnapshot(
            location_id=row["location_id"],
            lat_wgs84=row["lat_wgs84"],
            lng_wgs84=row["lng_wgs84"],
            tz_iana=_canonical_cn_tz(row["tz_iana"]),  # 大陆统一北京时间（新疆 Urumqi→Shanghai）
            country_code=row["country_code"],
            admin1=row["admin1"] or None,
            source="location_db",
            datum=row["datum"],
            version=row["version"],
        )

    def _meta(self, key: str) -> Optional[str]:
        conn = self._conn()
        if conn is None:
            return None
        try:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        except sqlite3.Error:
            return None
        finally:
            conn.close()
        return row["value"] if row else None
