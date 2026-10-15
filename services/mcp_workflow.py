"""Deterministic routing advice for existing MCP tools; performs no calculation."""

import re


_BIRTH = ["准确的出生年月日、小时和分钟", "已确认的出生地 location_id"]
_VERIFY = {"tool": "verify_calculation_claims", "when": "引用计算事实写回答前",
           "purpose": "用原样 calculation_reference 和原结果字段路径核对草稿事实"}

WORKFLOWS = {
    "natal": {
        "label": "本命盘", "patterns": (r"本命盘|出生星盘|natal|birth chart",),
        "needed": _BIRTH + ["宫制 placidus 或 whole_sign"],
        "steps": [("calculate_natal_chart", "取得本命盘数据"),
                  ("verify_natal_claims", "解读前核对星座、宫位、逆行和相位事实")],
    },
    "classical": {
        "label": "古典要素", "patterns": (r"古典|派系|尊贵|福点|精神点|classical|sect|dignit",),
        "needed": _BIRTH + ["宫制 placidus 或 whole_sign"],
        "steps": [("calculate_classical_factors", "取得派系、尊贵、福点和格局等数据")],
    },
    "releasing": {
        "label": "黄道释放", "patterns": (r"黄道释放|zodiacal releasing",),
        "needed": _BIRTH + ["需要查看的参考日期 as_of（可选）"],
        "steps": [("calculate_zodiacal_releasing", "取得福点与精神点的 L1–L3 周期")],
    },
    "time_lords": {
        "label": "法达与年小限", "patterns": (r"法达|年小限|firdaria|profection",),
        "needed": _BIRTH + ["宫制 placidus 或 whole_sign", "参考日期 as_of（可选）"],
        "steps": [("calculate_time_lords", "取得法达与年小限周期")],
    },
    "transits": {
        "label": "本命行运", "patterns": (r"行运|transit",),
        "needed": _BIRTH + ["查询起止日期 from_date 和 to_date"],
        "steps": [("calculate_transits_to_natal", "取得所选区间的精确行运接触")],
    },
    "solar_arc": {
        "label": "太阳弧", "patterns": (r"太阳弧|solar arc",),
        "needed": _BIRTH + ["年龄范围或参考日期（可选）"],
        "steps": [("calculate_solar_arc", "取得太阳弧方向与相位矩阵")],
    },
    "solar_return": {
        "label": "太阳返照", "patterns": (r"太阳返照|太阳回归|solar return",),
        "needed": _BIRTH + ["目标年份 target_year", "返照所在地 residence_location_id",
                           "宫制 placidus 或 whole_sign"],
        "steps": [("calculate_solar_return", "取得返照盘与本命叠加数据")],
    },
    "lunar_return": {
        "label": "月亮返照", "patterns": (r"月亮返照|月亮回归|月返|lunar return",),
        "needed": _BIRTH + ["目标年份 target_year", "目标月份 target_month", "返照所在地 residence_location_id",
                           "宫制 placidus 或 whole_sign"],
        "steps": [("calculate_lunar_return", "取得月返盘与本命叠加数据")],
    },
    "secondary_progressions": {
        "label": "次限推进", "patterns": (r"次限推进|次限推运|二次推运|secondary progression",),
        "needed": _BIRTH + ["查询日期 as_of 或年龄 age（二选一）", "宫制 placidus 或 whole_sign"],
        "steps": [("calculate_secondary_progressions", "取得次限星盘、四轴与对本命相位数据")],
    },
    "relationship": {
        "label": "关系盘", "patterns": (r"关系盘|比较盘|组合盘|synastry|composite|relationship",),
        "needed": ["两人的准确出生年月日、小时和分钟", "两人各自确认的出生地 location_id"],
        "steps": [("calculate_relationship_charts", "取得比较盘与组合中点盘数据")],
    },
    "davison": {
        "label": "时空中点盘", "patterns": (r"时空中点|davison|戴维森",),
        "needed": ["两人的准确出生年月日、小时和分钟", "两人各自确认的出生地 location_id", "宫制 placidus 或 whole_sign"],
        "steps": [("calculate_davison_chart", "取得时空中点盘数据")],
    },
    "relocation": {
        "label": "空间重置盘", "patterns": (r"空间重置|重置盘|迁居盘|relocation",),
        "needed": _BIRTH + ["迁居地 relocation_location_id", "宫制 placidus 或 whole_sign"],
        "steps": [("calculate_relocation_chart", "取得空间重置盘四轴与新宫位数据")],
    },
    "sky": {
        "label": "当前天象", "patterns": (r"当前天象|今日天象|天空|天象|sky",),
        "needed": ["观测时刻 moment（可选；默认当前时刻）"],
        "steps": [("get_current_sky", "取得所选时刻的天象数据")],
    },
    "timeline_synthesis": {
        "label": "多技法综合时间线", "patterns": (r"多技法|综合时间线|timeline synthesis",),
        "needed": _BIRTH + ["目标年份 target_year", "跨度 span_years（1–3 年，可选）"],
        "steps": [("calculate_timeline_synthesis", "取得带来源的跨技法时间线与重合时段")],
    },
    "saturn_jupiter_cycles": {
        "label": "土木流年与大表图", "patterns": (r"土木|saturn[ -]+jupiter cycles",),
        "needed": _BIRTH + ["参考日期 as_of（可选）", "年龄上限 max_age（1–120，默认 80）"],
        "steps": [("calculate_saturn_jupiter_cycles", "取得土木四轴周期与事件表")],
        "render_step": ("render_saturn_jupiter_cycles", "使用相同出生资料、参考日期和年龄范围生成土木周期大表图"),
    },
}


