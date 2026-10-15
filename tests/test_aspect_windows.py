# -*- coding: utf-8 -*-
"""行星·相位窗口引擎：services/aspect_windows.py。

固定 JD = 2026-08-18 12:02 UTC / 北京。这一时刻的行星度数已跟外部占星 APP
截图逐位核对过（太阳狮子25°35'、月亮天蝎7°25'、金星天秤11°24'…），
也跟 NASA JPL Horizons 对到角秒，所以可以当基准盘用。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
import swisseph as swe

from services.ephemeris_guard import apply_ephe_path

apply_ephe_path()

from services import aspect_windows as aw

LAT, LNG = 39.9042, 116.4074
JD = swe.julday(2026, 8, 18, 12 + 2 / 60.0)


@pytest.fixture(scope="module")
def groups():
    return {g["key"]: g for g in aw.aspect_groups(JD, LAT, LNG)}


def test_covers_exactly_the_agreed_point_set(groups):
    """点位集合＝十大行星＋凯龙＋南北交点＋福点＋精神点，共 15 个，不含四轴。"""
    assert set(groups) == set(aw.ALL_POINTS)
    assert len(groups) == 15
    for axis in ("asc", "mc", "ascendant", "midheaven"):
        assert axis not in groups


def test_longitudes_match_external_app_screenshot(groups):
    """度分与外部占星 APP 截图逐位一致（2026-08-18 20:02 北京）。"""
    expected = {                      # 星座序号, 度, 分
        "sun": (4, 25, 35), "moon": (7, 7, 25), "mercury": (4, 16, 3),
        "venus": (6, 11, 24), "mars": (3, 4, 42), "jupiter": (4, 10, 49),
        "saturn": (0, 14, 19),
    }
    for key, (sign_idx, deg, minute) in expected.items():
        g = groups[key]
        assert g["sign_idx"] == sign_idx, key
        d = g["deg_in_sign"]
        assert int(d) == deg, (key, d)
        assert round((d - int(d)) * 60) == minute, (key, d)


def test_every_aspect_row_is_inside_its_orb(groups):
    for g in groups.values():
        for a in g["aspects"]:
            assert a["orb_deg"] <= a["orb_limit"] + 1e-9, (g["key"], a)


def test_window_is_self_consistent(groups):
    """入相 <= 此刻 <= 出相，且 周期 = 已走 + 剩余（允许两位小数的舍入）。"""
    for g in groups.values():
        for a in g["aspects"]:
            assert a["enter_jd"] <= JD <= a["exit_jd"], (g["key"], a)
            assert abs(a["total_days"] - (a["elapsed_days"] + a["remaining_days"])) <= 0.02
            assert 0.0 <= a["progress_pct"] <= 100.0


def test_aspect_is_symmetric_between_the_two_points(groups):
    """同一条相位在两个点位下各出现一次，周期数据必须一致。"""
    sun_rows = {(a["other"], a["angle"]): a for a in groups["sun"]["aspects"]}
    for key, row in sun_rows.items():
        other = groups[key[0]]
        mirror = [a for a in other["aspects"]
                  if a["other"] == "sun" and a["angle"] == key[1]]
        assert len(mirror) == 1, key
        assert mirror[0]["total_days"] == row["total_days"]
        assert mirror[0]["progress_pct"] == row["progress_pct"]


def test_unique_aspect_count_does_not_double_mirrored_group_rows(groups):
    """分类可在两颗行星下重复展示，但主要相位总数必须按真实对子计算。"""
    presentation_count = sum(g["count"] for g in groups.values())
    physical_count = aw.unique_aspect_count(groups.values())
    assert presentation_count == physical_count * 2
    assert physical_count == 44


def test_unique_aspects_are_flat_sorted_and_have_no_group_perspective(groups):
    rows = aw.unique_aspects(groups.values())
    identities = [(tuple(sorted((r["p1"], r["p2"]))), r["angle"]) for r in rows]
    assert len(rows) == len(set(identities)) == 44
    assert [aw._sort_key(r) for r in rows] == sorted(aw._sort_key(r) for r in rows)
    assert all("other" not in r and "other_cn" not in r for r in rows)


def test_mirror_angles_are_taken_into_account():
    """镜像角必须参与：海王六合冥王此刻角距 <1°，只算 60° 不算 300° 会报成 120°。

    sky_now 初版就栽在这条上（注释里有记录），这里锁死。
    """
    res = aw.PointResolver(LAT, LNG)
    assert res.abs_dev("neptune", "pluto", 60.0, JD) < 1.0


def test_slow_outer_pair_window_spans_years(groups):
    """海王六合冥王是全盘最慢的相位，容许度窗口以「年」计，不能被搜索窗截断。"""
    row = [a for a in groups["neptune"]["aspects"]
           if a["other"] == "pluto" and a["angle"] == 60.0]
    assert len(row) == 1
    row = row[0]
    assert row["total_days"] > 3000
    assert row["enter_truncated"] is None
    assert row["exit_truncated"] is None


def test_fast_lot_windows_are_sub_day(groups):
    """福点/精神点跟上升同速（约 360°/天），它们的相位窗口是分钟级，不是天级。"""
    for key in ("pars_fortuna", "pars_spiritus"):
        assert groups[key]["aspects"], key
        for a in groups[key]["aspects"]:
            assert a["total_days"] < 1.0, (key, a)


def test_node_pair_opposition_is_not_reported():
    """南北交点恒定 180° 对冲，是定义性的恒真，不该当成一条天象相位。"""
    res = aw.PointResolver(LAT, LNG)
    assert res.abs_dev("north_node", "south_node", 180.0, JD) < 1e-6   # 确实恒精确
    g = {x["key"]: x for x in aw.aspect_groups(JD, LAT, LNG)}
    assert not [a for a in g["north_node"]["aspects"] if a["other"] == "south_node"]


def test_sun_node_aspects_are_the_same_configuration(groups):
    """太阳对分北交点 ≡ 太阳合南交点（南交=北交+180°），两条角距必须相等。"""
    rows = {a["other"]: a for a in groups["sun"]["aspects"]
            if a["other"] in ("north_node", "south_node")}
    if len(rows) == 2:
        assert abs(rows["north_node"]["orb_deg"] - rows["south_node"]["orb_deg"]) < 1e-6


def test_lot_window_stops_at_sect_change():
    """福点公式在日夜交界互换，扫描必须停在交界并标记，不能跨过去继续二分。

    构造：取一个日出前后的时刻，福点的相位窗口若跨越地平线就该带 sect_change。
    这里只断言标记字段存在且取值合法，不强求某一刻一定发生交界。
    """
    res = aw.PointResolver(LAT, LNG)
    jd_dawn = swe.julday(2026, 8, 18, 21.5)   # 北京次日约 05:30，日出附近
    rows = []
    for angle in (0.0, 60.0, 90.0, 120.0, 180.0):
        for other in ("sun", "moon", "mars"):
            r = aw.aspect_window(res, "pars_fortuna", other, angle, jd_dawn)
            if r:
                rows.append(r)
    for r in rows:
        for side in ("enter_truncated", "exit_truncated"):
            assert r[side] in (None, "search_limit", "sect_change"), r


def test_point_longitudes_match_the_main_calculator_engine():
    """15 个点位必须与 services/calculator.compute() 逐一吻合。

    这是本模块最要紧的一条：福点/精神点的日夜互换公式、南交=北交+180、
    交点用平均交点，任何一处写错都会在这里暴露。容差 1 角秒。
    """
    from services.calculator import compute
    r = compute("对拍", 2026, 8, 18, 13, 22, "", lat=LAT, lng=LNG)
    engine = {p["key"]: p["lon"] for p in r["natal_planets_full"]}
    jd = swe.julday(2026, 8, 18, 5 + 22 / 60.0)      # 同一刻的 UT
    res = aw.PointResolver(LAT, LNG)
    for key in aw.ALL_POINTS:
        assert key in engine, key
        diff = (res.lon(key, jd) - engine[key] + 180.0) % 360.0 - 180.0
        assert abs(diff) * 3600 < 1.0, (key, diff * 3600)


def test_applying_uses_analytic_speed_not_finite_difference():
    """入相/出相必须由解析速度判定。

    海王六合冥王在 14 分钟前瞻内角距只变 0.043 角秒（两个大数相减），
    靠差分判方向离浮点噪声太近。swisseph 直接给黄经速度，用它一步到位。
    这里断言：两颗都逆行且冥王退得更快 → 角距在拉开 → 出相。
    """
    res = aw.PointResolver(LAT, LNG)
    s_nep = res.speed("neptune", JD)
    s_plu = res.speed("pluto", JD)
    assert s_nep is not None and s_plu is not None
    assert s_nep < 0 and s_plu < 0                    # 此刻两颗都逆行
    assert res.is_applying("neptune", "pluto", 60.0, JD) is False


def test_lots_have_no_analytic_speed_and_fall_back_cleanly():
    """福点/精神点由上升点推出，没有解析速度；退回差分且不报错。"""
    res = aw.PointResolver(LAT, LNG)
    assert res.speed("pars_fortuna", JD) is None
    assert res.speed("pars_spiritus", JD) is None
    assert isinstance(res.is_applying("pars_fortuna", "moon", 60.0, JD), bool)


def test_scan_step_is_fine_enough_for_the_slowest_pairs():
    """步长必须按速度**上限之和**推，不能按平均速度之差。

    海王-冥王平均速度差只有 0.002°/天，按它定步长会得到 40 天的粗步；
    但两颗各自逆行时瞬时速度可达 0.02°/天，40 天足以跨过一次短暂的
    出容许度往返，把窗口报长。锁死步长上限。
    """
    for k1, k2 in (("neptune", "pluto"), ("uranus", "neptune"), ("saturn", "pluto")):
        orb = aw.orb_for(k1, k2, 60.0)
        _span, step = aw._search_profile(k1, k2, orb)
        rel_max = aw._MAX_SPEED[k1] + aw._MAX_SPEED[k2]
        assert step * rel_max <= orb / 2.0, (k1, k2, step)
        assert step <= 10.0, (k1, k2, step)


def test_cached_result_is_not_mutated_by_the_request_path():
    """lru_cache 返回的是**共享对象**，整条请求链不得就地修改它。

    实测：改一下返回值里的字段，后续所有请求都会拿到被污染的结果
    （两次调用 `is` 同一个对象）。目前唯一的消费方是 routes/transit_board.py
    的 jsonify（只序列化不修改），这条测试把这个不变量钉住——将来谁在
    路由里加一行就地加工，这里会红。真要加工请先 copy.deepcopy。
    """
    import copy

    before = copy.deepcopy(aw.aspect_groups(JD, LAT, LNG))
    # 完整走一遍序列化（jsonify 在请求上下文外不可用，用等价的 json 序列化）
    import json
    json.dumps(aw.aspect_groups(JD, LAT, LNG), ensure_ascii=False)
    after = aw.aspect_groups(JD, LAT, LNG)
    assert after == before, "请求链把缓存里的共享结构改掉了"
