"""Deterministic routing advice for existing MCP tools; performs no calculation."""

import re


_BIRTH = ["准确的出生年月日、小时和分钟", "已确认的出生地 location_id"]
_VERIFY = {"tool": "verify_calculation_claims", "when": "引用计算事实写回答前",
           "purpose": "用原样 calculation_reference 和原结果字段路径核对草稿事实"}

WORKFLOWS = {
    "salience": {
        "label": "本命结构显著性", "patterns": (r"本命重点|重点提取|显著性|natal salience|salience",),
        "needed": _BIRTH,
        "steps": [("calculate_natal_salience", "提取共同终端、主要入口、多入口候选及完整状态画像")],
    },
    "natal_structure": {
        "label": "本命结构图谱", "patterns": (r"本命结构|结构图谱|natal structure|dispositor graph",),
        "needed": _BIRTH,
        "steps": [("calculate_natal_structure_graph", "计算定位链、闭环、汇聚、相位构型及依赖关系")],
    },
    "natal": {
        "label": "本命盘", "patterns": (r"本命盘|出生星盘|\bnatal\b|birth chart",),
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
        "label": "本命行运", "patterns": (r"行运|\btransits?\b",),
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
        "label": "关系盘", "patterns": (r"关系盘|比较盘|synastry|relationship",),
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

# Optional image steps are explicit: a data request never requires rendering.
# The data step provides fields for verification; rendering may be called directly
# if the user only wants an image, because each renderer validates its own source.
_IMAGE_STEPS = {
    "natal": ("render_natal_chart", "生成本命盘 PNG"),
    "solar_arc": ("render_solar_arc_biwheel", "生成指定年龄的太阳弧双盘 PNG"),
    "solar_return": ("render_solar_return_chart", "生成所选年份与地点的太阳返照盘 PNG"),
    "lunar_return": ("render_lunar_return_chart", "生成所选月份与地点的月亮返照盘 PNG"),
    "secondary_progressions": ("render_secondary_progressions_chart", "生成次限推进双盘 PNG"),
    "davison": ("render_davison_chart", "生成时空中点盘 PNG"),
    "relocation": ("render_relocation_chart", "生成空间重置盘 PNG"),
}
for _goal, _render in _IMAGE_STEPS.items():
    WORKFLOWS[_goal]["render_step"] = _render
WORKFLOWS["solar_arc"]["image_needed"] = _BIRTH + ["绘图年龄 age 或参考日期 as_of（可选）；图片显示一个年龄，不是年龄区间"]

WORKFLOWS.update({
    "sky_chart": {
        "label": "指定地点天象盘", "patterns": (r"(?:当前|今日|今天)?天象盘|sky chart|(?:画|绘制|出图)\s*(?:一张|一下)?\s*(?:当前|今日|今天)?(?:天象|天空)",),
        "needed": ["已确认的观测地点 location_id", "观测时刻 moment（带时区；可选，默认当前时刻）"],
        "steps": [("calculate_sky_chart", "取得指定时刻、地点的星体、宫位和四轴数据")],
        "location_purpose": "确认观测地点；不要求是出生地",
        "render_step": ("render_sky_chart", "生成指定时刻、地点的天象盘 PNG"),
    },
    "transit_snapshot": {
        "label": "单一时刻行运与双盘", "patterns": (r"行运(?:快照|双盘)|(?:现在|此刻|当前|今天|今日)的?行运|transit (?:snapshot|biwheel)|(?:current|now) transits?",),
        "needed": _BIRTH + ["行运时刻 moment（带时区；可选，默认当前时刻）"],
        "steps": [("get_transit_snapshot", "取得一个时刻的行运位置及对本命的容许度内相位")],
        "render_step": ("render_transit_biwheel", "生成本命内圈、行运外圈的双盘 PNG"),
    },
    "progressed_lunation": {
        "label": "次限月相周期", "patterns": (r"次限月相|次限日月|progressed (?:lunation|lunar phase)",),
        "needed": _BIRTH + ["参考日期 as_of（可选）"],
        "steps": [("calculate_progressed_lunation", "取得次限日月八阶段与阶段变化时间线")],
    },
    "jones": {
        "label": "琼斯格局与分布图", "patterns": (r"琼斯|\bjones\b",),
        "needed": _BIRTH + ["古典数据的宫制 placidus 或 whole_sign；仅画琼斯分布图不需要此参数"],
        "steps": [("calculate_classical_factors", "取得琼斯分类及边界状态；不能据此直接下心理诊断")],
        "render_step": ("render_jones_pattern", "生成十星琼斯格局分布图 PNG"),
        "image_needed": _BIRTH,
    },
    "releasing_l4": {
        "label": "黄道释放 L4", "patterns": (r"黄道释放\s*的?\s*(?:l4|第四层|第四级|四级)|(?:l4|第四层|第四级|四级)\s*黄道释放|zodiacal releasing\s*(?:l4|level[ -]?4)",),
        "needed": _BIRTH + ["参考日期 as_of（可选）", "从 L1–L3 结果确认 lot（fortune/spirit）、目标 L3 的 parent_start 和 parent_sign；不能猜选父周期"],
        "steps": [("calculate_zodiacal_releasing", "取得可供选择的 L3 父周期"),
                  ("calculate_zodiacal_releasing_l4", "用户确认父周期后，将其 lot、精确起始日期和星座键传入以取得 L4")],
    },
    "relationship_observation": {
        "label": "关系结构观察", "patterns": (r"关系观察|关系结构观察|relationship observation|john green",),
        "needed": ["确认 mode 为 synastry（两人）或 natal（可一人）", "各人的准确出生资料与已确认的 location_id", "明确确认关系场景 relationship_type；不能把默认值当作用户确认"],
        "steps": [("calculate_relationship_observation", "取得接触、双方本命结构及观察路径；不输出匹配评分或心理诊断")],
    },
    "composite": {
        "label": "组合中点盘", "patterns": (r"组合(?:中点)?盘|\bcomposite\b",),
        "needed": ["两人的准确出生年月日、小时和分钟", "两人各自确认的出生地 location_id"],
        "steps": [("calculate_relationship_charts", "取得组合中点盘及关系盘数据")],
        "render_step": ("render_composite_chart", "生成组合中点盘 PNG；不是比较盘或戴维森盘"),
    },
    "house_rulers": {
        "label": "十二宫宫主定位链", "patterns": (r"宫主|house ruler",),
        "needed": _BIRTH + ["宫制 placidus 或 whole_sign"],
        "steps": [("calculate_house_rulers", "取得十二宫宫主的传统与现代定位链")],
    },
    "aspect_windows": {
        "label": "当前相位容许度窗口", "patterns": (r"相位(?:出入|容许度)?窗口|aspect windows?",),
        "needed": ["已确认的计算地点 location_id（用于福点与精神点）", "观测时刻 moment（带时区；可选）"],
        "location_purpose": "确认福点与精神点的计算地点",
        "steps": [("calculate_aspect_windows", "取得当前容许度内相位及已经过、剩余的窗口时间")],
    },
    "lifetime_transits": {
        "label": "生涯行运摘要", "patterns": (r"(?:生涯|终身)行运|lifetime transit",),
        "needed": _BIRTH,
        "steps": [("calculate_lifetime_transit_summary", "按七岁章节汇总长期精确行运次数；次数不代表吉凶")],
    },
    "house_ingresses": {
        "label": "土木进入本命宫位", "patterns": (r"(?:土星|木星|土木).{0,4}(?:进宫|进入.{0,4}宫)|house ingress",),
        "needed": _BIRTH + ["planet 与起止日期过滤（可选）"],
        "steps": [("calculate_house_ingresses", "取得土木进入本命 Placidus 宫位的日期及逆行重入")],
    },
})


# Only these specific aliases replace their own generic term. A long match is
# never evidence that another technique can be discarded.
_SPECIALIZES = {
    "sky_chart": {"sky"},
    "transit_snapshot": {"transits"},
    "lifetime_transits": {"transits"},
    "natal_structure": {"natal"},
    "salience": {"natal"},
    "releasing_l4": {"releasing"},
    "relationship_observation": {"relationship"},
    "house_ingresses": {"saturn_jupiter_cycles"},
}
_EVENT_SCOPE = re.compile(
    r"精确(?:发生)?(?:日期|时间|相位)|起止|区间|到年底|到明年|未来|"
    r"从.+?(?:到|至)|exact (?:dates?|events?|aspects?)|date range|through|next year")
_EXPLICIT_SNAPSHOT = re.compile(r"行运(?:快照|双盘)|transit (?:snapshot|biwheel)")
_DRAWING = re.compile(r"画|绘制|出图|图片|格局图|大表图|双盘|\bdraw\b|\brender\b|\bimage\b|\bpng\b|\bbiwheel\b")


def _output_mode(phrase):
    # Handle common explicit negatives before looking for a drawing request.
    no_image = re.search(r"(?:不要|无需|不用|不需要)(?:画图|绘图|图片|出图|图)|\b(?:no|without) (?:images?|rendering)\b", phrase)
    if no_image:
        return "data"
    if not _DRAWING.search(phrase):
        return "data" if re.search(r"只(?:要|需).*数据|\bdata only\b", phrase) else "unspecified"
    only = re.search(r"只(?:要|需|画|绘制|出图)|仅(?:要|需|画|绘制)|\bonly\b", phrase)
    data = re.search(r"数据|解读|解释|分析|\bdata\b|\binterpret", phrase)
    return "image_only" if only and not data else "data_and_image"


def _matching_goals(phrase, output_mode="unspecified"):
    if phrase in WORKFLOWS:
        return [phrase]
    hits = [(key, match.start(), match.end())
            for key, spec in WORKFLOWS.items()
            for pattern in spec["patterns"] for match in re.finditer(pattern, phrase)]
    # A shared drawing verb in "画本命盘和天象" applies to the sky too, but
    # must not produce a regex span covering the independent natal request.
    if output_mode in {"image_only", "data_and_image"}:
        hits = [("sky_chart" if key == "sky" else key, a, b) for key, a, b in hits]
    # Scope belongs to each clause, not the entire request. Explicit snapshot
    # plus event dates remains ambiguous; "current" alone yields to a range.
    for clause in re.finditer(r"[^，,。;；]+", phrase):
        if not _EVENT_SCOPE.search(clause.group()):
            continue
        snapshots = [(key, a, b) for key, a, b in hits
                     if key == "transit_snapshot" and clause.start() <= a < clause.end()]
        for hit in snapshots:
            _, a, b = hit
            if not _EXPLICIT_SNAPSHOT.search(phrase[a:b]):
                hits.remove(hit)
            # A non-contained scope marker preserves the event route even
            # when an explicit snapshot is also requested in the same clause.
            hits.append(("transits", clause.start(), clause.end()))
    selected = {key for key, start, end in hits if not any(
        key in _SPECIALIZES.get(other, ()) and a <= start and end <= b and b - a > end - start
        for other, a, b in hits)}
    return [key for key in WORKFLOWS if key in selected]


def recommend(goal: str, available_tools: set[str]) -> dict:
    """Return a workflow only when the requested technique is unambiguous."""
    if not isinstance(goal, str) or not goal.strip() or len(goal) > 500:
        return {"status": "invalid_input", "error": "请用不超过 500 字说明想查看的占星内容。"}
    phrase = goal.strip().lower()
    output_mode = _output_mode(phrase)
    matches = _matching_goals(phrase, output_mode)
    if len(matches) != 1:
        candidates = matches or list(WORKFLOWS)
        return {"status": "needs_clarification", "next_action": "ask_user",
                "reason": "multiple_goals" if matches else "unknown_goal",
                "question": "想先看哪一项，还是分别查看全部候选内容？" if matches else "想查看哪一种占星计算内容？",
                "error": "请确认要使用哪一种已支持的计算内容。",
                "options": [{"goal": key, "label": WORKFLOWS[key]["label"]}
                            for key in candidates]}
    key = matches[0]
    spec = WORKFLOWS[key]
    wants_image = output_mode in {"image_only", "data_and_image"}
    image_only = output_mode == "image_only"
    renderer = spec.get("render_step")
    if wants_image and not renderer:
        return {"status": "needs_clarification", "next_action": "ask_user",
                "reason": "unsupported_output",
                "question": "该流程没有对应绘图工具，是否改为查看计算数据？",
                "options": [{"goal": key, "label": spec["label"] + "（数据）"}]}
    calculation_steps = [renderer] if image_only else spec["steps"]
    first_tool = calculation_steps[0][0]
    required_tools = {tool for tool, _ in calculation_steps}
    if wants_image:
        required_tools.add(renderer[0])
    if key != "natal" and not image_only:
        required_tools.add(_VERIFY["tool"])
    if key != "sky":
        required_tools.add("search_birthplace")
    missing = required_tools - available_tools
    if missing:
        return {"status": "unavailable", "error": "所需工具当前未注册。",
                "missing_tools": sorted(missing)}
    steps = []
    if key != "sky":
        searches = 2 if key in {"solar_return", "lunar_return", "relationship", "davison", "relocation", "composite", "relationship_observation"} else 1
        steps.append({"tool": "search_birthplace", "when": "尚未确认地点 ID 时；已有确认 ID 则跳过",
                      "purpose": spec.get("location_purpose", "确认出生地" if searches == 1 else "分别确认所需地点")})
    steps.extend({"tool": tool, "when": "资料齐全后" if tool == first_tool else ("确认 L3 父周期后" if tool == "calculate_zodiacal_releasing_l4" else "解读前"),
                  "purpose": purpose} for tool, purpose in calculation_steps)
    if renderer and not image_only and output_mode != "data" and renderer[0] in available_tools:
        render_tool, purpose = renderer
        steps.append({"tool": render_tool, "when": "用户要求出图时", "purpose": purpose + "；仅需图片时可直接调用出图工具，其内部会计算并校验来源"})
    if key != "natal" and not image_only:
        steps.append(dict(_VERIFY))
    return {"status": "ok", "goal": key, "label": spec["label"],
            "output_mode": output_mode,
            "next_action": "check_required_information", "input_readiness": "not_checked",
            "clarification_policy": "结合已有对话只询问缺失或含糊的必需资料；资料齐全则继续，不重复询问。推荐成功不代表资料已齐全。",
            "required_information": list(spec.get("image_needed", spec["needed"]) if image_only else spec["needed"]), "steps": steps,
            "first_calculation_tool": first_tool,
            "boundary": "这是工具调用建议，不是计算结果或心理解释；缺少必需资料时向用户确认，不自行补值。"}
