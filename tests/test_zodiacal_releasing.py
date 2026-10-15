"""黄道释放（纯 Python 3.8 引擎）测试。

- 引擎不变量：直接测 _compute_releasing，3.8 上也能跑（不依赖 astrologica）。
- 端到端：monkeypatch compute() 提供福点/精神点经度，验证响应树结构。
- 标记：巅峰（相对福点·角宫·分三级）、完结期。
- 对拍基准：只比对 astrologica 的 **L1** 周期边界；LB / 完成期 / peak 均按 Brennan
  口径偏离 astrologica（它每次回到父级起点都重跳对宫，会让 L2+ 星座整体偏移），
  这几项的裁判改用 Astro-Seek 固定日期（Al Gore AA 级样本）。
  astrologica 缺失（如服务器 3.8）时自动 skip。
"""
import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from services import zodiacal_releasing as zr

_BIRTH = datetime(1990, 4, 15, 18, 0, tzinfo=timezone(timedelta(hours=8)))


def _window_end(birth, year_length_days=360.0):
    # 窗口按公历年龄截断，与 year_length_days 无关（见 LIFESPAN_AGE_YEARS 注释）。
    del year_length_days
    return birth + timedelta(days=zr.LIFESPAN_AGE_YEARS * zr._CIVIL_YEAR_DAYS)


