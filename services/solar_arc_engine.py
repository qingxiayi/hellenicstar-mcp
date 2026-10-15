"""True solar-arc calculations based on the Sun's daily ephemeris motion."""

from dataclasses import dataclass
import math

import swisseph as swe


ENGINE_VERSION = "true-solar-arc-1"
TROPICAL_YEAR_DAYS = 365.2422
MAX_SUPPORTED_AGE = 120
_SUN_FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED
_AGE_TOLERANCE = 1e-7


class EphemerisModeError(RuntimeError):
    """Raised when strict Swiss Ephemeris mode falls back to another engine."""


@dataclass(frozen=True)
class AgeTimeCoordinates:
    progressed_ephemeris_jd: float
    event_civil_jd: float


def _finite(name: str, value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def normalize_longitude(longitude: float) -> float:
    """Return a longitude in the half-open interval [0, 360)."""
    return _finite("longitude", longitude) % 360.0


def normalize(longitude: float) -> float:
    """Public shorthand for :func:`normalize_longitude`."""
    return normalize_longitude(longitude)


def forward_arc(start: float, end: float) -> float:
    """Return the zodiacally forward distance from start to end."""
    return (normalize_longitude(end) - normalize_longitude(start)) % 360.0


def circular_midpoint(first: float, second: float) -> float:
    """Return the midpoint along the shorter arc between two longitudes."""
    first = normalize_longitude(first)
    second = normalize_longitude(second)
    signed_distance = (second - first + 180.0) % 360.0 - 180.0
    return normalize_longitude(first + signed_distance / 2.0)


def sun_longitude(jd: float, *, require_swieph: bool = False) -> float:
    """Calculate tropical solar longitude at ``jd``.

    Swiss Ephemeris installations without external ephemeris files can
    legitimately fall back to Moshier. Callers that require deployment-grade
    Swiss files can opt into strict flag validation with ``require_swieph``.
    """
    jd = _finite("jd", jd)
    position, returned_flags = swe.calc_ut(jd, swe.SUN, _SUN_FLAGS)
    if require_swieph and (
        returned_flags & swe.FLG_MOSEPH or not returned_flags & swe.FLG_SWIEPH
    ):
        raise EphemerisModeError(
            f"Swiss Ephemeris required, but calc_ut returned flags {returned_flags}"
        )
    return normalize_longitude(position[0])


def arc_at_age(
    birth_jd: float,
    natal_sun: float,
    age: float,
    *,
    require_swieph: bool = False,
) -> float:
    """Return the true solar arc at age, where one year advances one ephemeris day."""
    birth_jd = _finite("birth_jd", birth_jd)
    natal_sun = _finite("natal_sun", natal_sun)
    age = _finite("age", age)
    if age < 0:
        raise ValueError("age must be non-negative")
    progressed_sun = sun_longitude(birth_jd + age, require_swieph=require_swieph)
    return forward_arc(natal_sun, progressed_sun)


def solve_age(
    birth_jd: float,
    natal_sun: float,
    required_arc: float,
    min_age: float,
    max_age: float,
    *,
    require_swieph: bool = False,
) -> float | None:
    """Return the first age matching an arc, or ``None`` if unbracketed.

    The solver is intentionally limited to one solar-arc revolution and the
    monotonic 0--120 year human-age interval. One-year brackets therefore
    locate the first root without confusing a longitude crossing with a wrap.
    """
    birth_jd = _finite("birth_jd", birth_jd)
    natal_sun = _finite("natal_sun", natal_sun)
    target = normalize_longitude(required_arc)
    min_age = _finite("min_age", min_age)
    max_age = _finite("max_age", max_age)
    if min_age < 0 or max_age > MAX_SUPPORTED_AGE or max_age < min_age:
        raise ValueError(
            f"age window must be ordered and within 0..{MAX_SUPPORTED_AGE}"
        )

    def residual(age: float) -> float:
        # forward_arc unwraps solar longitude crossings at 0 degrees. Within
        # the supported human-age range this is a continuous increasing arc.
        return arc_at_age(
            birth_jd, natal_sun, age, require_swieph=require_swieph
        ) - target

    left = min_age
    left_value = residual(left)
    if abs(left_value) <= 1e-12:
        return left

    while left < max_age:
        right = min(left + 1.0, max_age)
        right_value = residual(right)
        if abs(right_value) <= 1e-12:
            return right
        if left_value < 0 < right_value:
            while right - left > _AGE_TOLERANCE / 2.0:
                midpoint = (left + right) / 2.0
                midpoint_value = residual(midpoint)
                if midpoint_value < 0:
                    left = midpoint
                else:
                    right = midpoint
            return (left + right) / 2.0
        left, left_value = right, right_value
    return None


def age_time_coordinates(birth_jd: float, age: float) -> AgeTimeCoordinates:
    """Keep symbolic progression time separate from the corresponding civil time."""
    birth_jd = _finite("birth_jd", birth_jd)
    age = _finite("age", age)
    if age < 0:
        raise ValueError("age must be non-negative")
    return AgeTimeCoordinates(
        progressed_ephemeris_jd=birth_jd + age,
        event_civil_jd=birth_jd + age * TROPICAL_YEAR_DAYS,
    )
