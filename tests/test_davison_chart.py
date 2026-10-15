import pytest
import swisseph as swe
from services.davison_chart import (
    compute_davison_space_time_midpoint,
    compute_davison_chart_full,
)
from services.mcp_extended import davison_data, render_davison_png
from services.mcp_natal import _compute_source
from services.mcp_validation import validate_output


def test_davison_space_time_midpoint_calculation():
    # Case: Charles & Diana
    # Charles: 1948-11-14 21:14 GMT, London (51.5074 N, 0.1278 W)
    # Diana: 1961-07-01 18:45 GMT, Sandringham (52.8300 N, 0.5100 E)
    jd_c = swe.julday(1948, 11, 14, 21.0 + 14.0 / 60.0)
    lat_c, lon_c = 51.5074, -0.1278

    jd_d = swe.julday(1961, 7, 1, 18.0 + 45.0 / 60.0)
    lat_d, lon_d = 52.8300, 0.5100

    mid = compute_davison_space_time_midpoint(jd_c, lat_c, lon_c, jd_d, lat_d, lon_d)
    # Expected midpoint UT: 1955-03-09 19:59:30
    assert mid["year"] == 1955
    assert mid["month"] == 3
    assert mid["day"] == 9
    assert mid["hour"] == 19
    assert mid["minute"] == 59
    assert abs(mid["second"] - 30.0) < 0.1
    # Expected coordinates: ~52.1687 N, 0.1911 E
    assert abs(mid["lat"] - 52.1687) < 0.01
    assert abs(mid["lng"] - 0.1911) < 0.01


def test_davison_uncorrected_midpoint_uses_mean_geographic_longitude():
    jd = swe.julday(2000, 1, 1, 12)
    midpoint = compute_davison_space_time_midpoint(jd, 10, 170, jd, 20, -170)
    assert midpoint["lat"] == 15
    assert midpoint["lng"] == 0


def test_davison_whole_sign_houses_match_natal_engine():
    natal = _compute_source(year=1990, month=4, day=15, hour=18, minute=0,
                            location_id="gn:2988507", house_system="whole_sign", fold=None)
    context = natal["birth_context"]
    jd = swe.julday(1990, 4, 15, 16)
    result = compute_davison_chart_full(jd, context["lat"], context["lng"],
                                        jd, context["lat"], context["lng"],
                                        house_system="whole_sign")
    expected = {p["key"]: p["house_w"] for p in natal["natal_planets_full"]}
    for key, planet in result["chart"]["planets"].items():
        assert planet["house"] == expected[key]
    assert result["chart"]["planets"]["sun"]["house"] == 8


def test_davison_chart_charles_and_diana_benchmark():
    jd_c = swe.julday(1948, 11, 14, 21.0 + 14.0 / 60.0)
    lat_c, lon_c = 51.5074, -0.1278

    jd_d = swe.julday(1961, 7, 1, 18.0 + 45.0 / 60.0)
    lat_d, lon_d = 52.8300, 0.5100

    res = compute_davison_chart_full(jd_c, lat_c, lon_c, jd_d, lat_d, lon_d, house_system="placidus")

    chart = res["chart"]
    planets = chart["planets"]
    axes = chart["axes"]

    # Astro-Seek Benchmark for Charles & Diana Davison Chart:
    # Sun: 348.48° (Pisces 18°29')
    # Moon: 182.48° (Libra 2°29')
    # ASC: 191.74° (Libra 11°44')
    # MC: 105.48° (Cancer 15°29')
    assert abs(planets["sun"]["longitude"] - 348.47) < 0.02
    assert planets["sun"]["sign"] == "双鱼座"
    assert abs(planets["moon"]["longitude"] - 182.47) < 0.02
    assert planets["moon"]["sign"] == "天秤座"
    assert abs(axes["ascendant"]["longitude"] - 191.7344) < 0.02
    assert axes["ascendant"]["sign"] == "天秤座"
    assert abs(axes["midheaven"]["longitude"] - 105.47) < 0.02
    assert axes["midheaven"]["sign"] == "巨蟹座"

    # 十大行星齐全且有落宫
    for p in ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"):
        assert p in planets
        assert 1 <= planets[p]["house"] <= 12

    # 12 宫宫头与月相
    assert len(chart["house_cusps"]) == 12
    assert 1 <= chart["lunation_phase"]["phase_num"] <= 8
    assert len(res["aspects"]) > 0


def test_davison_mcp_data_and_wheel():
    p_a = dict(year=1990, month=4, day=15, hour=18, minute=0, location_id="gn:2988507")
    p_b = dict(year=1988, month=8, day=1, hour=9, minute=30, location_id="gn:2988507")

    data = davison_data(person_a=p_a, person_b=p_b, house_system="placidus")
    assert data["status"] == "ok"
    assert "a" in data["birth_context"] and "b" in data["birth_context"]
    assert "midpoint_space_time" in data
    assert "chart" in data
    assert "aspects" in data

    # 渲染图表
    info, png = render_davison_png(person_a=p_a, person_b=p_b, house_system="placidus")
    assert info["status"] == "ok"
    assert png is not None
    assert png.startswith(b"\x89PNG")


def test_davison_quality_rejects_wrong_whole_sign_house():
    person = dict(year=1990, month=4, day=15, hour=18, minute=0,
                  location_id="gn:2988507")
    data = davison_data(person_a=person, person_b=person, house_system="whole_sign")
    args = dict(person_a=person, person_b=person, house_system="whole_sign")
    assert validate_output("calculate_davison_chart", data, args) == []
    data["chart"]["planets"]["sun"]["house"] = 1
    assert validate_output("calculate_davison_chart", data, args) == [
        {"path": "/chart/planets/sun/house", "rule": "whole_sign_house_matches_sign"}
    ]



@pytest.mark.parametrize('month,expected_retrograde', [(4, False), (11, True)])
def test_davison_chiron_render_preserves_calculated_motion(monkeypatch, month, expected_retrograde):
    from services import mcp_extended as ext
    person = dict(year=1990, month=month, day=15, hour=18, minute=0,
                  location_id='gn:2988507')
    data = ext.davison_data(person_a=person, person_b=person, house_system='placidus')
    chiron = data['chart']['special_points']['chiron']
    assert chiron['retrograde'] is expected_retrograde
    captured = {}
    def render(planets, *args, **kwargs):
        captured.update(planets)
        return b'png-test-double'
    monkeypatch.setattr(ext, '_render', render)
    info, _ = ext.render_davison_png(person_a=person, person_b=person, house_system='placidus')
    assert info['status'] == 'ok'
    assert captured['chiron'] == {'lon': chiron['longitude'], 'retrograde': chiron['retrograde']}