def _sign_of(lon):
    return zr._Sign(int(lon % 360 // 30))


# ── 引擎不变量（无 astrologica 依赖，3.8 可跑）────────────────────────────

def test_release_invariants():
    end = _window_end(_BIRTH)
    periods = zr._compute_releasing(
        10.5, _BIRTH, max_level=4, year_length_days=360.0,
        capricorn_years=30, end=end, fortune_sign=_sign_of(10.5),
    )
    assert periods, "应产出周期"
    l1 = [p for p in periods if p.level == 1]
    # 起始星座 = 福点星座（10.5° → 白羊），L1 按黄道顺序推进
    assert l1[0].sign.name == "ARIES"
    assert l1[1].sign.name == "TAURUS"
    # 福点自身星座（合）→ 主峰
    assert l1[0].peak == "peak"
    # 所有周期落在窗口内，且非零长
    assert all(_BIRTH <= p.start < p.end <= end for p in periods)
    # 截断：最末周期正好抵到窗口上界
    assert max(p.end for p in periods) == end
    # LB 只可能出现在 level>=2，且确实存在
    assert all(p.level >= 2 for p in periods if p.is_lb)
    assert any(p.is_lb for p in periods)
    # 完成期同样只在 level>=2
    assert all(p.level >= 2 for p in periods if p.is_completion)
    # 同一周期不会同时是 LB 和完成期
    assert not any(p.is_lb and p.is_completion for p in periods)


def test_lb_fires_at_most_once_per_parent():
    """同一父周期只允许一次 LB；之后回到父级起始星座应标完成期（Brennan）。

    旧实现没有一次性开关，每次游标将回到父级起始星座都会重跳对宫。因为 LB 把
    游标挪到 parent+6，从那里只需再走 6 宫就会第二次命中，所以摩羯(27)/水瓶(30)
    这两个够长的 L1 会冒出第二个 LB，且此后子序列星座全部偏移。
    """
    end = _window_end(_BIRTH)
    for cap in (27, 30):
        for lot_lon in (285.0, 315.0):   # 摩羯 / 水瓶 起始
            periods = zr._compute_releasing(
                lot_lon, _BIRTH, max_level=4, year_length_days=360.0,
                capricorn_years=cap, end=end, fortune_sign=_sign_of(lot_lon),
            )
            for parent in [p for p in periods if p.level < 4]:
                kids = [
                    p for p in periods
                    if p.level == parent.level + 1
                    and parent.start <= p.start < parent.end
                ]
                lbs = [p for p in kids if p.is_lb]
                comps = [p for p in kids if p.is_completion]
                assert len(lbs) <= 1, (
                    f"cap={cap} lot={lot_lon} L{parent.level}{parent.sign.name}"
                    f" 出现 {len(lbs)} 次 LB"
                )
                # 完成期必须落在父级起始星座上，且只能在发生过 LB 之后
                for c in comps:
                    assert c.sign == parent.sign, "完成期星座应等于父级起始星座"
                    assert lbs and lbs[0].start < c.start, "完成期必须在 LB 之后"


def test_lb_absent_when_parent_too_short():
    """L1 短于约 17.6 年时走不满一圈，不可能有 LB（Brennan：至少 17 年）。"""
    end = _window_end(_BIRTH)
    # 金牛 8 年、天秤 8 年、射手 12 年、双鱼 12 年、白羊 15 年、天蝎 15 年
    for lot_lon in (45.0, 195.0, 255.0, 345.0, 15.0, 225.0):
        periods = zr._compute_releasing(
            lot_lon, _BIRTH, max_level=2, year_length_days=360.0,
            capricorn_years=27, end=end, fortune_sign=_sign_of(lot_lon),
        )
        first_l1 = [p for p in periods if p.level == 1][0]
        kids = [p for p in periods if p.level == 2
                and first_l1.start <= p.start < first_l1.end]
        assert not any(p.is_lb for p in kids), (
            f"{first_l1.sign.name}（{(first_l1.end-first_l1.start).days/360:.0f}年）"
            f" 不应有 LB"
        )


def test_release_capricorn_years_variants_differ():
    end = _window_end(_BIRTH)
    # 摩羯起盘（280° → 摩羯），30 年 vs 27 年应产生不同的子级边界
    p30 = zr._compute_releasing(280.0, _BIRTH, 4, 360.0, 30, end, fortune_sign=_sign_of(280.0))
    p27 = zr._compute_releasing(280.0, _BIRTH, 4, 360.0, 27, end, fortune_sign=_sign_of(280.0))
    assert [p.end for p in p30] != [p.end for p in p27]


def test_release_max_level_bounds():
    end = _window_end(_BIRTH)
    with pytest.raises(ValueError):
        zr._compute_releasing(10.5, _BIRTH, 5, 360.0, 30, end, fortune_sign=_sign_of(10.5))
    with pytest.raises(ValueError):
        zr._compute_releasing(10.5, _BIRTH, 4, 360.0, 28, end, fortune_sign=_sign_of(10.5))


# ── 巅峰期：相对福点、只角宫、分三级（Brennan）──────────────────────────

def test_peak_marks_all_four_angles_from_fortune():
    """高峰期标相对福点的四个角宫，同一个符号，不分等级。

    角宫的选择（idx{0,3,6,9}，不含拱与六分）与 Brennan 一致；偏离只在于不再把
    1/10 位算主峰、7 位算中峰、4 位算次峰——没有依据说第 4、第 7 位一定次一等，
    四个都是高峰信号，不替读者排大小。
    """
    F = zr._Sign(3)  # 福点在巨蟹
    pk = lambda i: zr._peak_kind(zr._Sign(i), F)
    assert pk(3) == "peak", "巨蟹 第 1 位 合"
    assert pk(6) == "peak", "天秤 第 4 位 下弦刑"
    assert pk(9) == "peak", "摩羯 第 7 位 冲"
    assert pk(0) == "peak", "白羊 第 10 位 上弦刑"
    # 拱(idx4/8)、六分(idx2/10)、不合意(idx1/5/7/11) 一律不标
    for i in range(12):
        if i not in (0, 3, 6, 9):
            assert pk(i) is None, f"{zr.SIGN_KEYS[i]} 不该有高峰标记"
    # 孟浩老师质疑的那个：双子相对巨蟹是第 12 位，确实不该有标记
    assert pk(2) is None, "双子 第 12 位"


def test_peak_has_no_grades():
    """API 不再返回 major/moderate/minor 这三种等级。"""
    end = _window_end(_BIRTH)
    periods = zr._compute_releasing(
        10.5, _BIRTH, max_level=4, year_length_days=360.0,
        capricorn_years=27, end=end, fortune_sign=_sign_of(10.5),
    )
    values = {p.peak for p in periods}
    assert values <= {"peak", None}, f"出现了分级值: {values}"
    assert "peak" in values
    # 四个角宫都应被标到，不是只有两个
    marked = {
        (p.sign.value - _sign_of(10.5).value) % 12
        for p in periods if p.peak
    }
    assert marked == {0, 3, 6, 9}, f"标记的相对位 {marked}"


# ── 端到端响应结构 ───────────────────────────────────────────────────────

def test_calculate_zodiacal_releasing_returns_fortune_and_spirit_tables(monkeypatch):
    def fake_compute(name, year, month, day, hour, minute, city, **kwargs):
        # 10.5° → 白羊（福点）；250.25° → 射手（精神点）
        return {"sect": "日生人", "fof_lon": 10.5, "pos_lon": 250.25}

    monkeypatch.setattr(zr, "compute", fake_compute)
    result = zr.calculate_zodiacal_releasing(
        {
            "name": "Ada", "year": 1990, "month": 1, "day": 1,
            "hour": 12, "minute": 30, "city": "北京",
            "lat": 39.9, "lng": 116.4, "tz": "Asia/Shanghai",
        },
        max_level=3,
        now=datetime(1990, 1, 10, tzinfo=timezone(timedelta(hours=8))),
    )

    assert result["success"] is True
    assert result["sect"] == "日生人"
    assert result["capricorn_years"] == 27   # 默认应为 Brennan/Valens 标准 27
    assert result["lots"]["fortune"]["lot_label"] == "福点"
    assert result["lots"]["fortune"]["lot_sign"] == "白羊座"
    assert result["lots"]["spirit"]["lot_label"] == "精神点"
    assert result["lots"]["spirit"]["lot_sign"] == "射手座"

    fortune_root = result["lots"]["fortune"]["periods"][0]
    assert fortune_root["level"] == 1
    assert fortune_root["sign_cn"] == "白羊座"
    # 福点根（白羊，相对福点白羊=合）→ 主峰
    assert fortune_root["peak"] == "peak"
    assert fortune_root["is_peak"] is True
    assert fortune_root["is_current"] is True          # 出生后第 10 天落在首个 L1（白羊）内
    assert fortune_root["children"][0]["level"] == 2   # 懒加载前完整含子级
    # L1 黄道顺序：白羊 → 金牛
    assert result["lots"]["fortune"]["periods"][1]["sign_cn"] == "金牛座"

    # 关键：精神点根（射手）相对福点（白羊）是第 9 位=拱，按 Brennan 不是巅峰
    spirit_root = result["lots"]["spirit"]["periods"][0]
    assert spirit_root["sign_cn"] == "射手座"
    assert spirit_root["peak"] is None
    assert spirit_root["is_peak"] is False


def test_calculate_zodiacal_releasing_requires_existing_lot_longitudes(monkeypatch):
    def fake_compute(*args, **kwargs):
        return {"sect": "日生人", "fof_lon": None, "pos_lon": 250.25}

    monkeypatch.setattr(zr, "compute", fake_compute)
    with pytest.raises((TypeError, ValueError)):
        zr.calculate_zodiacal_releasing(
            {
                "name": "Ada", "year": 1990, "month": 1, "day": 1,
                "hour": 12, "minute": 30, "city": "北京",
            }
        )


def test_lazy_l4_matches_the_same_parent_in_full_tree(monkeypatch):
    """按需 L4 必须与旧的完整四级树逐字段一致，不能为了提速改变日期或标记。"""
    monkeypatch.setattr(
        zr, "compute",
        lambda *args, **kwargs: {"sect": "日生人", "fof_lon": 10.5, "pos_lon": 250.25},
    )
    monkeypatch.setattr(zr, "_resolve_birth_dt", lambda *args, **kwargs: _BIRTH)
    user = {
        "name": "Ada", "year": 1990, "month": 4, "day": 15,
        "hour": 18, "minute": 0, "city": "北京",
    }
    now = datetime(1991, 1, 1, tzinfo=_BIRTH.tzinfo)
    shallow = zr.calculate_zodiacal_releasing(user, max_level=3, now=now)
    full = zr.calculate_zodiacal_releasing(user, max_level=4, now=now)
    parent = shallow["lots"]["spirit"]["periods"][0]["children"][0]["children"][0]
    expected = full["lots"]["spirit"]["periods"][0]["children"][0]["children"][0]["children"]

    lazy = zr.calculate_zodiacal_releasing_l4(
        user, "spirit", parent["start"], parent["sign"], now=now,
    )
    assert lazy["periods"] == expected
    assert lazy["periods"]
    assert {p["level"] for p in lazy["periods"]} == {4}


def test_lazy_l4_rejects_a_parent_not_in_the_chart(monkeypatch):
    monkeypatch.setattr(
        zr, "compute",
        lambda *args, **kwargs: {"sect": "日生人", "fof_lon": 10.5, "pos_lon": 250.25},
    )
    monkeypatch.setattr(zr, "_resolve_birth_dt", lambda *args, **kwargs: _BIRTH)
    user = {
        "name": "Ada", "year": 1990, "month": 4, "day": 15,
        "hour": 18, "minute": 0, "city": "北京",
    }
    with pytest.raises(ValueError, match="不存在|不匹配"):
        zr.calculate_zodiacal_releasing_l4(
            user, "spirit", "2099-01-01", "ARIES",
        )


# ── _resolve_birth_dt：走权威解析链，非内置城市名不再退回 Shanghai，fold 不丢 ──

def test_resolve_birth_dt_uses_location_resolver_for_non_builtin_city():
    """Paris 不在旧版 _get_timezone_for_city 的内置城市名表里；显式 lat/lng 应
    直接解析到 Europe/Paris，而不是静默退回旧兜底 Asia/Shanghai。"""
    dt = zr._resolve_birth_dt(
        1990, 4, 15, 18, 0, "巴黎",
        location_id=None, lat_in=48.8566, lng_in=2.3522, tz_in=None, fold_in=None,
    )
    assert "Paris" in str(dt.tzinfo)
    assert dt.utcoffset() == timedelta(hours=2)  # 1990-04-15 已进入 CEST 夏令时


def test_resolve_birth_dt_threads_fold_through_civil_time_resolver():
    """2023-11-05 01:30 America/New_York 是秋拨重叠的歧义挂钟时刻（1:59:59 EDT
    跳回 1:00:00 EST）；fold=0/fold=1 必须落到不同的真实 UTC 瞬间，不能像修复前
    那样被 datetime() 默认 fold=0 悄悄压平成同一个瞬间。"""
    dt_fold0 = zr._resolve_birth_dt(
        2023, 11, 5, 1, 30, "New York",
        location_id=None, lat_in=40.7128, lng_in=-74.0060, tz_in=None, fold_in=0,
    )
    dt_fold1 = zr._resolve_birth_dt(
        2023, 11, 5, 1, 30, "New York",
        location_id=None, lat_in=40.7128, lng_in=-74.0060, tz_in=None, fold_in=1,
    )
    assert dt_fold0.utcoffset() != dt_fold1.utcoffset()
    assert dt_fold0.astimezone(timezone.utc) != dt_fold1.astimezone(timezone.utc)


# ── 对拍 astrologica（开发期基准，3.8 上自动 skip）──────────────────────────
# 只比对「周期边界 / 子级 / LB」——peak 已改为 Brennan 口径（相对福点、角宫、分三级），
# 与 astrologica 的 is_peak 定义不同，故不在对拍范围。

def _astrologica_periods(lot_lon, birth_dt, max_level, year_length_days,
                         capricorn_years, end):
    from astrologica import (
        compute_zodiacal_releasing, compute_natal_chart,
        ChartData, Place, Lot, HouseSystem, LotPosition,
    )
    chart = compute_natal_chart(
        ChartData(datetime=birth_dt, place=Place(latitude=39.9, longitude=116.4)),
        house_system=HouseSystem.WHOLE_SIGN,
    )
    new_lots = dict(chart.lots)
    new_lots[Lot.FORTUNE] = LotPosition(lot=Lot.FORTUNE, longitude=lot_lon)
    chart = dataclasses.replace(chart, lots=new_lots)
    return compute_zodiacal_releasing(
        chart, lot=Lot.FORTUNE, max_level=max_level,
        year_length_days=year_length_days, capricorn_years=capricorn_years, end=end,
    )


def _astrologica_periods_for_lot(lot_lon, birth_dt, lot, max_level,
                                 year_length_days, capricorn_years, end,
                                 latitude, longitude):
    """用真实案例的本地 lot 经度，调用独立库计算指定 lot 的释放周期。"""
    from astrologica import (
        compute_zodiacal_releasing, compute_natal_chart,
        ChartData, Place, LotPosition, HouseSystem,
    )
    chart = compute_natal_chart(
        ChartData(datetime=birth_dt, place=Place(latitude=latitude, longitude=longitude)),
        house_system=HouseSystem.WHOLE_SIGN,
    )
    new_lots = dict(chart.lots)
    new_lots[lot] = LotPosition(lot=lot, longitude=lot_lon)
    chart = dataclasses.replace(chart, lots=new_lots)
    return compute_zodiacal_releasing(
        chart, lot=lot, max_level=max_level,
        year_length_days=year_length_days, capricorn_years=capricorn_years, end=end,
    )


# 覆盖全部 12 个起始星座 + 摩羯 27/30 + L3/L4 + 回归年长
@pytest.mark.parametrize("lot_lon", [15 + 30 * i for i in range(12)] + [275.0, 295.0])
@pytest.mark.parametrize("max_level,capricorn_years,year_length_days", [
    (4, 30, 360.0),
    (3, 30, 360.0),
    (4, 27, 360.0),
    (4, 30, 365.2425),
])
def test_matches_astrologica_oracle(lot_lon, max_level, capricorn_years, year_length_days):
    pytest.importorskip("astrologica")
    end = _window_end(_BIRTH, year_length_days)
    mine = zr._compute_releasing(
        lot_lon, _BIRTH, max_level, year_length_days, capricorn_years, end,
        fortune_sign=_sign_of(lot_lon),
    )
    oracle = _astrologica_periods(
        lot_lon, _BIRTH, max_level, year_length_days, capricorn_years, end,
    )
    # 只对拍 L1。
    #
    # astrologica 不是 LB 规则的裁判：它每次游标回到父级起始星座都重跳对宫，
    # 没有「同一父周期只跳一次」的限制，与 Brennan 相反（ep.192："it doesn't do
    # a loosing of the bond the second time. It just like, repeats."）。
    #
    # 关键是这条规则会改变**整条子序列的星座**，不只是一个布尔标记，而且任何够长
    # 的父周期都会触发（水瓶 L2 = 2.5 年、摩羯 L2 = 2.25 年，都长于 L3 走满一圈
    # 所需的 211/144 = 1.47 年）。所以 L2 及以下没有一个层级能与它逐节点对齐——
    # 实测 11346 vs 11398 个节点。不是我们算错，是基准错。
    #
    # L1 不参与 LB（_release 里 `if level > 1`），是纯小年数查表递推，因此仍可
    # 安全对拍，能守住小年数表 / 年长 / 摩羯 27-30 / 截断边界这几类回归。
    # L2 及以下的权威裁判改用 Astro-Seek 固定日期：
    # 见 test_astroseek_al_gore_reference 与 test_lb_fires_at_most_once_per_parent。
    mine_l1 = [p for p in mine if p.level == 1]
    oracle_l1 = [p for p in oracle if p.level == 1]
    assert len(mine_l1) == len(oracle_l1), (
        f"L1 节点数不一致 {len(mine_l1)} != {len(oracle_l1)}"
    )
    for i, (m, o) in enumerate(zip(mine_l1, oracle_l1)):
        assert m.sign.name == o.sign.name, f"L1 #{i} sign"
        assert m.start == o.start, f"L1 #{i} start"
        assert m.end == o.end, f"L1 #{i} end"
        assert not m.is_lb and not o.is_lb, f"L1 #{i} 不应有 LB"


# 真实出生资料补充对拍：lot 经度仍来自项目自己的本命计算，释放周期由独立库复算。
# 这样同时覆盖“本地 lot → 起始星座”和“L1 小年数 / 年长 / 100 岁窗口”两段边界。
_REAL_ZR_CASES = [
    pytest.param(
        "Emma Watson", 1990, 4, 15, 18, 0,
        "Paris", 48.8566, 2.3522, "Europe/Paris",
        id="emma-watson-paris",
    ),
    pytest.param(
        "Al Gore", 1948, 3, 31, 12, 53,
        "Washington", 38.8951, -77.0364, "America/New_York",
        id="al-gore-washington",
    ),
]


@pytest.mark.parametrize(
    "name,year,month,day,hour,minute,city,latitude,longitude,tz_name",
    _REAL_ZR_CASES,
)
@pytest.mark.parametrize("lot_key,lot_enum", [("fortune", "FORTUNE"), ("spirit", "SPIRIT")])
@pytest.mark.parametrize("capricorn_years", [27, 30])
def test_real_cases_match_astrologica_l1_for_both_lots(
    name, year, month, day, hour, minute, city, latitude, longitude, tz_name,
    lot_key, lot_enum, capricorn_years,
):
    """真实案例的福点/精神点 L1 在两种摩羯年长下都与独立实现对齐。"""
    pytest.importorskip("astrologica")
    user = {
        "name": name, "year": year, "month": month, "day": day,
        "hour": hour, "minute": minute, "city": city,
        "lat": latitude, "lng": longitude, "tz": tz_name,
    }
    context = zr.compute(name, year, month, day, hour, minute, city,
                         lat=latitude, lng=longitude, tz=tz_name)
    lot_lon_key = "fof_lon" if lot_key == "fortune" else "pos_lon"
    lot_lon = context[lot_lon_key]
    birth_dt = zr._resolve_birth_dt(
        year, month, day, hour, minute, city,
        location_id=None, lat_in=latitude, lng_in=longitude,
        tz_in=tz_name, fold_in=None,
    )
    end = _window_end(birth_dt)
    fortune_sign = _sign_of(context["fof_lon"])

    mine = zr._compute_releasing(
        lot_lon, birth_dt, max_level=4, year_length_days=365.2425,
        capricorn_years=capricorn_years, end=end, fortune_sign=fortune_sign,
    )
    from astrologica import Lot
    oracle = _astrologica_periods_for_lot(
        lot_lon, birth_dt, getattr(Lot, lot_enum), max_level=4,
        year_length_days=365.2425, capricorn_years=capricorn_years, end=end,
        latitude=latitude, longitude=longitude,
    )
    mine_l1 = [period for period in mine if period.level == 1]
    oracle_l1 = [period for period in oracle if period.level == 1]
    assert len(mine_l1) == len(oracle_l1)
    for index, (local_period, oracle_period) in enumerate(zip(mine_l1, oracle_l1)):
        assert local_period.sign.name == oracle_period.sign.name, f"{name} {lot_key} L1 #{index} sign"
        assert local_period.start == oracle_period.start, f"{name} {lot_key} L1 #{index} start"
        assert local_period.end == oracle_period.end, f"{name} {lot_key} L1 #{index} end"
        assert local_period.end <= end
    assert mine_l1[-1].end == end


@pytest.mark.parametrize(
    "name,year,month,day,hour,minute,city,latitude,longitude,tz_name",
    _REAL_ZR_CASES,
)
@pytest.mark.parametrize("lot_key", ["fortune", "spirit"])
@pytest.mark.parametrize("capricorn_years", [27, 30])
def test_real_cases_have_one_lb_then_completion_per_parent(
    name, year, month, day, hour, minute, city, latitude, longitude, tz_name,
    lot_key, capricorn_years,
):
    """真实案例也必须遵守 Brennan 的一次 LB / 后续 Completion 规则。"""
    user = {
        "name": name, "year": year, "month": month, "day": day,
        "hour": hour, "minute": minute, "city": city,
        "lat": latitude, "lng": longitude, "tz": tz_name,
    }
    result = zr.calculate_zodiacal_releasing(
        user, max_level=4, capricorn_years=capricorn_years,
        now=datetime(year + 99, month, day, hour, minute,
                     tzinfo=zr._resolve_birth_dt(
                         year, month, day, hour, minute, city,
                         location_id=None, lat_in=latitude, lng_in=longitude,
                         tz_in=tz_name, fold_in=None,
                     ).tzinfo),
    )
    for parent in result["lots"][lot_key]["periods"]:
        children = parent.get("children", [])
        lbs = [child for child in children if child["is_lb"]]
        completions = [child for child in children if child["is_completion"]]
        assert len(lbs) <= 1, f"{name} {lot_key} {parent['sign_cn']} 出现多个 LB"
        assert all(child["sign_cn"] == parent["sign_cn"] for child in completions)
        if completions:
            assert lbs and lbs[0]["start"] < completions[0]["start"]


# ── Astro-Seek 固定日期回归（LB / 完成期的权威裁判）─────────────────────────
# 样本：Al Gore，1948-03-31 12:53，Washington D.C.（Astro-Databank AA 级出生资料）。
# 仅作公开计算样本，不涉及现实事件解读。
# 参照：https://horoscopes.astro-seek.com/zodiacal-releasing-astrology-calculator
#
# 这组日期是 LB 规则的裁判，取代 astrologica——后者在摩羯/水瓶 L1 上会误报
# 第二次 LB（2000-04-27 / 2027-02-05 本应是完成期）。

_AL_GORE = {
    "name": "Al Gore", "year": 1948, "month": 3, "day": 31,
    "hour": 12, "minute": 53, "city": "Washington",
    "lat": 38.8951, "lng": -77.0364, "tz": -5.0,
}

# (lot, L1 星座, 起始日, 标记类型, 标记日, 标记星座)
_ASTROSEEK_NODES = [
    ("spirit", "摩羯座", "1974-11-10", "lb",         "1992-03-10", "巨蟹座"),
    ("spirit", "摩羯座", "1974-11-10", "completion", "2000-04-27", "摩羯座"),
    ("spirit", "水瓶座", "2001-06-21", "lb",         "2018-10-20", "狮子座"),
    ("spirit", "水瓶座", "2001-06-21", "completion", "2027-02-05", "水瓶座"),
    ("fortune", "双子座", "1970-12-01", "lb",        "1988-03-31", "射手座"),
    ("fortune", "巨蟹座", "1990-08-18", "lb",        "2007-12-17", "摩羯座"),
]


@pytest.fixture(scope="module")
def _al_gore_result():
    return zr.calculate_zodiacal_releasing(
        dict(_AL_GORE), max_level=2, capricorn_years=27,
        now=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=-5))),
    )


