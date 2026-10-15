# -*- coding: utf-8 -*-
"""
services/civil_time_resolver.py —— CivilTimeResolver（时间独立成层）。

把「当地民用时间 + IANA 时区 → 唯一出生瞬间(UTC/JD)」这层从冻结引擎里剥出来，
全显式、零静默。根治 plan §1 的两类老病：
  - 手维 China DST 表错套港台（1987 误算 +9，正确 +8）
  - `_parse_timezone_offset` 的 `except: return 0.0`（无效时区静默变 UTC 盘）

分类靠 zoneinfo 的 PEP 495 fold 语义，**只比同一挂钟时间 fold=0/fold=1 的偏移**：
  off0 == off1  → NORMAL       唯一真实时刻
  off0  > off1  → AMBIGUOUS    秋拨重叠：挂钟时间出现两次，返回两个候选让用户选
  off0  < off1  → NONEXISTENT  春拨空白：挂钟时间不存在，报 422 让用户修正
  ZoneInfo 抛错 → INVALID_TZ   直接 error，绝不 return 0.0 兜底

为什么这条规则对负夏令时（Europe/Dublin）和一次性基准位移（Asia/Kathmandu
1986 +5:30→+5:45）都成立：它只看「挂钟是向前跳(gap)还是向后倒(overlap)」，
与「是不是 DST / DST 是正是负」无关，是个不变量。故不为任何区做特例。

JD 用纯 Python 算（与 swisseph SE_GREG_CAL 的 swe.julday 数值全等，已在 smoke 对拍），
让本层保持无 swisseph 运行依赖——和 services/zodiacal_releasing.py 一样可在 3.8 直接跑，
也避免再引入「swe / 纯算」两套并行真相源（正是本次重构要消灭的模式）。
"""

import importlib.metadata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Tuple

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # Python 3.8 服务器（与 services/zodiacal_releasing.py、
    # engine/natal_chart.py 同款兼容写法；这里之前是唯一的裸 import，真 3.8
    # 上会在 compute() 内部间接崩成 ModuleNotFoundError）
    from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # type: ignore

from services.location_resolver import LocationSnapshot

RESOLVER_VERSION = "civil-time-resolver-1"


def _tzdata_version() -> str:
    """记录 pip tzdata 包版本作可复现标记。

    注意：macOS/Linux 上 zoneinfo 先读系统 TZPATH 再回退 pip tzdata 包，
    故此处记录的版本未必等于运行时真正用到的 IANA 数据版本——它是个
    *标记*，不等于关上 plan §6.2「跨机复现」那道门（那道门 P2 不负责证明）。
    """
    try:
        return importlib.metadata.version("tzdata")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _julian_day_ut(dt_utc: datetime) -> float:
    """UTC 民用时间 → Julian Day (UT)。

    Fliegel–Van Flandern 标准格里历公式，JD 以正午为 0.0 起点，
    与 swisseph `swe.julday(y,m,d,h, SE_GREG_CAL)` 数值全等（smoke 对拍验证）。
    """
    y, m, d = dt_utc.year, dt_utc.month, dt_utc.day
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    jdn = d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045
    frac = ((dt_utc.hour - 12) / 24.0
            + dt_utc.minute / 1440.0
            + dt_utc.second / 86400.0
            + dt_utc.microsecond / 86_400_000_000.0)
    return jdn + frac


class ResolutionStatus(str, Enum):
    NORMAL = "normal"            # 唯一真实时刻
    AMBIGUOUS = "ambiguous"      # 秋拨：两个真实 UTC，需用户选
    NONEXISTENT = "nonexistent"  # 春拨空白：零个真实时刻，422
    INVALID_TZ = "invalid_tz"    # 时区名无效，直接 error，禁止 UTC 兜底
    INVALID_FOLD = "invalid_fold"  # fold 参数非法，只接受 0/1


@dataclass(frozen=True)
class ResolvedBirthContext:
    """全盘唯一出生瞬间真相。不可变，可持久化。"""
    snapshot: LocationSnapshot
    civil_dt: str               # 原始当地时间（ISO，保留供展示/重算）
    utc_datetime: str           # 唯一 UTC（ISO）
    utc_offset: float           # 小时
    julian_day_ut: float        # swisseph 直接吃
    fold: int                   # 0/1（ambiguous 时用户所选）
    resolution_status: str      # ResolutionStatus 值
    tzdata_version: str
    resolver_version: str


@dataclass(frozen=True)
class CivilTimeResolution:
    """resolve() 的返回包：把「plan 说输出一个 context，但歧义要返两个」收敛在一处。

      NORMAL                → context 单值
      AMBIGUOUS 且已选 fold  → context 单值（status=ambiguous）
      AMBIGUOUS 未选 fold    → candidates 两项（fold=0 在前/UTC 较早，fold=1 在后）
      NONEXISTENT/INVALID_TZ → context=None, candidates=()，message 说明原因
    """
    status: ResolutionStatus
    context: Optional[ResolvedBirthContext] = None
    candidates: Tuple[ResolvedBirthContext, ...] = field(default_factory=tuple)
    message: str = ""


