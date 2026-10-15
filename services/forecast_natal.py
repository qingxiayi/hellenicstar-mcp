"""Lightweight, validated natal boundary for forecast calculations."""

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Mapping

from services.civil_time_resolver import CivilTimeResolver
from services.engine_adapter import calc_from_context
from services.location_resolver import LocationResolver


NATAL_ENGINE_VERSION = "forecast-natal-1"

_PLANETS = (
    "sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn",
    "uranus", "neptune", "pluto",
)
_SPECIAL_POINTS = {
    "true_north_lunar_node": "north_node",
    "true_south_lunar_node": "south_node",
    "chiron": "chiron",
    "part_of_fortune": "fortuna",
    "part_of_spirit": "spiritus",
}
_AXES = {
    "ascendant": "asc",
    "descendant": "dsc",
    "midheaven": "mc",
    "imum_coeli": "ic",
}


@dataclass(frozen=True)
class ForecastPoint:
    longitude: float
    house: int


@dataclass(frozen=True)
class ForecastNatalSnapshot:
    context: Any
    birth_jd_ut: float
    planets: Mapping[str, ForecastPoint]
    axes: Mapping[str, float]
    natal_engine_version: str
    cusps: tuple[float, ...] = ()


@dataclass(frozen=True)
class ForecastNatalError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


def _longitude(value: Any, point_name: str) -> float:
    try:
        longitude = float(value)
    except (TypeError, ValueError) as exc:
        raise ForecastNatalError(
            "invalid_longitude", f"{point_name} 缺少有效黄经"
        ) from exc
    if not math.isfinite(longitude):
        raise ForecastNatalError("invalid_longitude", f"{point_name} 缺少有效黄经")
    return longitude % 360.0


def _forecast_point(raw: Mapping[str, Any], point_name: str) -> ForecastPoint:
    house_value = raw.get("house")
    if isinstance(house_value, bool):
        raise ForecastNatalError("invalid_house", f"{point_name} 宫位必须在 1..12")
    try:
        house = int(house_value)
    except (TypeError, ValueError) as exc:
        raise ForecastNatalError(
            "invalid_house", f"{point_name} 宫位必须在 1..12"
        ) from exc
    if house_value != house or not 1 <= house <= 12:
        raise ForecastNatalError("invalid_house", f"{point_name} 宫位必须在 1..12")
    return ForecastPoint(_longitude(raw.get("longitude"), point_name), house)


def snapshot_from_engine_data(ctx: Any, data: Mapping[str, Any]) -> ForecastNatalSnapshot:
    raw_planets = data.get("planets") or {}
    if "sun" not in raw_planets:
        raise ForecastNatalError("missing_sun", "本命引擎结果缺少太阳")

    planets = {
        name: _forecast_point(raw_planets[name], name)
        for name in _PLANETS
        if name in raw_planets
    }
    special_points = data.get("special_points") or {}
    for engine_name, forecast_name in _SPECIAL_POINTS.items():
        if engine_name in special_points:
            planets[forecast_name] = _forecast_point(
                special_points[engine_name], engine_name
            )

    raw_axes = data.get("axes") or {}
    axes = {}
    for engine_name, forecast_name in _AXES.items():
        raw_axis = raw_axes.get(engine_name)
        if not isinstance(raw_axis, Mapping) or "longitude" not in raw_axis:
            raise ForecastNatalError("missing_axis", f"本命引擎结果缺少轴点 {engine_name}")
        axes[forecast_name] = _longitude(raw_axis["longitude"], engine_name)

    raw_houses = data.get("houses") or {}
    raw_cusps = raw_houses.get("cusps") if isinstance(raw_houses, Mapping) else None
    if not isinstance(raw_cusps, (list, tuple)) or len(raw_cusps) < 12:
        raise ForecastNatalError("missing_cusps", "本命引擎结果缺少十二宫宫头")
    cusps = tuple(
        _longitude(raw_cusps[index], f"cusp{index + 1}")
        for index in range(12)
    )

    return ForecastNatalSnapshot(
        context=ctx,
        birth_jd_ut=ctx.julian_day_ut,
        planets=MappingProxyType(planets),
        axes=MappingProxyType(axes),
        natal_engine_version=NATAL_ENGINE_VERSION,
        cusps=cusps,
    )


def build_forecast_natal(body: Mapping[str, Any]) -> ForecastNatalSnapshot:
    location = LocationResolver().resolve(
        location_id=body.get("location_id"),
        lat=body.get("lat"),
        lng=body.get("lng"),
        query=body.get("query"),
    )
    if location is None:
        raise ForecastNatalError("location_not_found", "地点缺失或无法解析")

    resolution = CivilTimeResolver().resolve(
        location,
        body.get("year"), body.get("month"), body.get("day"),
        body.get("hour"), body.get("minute"), fold=body.get("fold"),
    )
    if resolution.context is None:
        status = getattr(resolution.status, "value", str(resolution.status))
        raise ForecastNatalError(status, resolution.message)

    ctx = resolution.context
    city = body.get("city") or body.get("query") or ""
    data = calc_from_context(
        ctx, body.get("name") or "", city, location.country_code or "CN"
    )
    return snapshot_from_engine_data(ctx, data)