def test_astroseek_al_gore_spirit_lot_sign(_al_gore_result):
    assert _al_gore_result["lots"]["spirit"]["lot_sign"] == "天蝎座"


@pytest.mark.parametrize(
    "lot,l1_sign,l1_start,kind,mark_date,mark_sign", _ASTROSEEK_NODES
)
def test_astroseek_al_gore_reference(_al_gore_result, lot, l1_sign, l1_start,
                                     kind, mark_date, mark_sign):
    l1s = [p for p in _al_gore_result["lots"][lot]["periods"]
           if p["sign_cn"] == l1_sign and p["start"] == l1_start]
    assert len(l1s) == 1, f"未找到 L1 {l1_sign} @ {l1_start}"
    kids = l1s[0]["children"]
    hit = [k for k in kids if k["start"] == mark_date]
    assert len(hit) == 1, f"未找到 L2 节点 @ {mark_date}"
    node = hit[0]
    assert node["sign_cn"] == mark_sign, f"{mark_date} 星座应为 {mark_sign}"
    if kind == "lb":
        assert node["is_lb"] and not node["is_completion"]
    else:
        assert node["is_completion"] and not node["is_lb"]


def test_astroseek_al_gore_no_second_lb(_al_gore_result):
    """旧实现在摩羯/水瓶 L1 里各有 2 个 LB；修正后每个 L1 至多 1 个。"""
    for lot in ("spirit", "fortune"):
        for l1 in _al_gore_result["lots"][lot]["periods"]:
            lbs = [k for k in l1["children"] if k["is_lb"]]
            assert len(lbs) <= 1, (
                f"{lot} L1 {l1['sign_cn']} @ {l1['start']} 有 {len(lbs)} 个 LB："
                f"{[k['start'] for k in lbs]}"
            )