class CivilTimeResolver:
    def resolve(self, snapshot: LocationSnapshot,
                year: int, month: int, day: int, hour: int, minute: int,
                fold: Optional[int] = None) -> CivilTimeResolution:
        """当地民用时间 + snapshot.tz_iana → 唯一/歧义/空白/无效 四类，全显式。"""
        if fold is not None:
            try:
                parsed_fold = int(fold)
            except (TypeError, ValueError):
                return CivilTimeResolution(
                    ResolutionStatus.INVALID_FOLD,
                    message=f"非法 fold 参数 '{fold}'：只接受 0 或 1",
                )
            if parsed_fold not in (0, 1) or isinstance(fold, bool):
                return CivilTimeResolution(
                    ResolutionStatus.INVALID_FOLD,
                    message=f"非法 fold 参数 '{fold}'：只接受 0 或 1",
                )
            fold = parsed_fold

        tz_name = snapshot.tz_iana if snapshot else ""
        if not tz_name:
            return CivilTimeResolution(
                ResolutionStatus.INVALID_TZ,
                message="时区缺失：snapshot.tz_iana 为空，禁止 UTC 兜底",
            )
        try:
            zone = ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):
            return CivilTimeResolution(
                ResolutionStatus.INVALID_TZ,
                message=f"无效时区名 '{tz_name}'：直接报错，不出 UTC 盘",
            )

        dt0 = datetime(year, month, day, hour, minute, fold=0, tzinfo=zone)
        dt1 = datetime(year, month, day, hour, minute, fold=1, tzinfo=zone)
        off0 = dt0.utcoffset()
        off1 = dt1.utcoffset()
        if off0 is None or off1 is None:  # ZoneInfo 有效区恒返 timedelta；防御兼类型收窄
            return CivilTimeResolution(
                ResolutionStatus.INVALID_TZ,
                message=f"时区 '{tz_name}' 未返回偏移，禁止 UTC 兜底",
            )

        # NORMAL：两 fold 偏移相同 → 此挂钟时间唯一存在
        if off0 == off1:
            ctx = self._build_context(snapshot, year, month, day, hour, minute,
                                      zone, 0, ResolutionStatus.NORMAL)
            return CivilTimeResolution(ResolutionStatus.NORMAL, context=ctx)

        # NONEXISTENT：偏移变大（挂钟向前跳）→ 春拨空白，零个真实时刻
        if off0 < off1:
            return CivilTimeResolution(
                ResolutionStatus.NONEXISTENT,
                message=(f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d} "
                         f"在 {tz_name} 是春拨空白时刻（不存在），请修正出生时间"),
            )

        # AMBIGUOUS：偏移变小（挂钟向后倒）→ 秋拨重叠，两个真实 UTC
        if fold is not None:
            ctx = self._build_context(snapshot, year, month, day, hour, minute,
                                      zone, fold, ResolutionStatus.AMBIGUOUS)
            return CivilTimeResolution(ResolutionStatus.AMBIGUOUS, context=ctx)

        c0 = self._build_context(snapshot, year, month, day, hour, minute,
                                 zone, 0, ResolutionStatus.AMBIGUOUS)
        c1 = self._build_context(snapshot, year, month, day, hour, minute,
                                 zone, 1, ResolutionStatus.AMBIGUOUS)
        return CivilTimeResolution(
            ResolutionStatus.AMBIGUOUS,
            candidates=(c0, c1),
            message=(f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d} "
                     f"在 {tz_name} 是秋拨歧义时刻（出现两次），请选择 fold"),
        )

    def _build_context(self, snapshot: LocationSnapshot,
                       year: int, month: int, day: int, hour: int, minute: int,
                       zone: ZoneInfo, fold: int,
                       status: ResolutionStatus) -> ResolvedBirthContext:
        local = datetime(year, month, day, hour, minute, fold=fold, tzinfo=zone)
        utc = local.astimezone(timezone.utc)
        off = local.utcoffset()
        if off is None:  # 不可达：resolve() 已挡无效/无偏移区，此处仅防御兼类型收窄
            raise ValueError(f"时区 '{zone.key}' 未返回 utcoffset")
        return ResolvedBirthContext(
            snapshot=snapshot,
            civil_dt=local.replace(tzinfo=None).isoformat(),
            utc_datetime=utc.replace(tzinfo=None).isoformat() + "Z",
            utc_offset=off.total_seconds() / 3600.0,
            julian_day_ut=_julian_day_ut(utc),
            fold=fold,
            resolution_status=status.value,
            tzdata_version=_tzdata_version(),
            resolver_version=RESOLVER_VERSION,
        )
