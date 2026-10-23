"""MCP-only clarification responses; no changes to the calculation API."""

BIRTH_FIELDS = ("year", "month", "day", "hour", "minute", "location_id")
_PROMPTS = {
    "year": "请补充出生年份。", "month": "请补充出生月份。",
    "day": "请补充出生日期。", "hour": "请确认准确的出生小时；时间不详时不能排本命盘。",
    "minute": "请确认出生分钟，不能把未知分钟补成 0。",
    "location_id": "请搜索并确认地点，或用经纬度解析地点 ID；同名地点需要用户选择。",
    "house_system": "请确认宫制：普拉西度（placidus）或整宫制（whole_sign）；已明确的选择可沿用。",
    "residence_location_id": "请确认用于太阳返照的地点；若采用出生地，请明确选择出生地的 location_id。",
    "target_year": "请确认太阳返照年份。",
    "target_month": "请确认月亮返照所在地的民用月份（1–12）。",
    "age_or_as_of": "请提供次限计算的年龄 age，或参考日期 as_of（YYYY-MM-DD）。",
    "from_date": "请确认查询起始日期（YYYY-MM-DD）。",
    "to_date": "请确认查询结束日期（YYYY-MM-DD）。",
    "lot": "请选择福点（fortune）或精神点（spirit）。",
    "parent_start": "请从已有黄道释放结果选择第三级周期，并传入其 start。",
    "parent_sign": "请传入所选第三级周期的 sign，不要猜测。",
    "fold": "该当地时间出现两次，请让用户从 candidates 中选择对应的 UTC 偏移，再传入 fold。",
    "relocation_location_id": "请确认空间重置的目标迁居地 location_id。",
}


def missing(value):
    return value is None or (isinstance(value, str) and not value.strip())


def clarification(fields, *, prompt=None, status="needs_clarification", candidates=None):
    required = []
    for field in fields:
        leaf = field.rsplit(".", 1)[-1]
        item = {"field": field, "prompt": _PROMPTS.get(leaf, "请核实该输入。")}
        if leaf == "house_system":
            item["options"] = ["placidus", "whole_sign"]
        required.append(item)
    message = prompt or "请补全或确认以下信息后重试；不要自行补值。"
    out = {"status": status, "error": message, "required_fields": list(fields),
           "clarification": {"required": required, "prompt_to_user": message},
           "next_action": "ask_user"}
    if candidates is not None:
        out["candidates"] = candidates
    return out


class ClarificationRequired(ValueError):
    def __init__(self, fields, prompt=None):
        self.response = clarification(fields, prompt=prompt)
        super().__init__(self.response["error"])


def tool_clarification(name, arguments, parameter_names):
    """Missing inputs reach this guard instead of failing as generic schema errors.

    Explicit arguments may reuse a user's prior choices. This cannot establish
    that the model obtained those values from a human; client instructions must
    still prohibit invented times, locations and choices.
    """
    fields = []
    if "year" in parameter_names:
        fields.extend(BIRTH_FIELDS)
    if "house_system" in parameter_names:
        fields.append("house_system")
    if "residence_location_id" in parameter_names:
        fields.extend(("residence_location_id", "target_year"))
    if "relocation_location_id" in parameter_names:
        fields.append("relocation_location_id")
    if name in {"calculate_lunar_return", "render_lunar_return_chart"}:
        fields.append("target_month")
    if name in {"calculate_secondary_progressions", "render_secondary_progressions_chart"}:
        if missing(arguments.get("age")) and missing(arguments.get("as_of")):
            fields.append("age_or_as_of")
    if name == "calculate_transits_to_natal":
        fields.extend(("from_date", "to_date"))
    if name == "calculate_timeline_synthesis":
        fields.append("target_year")
    if name == "calculate_zodiacal_releasing_l4":
        fields.extend(("lot", "parent_start", "parent_sign"))
    if name in {"calculate_sky_chart", "render_sky_chart", "calculate_aspect_windows"}:
        fields.append("location_id")
    absent = [field for field in fields if missing(arguments.get(field))]
    for person in ("person_a", "person_b"):
        if (name == 'calculate_relationship_observation' and person == 'person_b'
                and arguments.get('mode') == 'natal' and arguments.get(person) is None):
            continue
        if person in parameter_names:
            birth = arguments.get(person)
            birth = birth.model_dump() if hasattr(birth, "model_dump") else (birth or {})
            absent.extend(f"{person}.{field}" for field in BIRTH_FIELDS
                          if missing(birth.get(field)))
    if not absent:
        return None
    out = clarification(absent)
    if name == "calculate_timeline_synthesis" and "target_year" in absent:
        for item in out["clarification"]["required"]:
            if item["field"] == "target_year":
                item["prompt"] = "请确认时间线目标年份。"
    return out
