"""合刑冲矩阵 + 双盘载荷的回归测试。

矩阵覆盖 10 大行星 + 凯龙 + 南北交 + 福点 + 四轴的双向合/刑/冲；
双盘载荷给出本命内圈与太阳弧外圈（同一 arc 旋转）。
"""

from types import MappingProxyType

import pytest

import services.solar_arc_compute as solar_arc_compute
from services.forecast_natal import (
    ForecastNatalSnapshot,
    ForecastPoint,
    snapshot_from_engine_data,
)


def _snapshot(planets, axes, cusps=()):
    return ForecastNatalSnapshot(
        context=None,
        birth_jd_ut=2451545.0,
        planets=MappingProxyType(planets),
        axes=MappingProxyType(axes),
        natal_engine_version="test",
        cusps=tuple(cusps),
    )


def _use_arc_as_age(monkeypatch):
    """把所求弧直接当作事件年龄（与方向组测试同款替身）。"""
    monkeypatch.setattr(
        solar_arc_compute,
        "solve_age",
        lambda _jd, _sun, required_arc, age_from, age_to: (
            required_arc if age_from <= required_arc <= age_to else None
        ),
    )
    monkeypatch.setattr(
        solar_arc_compute,
        "sun_longitude",
        lambda _jd: 0.0,
    )


def _fifteen_points():
    """10 大行星 + 凯龙 + 南北交 + 福点，经度均匀铺满 360°。"""
    names = (
        "sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn",
        "uranus", "neptune", "pluto", "chiron", "north_node",
        "south_node", "fortuna",
    )
    return {
        name: ForecastPoint(longitude=idx * 24.0, house=(idx % 12) + 1)
        for idx, name in enumerate(names)
    }


def test_forecast_snapshot_carries_twelve_engine_cusps():
    class _Ctx:
        julian_day_ut = 2451545.0

    cusps = [(5.0 + index * 30.0) % 360.0 for index in range(12)]
    snapshot = snapshot_from_engine_data(_Ctx(), {
        "planets": {"sun": {"longitude": 10.0, "house": 1}},
        "special_points": {},
        "axes": {
            "ascendant": {"longitude": 5.0},
            "midheaven": {"longitude": 95.0},
            "descendant": {"longitude": 185.0},
            "imum_coeli": {"longitude": 275.0},
        },
        "houses": {"cusps": cusps},
    })

    assert snapshot.cusps == tuple(cusps)


def test_matrix_includes_fortune_and_axes(monkeypatch):
    """矩阵点集必须包含福点与四轴（用户核心诉求）。"""
    _use_arc_as_age(monkeypatch)
    snapshot = _snapshot(
        _fifteen_points(),
        {"asc": 5.0, "mc": 95.0, "dsc": 185.0, "ic": 275.0},
    )
    result = solar_arc_compute.compute_solar_arc_events(
        snapshot, 2000, 1, 1, 0, 0, age_to=80.0
    )
    matrix = result["matrix"]
    assert matrix
    sa_points = {item["sa_point"] for item in matrix}
    natal_points = {item["natal_point"] for item in matrix}
    for key in ("fortuna", "asc", "mc", "dsc", "ic"):
        assert key in sa_points
        assert key in natal_points


def test_matrix_aspects_are_conjunction_square_opposition(monkeypatch):
    _use_arc_as_age(monkeypatch)
    snapshot = _snapshot(
        _fifteen_points(),
        {"asc": 5.0, "mc": 95.0, "dsc": 185.0, "ic": 275.0},
    )
    result = solar_arc_compute.compute_solar_arc_events(
        snapshot, 2000, 1, 1, 0, 0, age_to=80.0
    )
    labels = {item["aspect"] for item in result["matrix"]}
    assert labels == {"合", "刑", "冲"}


def test_matrix_age_equals_required_arc_when_solve_is_identity(monkeypatch):
    """替身下事件年龄 = 所需弧；合刑冲的角度也如实保留。"""
    _use_arc_as_age(monkeypatch)
    snapshot = _snapshot(
        _fifteen_points(),
        {"asc": 5.0, "mc": 95.0, "dsc": 185.0, "ic": 275.0},
    )
    result = solar_arc_compute.compute_solar_arc_events(
        snapshot, 2000, 1, 1, 0, 0, age_to=80.0
    )
    for item in result["matrix"]:
        sa = snapshot.planets[item["sa_point"]].longitude if item["sa_point"] in snapshot.planets else snapshot.axes[item["sa_point"]]
        natal = snapshot.planets[item["natal_point"]].longitude if item["natal_point"] in snapshot.planets else snapshot.axes[item["natal_point"]]
        required = (natal + item["angle"] - sa) % 360.0
        assert abs(item["age"] - required) < 1e-9