def test_window_covers_late_life_nodes(_al_gore_result):
    """旧窗口 80×360=28800 天只到 78.85 岁，会切掉 2027-02-05 的水瓶完成期。"""
    aqua = [p for p in _al_gore_result["lots"]["spirit"]["periods"]
            if p["sign_cn"] == "水瓶座" and p["start"] == "2001-06-21"]
    assert aqua, "水瓶 L1 应在窗口内"
    assert any(k["start"] == "2027-02-05" and k["is_completion"]
               for k in aqua[0]["children"]), "2027-02-05 完成期应落在窗口内"


# ── 关键转折汇总 turning_points ───────────────────────────────────────────

def _tps(lot_lon, cap=27, max_level=2):
    end = _window_end(_BIRTH)
    periods = zr._compute_releasing(
        lot_lon, _BIRTH, max_level=max_level, year_length_days=360.0,
        capricorn_years=cap, end=end, fortune_sign=_sign_of(lot_lon),
    )
    return zr._turning_points(periods, _BIRTH), periods


_LONG_SIGNS = {"GEMINI", "CANCER", "LEO", "VIRGO", "CAPRICORN", "AQUARIUS"}
_SHORT_SIGNS = {"ARIES", "TAURUS", "LIBRA", "SCORPIO", "SAGITTARIUS", "PISCES"}


