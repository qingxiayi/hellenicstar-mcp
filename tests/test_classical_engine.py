"""Unit tests for classical_engine and extended classical calculations."""
import pytest
from services.classical_engine import (
    get_bound_lord,
    get_face_lord,
    compute_essential_dignities,
    compute_solar_state,
    compute_orientality,
    compute_receptions,
    compute_lots,
    EGYPTIAN_BOUNDS,
    CHALDEAN_FACES,
    DOROTHEAN_TRIPLICITY,
    SOLAR_THRESHOLDS,
)
from services.mcp_natal import calculate_classical_data, calculate_lots_data


def test_egyptian_bounds_lookup():
    # Aries bounds
    assert get_bound_lord(0, 0.0) == "jupiter"
    assert get_bound_lord(0, 5.9) == "jupiter"
    assert get_bound_lord(0, 6.0) == "venus"
    assert get_bound_lord(0, 11.9) == "venus"
    assert get_bound_lord(0, 12.0) == "mercury"
    assert get_bound_lord(0, 19.9) == "mercury"
    assert get_bound_lord(0, 20.0) == "mars"
    assert get_bound_lord(0, 24.9) == "mars"
    assert get_bound_lord(0, 25.0) == "saturn"
    assert get_bound_lord(0, 29.9) == "saturn"

    # Pisces bounds
    assert get_bound_lord(11, 0.0) == "venus"
    assert get_bound_lord(11, 11.9) == "venus"
    assert get_bound_lord(11, 12.0) == "jupiter"
    assert get_bound_lord(11, 15.9) == "jupiter"
    assert get_bound_lord(11, 16.0) == "mercury"
    assert get_bound_lord(11, 18.9) == "mercury"
    assert get_bound_lord(11, 19.0) == "mars"
    assert get_bound_lord(11, 27.9) == "mars"
    assert get_bound_lord(11, 28.0) == "saturn"


def test_chaldean_faces_lookup():
    # Aries 1: Mars, Aries 2: Sun, Aries 3: Venus
    assert get_face_lord(0, 5.0) == "mars"
    assert get_face_lord(0, 15.0) == "sun"
    assert get_face_lord(0, 25.0) == "venus"
    # Taurus 1: Mercury, Taurus 2: Moon, Taurus 3: Saturn
    assert get_face_lord(1, 5.0) == "mercury"
    assert get_face_lord(1, 15.0) == "moon"
    assert get_face_lord(1, 25.0) == "saturn"


def test_essential_dignities_scoring():
    # Sun in Leo 15° (Domicile=5, Triplicity=3 (day), Face=0/Mars, Term=Saturn) -> net score >= 8
    sun_leo = compute_essential_dignities("sun", 135.0, is_diurnal=True)
    assert sun_leo["domicile"] is True
    assert sun_leo["triplicity"] is True
    assert sun_leo["essential_score"] >= 8

    # Sun in Aquarius 11° (Detriment = -5)
    sun_aqu = compute_essential_dignities("sun", 311.3284, is_diurnal=True)
    assert sun_aqu["detriment"] is True
    assert sun_aqu["essential_score"] == -5


def test_solar_states_and_orientality():
    # Cazimi (<17')
    cazimi = compute_solar_state(100.1, 100.0)
    assert cazimi["state"] == "cazimi"

    # Combust (<8.5°)
    combust = compute_solar_state(105.0, 100.0)
    assert combust["state"] == "combust"

    # Under the beams (<17°)
    under = compute_solar_state(112.0, 100.0)
    assert under["state"] == "under_beams"

    # Free (>=17°)
    free = compute_solar_state(125.0, 100.0)
    assert free["state"] == "free"

    # Oriental: planet longitude < sun longitude (rises before sun)
    oriental = compute_orientality(90.0, 100.0)
    assert oriental["orientality"] == "oriental"

    # Occidental: planet longitude > sun longitude
    occidental = compute_orientality(110.0, 100.0)
    assert occidental["orientality"] == "occidental"


def test_calculate_classical_data_planets_filter():
    loc = "gn:2988507"
    res = calculate_classical_data(
        year=1990, month=4, day=15, hour=18, minute=0,
        location_id=loc, house_system="whole_sign",
        planets=["sun", "moon"]
    )
    assert res["status"] == "ok"
    assert len(res["classical_dignities_detail"]) == 2
    planet_keys = [p["planet"] for p in res["classical_dignities_detail"]]
    assert planet_keys == ["sun", "moon"]
    assert "receptions" in res
    assert "solar_state_thresholds" in res


def test_calculate_lots_data():
    loc = "gn:2988507"
    res = calculate_lots_data(
        year=1990, month=4, day=15, hour=18, minute=0,
        location_id=loc, house_system="whole_sign",
        lots=["fortune", "spirit", "marriage_male", "mother"]
    )
    assert res["status"] == "ok"
    assert len(res["lots"]) == 4
    for lot in res["lots"]:
        assert 0.0 <= lot["longitude"] < 360.0
        assert lot["sign"].endswith("座")
        assert 1 <= lot["house"] <= 12
        assert "formula" in lot

