"""Deterministic verification of submitted natal facts, never of prose meaning.

The reference is a reproducibility check, not authentication. Ground truth is
always recomputed on the server; no client-supplied chart table is trusted or
persisted. Only supported, explicitly submitted claims receive a verdict.
"""

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

FACT_SCHEMA = "natal-facts-v1"


class NatalReferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    year: StrictInt
    month: StrictInt
    day: StrictInt
    hour: StrictInt
    minute: StrictInt
    location_id: StrictStr
    house_system: StrictStr
    fold: StrictInt | None = None


class NatalFactReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: StrictStr
    input: NatalReferenceInput
    fingerprint: StrictStr = Field(min_length=64, max_length=64)


class NatalClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote: StrictStr = Field(min_length=1, max_length=1000,
                            description="Exact draft quote represented by this claim; echoed, not parsed.")
    kind: StrictStr = Field(max_length=40, description="sign, house, retrograde or aspect; other kinds are unverified.")
    point: StrictStr = Field(max_length=60, description="Planet or axis key, e.g. moon, saturn, asc; Chinese names accepted.")
    value: StrictStr | StrictInt | StrictBool = Field(description="Claimed sign name, house integer, retrograde boolean or aspect name/angle.")
    other_point: StrictStr | None = Field(default=None, max_length=60,
                                         description="Second point, required only for an aspect claim.")
    scope: StrictStr = Field(default="natal", max_length=40,
                            description="Only natal is supported; return/transit/relationship claims are unverified.")


_POINTS = {
    "sun": "太阳", "moon": "月亮", "mercury": "水星", "venus": "金星",
    "mars": "火星", "jupiter": "木星", "saturn": "土星", "uranus": "天王星",
    "neptune": "海王星", "pluto": "冥王星", "chiron": "凯龙星",
    "north_node": "北交点", "south_node": "南交点",
    "pars_fortuna": "福点", "pars_spiritus": "精神点",
    "asc": "上升点", "dsc": "下降点", "mc": "中天", "ic": "天底",
}
_POINT_ALIASES = {**{key: key for key in _POINTS},
                  **{value: key for key, value in _POINTS.items()},
                  "上升": "asc", "下降": "dsc", "凯龙": "chiron",
                  "ascendant": "asc", "descendant": "dsc",
                  "midheaven": "mc", "imum_coeli": "ic"}
_POINT_ALIASES.update({"true_north_lunar_node": "north_node",
                       "true_south_lunar_node": "south_node",
                       "part_of_fortune": "pars_fortuna", "part_of_spirit": "pars_spiritus"})
_SIGNS = dict(zip(
    ("aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio",
     "sagittarius", "capricorn", "aquarius", "pisces"),
    ("白羊座", "金牛座", "双子座", "巨蟹座", "狮子座", "处女座", "天秤座", "天蝎座",
     "射手座", "摩羯座", "水瓶座", "双鱼座")))
_SIGN_ALIASES = {**_SIGNS, **{s: s for s in _SIGNS.values()},
                 **{s.removesuffix("座"): s for s in _SIGNS.values()}}
_ASPECT_ALIASES = {
    "conjunction": 0, "合": 0, "合相": 0,
    "sextile": 60, "六分": 60, "六分相": 60,
    "square": 90, "刑": 90, "刑相": 90, "四分相": 90,
    "trine": 120, "拱": 120, "拱相": 120, "三分相": 120,
    "quincunx": 150, "梅花相": 150, "梅花相位": 150,
    "opposition": 180, "冲": 180, "冲相": 180, "对分相": 180,
}


def _key(value):
    return value.strip().lower() if isinstance(value, str) else None


def natal_reference(table):
    inputs = {**table["input"], "fold": table["birth_context"]["fold"]}
    payload = {"schema_version": FACT_SCHEMA, "input": inputs,
               "birth_context": table["birth_context"], "settings": table["settings"],
               "planets": table["planets"], "axes": table["axes"],
               "house_cusps": table["house_cusps"], "aspects": table["aspects"]}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return {"schema_version": FACT_SCHEMA, "input": inputs,
            "fingerprint": hashlib.sha256(encoded).hexdigest()}


