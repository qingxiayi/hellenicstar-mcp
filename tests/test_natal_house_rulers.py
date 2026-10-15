from services.natal_house_rulers import (
    HOUSE_CROSSES,
    MODERN_RULERS,
    TRADITIONAL_RULERS,
    build_house_ruler_chains,
    trace_ruler_chain,
)


def _planet(sign, house=1, retrograde=False):
    sign_index = ("Ari", "Tau", "Gem", "Can", "Leo", "Vir", "Lib", "Sco", "Sag", "Cap", "Aqu", "Pis").index(sign)
    return {
        "sign": sign,
        "sign_zh": sign,
        "longitude": sign_index * 30 + 10,
        "house": house,
        "retrograde": retrograde,
    }


def test_trace_stops_at_domicile_self_dispositor():
    planets = {
        "mars": _planet("Cap"),
        "saturn": _planet("Aqu", house=4, retrograde=True),
    }
    chain = trace_ruler_chain("mars", planets, 0, TRADITIONAL_RULERS)
    assert [node["planet"] for node in chain["nodes"]] == ["mars", "saturn"]
    assert chain["status"] == "self"
    assert chain["cycle_planets"] == ["saturn"]
    assert chain["nodes"][-1]["retrograde"] is True


def test_trace_detects_mutual_reception_without_infinite_recursion():
    planets = {
        "venus": _planet("Ari"),
        "mars": _planet("Tau"),
    }
    chain = trace_ruler_chain("venus", planets, 0, TRADITIONAL_RULERS)
    assert [node["planet"] for node in chain["nodes"]] == ["venus", "mars"]
    assert chain["status"] == "cycle"
    assert chain["cycle_start"] == 0
    assert chain["cycle_planets"] == ["venus", "mars"]


def test_aquarius_house_returns_separate_saturn_and_uranus_tracks():
    planets = {
        "saturn": _planet("Aqu", house=1),
        "uranus": _planet("Tau", house=4),
        "venus": _planet("Lib", house=9),
        # Remaining angular rulers used by the constructed cusps.
        "sun": _planet("Leo"),
        "mars": _planet("Ari"),
        "moon": _planet("Can"),
        "mercury": _planet("Gem"),
        "jupiter": _planet("Sag"),
        "neptune": _planet("Pis"),
        "pluto": _planet("Sco"),
    }
    result = build_house_ruler_chains(
        planets,
        [300, 330, 0, 30, 60, 90, 120, 150, 180, 210, 240, 270],
        300,
    )
    first = result["placidus"][0]
    assert first["house"] == 1
    assert first["sign"] == "Aqu"
    assert first["dual_ruler"] is True
    assert [track["house_ruler"] for track in first["tracks"]] == ["saturn", "uranus"]
    assert [node["planet"] for node in first["tracks"][0]["nodes"]] == ["saturn"]
    assert [node["planet"] for node in first["tracks"][1]["nodes"]] == ["uranus", "venus"]

    # 1 宫链就是命主星链：宫头星座＝上升星座，不再单列一份。
    assert first["chart_ruler"] is True
    assert "chart_ruler" not in result


def test_identical_traditional_and_modern_tracks_are_deduplicated():
    planets = {
        "mars": _planet("Ari"), "venus": _planet("Tau"),
        "mercury": _planet("Gem"), "moon": _planet("Can"),
        "sun": _planet("Leo"), "jupiter": _planet("Sag"),
        "saturn": _planet("Cap"), "uranus": _planet("Aqu"),
        "neptune": _planet("Pis"), "pluto": _planet("Sco"),
    }
    result = build_house_ruler_chains(planets, [i * 30 for i in range(12)], 0)
    aries = result["placidus"][0]
    assert aries["sign"] == "Ari"
    assert aries["dual_ruler"] is False
    assert len(aries["tracks"]) == 1


def test_all_twelve_houses_are_returned_in_three_modal_crosses():
    planets = {
        "mars": _planet("Ari"), "venus": _planet("Tau"),
        "mercury": _planet("Gem"), "moon": _planet("Can"),
        "sun": _planet("Leo"), "jupiter": _planet("Sag"),
        "saturn": _planet("Cap"), "uranus": _planet("Aqu"),
        "neptune": _planet("Pis"), "pluto": _planet("Sco"),
    }
    result = build_house_ruler_chains(planets, [i * 30 for i in range(12)], 0)
    for system in ("placidus", "whole_sign"):
        rows = result[system]
        assert [row["house"] for row in rows] == list(range(1, 13))
        by_house = {row["house"]: row for row in rows}
        assert [by_house[h]["cross"] for h in (1, 4, 7, 10)] == ["angular"] * 4
        assert [by_house[h]["cross"] for h in (2, 5, 8, 11)] == ["succedent"] * 4
        assert [by_house[h]["cross"] for h in (3, 6, 9, 12)] == ["cadent"] * 4
        # 只有 1 宫是命主星链。
        assert [h for h in range(1, 13) if by_house[h]["chart_ruler"]] == [1]


def test_每组十字按星盘方位排布():
    """1 在左、10 在顶，7 在右、4 在底；其他两组沿用同一几何。"""
    positions = {
        house: cross["positions"][house]
        for cross in HOUSE_CROSSES for house in cross["houses"]
    }
    assert (positions[1], positions[10], positions[7], positions[4]) == (
        "left", "top", "right", "bottom")
    assert (positions[2], positions[11], positions[8], positions[5]) == (
        "left", "top", "right", "bottom")
    assert (positions[3], positions[12], positions[9], positions[6]) == (
        "left", "top", "right", "bottom")


def test_modern_policy_uses_outer_planets_for_the_three_co_ruled_signs():
    assert TRADITIONAL_RULERS["Aqu"] == "saturn"
    assert TRADITIONAL_RULERS["Sco"] == "mars"
    assert TRADITIONAL_RULERS["Pis"] == "jupiter"
    assert MODERN_RULERS["Aqu"] == "uranus"
    assert MODERN_RULERS["Sco"] == "pluto"
    assert MODERN_RULERS["Pis"] == "neptune"
