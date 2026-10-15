"""Internal primary-directions geometry prototype; no MCP registration or timing key.

This computes natal equatorial and horizon coordinates only. In particular,
neither a difference between two OA values nor a house position is, by itself,
a Placidus primary-direction arc.
"""
from __future__ import annotations

from math import asin, degrees, isfinite, radians, tan

import swisseph as swe

from services.ephemeris_guard import apply_ephe_path


PLANET_IDS = {
    "sun": swe.SUN, "moon": swe.MOON, "mercury": swe.MERCURY,
    "venus": swe.VENUS, "mars": swe.MARS, "jupiter": swe.JUPITER,
    "saturn": swe.SATURN,
}
AXIS_LONGITUDE_TOLERANCE_DEG = 0.01  # only a diagnostic check of natal input


def _distance(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def horizon_coordinates(ra_deg: float, declination_deg: float,
                        latitude_deg: float) -> dict:
    """Return horizon RA offsets or explicitly mark a circumpolar point."""
    if not all(isfinite(value) for value in (ra_deg, declination_deg, latitude_deg)):
        raise ValueError("主限坐标必须为有限数值")
    if not -90 < latitude_deg < 90 or not -90 <= declination_deg <= 90:
        raise ValueError("主限坐标纬度超出范围")
    product = tan(radians(latitude_deg)) * tan(radians(declination_deg))
    # A tangent point has no rising/setting crossing; guard float roundoff at 1.
    if abs(declination_deg) == 90 or abs(product) >= 1 - 1e-12:
        return {"status": "unsupported_circumpolar", "ra_deg": ra_deg % 360,
                "declination_deg": declination_deg, "ascensional_difference_deg": None,
                "oblique_ascension_deg": None, "oblique_descension_deg": None}
    ad = degrees(asin(product))
    return {"status": "ok", "ra_deg": ra_deg % 360,
            "declination_deg": declination_deg,
            "ascensional_difference_deg": ad,
            "oblique_ascension_deg": (ra_deg - ad) % 360,
            "oblique_descension_deg": (ra_deg + ad) % 360}


def compute_primary_geometry(snapshot, planets: tuple[str, ...] = tuple(PLANET_IDS)) -> dict:
    """Reuse the resolved natal instant and Swiss data for a bounded diagnostic.

    Equatorial body coordinates include their physical ecliptic latitude.
    The ASC/MC references are ecliptic points (zero ecliptic latitude).
    No arcs, ages, dates, or directional aspects are calculated.
    """
    if any(name not in PLANET_IDS for name in planets):
        raise ValueError("主限原型包含未支持的行星")
    apply_ephe_path()
    context = snapshot.context
    jd = snapshot.birth_jd_ut
    latitude = context.snapshot.lat_wgs84
    longitude = context.snapshot.lng_wgs84
    eps_values, _ = swe.calc_ut(jd, swe.ECL_NUT)
    true_obliquity = eps_values[0]
    cusps, ascmc, _, _ = swe.houses_ex2(jd, latitude, longitude, b"P")
    for key, computed in (("asc", ascmc[0]), ("mc", ascmc[1])):
        if _distance(snapshot.axes[key], computed) > AXIS_LONGITUDE_TOLERANCE_DEG:
            raise ValueError(f"本命 {key} 与 Swiss Placidus 参照不一致")
    asc_ra, asc_dec, _ = swe.cotrans((ascmc[0], 0.0, 1.0), -true_obliquity)
    mc_ra, mc_dec, _ = swe.cotrans((ascmc[1], 0.0, 1.0), -true_obliquity)
    asc = horizon_coordinates(asc_ra, asc_dec, latitude)
    mc = horizon_coordinates(mc_ra, mc_dec, latitude)
    armc = ascmc[2] % 360
    bodies = {}
    for name in dict.fromkeys(planets):
        coordinates, flags = swe.calc_ut(jd, PLANET_IDS[name],
                                         swe.FLG_SWIEPH | swe.FLG_EQUATORIAL)
        if not flags & swe.FLG_SWIEPH or flags & swe.FLG_MOSEPH:
            raise ValueError(f"{name} 未使用 Swiss 星历文件")
        bodies[name] = horizon_coordinates(coordinates[0], coordinates[1], latitude)
    return {
        "status": "geometry_only", "method": "natal_equatorial_horizon",
        "birth_jd_ut": jd, "latitude_deg": latitude,
        "longitude_deg": longitude, "true_obliquity_deg": true_obliquity,
        "placidus_armc_deg": armc,
        "placidus_cusps_deg": list(cusps),
        "axes": {"asc": asc, "mc": mc}, "planets": bodies,
    }
