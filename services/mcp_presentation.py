"""Optional MCP response projection; calculation and validation stay full size."""

from inspect import Parameter, Signature
from typing import Literal


CONTROL_FIELDS = frozenset({
    "status", "birth_context", "settings", "calculation_reference",
    "fact_reference", "quality", "interpretation_workflow",
    "calculation_envelope", "presentation", "completeness", "layer_availability",
})
SUMMARY_LIMIT = 5


def public_signature(source: Signature) -> Signature:
    """Expose optional controls without adding them to recomputation inputs."""
    params = list(source.parameters.values())
    params.extend((
        Parameter("detail_level", Parameter.KEYWORD_ONLY, default="full",
                  annotation=Literal["full", "summary"]),
        Parameter("include", Parameter.KEYWORD_ONLY, default=None,
                  annotation=list[str] | None),
    ))
    return source.replace(parameters=params)


def validate_selection(detail_level, include):
    if detail_level not in ("full", "summary"):
        return {"status": "invalid_input", "error": "detail_level 只能是 full 或 summary。"}
    if include is not None and (not isinstance(include, list) or not include
                                or len(include) > 30 or any(
                                    not isinstance(key, str) or not key or len(key) > 80
                                    for key in include)):
        return {"status": "invalid_input", "error": "include 需为 1–30 个顶层内容字段名。"}
    return None


def _summarize(value, path, omitted):
    if isinstance(value, list):
        if len(value) > SUMMARY_LIMIT:
            omitted[path] = len(value) - SUMMARY_LIMIT
        return [_summarize(item, f"{path}/{index}", omitted)
                for index, item in enumerate(value[:SUMMARY_LIMIT])]
    if isinstance(value, dict):
        return {key: _summarize(item, f"{path}/{key}", omitted)
                for key, item in value.items()}
    return value


def project_result(result: dict, detail_level: str, include: list[str] | None) -> dict:
    """Project a checked result; leave verification references tied to full data."""
    if result.get("status") != "ok" or (detail_level == "full" and include is None):
        return result
    available = set(result) - CONTROL_FIELDS
    if include is not None:
        unknown = sorted(set(include) - available)
        if unknown:
            return {"status": "invalid_input", "error": "include 包含未知内容字段。",
                    "unknown_fields": unknown, "available_fields": sorted(available)}
    selected = available if include is None else set(include)
    omitted = {}
    projected = {}
    for key, value in result.items():
        if key in CONTROL_FIELDS or key in selected:
            projected[key] = (_summarize(value, f"/{key}", omitted)
                              if detail_level == "summary" and key in selected else value)
    projected["presentation"] = {
        "detail_level": detail_level,
        "included_fields": sorted(selected),
        "omitted_array_items": omitted,
        "reference_scope": "full_checked_result",
    }
    return projected
