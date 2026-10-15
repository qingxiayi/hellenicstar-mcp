"""
黄道释放 (Zodiacal Releasing) 计算服务

纯 Python 实现 Valens 黄道释放算法，无外部星历依赖，兼容 Python 3.8
（服务器运行时）。L1 周期边界逐节点对齐 astrologica 库的
compute_zodiacal_releasing；LB / 完成期 / 巅峰按 Brennan 口径，偏离 astrologica，
由 Astro-Seek 固定日期回归守护。对拍验证见 tests/test_zodiacal_releasing.py
（astrologica 仅作开发期校验基准，需 Python ≥ 3.11，非运行依赖）。

设计要点：
- 福点/精神点经度来自项目自己的 compute()（services/calculator.py），
  保证黄道释放的起始星座与本命盘 / 福点投影标签页完全一致。
- 释放本质是日期算术 + Valens 小年数查表：从 lot 所在星座起，按黄道顺序逐宫
  释放，递归细分至四级；子序列**第一次**回到父级起始星座时跳对宫（Loosing of
  the Bond），同一父周期只跳一次，再次回到时正常进入并标完成期（Completion）。
  算释放树本身不需要 Swiss Ephemeris。
- 输出完整四级周期树（L1→L2→L3→L4），按寿命窗口截断，避免天量节点。
"""
from __future__ import annotations

import enum
from collections import namedtuple
from datetime import datetime, timedelta
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python 3.8 服务器
    from backports.zoneinfo import ZoneInfo  # type: ignore

from services.calculator import compute

SIGN_KEYS = [
    "ARIES", "TAURUS", "GEMINI", "CANCER", "LEO", "VIRGO",
    "LIBRA", "SCORPIO", "SAGITTARIUS", "CAPRICORN", "AQUARIUS", "PISCES",
]

SIGN_CN_MAP = {
    "ARIES": "白羊座", "TAURUS": "金牛座", "GEMINI": "双子座", "CANCER": "巨蟹座",
    "LEO": "狮子座", "VIRGO": "处女座", "LIBRA": "天秤座", "SCORPIO": "天蝎座",
    "SAGITTARIUS": "射手座", "CAPRICORN": "摩羯座", "AQUARIUS": "水瓶座", "PISCES": "双鱼座",
}

LOT_LABELS = {"fortune": "福点", "spirit": "精神点"}

# 周期树按出生后这么多岁截断。四级释放在整段大周期内会产生数万节点，
# 一个人的可解读寿命窗口足够，前端再做懒加载渲染。
#
# 这里是**公历年龄**，不是释放年（360 日年）。旧实现写成
# `LIFESPAN_YEARS * year_length_days`，在 360 日年口径下 80 × 360 = 28800 天
# 只相当于 78.85 个公历年，会把晚年的转折节点截掉（Al Gore 样本的水瓶
# Completion 落在 2027-02-05，恰好被旧窗口切掉）。改为明确按公历年龄截断。
LIFESPAN_AGE_YEARS = 100
_CIVIL_YEAR_DAYS = 365.2425

# 关键转折汇总只列到这个年龄为止。周期树本身仍算到 LIFESPAN_AGE_YEARS（树视图
# 要能翻到晚年），但汇总是给人读自己一生用的，排到九十几岁没有实际意义。
TURNING_POINT_MAX_AGE = 84


# ── Valens 黄道释放引擎（纯 Python，3.8 兼容；L1 对齐 astrologica，LB 按 Brennan）──

class _Sign(enum.IntEnum):
    ARIES = 0
    TAURUS = 1
    GEMINI = 2
    CANCER = 3
    LEO = 4
    VIRGO = 5
    LIBRA = 6
    SCORPIO = 7
    SAGITTARIUS = 8
    CAPRICORN = 9
    AQUARIUS = 10
    PISCES = 11


# 一个释放周期。sign 是 _Sign（.name 取 'ARIES' 等，供 _period_to_dict 使用）。
_ReleasingPeriod = namedtuple(
    "_ReleasingPeriod",
    ["level", "sign", "start", "end", "is_lb", "is_completion", "peak"],
)