def recommend(goal: str, available_tools: set[str]) -> dict:
    """Return a workflow only when the requested technique is unambiguous."""
    if not isinstance(goal, str) or not goal.strip() or len(goal) > 500:
        return {"status": "invalid_input", "error": "请用不超过 500 字说明想查看的占星内容。"}
    phrase = goal.strip().lower()
    matches = ([phrase] if phrase in WORKFLOWS else [
        key for key, spec in WORKFLOWS.items()
        if any(re.search(pattern, phrase) for pattern in spec["patterns"])
    ])
    if len(matches) != 1:
        candidates = matches or list(WORKFLOWS)
        return {"status": "needs_clarification", "next_action": "ask_user",
                "error": "请确认要使用哪一种已支持的计算内容。",
                "options": [{"goal": key, "label": WORKFLOWS[key]["label"]}
                            for key in candidates]}
    key = matches[0]
    spec = WORKFLOWS[key]
    first_tool = spec["steps"][0][0]
    required_tools = {tool for tool, _ in spec["steps"]}
    if "render_step" in spec:
        required_tools.add(spec["render_step"][0])
    if key != "natal":
        required_tools.add(_VERIFY["tool"])
    if key != "sky":
        required_tools.add("search_birthplace")
    missing = required_tools - available_tools
    if missing:
        return {"status": "unavailable", "error": "所需工具当前未注册。",
                "missing_tools": sorted(missing)}
    steps = []
    if key != "sky":
        searches = 2 if key in {"solar_return", "lunar_return", "relationship", "davison", "relocation"} else 1
        steps.append({"tool": "search_birthplace", "when": "尚未确认地点 ID 时",
                      "purpose": "确认出生地" if searches == 1 else "分别确认所需地点"})
    steps.extend({"tool": tool, "when": "资料齐全后" if tool == first_tool else "解读前",
                  "purpose": purpose} for tool, purpose in spec["steps"])
    if "render_step" in spec:
        render_tool, purpose = spec["render_step"]
        steps.append({"tool": render_tool, "when": "用户要求出图时", "purpose": purpose})
    if key != "natal":
        steps.append(dict(_VERIFY))
    return {"status": "ok", "goal": key, "label": spec["label"],
            "required_information": list(spec["needed"]), "steps": steps,
            "first_calculation_tool": first_tool,
            "boundary": "这是工具调用建议，不是计算结果或心理解释；缺少必需资料时向用户确认，不自行补值。"}
