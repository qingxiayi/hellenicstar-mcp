# -*- coding: utf-8 -*-
"""services/transit_presentation.py —— 土木流年呈现层（设计 §8）。

把事件引擎的原始事件转换成：
  - 土星/木星统一四期（相邻两合轴节点组成一段，按起始轴命名）
  - 总览中的生涯曲线图说明（不重复塞进每一轮阶段卡）
  - 当前阶段 / 前后节点 / 未来三个最近节点（易变字段，as_of 注入式）
  - stats 计数

纯计算，不依赖 Flask/DB。当前状态属易变展示字段，测试注入固定 as_of_jd，
不写入黄金结果（§8.3）。

旧版按行星拆成两套阶段名，并给土星附加年龄解释。当前产品统一改为按宫位区间
定义的四期；旧年龄解释已撤除，生涯曲线说明只在总览集中展示。
"""
from typing import Dict, List, Optional

_DAYS_PER_YEAR = 365.25
# 四期按「起始轴」映射，规避经度排序歧义。每一期覆盖从该轴开始的三个宫位；
# 土星与木星共用同一套宫位历程名称，不再各自另造一套标签。
PHASE_GUIDE = [
    {
        "key": "adaptation",
        "number": 1,
        "name": "第一期·努力适应期",
        "short_name": "努力适应期",
        "house_range": "1—3宫",
        "from_axis": "Asc",
        "to_axis": "IC",
        "description": "自我要适应新的生存环境（1宫），过好自己的日子（2宫），享受沟通交流与学习阅览的乐趣（3宫）。",
    },
    {
        "key": "self_building",
        "number": 2,
        "name": "第二期·展现自己期",
        "short_name": "展现自己期",
        "house_range": "4—6宫",
        "from_axis": "IC",
        "to_axis": "Dsc",
        "description": "自我要得到家庭的支持（4宫），培养个人的才能与自信（5宫），强化自己的工作表现（6宫）。",
    },
    {
        "key": "relationship_expansion",
        "number": 3,
        "name": "第三期·交涉竞争期",
        "short_name": "交涉竞争期",
        "house_range": "7—9宫",
        "from_axis": "Dsc",
        "to_axis": "MC",
        "description": "自我要跟人建立合作关系与婚姻关系（7宫），会面临与别人的利益竞争、共生或冲突（8宫），然后提高自己的个人名声与社会地位（9宫）。",
    },
    {
        "key": "social_integration",
        "number": 4,
        "name": "第四期·事业高峰期",
        "short_name": "事业高峰期",
        "house_range": "10—12宫",
        "from_axis": "MC",
        "to_axis": "Asc",
        "description": "自我要实现个人的志向，建立管理者的地位（10宫），会面临建立团队与培养人脉的课题（11宫），然后回味1—11宫的一生经验，得到心灵的体会（12宫）。",
    },
]

_PHASE_BY_AXIS = {item["from_axis"]: item for item in PHASE_GUIDE}
SATURN_PHASE_NAME = {axis: item["name"] for axis, item in _PHASE_BY_AXIS.items()}
JUPITER_PHASE_NAME = dict(SATURN_PHASE_NAME)


def _build_phases(events, phase_names: Optional[Dict[str, str]] = None) -> List[Dict]:
    """相邻两合轴节点 → 一个阶段。按起始节点的轴命名并附四期语义。"""
    phase_names = phase_names or SATURN_PHASE_NAME
    phases = []
    for i in range(len(events) - 1):
        a, b = events[i], events[i + 1]
        guide = _PHASE_BY_AXIS.get(a.axis, {})
        phase = {
            "name": phase_names.get(a.axis, a.axis),
            "phase_key": guide.get("key"),
            "phase_number": guide.get("number"),
            "house_range": guide.get("house_range"),
            "from_axis": a.axis,
            "to_axis": b.axis,
            "start_age": round(a.age_years, 3),
            "end_age": round(b.age_years, 3),
            "duration_years": round(b.age_years - a.age_years, 3),
            "start_date": a.local_date or a.utc_datetime,
            "end_date": b.local_date or b.utc_datetime,
            "return_index": a.cycle,
            "start_event_id": a.event_id,
            "end_event_id": b.event_id,
        }
        phases.append(phase)
    return phases


def _current_phase_index(phases: List[Dict], current_age: float) -> Optional[int]:
    for idx, p in enumerate(phases):
        if p["start_age"] <= current_age < p["end_age"]:
            return idx
    return None


def _node_summary(e) -> Dict:
    """把一个事件压成「节点」摘要（前后节点/未来节点用）。"""
    base = {
        "event_id": e.event_id,
        "event_type": e.event_type,
        "age_years": round(e.age_years, 3),
        "date": e.local_date or e.utc_datetime,
        "direction": e.direction,
    }
    if e.event_type == "conjunction":
        base.update(
            planet=e.planet,
            planet_zh=e.planet_zh,
            axis=e.axis,
            display_label="%s合 %s" % (e.planet_zh, e.axis),
        )
    else:
        base.update(
            aspect=e.aspect,
            aspect_zh=e.aspect_zh,
            display_label="土木%s" % e.aspect_zh,
        )
    return base