# Valens 各星座小年数（黄道顺序，白羊起）。索引9(摩羯)的 30 是土星基准值，
# 实际每次由 capricorn_years 覆盖，默认 27（Brennan / Valens 黄道释放标准）。
_PERIOD_YEARS_DEFAULT = (15, 8, 20, 25, 19, 20, 8, 15, 12, 30, 30, 12)


def calculate_zodiacal_releasing(
    user_data: dict,
    max_level: int = 4,
    year_length_days: float = 360.0,
    capricorn_years: int = 27,
    now: Optional[datetime] = None,
) -> dict:
    """
    计算黄道释放周期表（福点 + 精神点）。

    参数：
      user_data: 含 name/year/month/day/hour/minute/city，可选 lat/lng/tz
      max_level: 显示层级 (1-4)，默认 4
      year_length_days: 年长度 360 (Valens) 或 365.2425 (回归年)
      capricorn_years: 摩羯周期 27（默认，Brennan/Valens 标准）或 30
      now: 当前时间，用于标记当前周期；默认按出生地时区取现在

    返回结构见 CLAUDE.md「黄道释放」节，外加每个周期的 level / age_start /
    age_end / is_current。
    """
    name, birth_dt, fof_lon, pos_lon, sect = _resolve_calculation_context(user_data)

    # 1. 截断窗口
    end = birth_dt + timedelta(days=LIFESPAN_AGE_YEARS * _CIVIL_YEAR_DAYS)
    if now is None:
        now = datetime.now(tz=birth_dt.tzinfo)

    # 2. 逐 lot 计算 + 构树（纯 Python 释放引擎，无需 astrologica）
    fortune_sign = _Sign(int(fof_lon % 360 // 30))  # 巅峰期统一以福点星座为参照
    spirit_shifted = _spirit_needs_shift(fof_lon, pos_lon)
    lots_result = {}
    boundaries = []
    lot_lons = {"fortune": fof_lon, "spirit": pos_lon}
    for lot_key in ("fortune", "spirit"):
        shift = spirit_shifted and lot_key == "spirit"
        periods = _compute_releasing(
            lot_lons[lot_key],
            birth_dt,
            max_level=max_level,
            year_length_days=year_length_days,
            capricorn_years=capricorn_years,
            end=end,
            fortune_sign=fortune_sign,
            shift_start=shift,
        )
        lots_result[lot_key] = {
            "lot_label": LOT_LABELS[lot_key],
            "lot_sign": _sign_cn(lot_lons[lot_key]),
            # 实际起释星座：精神点顺移时与本命星座不同，必须分开报，
            # 否则界面说「精神点起始于天蝎」而表格从射手起，对不上。
            "releasing_sign": _sign_cn(
                lot_lons[lot_key] + 30 if shift else lot_lons[lot_key]
            ),
            "shifted": shift,
            # 顶部汇总用：一生的 L2 解缚清单（含前奏期/完成期），与树中标记同源。
            "turning_points": _turning_points(periods, birth_dt),
            "periods": _build_tree(list(periods), birth_dt, now),
        }
        edge = _next_boundary(periods, now)
        if edge is not None:
            boundaries.append(edge)

    return {
        "success": True,
        "name": name,
        "sect": sect,
        "max_level": max_level,
        "year_length_days": year_length_days,
        "capricorn_years": capricorn_years,
        "spirit_shifted": spirit_shifted,
        # 当前周期标记在这一刻之后就失效了；缓存层据此过期（见 routes/timing.py）。
        "next_boundary": min(boundaries).isoformat() if boundaries else None,
        "lots": lots_result,
    }


def calculate_zodiacal_releasing_l4(
    user_data: dict,
    lot: str,
    parent_start: str,
    parent_sign: str,
    year_length_days: float = 360.0,
    capricorn_years: int = 27,
    now: Optional[datetime] = None,
) -> dict:
    """只计算一个已验证 L3 周期下的 L4 子周期。

    先以同一出生资料重建轻量的 L1-L3 时间线，再用 start + sign 找到真实 L3，
    最后只细分这一段。这样客户端无法伪造父周期边界，也不必传输完整 L4 树。
    """
    if lot not in LOT_LABELS:
        raise ValueError("lot must be fortune or spirit")
    if parent_sign not in SIGN_KEYS:
        raise ValueError("parent_sign is invalid")
    try:
        datetime.strptime(parent_start, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise ValueError("parent_start must be YYYY-MM-DD")

    _name, birth_dt, fof_lon, pos_lon, _sect = _resolve_calculation_context(user_data)
    if now is None:
        now = datetime.now(tz=birth_dt.tzinfo)
    end = birth_dt + timedelta(days=LIFESPAN_AGE_YEARS * _CIVIL_YEAR_DAYS)
    fortune_sign = _Sign(int(fof_lon % 360 // 30))
    lot_lon = fof_lon if lot == "fortune" else pos_lon
    # L4 必须与全树同口径顺移，否则按需加载的子周期会与上面的 L3 错开一宫。
    shift = lot == "spirit" and _spirit_needs_shift(fof_lon, pos_lon)
    periods = _compute_releasing(
        lot_lon, birth_dt, max_level=3,
        year_length_days=year_length_days,
        capricorn_years=capricorn_years,
        end=end, fortune_sign=fortune_sign, shift_start=shift,
    )
    matches = [
        p for p in periods
        if p.level == 3
        and p.start.strftime("%Y-%m-%d") == parent_start
        and p.sign.name == parent_sign
    ]
    if len(matches) != 1:
        raise ValueError("L3 周期不存在或与当前出生资料不匹配")

    parent = matches[0]
    period_table = list(_PERIOD_YEARS_DEFAULT)
    period_table[_Sign.CAPRICORN.value] = capricorn_years
    children = []
    _release(
        4, parent.sign, fortune_sign, parent.start, parent.end,
        4, year_length_days, tuple(period_table), children,
    )
    children.sort(key=lambda p: (p.start, p.level))
    edge = _next_boundary(children, now)
    return {
        "success": True,
        "lot": lot,
        "parent_start": parent_start,
        "parent_sign": parent_sign,
        "next_boundary": edge.isoformat() if edge is not None else None,
        "periods": [_period_to_dict(p, birth_dt, now) for p in children],
    }


def _resolve_calculation_context(user_data: dict):
    """解析出生瞬间和两个 lot；全树与按需 L4 共用同一条权威链。"""
    name = user_data.get("name", "")
    year = int(user_data["year"]); month = int(user_data["month"]); day = int(user_data["day"])
    hour = int(user_data["hour"]); minute = int(user_data["minute"])
    city = (user_data.get("city") or "").strip()
    location_id = user_data.get("location_id") or None
    lat_in = user_data.get("lat")
    lng_in = user_data.get("lng")
    tz_in = user_data.get("tz")
    fold_in = user_data.get("fold")

    # 福点/精神点经度与派系：优先使用调用方传入的预计算值（来自已缓存的
    # /calculate 结果），避免重复跑本命盘；缺失时才调 compute()。
    pre_fof = user_data.get("fof_lon")
    pre_pos = user_data.get("pos_lon")
    pre_sect = user_data.get("sect")
    if pre_fof is not None and pre_pos is not None and pre_sect:
        fof_lon = float(pre_fof)
        pos_lon = float(pre_pos)
        sect = str(pre_sect)
    else:
        natal = compute(name, year, month, day, hour, minute, city,
                        lat=lat_in, lng=lng_in, tz=tz_in,
                        location_id=location_id,
                        fold=fold_in)
        fof_lon = float(natal["fof_lon"])
        pos_lon = float(natal["pos_lon"])
        sect = natal.get("sect", "")

    # 出生瞬间（带时区）—— 走跟 compute() 同一条权威解析链（LocationResolver →
    # CivilTimeResolver），保证 t0 的时区/fold 与本命盘对齐同一个出生瞬间
    birth_dt = _resolve_birth_dt(year, month, day, hour, minute, city,
                                  location_id, lat_in, lng_in, tz_in, fold_in)

    return name, birth_dt, fof_lon, pos_lon, sect


def _sign_cn(longitude: float) -> str:
    key = SIGN_KEYS[int(longitude % 360 // 30)]
    return SIGN_CN_MAP[key]


def _spirit_needs_shift(fof_lon, pos_lon) -> bool:
    """精神点与福点同落一座时，释放精神点要先沿黄道顺移一宫（Valens 专门规则）。

    Valens 在《Anthology》第 4 卷把这条当作附带说明提出，说它重要却没解释理由。
    Chris Brennan 的原话（The Astrology Podcast ep.192 逐字稿，已 grep 核对）：

      "if the Lot of Spirit and Lot of Fortune fall in the same sign, then for the
       purpose of zodiacal releasing, you want to move the Lot of Spirit forward
       one sign in zodiacal order, and then start the Spirit periods from that
       sign, and you leave the Lot of Fortune in the natal sign that it's in and
       start the fortune periods from there."

    只移精神点，福点留在本命星座不动。Brennan 补充说从厄洛斯点释放时即使与福点
    同座也不顺移，这条只适用于精神点。

    为什么会同座：日生盘 福点 = ASC + 月 - 日、精神点 = ASC + 日 - 月（夜生互换），
    所以出生在朔（日月合）附近时两点都贴近 ASC，在望（日月冲）附近时都落到对面。
    不顺移的话两条释放序列会逐节点完全一致——事业与身体的时间轴 100% 重合，
    这显然不符合实际，顺移正是为了解开这个死锁。

    Brennan 与 Leisa Schaim 都说这规则初听「非常武断」(arbitrary)，但实测有效，
    他用 Harrison Ford、Linda Goodman、John Kerry 等盘验过。
    """
    return int(fof_lon % 360 // 30) == int(pos_lon % 360 // 30)


def _compute_releasing(lot_lon, t0, max_level, year_length_days, capricorn_years, end,
                       fortune_sign, shift_start=False):
    """从 lot 经度与出生瞬间 t0 生成扁平释放周期列表。

    shift_start=True 时起始星座沿黄道顺移一宫——这是 Valens 针对「精神点与福点
    同落一座」的专门规则，见 calculate_zodiacal_releasing 里的判定。

    L1 周期边界逐节点对齐 astrologica；LB / 完成期（is_completion）与巅峰（peak）
    按 Brennan 口径，均偏离 astrologica：
      - LB 同一父周期只发生一次，之后回到父级起始星座标完成期（见 _release）。
        astrologica 每次都重跳，会让 L2 及以下的星座整体偏移，故 L2+ 不与它对拍，
        改用 Astro-Seek 固定日期（见 tests 里的 Al Gore 回归用例）。
      - 巅峰统一以【本命福点星座 fortune_sign】为参照（见 _peak_kind）。
    返回按 (start, level) 排序的 _ReleasingPeriod 元组。end 为截断窗口上界。
    """
    if max_level < 1 or max_level > 4:
        raise ValueError("max_level must be between 1 and 4")
    if capricorn_years not in (27, 30):
        raise ValueError("capricorn_years must be 27 or 30")

    period_years = list(_PERIOD_YEARS_DEFAULT)
    period_years[_Sign.CAPRICORN.value] = capricorn_years
    period_table = tuple(period_years)

    starting_sign = _Sign(int(lot_lon % 360 // 30))
    if shift_start:
        starting_sign = _Sign((starting_sign.value + 1) % 12)
    out = []
    _release(1, starting_sign, fortune_sign, t0, end,
             max_level, year_length_days, period_table, out)
    out.sort(key=lambda p: (p.start, p.level))
    return tuple(out)


def _release(level, parent_sign, fortune_sign, parent_start, parent_end,
             max_level, year_length_days, period_table, out):
    """在 [parent_start, parent_end) 内穷尽填充 level 级周期（Valens exhaustive fill）。

    单位年长 = 1/12^(level-1)：L1 每宫贡献完整小年数，L2 为 1/12（月），依次细分。

    LB（解除束缚）规则，按 Brennan：子序列按黄道顺序**第一次**走满 12 宫回到
    父级起始星座时，不进入该星座而跳到它的对宫，落点周期 is_lb=True；
    **同一父周期只发生一次**。此后序列继续推进，再次回到父级起始星座时正常
    进入该星座，该周期 is_completion=True（完成期）。

      > "it eventually does come back to where it started, but it doesn't do a
      >  loosing of the bond the second time. It just like, repeats. It does
      >  actually come back to the original sign at that point."
      >  —— Chris Brennan, The Astrology Podcast ep.192

    只有够长的 L1（摩羯 27 年 / 水瓶 30 年）才走得到第二次回返，其余 10 个
    星座的 L1 在第一次 LB 之后就结束了。注意 LB 把游标挪到 parent+6，从那里
    只需再走 6 宫就会第二次碰到 parent——所以缺了 lb_used 这个一次性开关时，
    误报来得比"再走一整圈"早得多（Al Gore 摩羯 L1：真 LB 1992-03-10，
    误报 2000-04-27）。

    本函数对每个父周期递归调用，lb_used 是局部状态，因此该规则自动递归
    适用于 L2 / L3 / L4。

    巅峰 peak 统一以 fortune_sign（本命福点星座）为参照。
    """
    unit_years = 1.0 / (12.0 ** (level - 1))
    current_idx = parent_sign.value
    current_start = parent_start
    pending_lb_flag = False
    pending_completion_flag = False
    lb_used = False

    # 安全上限，防父级长度异常导致死循环（与 astrologica 一致）。
    for _ in range(2048):
        if current_start >= parent_end:
            break
        years_this = period_table[current_idx] * unit_years
        if years_this <= 0.0:
            break
        days_this = years_this * year_length_days
        current_end = min(current_start + timedelta(days=days_this), parent_end)

        sign_obj = _Sign(current_idx)
        is_lb = pending_lb_flag
        is_completion = pending_completion_flag
        pending_lb_flag = False
        pending_completion_flag = False

        out.append(_ReleasingPeriod(
            level=level, sign=sign_obj, start=current_start, end=current_end,
            is_lb=is_lb, is_completion=is_completion,
            peak=_peak_kind(sign_obj, fortune_sign),
        ))

        if level < max_level and current_end > current_start:
            _release(level + 1, sign_obj, fortune_sign, current_start, current_end,
                     max_level, year_length_days, period_table, out)

        current_start = current_end

        # 下一宫：子级（level>1）回到父级起始星座时，第一次跳对宫（LB），
        # 之后不再跳，正常进入该星座并标记完成期（Completion）。
        next_idx = (current_idx + 1) % 12
        if level > 1 and next_idx == parent_sign.value:
            if not lb_used:
                current_idx = (parent_sign.value + 6) % 12
                pending_lb_flag = True
                lb_used = True
            else:
                current_idx = next_idx
                pending_completion_flag = True
        else:
            current_idx = next_idx


def _peak_kind(sign_obj, fortune_sign):
    """高峰期：释放星座相对【本命福点 fortune_sign】落在四个角宫之一。

    idx ∈ {0, 3, 6, 9} —— 第 1 位（合）、第 4 位（下弦刑）、第 7 位（冲）、
    第 10 位（上弦刑）。四个都标，用同一个符号。

    与 Brennan 的差别只在**不分等级**：他把 1/10 位算主峰、7 位算中峰、4 位算
    次峰，但孟浩老师认为这个排序不成立——没有依据说福点的第 4、第 7 位一定比
    第 1、第 10 位次一等。四个都是高峰信号，不替读者排大小。

    拱（idx 4/8）与六分（idx 2/10）一律不算，这一条与 Brennan 一致。

    返回 "peak" 或 None（保留字符串而非布尔，是为了不改 API 字段类型）。
    """
    idx = (sign_obj.value - fortune_sign.value) % 12
    return "peak" if idx in (0, 3, 6, 9) else None


def _resolve_birth_dt(year, month, day, hour, minute, city,
                       location_id, lat_in, lng_in, tz_in, fold_in) -> datetime:
    """构造带时区的出生瞬间。

    走跟 compute() 同一条权威解析链（LocationResolver → CivilTimeResolver），
    契约也跟 compute() 完全一致：地点解不出 / 歧义未选 fold / 春拨空白 /
    无效时区 / 非法 fold，一律抛 BirthContextError，交给 app.py 的路由层
    转 409/422（见 api_zodiacal_releasing 里的 except BirthContextError）。

    （原来这里"解析失败就静默退回旧时区表"，理由是"compute() 已经校验过，
    这里理论不可达"——但预算好 fof_lon/pos_lon 走快路径时会跳过 compute()
    本身那次校验，前提不成立。实测纽约 2024-11-03 01:30 秋拨歧义、不传 fold，
    会被静默按 Asia/Shanghai 计算，UTC 偏差 12+ 小时。已改成跟 compute() 同一份
    "绝不静默兜底"契约，不再需要 tz_in 兜底路径。）
    """
    ctx = _resolve_birth_context(year, month, day, hour, minute, city,
                                 location_id, lat_in, lng_in, tz_in, fold_in)
    zone = ZoneInfo(ctx.snapshot.tz_iana)
    return datetime(year, month, day, hour, minute, fold=ctx.fold, tzinfo=zone)


def _resolve_birth_context(year, month, day, hour, minute, city,
                           location_id, lat_in, lng_in, tz_in, fold_in):
    """Same authoritative resolution, exposed internally for cache identity.

    No alternate UTC calculation; retain the complete location/version snapshot.
    """
    from services.calculator import BirthContextError
    from services.location_resolver import LocationResolver
    from services.civil_time_resolver import CivilTimeResolver, ResolutionStatus

    snapshot = LocationResolver().resolve(
        location_id=location_id,
        lat=float(lat_in) if lat_in is not None else None,
        lng=float(lng_in) if lng_in is not None else None,
        query=city,
    )
    if snapshot is None:
        raise ValueError(
            f"无法解析地点「{city or location_id or ''}」的坐标/时区，"
            f"请从下拉列表选择城市后重试。"
        )

    res = CivilTimeResolver().resolve(
        snapshot, year, month, day, hour, minute, fold=fold_in
    )
    if res.context is None or res.status not in (
        ResolutionStatus.NORMAL, ResolutionStatus.AMBIGUOUS
    ):
        raise BirthContextError(res.status.value, res.message, res.candidates)

    return res.context


def _next_boundary(periods, now: datetime):
    """当前这条周期链里最早结束的那个时刻（即下一次 is_current 会变化的瞬间）。

    is_current 是 (树, now) 的纯函数，但响应里只落了 "YYYY-MM-DD" 日期串，
    路由层无法从 JSON 反推出秒级边界。所以在这里把它算出来随响应返回，
    给缓存层当过期时间用——否则缓存键只到「天」，而 L4 周期最短 1.67 天、
    边界落在一天内任意时刻，同一民用日内跨界后缓存会继续吐旧的当前周期。

    当前链上 L1⊃L2⊃L3⊃L4 层层包含，所以最早结束的必然是最深那一级。
    """
    ends = [p.end for p in periods if p.start <= now < p.end]
    return min(ends) if ends else None


def _turning_points(periods, birth_dt: datetime) -> list:
    """把一生的 L2 解缚（LB）提炼成关键转折清单，供前端顶部汇总直接使用。

    纯几何推导，不含任何事件解释。每条转折由同一个 L1 下的三个 L2 构成：

      前奏期 foreshadowing —— LB 之前**第一次**走到「LB 将落入的那个星座」的 L2。
        L2 从 L1 起始星座起按黄道顺序推进，所以第 7 个 L2 必然是对宫，也就是后来
        LB 的落点；它距 L1 起点约 8.25–9.33 年（实测六个长周期星座都落在这区间，
        与 Brennan「松绑前约 8 年」一致）。
      解缚期 loosing_of_bond —— is_lb 的那个 L2，恒在 L1 起点后 211/12 = 17.58
        个释放年（摩羯取 27）。
      完成期 completion —— is_completion 的那个 L2，LB 之后序列重新回到 L1 起始
        星座。只有摩羯/水瓶这类够长的 L1 才走得到，否则为 None。

    触发门槛：L1 必须长于约 17.6 年，因此十二星座里只有双子 20 / 巨蟹 25 /
    狮子 19 / 处女 20 / 摩羯 27 / 水瓶 30 这六个能产生 LB；白羊 15、金牛 8、
    天秤 8、天蝎 15、射手 12、双鱼 12 永远不会。

    条数不写死：修正重复 LB 后多数盘是 1–2 条，但窗口内确实可能出现第 3 条
    （晚年再进一个长周期），一律如实返回。
    """
    out = []
    l1_list = [p for p in periods if p.level == 1]
    for l1 in l1_list:
        l2_list = [
            p for p in periods
            if p.level == 2 and l1.start <= p.start < l1.end
        ]
        lb = next((p for p in l2_list if p.is_lb), None)
        if lb is None:
            continue  # L1 太短，走不满一圈
        completion = next((p for p in l2_list if p.is_completion), None)
        # 前奏期：与 LB 同星座、但更早的那个 L2（序列里只会有一个）
        foreshadowing = next(
            (p for p in l2_list if p.sign == lb.sign and p.start < lb.start), None
        )

        def _window(p):
            if p is None:
                return None
            return {
                "start": p.start.strftime("%Y-%m-%d"),
                "end": p.end.strftime("%Y-%m-%d"),
                "sign": p.sign.name,
                "sign_cn": SIGN_CN_MAP.get(p.sign.name, p.sign.name),
                "age_start": round((p.start - birth_dt).days / 365.25, 1),
            }

        if (lb.start - birth_dt).days / 365.25 >= TURNING_POINT_MAX_AGE:
            continue  # 超过汇总年龄上限，不列（树里仍在）
        out.append({
            "l1_sign": l1.sign.name,
            "l1_sign_cn": SIGN_CN_MAP.get(l1.sign.name, l1.sign.name),
            "l1_start": l1.start.strftime("%Y-%m-%d"),
            "l1_end": l1.end.strftime("%Y-%m-%d"),
            "from_sign": l1.sign.name,              # 跳出（= L1 起始星座）
            "from_sign_cn": SIGN_CN_MAP.get(l1.sign.name, l1.sign.name),
            "to_sign": lb.sign.name,                # 跳入（= 对宫）
            "to_sign_cn": SIGN_CN_MAP.get(lb.sign.name, lb.sign.name),
            "foreshadowing": _window(foreshadowing),
            "loosing_of_bond": _window(lb),
            "completion": _window(completion),
        })
    return out


def _build_tree(periods: list, birth_dt: datetime, now: datetime) -> list:
    """扁平周期列表 → 嵌套树（L1→children L2→…→L4），并标记当前周期。

    _compute_releasing 输出已按 (start, level) 排序；用栈把每个周期挂到时间上
    包含它的父级下。子级 start 严格落在父级 [start, end) 内，兄弟边界相等时出栈。
    """
    if not periods:
        return []
    periods.sort(key=lambda p: (p.start, p.level))

    trees: list = []
    stack: list = []  # [(node_dict, parent_end)]
    for p in periods:
        node = _period_to_dict(p, birth_dt, now)
        while stack and p.start >= stack[-1][1]:
            stack.pop()
        if stack:
            stack[-1][0]["children"].append(node)
        else:
            trees.append(node)
        stack.append((node, p.end))
    return trees


def _period_to_dict(p, birth_dt: datetime, now: datetime) -> dict:
    sign_key = p.sign.name  # IntEnum：用 .name 取 'ARIES'，不可用 str()（3.11+ 返回 '0'）
    age_start = round((p.start - birth_dt).days / 365.25, 1)
    age_end = round((p.end - birth_dt).days / 365.25, 1)
    return {
        "level": p.level,
        "sign": sign_key,
        "sign_cn": SIGN_CN_MAP.get(sign_key, sign_key),
        "start": p.start.strftime("%Y-%m-%d"),
        "end": p.end.strftime("%Y-%m-%d"),
        "age_start": age_start,
        "age_end": age_end,
        "is_lb": bool(p.is_lb),
        "is_completion": bool(p.is_completion),  # 完成期：LB 之后序列再次回到父级起始星座
        "peak": p.peak,                  # None / "major" / "moderate" / "minor"（相对福点）
        "is_peak": p.peak is not None,   # 兼容旧前端
        "is_current": bool(p.start <= now < p.end),
        "children": [],
    }
