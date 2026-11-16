"""Single registry and tropical ecliptic house geometry.

A placement uses longitude between consecutive cusps (no cusp orb, latitude or
mundane-position correction). Failures are explicit: never substitute a system.
"""
from dataclasses import dataclass
import math
import swisseph as swe


class HouseCalculationError(ValueError):
    """Requested geometry is unavailable; callers must not substitute houses."""


@dataclass(frozen=True)
class HouseSystem:
    code: bytes
    label: str


HOUSE_SYSTEMS = {
    'placidus': HouseSystem(b'P', 'Placidus'),
    'whole_sign': HouseSystem(b'W', 'Whole Sign'),
    'equal': HouseSystem(b'E', 'Equal'),
    'koch': HouseSystem(b'K', 'Koch'),
    'regiomontanus': HouseSystem(b'R', 'Regiomontanus'),
    'porphyry': HouseSystem(b'O', 'Porphyry'),
    'campanus': HouseSystem(b'C', 'Campanus'),
}
LEGACY_METHOD_SYSTEMS = ('placidus', 'whole_sign')


def house_system_spec(system):
    if not isinstance(system, str) or system not in HOUSE_SYSTEMS:
        raise ValueError('house_system 必须为 ' + ', '.join(HOUSE_SYSTEMS))
    return HOUSE_SYSTEMS[system]


def system_from_code(value):
    """Internal Swiss-code adapter; public inputs use canonical registry names."""
    if isinstance(value, bytes):
        value = value.decode('ascii')
    if isinstance(value, str) and value in HOUSE_SYSTEMS:
        return value
    if isinstance(value, str) and len(value) == 1:
        value = value.upper()
    for name, spec in HOUSE_SYSTEMS.items():
        if value == spec.code.decode() or (name == 'equal' and value == 'A'):
            return name
    raise ValueError(f'Unsupported house system: {value!r}')


def validate_cusps(cusps):
    if len(cusps) != 12 or not all(math.isfinite(c) for c in cusps):
        raise ValueError('需要十二个有限宫头度数')
    widths = [(cusps[(i + 1) % 12] - cusps[i]) % 360 for i in range(12)]
    if any(w <= 1e-10 or w >= 180 for w in widths) or not math.isclose(sum(widths), 360, abs_tol=1e-7):
        raise HouseCalculationError('宫头在此纬度/时刻退化或逆序，无法按黄经区间可靠落宫；未替换宫制')


def house_of(longitude, cusps):
    """Half-open intervals: an exact cusp belongs to the house starting there."""
    validate_cusps(cusps)
    if not math.isfinite(longitude):
        raise ValueError('行星黄经必须是有限数值')
    lon = longitude % 360
    for i, cusp in enumerate(cusps):
        width = (cusps[(i + 1) % 12] - cusp) % 360
        if (lon - cusp) % 360 < width:
            return i + 1
    raise ValueError('无法确定落宫')


@dataclass(frozen=True)
class HouseFrame:
    system: str
    cusps: tuple
    ascmc: tuple

    def house_of(self, longitude):
        return house_of(longitude, self.cusps)


def _frame(system, result):
    cusps, ascmc = result
    cusps = tuple(c % 360 for c in cusps)
    validate_cusps(cusps)
    if not all(math.isfinite(v) for v in ascmc):
        raise ValueError('四轴计算返回无效数值')
    return HouseFrame(system, cusps, tuple(ascmc))


def calculate_houses(jd_ut, latitude, longitude, system='placidus'):
    spec = house_system_spec(system)
    if not all(math.isfinite(v) for v in (jd_ut, latitude, longitude)):
        raise ValueError('时刻与坐标必须是有限数值')
    if not -90 < latitude < 90 or not -180 <= longitude <= 180:
        raise ValueError('宫位计算需要有效经纬度，且不能位于地理极点')
    try:
        return _frame(system, swe.houses(jd_ut, latitude, longitude, spec.code))
    except swe.Error as exc:
        raise HouseCalculationError(f'{system} 宫位在此纬度/时刻无法计算；未替换宫制：{exc}') from exc


def houses_at_armc(armc, latitude, obliquity, system):
    spec = house_system_spec(system)
    if not all(math.isfinite(v) for v in (armc, latitude, obliquity)) or not -90 < latitude < 90:
        raise ValueError('无效的 ARMC 宫位计算参数')
    try:
        return _frame(system, swe.houses_armc(armc, latitude, obliquity, spec.code))
    except swe.Error as exc:
        raise HouseCalculationError(f'{system} 推进宫位无法计算；未替换宫制：{exc}') from exc

# Capability boundary: method-specific tools do not inherit the generic enum.
GENERIC_HOUSE_TOOLS = frozenset({
    'calculate_natal_chart', 'render_natal_chart', 'calculate_house_rulers',
    'calculate_solar_return', 'render_solar_return_chart',
    'calculate_lunar_return', 'render_lunar_return_chart',
    'calculate_secondary_progressions', 'render_secondary_progressions_chart',
    'calculate_davison_chart', 'render_davison_chart',
    'calculate_relocation_chart', 'render_relocation_chart',
    'calculate_lots', 'calculate_time_lords',
    'calculate_relationship_charts', 'render_composite_chart',
    'calculate_sky_chart', 'render_sky_chart',
})


def systems_for_tool(name):
    if name in GENERIC_HOUSE_TOOLS:
        return tuple(HOUSE_SYSTEMS)
    if name == 'calculate_relationship_observation':
        return ('placidus',)
    return LEGACY_METHOD_SYSTEMS