@pytest.mark.parametrize("lot_lon", [15 + 30 * i for i in range(12)])
def test_turning_points_geometry_holds_for_every_start_sign(lot_lon):
    """十二个起始星座全覆盖：每条转折的三个窗口都必须满足确定性几何关系。"""
    tps, periods = _tps(lot_lon)
    for t in tps:
        # 跳出 = L1 起始星座；跳入 = 其对宫
        assert t["from_sign"] == t["l1_sign"]
        from_idx = zr.SIGN_KEYS.index(t["from_sign"])
        assert t["to_sign"] == zr.SIGN_KEYS[(from_idx + 6) % 12]
        # 只有长周期星座能触发
        assert t["l1_sign"] in _LONG_SIGNS

        lb = t["loosing_of_bond"]
        assert lb is not None and lb["sign"] == t["to_sign"]

        # 前奏期：与 LB 同星座，但更早
        fore = t["foreshadowing"]
        assert fore is not None, "长周期 L1 必有前奏期（第 7 个 L2 就是对宫）"
        assert fore["sign"] == lb["sign"], "前奏期星座应等于 LB 落入星座"
        assert fore["start"] < lb["start"], "前奏期应早于 LB"

        # 完成期：回到 L1 起始星座，且晚于 LB
        comp = t["completion"]
        if comp is not None:
            assert comp["sign"] == t["l1_sign"], "完成期星座应等于 L1 起始星座"
            assert comp["start"] > lb["start"], "完成期应晚于 LB"

        # 三个窗口都落在该 L1 内
        for w in (fore, lb, comp):
            if w:
                assert t["l1_start"] <= w["start"] < t["l1_end"]