def build_presentation(engine_events: Dict[str, List], birth_jd: float,
                       as_of_jd: Optional[float] = None,
                       max_age: float = 80.0) -> Dict:
    """组装阶段、当前状态与统计。

    engine_events: compute_transit_events 的返回（saturn_events/jupiter_events/aspects）。
    as_of_jd:      「现在」的儒略日；None 表示不生成 current（黄金结果不含 current）。
    """
    saturn_events = engine_events["saturn_events"]
    jupiter_events = engine_events["jupiter_events"]
    aspects = engine_events["aspects"]

    saturn_phases = _build_phases(saturn_events, SATURN_PHASE_NAME)
    jupiter_phases = _build_phases(jupiter_events, JUPITER_PHASE_NAME)

    stats = {
        "saturn_count": len(saturn_events),
        "jupiter_count": len(jupiter_events),
        "aspect_count": len(aspects),
    }

    result = {
        "phase_guide": PHASE_GUIDE,
        "saturn_phases": saturn_phases,
        "jupiter_phases": jupiter_phases,
        "stats": stats,
    }

    _attach_current(result, saturn_events, jupiter_events, aspects,
                    saturn_phases, jupiter_phases, birth_jd, as_of_jd, max_age)
    return result


def _attach_current(result, saturn_events, jupiter_events, aspects,
                    saturn_phases, jupiter_phases, birth_jd, as_of_jd, max_age):
    if as_of_jd is not None:
        current_age = (as_of_jd - birth_jd) / _DAYS_PER_YEAR
        all_nodes = sorted(saturn_events + jupiter_events + aspects,
                           key=lambda e: e.age_years)
        prev_node = None
        next_node = None
        future = []
        for e in all_nodes:
            if e.age_years <= current_age:
                prev_node = e
            else:
                if next_node is None:
                    next_node = e
                if len(future) < 3:
                    future.append(e)
        result["current"] = {
            "as_of_age": round(current_age, 3),
            "in_range": 0.0 <= current_age <= max_age,
            "saturn_phase_index": _current_phase_index(saturn_phases, current_age),
            "jupiter_phase_index": _current_phase_index(jupiter_phases, current_age),
            "previous_node": _node_summary(prev_node) if prev_node else None,
            "next_node": _node_summary(next_node) if next_node else None,
            "upcoming_nodes": [_node_summary(e) for e in future],
        }

    return result


# —————————————————————— §9 完整响应组装 —————————————————————— #

SCHEMA_VERSION = "saturn-jupiter-transits-response-2"
ENGINE_VERSION = "precise-ephemeris-1"


def assemble_transit_report(natal_axes: Dict[str, float], birth_jd: float,
                            natal_meta: Dict, max_age: float = 80.0,
                            tz=None, as_of_jd: Optional[float] = None) -> Dict:
    """纯组装：本命四轴 + 出生 JD → 设计 §9 完整响应 dict（无 Flask/解析器）。

    natal_meta: {name, civil_datetime, timezone, location_name}。
    在此调用事件引擎与阶段构建，保证 API 层只做认证/解析/HTTP 映射。
    """
    import swisseph as swe
    from services.saturn_jupiter_transits import (
        RULE_VERSION, compute_transit_events)
    from services.transit_ephemeris import body_at

    engine_events = compute_transit_events(natal_axes, birth_jd, max_age=max_age, tz=tz)
    pres = build_presentation(engine_events, birth_jd, as_of_jd=as_of_jd, max_age=max_age)

    probe = body_at("saturn", birth_jd)  # 引擎元数据：实际星历模式/旗标
    report = {
        "schema_version": SCHEMA_VERSION,
        "engine": {
            "engine_version": ENGINE_VERSION,
            "rule_version": RULE_VERSION,
            "pyswisseph_version": getattr(swe, "version", "?"),
            "ephemeris_mode": probe.ephemeris_mode,
            "returned_flags": probe.returned_flags,
        },
        "natal": {
            "name": natal_meta.get("name", ""),
            "civil_datetime": natal_meta.get("civil_datetime"),
            "timezone": natal_meta.get("timezone"),
            "location_name": natal_meta.get("location_name"),
            "axes": {k: round(v, 3) for k, v in natal_axes.items()},
        },
        "range": {"min_age": 0, "max_age": max_age},
        "saturn_events": [e.as_dict() for e in engine_events["saturn_events"]],
        "jupiter_events": [e.as_dict() for e in engine_events["jupiter_events"]],
        "aspects": [e.as_dict() for e in engine_events["aspects"]],
        "phase_guide": pres["phase_guide"],
        "saturn_phases": pres["saturn_phases"],
        "jupiter_phases": pres["jupiter_phases"],
        "stats": pres["stats"],
    }
    if "current" in pres:
        report["current"] = pres["current"]
    return report
