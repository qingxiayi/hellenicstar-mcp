import pytest
import swisseph as swe
from services.lunar_return import compute_lunar_return_full, find_lunar_return_jd

def test_lunar_return_emma_watson():
    # Emma Watson 1990-04-15 18:00 Paris (lat=48.8566, lng=2.3522)
    res = compute_lunar_return_full(
        birth_year=1990, birth_month=4, birth_day=15, birth_hour=18, birth_minute=0,
        birth_lat=48.8566, birth_lng=2.3522,
        target_year=2026, target_month=4,
        residence_lat=48.8566, residence_lng=2.3522, residence_tz="Europe/Paris", residence_city="巴黎",
        house_system="placidus"
    )
    assert res["house_system"] == "placidus"
    # 月亮返照时刻：月亮经度与本命必须绝对一致（误差 < 1e-7 度）
    natal_moon = res["natal"]["planets"]["moon"]["longitude"]
    lr_moon = res["single"]["planets"]["moon"]["longitude"]
    assert abs(natal_moon - lr_moon) < 1e-7
    # 2026年4月的月亮返照在 2026-04-08
    assert res["lr_utc"].startswith("2026-04-08")
    # 检查单盘维度齐备
    assert "planets" in res["single"]
    assert "angles" in res["single"]
    assert "houses" in res["single"]
    assert "aspects" in res["single"]
    assert "jones_pattern" in res["single"]
    assert "mean_north_node" in res["single"]["special_points"]
    assert res["single"]["lunation_phase"]["phase_name"] in (
        "新月", "娥眉月", "上弦月", "盈凸月", "满月", "亏凸月", "下弦月", "残月")
    # 检查叠加维度齐备
    assert "lr_planets_in_natal_houses" in res["overlay"]
    assert "natal_planets_in_lr_houses" in res["overlay"]
    assert "cross_aspects" in res["overlay"]
    assert "focus" in res
    assert res["focus"]["asc_ruler"]["planet"] in res["single"]["planets"]

def test_lunar_return_whole_sign():
    res = compute_lunar_return_full(
        birth_year=1990, birth_month=4, birth_day=15, birth_hour=18, birth_minute=0,
        birth_lat=48.8566, birth_lng=2.3522,
        target_year=2026, target_month=4,
        residence_lat=48.8566, residence_lng=2.3522, residence_tz="Europe/Paris", residence_city="巴黎",
        house_system="whole_sign"
    )
    assert res["house_system"] == "whole_sign"


def test_two_returns_in_one_month_select_nearest_day():
    target = swe.calc_ut(swe.julday(2026, 4, 1, 12), swe.MOON)[0][0]
    first = find_lunar_return_jd(target, 2026, 4, target_day=1)
    second = find_lunar_return_jd(target, 2026, 4, target_day=30)
    assert second - first > 25
    assert swe.revjul(first)[:2] == (2026, 4)
    assert swe.revjul(second)[:2] == (2026, 4)
    with pytest.raises(ValueError):
        find_lunar_return_jd(target, 2026, 4, target_day=31)


def test_return_month_uses_residence_civil_calendar():
    target = swe.calc_ut(swe.julday(2026, 4, 30, 18), swe.MOON)[0][0]
    jd = find_lunar_return_jd(target, 2026, 5, target_day=1,
                              tz_iana="Pacific/Kiritimati")
    assert swe.revjul(jd)[:3] == (2026, 4, 30)


def test_lunar_chart_outlines_zodiac_without_rewriting_other_text(monkeypatch):
    from services import mcp_compat_utils as calculate
    from services.mcp_extended import _render
    captured = []
    monkeypatch.setattr(calculate, "_svg_to_png", lambda svg, size: captured.append(svg) or b"png")
    assert _render({}, [i * 30 for i in range(12)], 0, 90, [],
                   system="whole_sign", outline_zodiac=True) == b"png"
    assert captured[0].count('class="zodiac-outline"') >= 12
    assert "♈</text>" not in captured[0]
    assert "chart-house" in captured[0]