@pytest.mark.parametrize("lot_lon", [15 + 30 * i for i in range(12)])
def test_turning_points_are_reverse_lookupable_in_the_tree(lot_lon):
    """汇总里的每个窗口都能在释放树里反查到唯一一个 L2 周期。"""
    tps, periods = _tps(lot_lon)
    l2 = [p for p in periods if p.level == 2]
    for t in tps:
        for key, flag in (("loosing_of_bond", "is_lb"), ("completion", "is_completion")):
            w = t[key]
            if w is None:
                continue
            hits = [
                p for p in l2
                if p.start.strftime("%Y-%m-%d") == w["start"]
                and p.sign.name == w["sign"]
                and getattr(p, flag)
            ]
            assert len(hits) == 1, f"{key} @ {w['start']} 应唯一对应树中一个 L2"
        fore = t["foreshadowing"]
        hits = [
            p for p in l2
            if p.start.strftime("%Y-%m-%d") == fore["start"]
            and p.sign.name == fore["sign"]
        ]
        assert len(hits) == 1, "前奏期应唯一对应树中一个 L2"


def test_turning_points_empty_for_short_l1_only_runs():
    """L1 全是短周期时汇总为空（孟浩：部分人一生 0 次）。"""
    # 金牛 8 年起步，窗口内第一个 L1 就是短的；逐条检查每个 L1
    for lot_lon in (45.0, 195.0):
        tps, periods = _tps(lot_lon)
        l1_signs = {t["l1_sign"] for t in tps}
        assert not (l1_signs & _SHORT_SIGNS), "短周期 L1 不应出现在汇总里"


def test_completion_only_for_capricorn_and_aquarius_l1():
    """完成期只有摩羯/水瓶 L1 才走得到（其余长周期 LB 后剩余年数不够 6 宫）。"""
    has_comp = set()
    for lot_lon in [15 + 30 * i for i in range(12)]:
        tps, _ = _tps(lot_lon)
        for t in tps:
            if t["completion"] is not None:
                has_comp.add(t["l1_sign"])
    assert has_comp <= {"CAPRICORN", "AQUARIUS"}, f"意外的完成期来源：{has_comp}"
    assert has_comp, "摩羯/水瓶 L1 应能产生完成期"


def test_turning_points_count_not_hardcoded(_al_gore_result):
    """条数如实返回，不写死 1-2；但只列到 TURNING_POINT_MAX_AGE 为止。

    高尔福点在 100 岁窗口内本有 3 次，第 3 次落在 84.4 岁，超过汇总上限被滤掉。
    """
    fortune = _al_gore_result["lots"]["fortune"]["turning_points"]
    assert len(fortune) == 2, f"84 岁上限后应为 2 次，实得 {len(fortune)}"
    spirit = _al_gore_result["lots"]["spirit"]["turning_points"]
    assert len(spirit) == 2
    for t in fortune + spirit:
        assert t["loosing_of_bond"]["age_start"] < zr.TURNING_POINT_MAX_AGE


def test_age_cap_only_trims_the_summary_not_the_tree(_al_gore_result):
    """84 岁上限只作用于汇总；树里仍有 84 岁之后的周期。"""
    deepest_end = max(
        l1["end"] for l1 in _al_gore_result["lots"]["fortune"]["periods"]
    )
    assert deepest_end > "2032-01-01", "树应覆盖到晚年"
    # 被滤掉的那次（84.4 岁、2032-08-07）仍能在树里用 is_lb 找到
    found = False
    for l1 in _al_gore_result["lots"]["fortune"]["periods"]:
        for l2 in l1["children"]:
            if l2["is_lb"] and l2["start"] == "2032-08-07":
                found = True
    assert found, "树里应保留 84 岁后的 LB 标记"


