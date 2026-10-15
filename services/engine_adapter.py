# -*- coding: utf-8 -*-
"""
services/engine_adapter.py —— EngineAdapter（plan §5.2/§5.3）。

接收 CivilTimeResolver 产出的 ResolvedBirthContext，把唯一 UTC 瞬间拆成引擎天文层
需要的形态，一次出全量（行星 / 宫位 / 四轴 / 南北交点 / 凯龙 / 福点·精神点 /
日月食 / 相位 / 相位格局）。
"""

from datetime import datetime
from typing import Dict

from services.civil_time_resolver import ResolvedBirthContext

# 四轴不参与相位格局判定：上升/中天是地平与子午的交点，随出生时间每 4 分钟走 1°，
# 拿它当大三角或 T三角的一角，图形的成立与否会被生时误差直接左右。
# engine/natal_chart.py::calculate 里的 pattern_points 早就排除了四轴，但生产路径
# 走的是 adapter.py 的那套检测器，它只丢弃"全部由虚点组成"的格局，含一个上升点的
# T三角照样留下（实测三张盘冒出 6 条）。adapter.py 是禁止改动的遗留适配层，
# 因此在它外面统一过滤——这是本仓库唯一的格局四轴口径。
# 南北交点与凯龙不在此列：它们是黄道上的真实点位，不随生时秒级漂移。
_PATTERN_EXCLUDED_POINTS = ("上升点", "中天", "下降点", "天底")


def strip_axis_patterns(patterns: Dict) -> Dict:
    """丢弃任何含四轴的格局条目。缺一角的 T三角不再是 T三角，整条剔除。"""
    if not isinstance(patterns, dict):
        return patterns
    cleaned = {}
    for key, entries in patterns.items():
        if isinstance(entries, list):
            cleaned[key] = [
                entry for entry in entries
                if not (isinstance(entry, (list, tuple))
                        and any(p in _PATTERN_EXCLUDED_POINTS for p in entry))
            ]
        else:
            cleaned[key] = entries
    return cleaned


def _strip_axes_from_result(result: Dict) -> Dict:
    """就地清洗 result['patterns']['phase_patterns_enhanced']。"""
    patterns = (result or {}).get("patterns", {})
    if isinstance(patterns, dict) and "phase_patterns_enhanced" in patterns:
        patterns["phase_patterns_enhanced"] = strip_axis_patterns(
            patterns["phase_patterns_enhanced"]
        )
    return result


def calc_from_context(ctx: ResolvedBirthContext, name: str = "",
                      city: str = "", country_code: str = "CN") -> Dict:
    """ResolvedBirthContext → 完整本命盘 data（与旧 get_natal_data 返回同构）。"""
    from engine.natal_chart import NatalChartCalculator
    from adapter import _enhance_with_patterns

    snap = ctx.snapshot
    civ = datetime.fromisoformat(ctx.civil_dt)

    resolved = {
        "lat": snap.lat_wgs84,
        "lng": snap.lng_wgs84,
        "utc_offset": ctx.utc_offset,
    }

    nc = NatalChartCalculator()
    raw = nc.calculate(
        civ.year, civ.month, civ.day, civ.hour, civ.minute,
        city, country_code, resolved=resolved,
    )
    if raw.get("status") != "success":
        raise RuntimeError(f"引擎计算失败: {raw.get('message')}")

    return _strip_axes_from_result(_enhance_with_patterns(raw))