def test_bi_wheel_carries_natal_frame_and_rotated_solar_arc(monkeypatch):
    """双盘载荷：内圈本命框架（cusps/asc/mc）+ 外圈 SA 行星与 SA 四轴
    都按同一 arc 相对本命旋转。"""
    _use_arc_as_age(monkeypatch)
    natal_cusps = tuple((5.0 + index * 30.0) % 360.0 for index in range(12))
    snapshot = _snapshot(
        _fifteen_points(),
        {"asc": 5.0, "mc": 95.0, "dsc": 185.0, "ic": 275.0},
        natal_cusps,
    )
    monkeypatch.setattr(solar_arc_compute, "sun_longitude", lambda _jd: 40.0)
    result = solar_arc_compute.compute_solar_arc_events(
        snapshot, 2000, 1, 1, 0, 0, age_to=80.0
    )
    bw = result["bi_wheel"]
    assert bw["natal"]["asc_lon"] == 5.0
    assert bw["natal"]["mc_lon"] == 95.0
    sa_planets = bw["solar_arc"]["planets"]
    sa_angles = bw["solar_arc"]["angles"]
    assert "fortuna" in sa_planets
    arc = bw["solar_arc"]["arc"]
    assert abs(sa_angles["asc"] - (5.0 + arc) % 360.0) < 1e-9
    assert abs(sa_planets["sun"]["lon"] - (0.0 + arc) % 360.0) < 1e-9
    assert bw["natal"]["cusps"] == list(natal_cusps)
    assert bw["solar_arc"]["cusps"] == [
        (cusp + arc) % 360.0 for cusp in natal_cusps
    ]
    assert bw["cross_aspects"], "双盘中心必须有当前跨盘相位线数据"
    assert bw["degree_contacts"], "合相必须有连接内外圈的接触线数据"


def test_biwheel_aspect_lines_include_fortune_nodes_chiron_and_axes(monkeypatch):
    """太阳弧双盘相位线与事件矩阵使用同一个完整 18 点集。"""
    _use_arc_as_age(monkeypatch)  # arc=0，18 个点都与自己的本命位置精确合相
    snapshot = _snapshot(
        _fifteen_points(),
        {"asc": 5.0, "mc": 95.0, "dsc": 185.0, "ic": 275.0},
    )
    bw = solar_arc_compute.compute_solar_arc_wheel(snapshot, 40.0)
    self_conjunctions = {
        item["sr_planet"]
        for item in bw["cross_aspects"]
        if item["angle"] == 0.0 and item["sr_planet"] == item["natal_planet"]
    }
    assert self_conjunctions == {
        "sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn",
        "uranus", "neptune", "pluto", "chiron", "north_node", "south_node",
        "fortuna", "asc", "mc", "dsc", "ic",
    }
    assert len([
        item for item in bw["degree_contacts"]
        if item["sr_planet"] == item["natal_point"]
    ]) == 18


def test_lightweight_wheel_uses_the_exact_selected_age(monkeypatch):
    """时间步进接口必须按新年龄重新求弧，不能重复返回首次加载的固定双盘。"""
    snapshot = _snapshot(
        _fifteen_points(),
        {"asc": 5.0, "mc": 95.0, "dsc": 185.0, "ic": 275.0},
    )
    monkeypatch.setattr(
        solar_arc_compute,
        "sun_longitude",
        lambda jd: (jd - snapshot.birth_jd_ut) % 360.0,
    )
    first = solar_arc_compute.compute_solar_arc_wheel(snapshot, 20.0)
    second = solar_arc_compute.compute_solar_arc_wheel(snapshot, 20.5)
    assert first["solar_arc"]["arc"] == 20.0
    assert second["solar_arc"]["arc"] == 20.5
    assert first["solar_arc"]["planets"]["sun"]["lon"] != second["solar_arc"]["planets"]["sun"]["lon"]
    assert first["natal"] == second["natal"]


@pytest.mark.parametrize("age", [-0.01, 80.01, float("nan"), "bad"])
def test_lightweight_wheel_rejects_age_outside_supported_range(age):
    snapshot = _snapshot(
        _fifteen_points(),
        {"asc": 5.0, "mc": 95.0, "dsc": 185.0, "ic": 275.0},
    )
    with pytest.raises(ValueError):
        solar_arc_compute.compute_solar_arc_wheel(snapshot, age)


def test_wheel_cross_aspects_carry_applying_direction(monkeypatch):
    """太阳弧跨盘相位必须带入相/出相，且方向与实际演化一致。

    本命卡片一直有这个标记，双盘却没有。太阳弧的判定比本命简单：整张盘以
    同一个弧匀速前推、本命盘不动，所以把弧推进一小步重算容许度即可——
    收窄是入相，拉开是出相。这里用「把年龄真的往后推一点」来交叉验证方向，
    而不是重复实现同一套公式自证。
    """
    snapshot = _snapshot(
        _fifteen_points(),
        {"asc": 5.0, "mc": 95.0, "dsc": 185.0, "ic": 275.0},
    )
    now = solar_arc_compute.compute_solar_arc_wheel(snapshot, 30.0)
    later = solar_arc_compute.compute_solar_arc_wheel(snapshot, 30.05)

    rows = now["cross_aspects"]
    assert rows, "样例盘应当有跨盘相位"
    assert all("applying" in row for row in rows)

    later_orbs = {
        (row["sr_planet"], row["natal_planet"], row["angle"]): row["orb"]
        for row in later["cross_aspects"]
    }
    checked = 0
    for row in rows:
        if row["applying"] is None:
            continue
        key = (row["sr_planet"], row["natal_planet"], row["angle"])
        if key not in later_orbs:
            continue
        checked += 1
        shrinking = later_orbs[key] < row["orb"]
        assert shrinking == row["applying"], (
            f"{key} 标记为{'入相' if row['applying'] else '出相'}，"
            f"但容许度 {row['orb']:.4f} → {later_orbs[key]:.4f}"
        )
    assert checked >= 5, f"有效校验样本过少：{checked}"

    # 合相同时进入 degree_contacts，两处方向必须一致。
    contact_map = {
        (row["sr_planet"], row["natal_point"]): row.get("applying")
        for row in now["degree_contacts"]
    }
    for row in rows:
        if row["angle"] != 0.0:
            continue
        key = (row["sr_planet"], row["natal_planet"])
        if key in contact_map:
            assert contact_map[key] == row["applying"]