def test_turning_points_al_gore_exact_dates(_al_gore_result):
    """Astro-Seek 固定日期 + 前奏期/完成期的确定性推导。"""
    spirit = _al_gore_result["lots"]["spirit"]["turning_points"]
    t0 = spirit[0]
    assert (t0["l1_sign_cn"], t0["from_sign_cn"], t0["to_sign_cn"]) == ("摩羯座", "摩羯座", "巨蟹座")
    assert t0["loosing_of_bond"]["start"] == "1992-03-10"
    assert t0["completion"]["start"] == "2000-04-27"
    assert t0["foreshadowing"]["start"] == "1984-01-22"
    assert t0["foreshadowing"]["sign_cn"] == "巨蟹座"
    t1 = spirit[1]
    assert t1["loosing_of_bond"]["start"] == "2018-10-20"
    assert t1["completion"]["start"] == "2027-02-05"

    fortune = _al_gore_result["lots"]["fortune"]["turning_points"]
    assert fortune[0]["loosing_of_bond"]["start"] == "1988-03-31"
    assert fortune[1]["loosing_of_bond"]["start"] == "2007-12-17"
    # 长周期但非摩羯/水瓶 → 无完成期
    assert fortune[0]["completion"] is None
    assert fortune[1]["completion"] is None


def test_turning_points_present_for_both_lots(_al_gore_result):
    """精神点与福点都要各自带一份汇总（前端顶部并列显示）。"""
    for lot in ("fortune", "spirit"):
        d = _al_gore_result["lots"][lot]
        assert "turning_points" in d
        assert isinstance(d["turning_points"], list)
        for t in d["turning_points"]:
            for k in ("l1_sign", "l1_sign_cn", "l1_start", "l1_end",
                      "from_sign", "to_sign", "foreshadowing",
                      "loosing_of_bond", "completion"):
                assert k in t, f"{lot} 缺字段 {k}"
            assert "age_start" in t["loosing_of_bond"]


# ── 当前周期边界：next_boundary 供缓存层按秒过期 ──────────────────────────

def test_next_boundary_is_the_deepest_current_period_end():
    """next_boundary = 当前周期链里最早结束的那个时刻（必为最深一级）。"""
    end = _window_end(_BIRTH)
    now = _BIRTH + timedelta(days=30 * 365.2425)
    periods = zr._compute_releasing(
        10.5, _BIRTH, max_level=4, year_length_days=360.0,
        capricorn_years=27, end=end, fortune_sign=_sign_of(10.5),
    )
    edge = zr._next_boundary(periods, now)
    current = [p for p in periods if p.start <= now < p.end]
    assert current, "该时刻应落在周期链内"
    assert edge == min(p.end for p in current)
    # 链是层层包含的，所以最早结束的就是最深那一级
    deepest = max(current, key=lambda p: p.level)
    assert edge == deepest.end
    # 边界之后原链不再当前
    assert not any(p.start <= edge < p.end for p in current if p.level == deepest.level)


def test_next_boundary_is_not_midnight_aligned():
    """边界落在一天内任意时刻，所以缓存键只到「天」是不够的。"""
    end = _window_end(_BIRTH)
    offsets = set()
    for days in (3000, 6000, 9000, 12000, 15000):
        now = _BIRTH + timedelta(days=days)
        periods = zr._compute_releasing(
            250.25, _BIRTH, max_level=4, year_length_days=360.0,
            capricorn_years=27, end=end, fortune_sign=_sign_of(10.5),
        )
        edge = zr._next_boundary(periods, now)
        if edge is not None:
            offsets.add((edge.hour, edge.minute))
    assert offsets, "应取到边界"
    assert offsets != {(0, 0)}, "边界并非都落在午夜——按天失效会漏掉同日跨界"


def test_response_exposes_next_boundary_for_both_entry_points(monkeypatch):
    def fake_compute(*args, **kwargs):
        return {"sect": "日生人", "fof_lon": 10.5, "pos_lon": 250.25}

    monkeypatch.setattr(zr, "compute", fake_compute)
    body = {"name": "Ada", "year": 1990, "month": 4, "day": 15,
            "hour": 18, "minute": 0, "city": "北京",
            "lat": 39.9, "lng": 116.4, "tz": "Asia/Shanghai"}
    now = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=8)))

    full = zr.calculate_zodiacal_releasing(dict(body), max_level=3, now=now)
    assert "next_boundary" in full
    assert full["next_boundary"], "活着的人应有下一个边界"
    parsed = datetime.fromisoformat(full["next_boundary"])
    assert parsed.tzinfo is not None, "必须带时区，否则缓存层无法跨时区比较"
    assert parsed > now

    # L4 端点同样要带，否则 L4 缓存仍按天失效
    l3 = None
    for l1 in full["lots"]["spirit"]["periods"]:
        for l2 in l1["children"]:
            for node in l2["children"]:
                if node["is_current"]:
                    l3 = node
    assert l3 is not None, "应能找到当前 L3"
    l4 = zr.calculate_zodiacal_releasing_l4(
        dict(body), lot="spirit", parent_start=l3["start"],
        parent_sign=l3["sign"], now=now,
    )
    assert "next_boundary" in l4 and l4["next_boundary"]
    assert datetime.fromisoformat(l4["next_boundary"]) > now




# ── Valens 同座顺移规则 ──────────────────────────────────────────────────
# 精神点与福点同落一座时，释放精神点要先沿黄道顺移一宫；福点不动。
# Brennan 逐字原话（The Astrology Podcast ep.192，已对全文 grep 核对）：
#   "if the Lot of Spirit and Lot of Fortune fall in the same sign, then for the
#    purpose of zodiacal releasing, you want to move the Lot of Spirit forward
#    one sign in zodiacal order... and you leave the Lot of Fortune in the natal
#    sign that it's in"

def test_spirit_shift_only_when_lots_share_a_sign():
    assert zr._spirit_needs_shift(10.0, 25.0) is True      # 同在白羊
    assert zr._spirit_needs_shift(10.0, 35.0) is False     # 白羊 / 金牛
    assert zr._spirit_needs_shift(355.0, 5.0) is False     # 双鱼 / 白羊（跨 0°）
    assert zr._spirit_needs_shift(350.0, 358.0) is True    # 同在双鱼


