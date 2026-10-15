import pytest
import swisseph as swe
from services.mcp_natal import _compute_source
from services.relocation_chart import compute_relocation_chart_full
from services.mcp_extended import relocation_data, render_relocation_png
from services.mcp_validation import validate_output


def test_relocation_emma_watson_new_york_benchmark():
    # Emma Watson: 1990-04-15 18:00 Paris (UT 16:00, lat=48.85341, lng=2.3488)
    natal = _compute_source(
        year=1990, month=4, day=15, hour=18, minute=0,
        location_id="gn:2988507", house_system="placidus", fold=None
    )

    # Relocation to New York (lat=40.7128, lng=-74.0060)
    reloc = compute_relocation_chart_full(
        natal,
        reloc_lat=40.7128,
        reloc_lng=-74.0060,
        reloc_location_id="gn:5128581",
        reloc_name="New York",
        reloc_tz="America/New_York",
        house_system="placidus"
    )

    # 1. 绝对不变量：行星黄道经度与本命必须 100% 一致 (0 误差)
    natal_planets = {p["key"]: p for p in natal.get("natal_planets_full", [])}
    reloc_planets = {p["key"]: p for p in reloc["planets"]}
    for k in ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"):
        natal_lon = natal_planets[k]["lon"]
        reloc_lon = reloc_planets[k]["longitude"]
        assert abs(natal_lon - reloc_lon) < 1e-4

    # 2. Astro-Seek Relocation Benchmark (Emma Watson in New York):
    # Relocated ASC: 116.63° (Cancer 26°38')
    # Relocated MC: 10.39° (Aries 10°23')
    axes = reloc["axes"]
    assert abs(axes["ascendant"]["longitude"] - 116.635) < 0.02
    assert axes["ascendant"]["sign"] == "巨蟹座"
    assert abs(axes["midheaven"]["longitude"] - 10.39) < 0.02
    assert axes["midheaven"]["sign"] == "白羊座"

    # 3. 四轴偏移量
    shifts = reloc["angular_shifts"]
    assert abs(shifts["delta_asc_deg"] - (-60.38)) < 0.1
    assert abs(shifts["delta_mc_deg"] - (-75.85)) < 0.1

    # 4. 宫位变动
    changed = [p for p in reloc["planets"] if p["house_changed"]]
    assert len(changed) >= 8


def test_relocation_whole_sign_houses_and_natal_comparison():
    natal = _compute_source(year=1990, month=4, day=15, hour=18, minute=0,
                            location_id="gn:2988507", house_system="whole_sign", fold=None)
    reloc = compute_relocation_chart_full(natal, 40.7128, -74.0060,
                                          "gn:5128581", house_system="whole_sign")
    natal_houses = {p["key"]: p["house_w"] for p in natal["natal_planets_full"]}
    asc_sign = int(reloc["axes"]["ascendant"]["longitude"] // 30)
    for planet in reloc["planets"]:
        expected_house = (int(planet["longitude"] // 30) - asc_sign) % 12 + 1
        assert planet["relocated_house"] == expected_house
        if planet["key"] in natal_houses:
            assert planet["natal_house"] == natal_houses[planet["key"]]
            assert planet["house_changed"] == (natal_houses[planet["key"]] != expected_house)
    sun = next(p for p in reloc["planets"] if p["key"] == "sun")
    moon = next(p for p in reloc["planets"] if p["key"] == "moon")
    assert sun["relocated_house"] == 10
    assert moon["natal_house"] == 4


def test_relocation_mcp_data_and_wheel():
    data = relocation_data(
        year=1990, month=4, day=15, hour=18, minute=0,
        location_id="gn:2988507", relocation_location_id="gn:5128581",
        house_system="placidus"
    )
    assert data["status"] == "ok"
    assert "relocation_location" in data
    assert "angular_shifts" in data
    assert "axes" in data
    assert "house_cusps" in data
    assert "planets" in data
    assert "aspects" in data

    # 渲染图表
    info, png = render_relocation_png(
        year=1990, month=4, day=15, hour=18, minute=0,
        location_id="gn:2988507", relocation_location_id="gn:5128581",
        house_system="placidus"
    )
    assert info["status"] == "ok"
    assert png is not None
    assert png.startswith(b"\x89PNG")


def test_relocation_quality_rejects_wrong_house_change():
    args = dict(year=1990, month=4, day=15, hour=18, minute=0,
                location_id="gn:2988507", relocation_location_id="gn:5128581",
                house_system="whole_sign")
    data = relocation_data(**args)
    assert validate_output("calculate_relocation_chart", data, args) == []
    data["planets"][0]["house_changed"] = not data["planets"][0]["house_changed"]
    assert validate_output("calculate_relocation_chart", data, args) == [
        {"path": "/planets/0/house_changed", "rule": "house_change_matches_houses"}
    ]