def _claim_result(claim, table, index):
    out = {"index": index, "claim": claim, "verdict": "unverified"}
    if claim["scope"] != "natal":
        return {**out, "reason": "仅核对本命事实；此断言属于其他盘或时间范围。"}
    kind = claim["kind"]
    point = _POINT_ALIASES.get(_key(claim["point"]))
    other = _POINT_ALIASES.get(_key(claim.get("other_point")))
    if kind not in {"sign", "house", "retrograde", "aspect"} or point is None:
        return {**out, "reason": "断言类型或星体不在本次核对范围内。"}
    value = claim["value"]
    if kind != "aspect" and claim.get("other_point") is not None:
        return {**out, "reason": "多个星体的断言需要拆成独立事实。"}
    if kind == "aspect":
        angle = value if type(value) is int else _ASPECT_ALIASES.get(_key(value))
        if angle not in {0, 60, 90, 120, 150, 180} or other is None or other == point:
            return {**out, "reason": "请提供两个不同星体及可识别的相位名称或角度。"}
        matches = [(i, a) for i, a in enumerate(table["aspects"])
                   if {_POINT_ALIASES.get(_key(a["point1"])),
                       _POINT_ALIASES.get(_key(a["point2"]))} == {point, other}]
        if not matches:
            return {**out, "reason": "返回的相位表未包含该星体组合；缺记录不能证明该断言成立或被捏造。"}
        evidence = [{"path": f"/aspects/{i}", "value": a} for i, a in matches]
        supported = any(a["angle"] == angle for _, a in matches)
    else:
        pair = next(((i, p) for i, p in enumerate(table["planets"]) if p["key"] == point), None)
        if pair:
            i, planet = pair
            actual = planet.get(kind)
            path = f"/planets/{i}/{kind}"
        elif point in table["axes"] and kind == "sign":
            actual = table["axes"][point]["sign_zh"]
            path = f"/axes/{point}/sign_zh"
        else:
            return {**out, "reason": "计算结果中没有可用于该断言的字段。"}
        if actual is None:
            return {**out, "reason": "计算结果未提供该值。"}
        if kind == "sign":
            expected = _SIGN_ALIASES.get(_key(value))
        elif kind == "house":
            expected = value if type(value) is int and 1 <= value <= 12 else None
        else:
            expected = value if type(value) is bool else {
                "逆行": True, "retrograde": True, "顺行": False, "direct": False,
            }.get(_key(value))
        if expected is None:
            return {**out, "reason": "断言值无法识别；宫位需为 1–12 的整数。"}
        supported = actual == expected
        evidence = [{"path": path, "value": actual}]
    return {**out, "verdict": "supported" if supported else "contradicted",
            "evidence": evidence,
            "reason": "与本次计算字段一致。" if supported else "与本次计算字段冲突，请依据 evidence 修正。"}


def verify_natal_claims_data(reference, claims):
    """Recompute the reference chart and compare only explicitly submitted facts."""
    from services.mcp_natal import calculate_natal_data

    ref = NatalFactReference.model_validate(reference).model_dump()
    if ref["schema_version"] != FACT_SCHEMA:
        return {"status": "invalid_reference", "error": "盘面引用版本不支持，请重新调用 calculate_natal_chart。",
                "next_action": "recalculate_chart"}
    if not 1 <= len(claims) <= 100:
        return {"status": "invalid_input", "error": "每次提交 1–100 条结构化断言。"}
    parsed = [NatalClaim.model_validate(claim).model_dump() for claim in claims]
    table = calculate_natal_data(**ref["input"])
    if table["status"] != "ok":
        return table
    from services.mcp_validation import validate_output, blocked
    issues = validate_output("calculate_natal_chart", table, ref["input"])
    if issues:
        return blocked("calculate_natal_chart", issues)
    if table["fact_reference"] != ref:
        return {"status": "reference_mismatch",
                "error": "输入、宫制或计算结果与引用不一致；请重新取盘并核实引用，再提交断言。",
                "next_action": "recalculate_chart"}
    results = [_claim_result(claim, table, i) for i, claim in enumerate(parsed)]
    counts = {verdict: sum(r["verdict"] == verdict for r in results)
              for verdict in ("supported", "contradicted", "unverified")}
    assessment = ("contains_conflicts" if counts["contradicted"] else
                  "no_verifiable_claims" if not counts["supported"] else
                  "partially_verified" if counts["unverified"] else "submitted_claims_supported")
    return {"status": "ok", "assessment": assessment, "counts": counts,
            "fact_reference": table["fact_reference"], "claims": results,
            "coverage": {"submitted_claims": len(results),
                         "checked_claims": counts["supported"] + counts["contradicted"],
                         "quote_semantics_checked": False,
                         "full_report_checked": False},
            "scope": "仅核对已提交的结构化本命断言。quote 原文只回显，未验证其与结构化断言的语义一致性；未核对整篇解读、遗漏的事实、心理推论或事件判断。",
            "next_action": "correct_conflicting_claims" if counts["contradicted"] else
                           "review_unverified_claims" if counts["unverified"] else "use_verified_facts"}