def test_shift_moves_start_one_sign_and_leaves_fortune_alone(monkeypatch):
    """顺移只作用于精神点，福点留在本命星座。"""
    def fake_compute(*a, **k):
        # 两点同落天蝎（天蝎 = idx 7，210°–240°）
        return {"sect": "日生人", "fof_lon": 237.0, "pos_lon": 221.0}

    monkeypatch.setattr(zr, "compute", fake_compute)
    body = {"name": "x", "year": 1972, "month": 10, "day": 8,
            "hour": 9, "minute": 15, "city": "北京",
            "lat": 39.9042, "lng": 116.4074, "tz": "Asia/Shanghai"}
    r = zr.calculate_zodiacal_releasing(dict(body), max_level=2)

    assert r["spirit_shifted"] is True
    sp, fo = r["lots"]["spirit"], r["lots"]["fortune"]
    # 本命星座都是天蝎，但起释星座不同
    assert sp["lot_sign"] == "天蝎座" and fo["lot_sign"] == "天蝎座"
    assert sp["releasing_sign"] == "射手座", "精神点顺移一宫"
    assert fo["releasing_sign"] == "天蝎座", "福点不动"
    assert sp["shifted"] is True and fo["shifted"] is False
    # L1 首格随之不同
    assert sp["periods"][0]["sign_cn"] == "射手座"
    assert fo["periods"][0]["sign_cn"] == "天蝎座"
    # 两条时间轴不再逐节点重合（不顺移时会完全一样）
    sp_dates = [t["loosing_of_bond"]["start"] for t in sp["turning_points"]]
    fo_dates = [t["loosing_of_bond"]["start"] for t in fo["turning_points"]]
    assert sp_dates and fo_dates and sp_dates != fo_dates


def test_no_shift_when_lots_differ(monkeypatch):
    def fake_compute(*a, **k):
        return {"sect": "日生人", "fof_lon": 10.5, "pos_lon": 250.25}

    monkeypatch.setattr(zr, "compute", fake_compute)
    r = zr.calculate_zodiacal_releasing(
        {"name": "x", "year": 1990, "month": 4, "day": 15, "hour": 18,
         "minute": 0, "city": "北京", "lat": 39.9, "lng": 116.4,
         "tz": "Asia/Shanghai"}, max_level=2)
    assert r["spirit_shifted"] is False
    for k in ("spirit", "fortune"):
        lot = r["lots"][k]
        assert lot["shifted"] is False
        assert lot["releasing_sign"] == lot["lot_sign"]


def test_john_kerry_regression_for_the_shift_rule():
    """Brennan 的实证案例：克里 2004 年 8 月的解缚只在顺移后才出现。

    John Kerry 1943-12-11 08:03 MWT Aurora, Colorado（Astro-Databank AA）。
    满月出生，福点与精神点同落双子座。2004 年他是民主党总统候选人。
    顺移后精神点解缚 2004-08-22，跳入双鱼——双鱼相对福点双子正是第 10 位，
    名望角宫。不顺移则 2004 年无解缚（最近的在 2005-08-17 与 1980-12-26）。
    """
    body = dict(name="Kerry", year=1943, month=12, day=11, hour=8, minute=3,
                city="Denver", lat=39.7294, lng=-104.8319, tz=-7.0)
    r = zr.calculate_zodiacal_releasing(dict(body), max_level=2, capricorn_years=27)
    assert r["spirit_shifted"] is True
    sp = r["lots"]["spirit"]
    assert sp["lot_sign"] == "双子座" and sp["releasing_sign"] == "巨蟹座"
    hits = [t for t in sp["turning_points"]
            if t["loosing_of_bond"]["start"] == "2004-08-22"]
    assert len(hits) == 1, "顺移后应在 2004-08-22 解缚"
    t = hits[0]
    assert t["from_sign_cn"] == "处女座" and t["to_sign_cn"] == "双鱼座"
    # 跳入星座相对福点是第 10 位 → 高峰
    assert zr._peak_kind(zr._Sign(11), zr._Sign(2)) == "peak"

    # 不顺移的对照：2004 年没有解缚
    _n, birth, fof, pos, _s = zr._resolve_calculation_context(dict(body))
    end = birth + timedelta(days=zr.LIFESPAN_AGE_YEARS * zr._CIVIL_YEAR_DAYS)
    plain = zr._compute_releasing(
        pos, birth, 2, 360.0, 27, end,
        fortune_sign=zr._Sign(int(fof % 360 // 30)), shift_start=False)
    starts = [t["loosing_of_bond"]["start"] for t in zr._turning_points(plain, birth)]
    assert not any(s.startswith("2004") for s in starts), \
        f"不顺移时 2004 年不应有解缚，实得 {starts}"


def test_lazy_l4_uses_the_same_shift_as_the_full_tree():
    """按需加载的 L4 必须同口径顺移，否则会与上面的 L3 错开一宫。"""
    body = dict(name="Kerry", year=1943, month=12, day=11, hour=8, minute=3,
                city="Denver", lat=39.7294, lng=-104.8319, tz=-7.0)
    full = zr.calculate_zodiacal_releasing(dict(body), max_level=3, capricorn_years=27)
    l3 = None
    for l1 in full["lots"]["spirit"]["periods"]:
        for l2 in l1["children"]:
            for node in l2["children"]:
                if node["is_current"]:
                    l3 = node
    assert l3 is not None
    l4 = zr.calculate_zodiacal_releasing_l4(
        dict(body), lot="spirit", parent_start=l3["start"], parent_sign=l3["sign"])
    assert l4["periods"], "应能细分出 L4"
    assert l4["periods"][0]["sign_cn"] == l3["sign_cn"], "L4 首格应从父级星座起"
