"""Backward compatibility tests for all 29 MCP tools.

Verifies that the current codebase preserves structural backward compatibility
against frozen baseline snapshots in tests/snapshots/:
- No missing fields
- No renamed or moved fields
- No type changes (with strict bool vs int separation)
- Non-None fields never become None (snapshot None may become any type)
- Non-empty lists in snapshots never become empty
- Additional new fields are permitted
"""
import asyncio
import base64
import inspect
import json
import os
import pytest

import mcp_server as m
from mcp.types import CallToolResult
from services.mcp_facts import NatalClaim, NatalFactReference
from services.mcp_result_facts import CalculationReference, CalculationClaim
from tests.mcp_aspect_comparison import align_natal_output

SNAPSHOTS_DIR = os.path.join(os.path.dirname(__file__), "snapshots")

ALL_TOOLS = [
    "search_birthplace",
    "resolve_birth_coordinates",
    "calculate_natal_chart",
    "render_natal_chart",
    "render_jones_pattern",
    "calculate_classical_factors",
    "calculate_zodiacal_releasing",
    "calculate_time_lords",
    "calculate_solar_arc",
    "calculate_transits_to_natal",
    "get_transit_snapshot",
    "calculate_saturn_jupiter_cycles",
    "calculate_house_ingresses",
    "calculate_progressed_lunation",
    "calculate_solar_return",
    "render_solar_return_chart",
    "calculate_relationship_charts",
    "render_composite_chart",
    "get_current_sky",
    "calculate_house_rulers",
    "calculate_zodiacal_releasing_l4",
    "calculate_lifetime_transit_summary",
    "calculate_aspect_windows",
    "calculate_sky_chart",
    "render_sky_chart",
    "render_transit_biwheel",
    "render_solar_arc_biwheel",
    "verify_natal_claims",
    "verify_calculation_claims",
]


def assert_structure_backward_compatible(actual, expected, path=""):
    """Check structural backward compatibility: actual must satisfy expected schema."""
    # Rule 4: Snapshot None may become any value in actual
    if expected is None:
        return

    # Rule 3: Snapshot non-None becoming None is a failure
    if actual is None:
        pytest.fail(f"Value at '{path or '/'}' became None (expected {type(expected).__name__})")

    # Rule 2: bool and int must be strictly distinguished
    if isinstance(expected, bool) or isinstance(actual, bool):
        if type(actual) is not type(expected):
            pytest.fail(f"Type mismatch at '{path or '/'}': expected {type(expected).__name__}, got {type(actual).__name__}")
    elif type(actual) is not type(expected):
        pytest.fail(f"Type mismatch at '{path or '/'}': expected {type(expected).__name__}, got {type(actual).__name__}")

    if isinstance(expected, dict):
        for key, exp_val in expected.items():
            subpath = f"{path}/{key}"
            if key not in actual:
                pytest.fail(f"Missing required field: '{subpath}'")
            assert_structure_backward_compatible(actual[key], exp_val, subpath)

    elif isinstance(expected, list):
        if len(expected) > 0:
            if len(actual) == 0:
                pytest.fail(f"List at '{path or '/'}' became empty (expected non-empty list)")
            for idx, act_elem in enumerate(actual):
                exp_elem = expected[idx] if idx < len(expected) else expected[0]
                assert_structure_backward_compatible(act_elem, exp_elem, f"{path}[{idx}]")


def _to_json_compatible(obj):
    """Normalize object to standard JSON-compatible data (strings for dict keys, etc.)."""
    return json.loads(json.dumps(obj, ensure_ascii=False))


# ── 检查器自身行为自测（手工构造小字典） ────────────────────────────────────

def test_checker_missing_field_fails():
    with pytest.raises(pytest.fail.Exception, match="Missing required field: '/b'"):
        assert_structure_backward_compatible({"a": 1}, {"a": 1, "b": 2})


def test_checker_bool_int_type_mismatch_fails():
    with pytest.raises(pytest.fail.Exception, match="Type mismatch at '/flag': expected bool, got int"):
        assert_structure_backward_compatible({"flag": 1}, {"flag": True})
    with pytest.raises(pytest.fail.Exception, match="Type mismatch at '/flag': expected int, got bool"):
        assert_structure_backward_compatible({"flag": True}, {"flag": 1})


def test_checker_non_none_to_none_fails():
    with pytest.raises(pytest.fail.Exception, match="Value at '/name' became None"):
        assert_structure_backward_compatible({"name": None}, {"name": "test"})


def test_checker_snapshot_none_allows_any_value():
    assert_structure_backward_compatible({"val": "anything"}, {"val": None})
    assert_structure_backward_compatible({"val": 123}, {"val": None})
    assert_structure_backward_compatible({"val": True}, {"val": None})
    assert_structure_backward_compatible({"val": None}, {"val": None})


def test_checker_allows_new_fields():
    assert_structure_backward_compatible({"a": 1, "new_field": "added"}, {"a": 1})


def test_checker_non_empty_list_becoming_empty_fails():
    with pytest.raises(pytest.fail.Exception, match="became empty"):
        assert_structure_backward_compatible({"items": []}, {"items": [{"id": 1}]})


# ── 29 个 MCP 工具快照回归测试 ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def natal_calculation_reference():
    """Compute base natal chart reference dynamically for verification tools."""
    snap_path = os.path.join(SNAPSHOTS_DIR, "calculate_natal_chart.json")
    with open(snap_path, "r", encoding="utf-8") as f:
        snap = json.load(f)
    return asyncio.run(m.calculate_natal_chart(**snap["input"]))


@pytest.mark.parametrize("tool_name", ALL_TOOLS)
def test_tool_backward_compat(tool_name, natal_calculation_reference):
    snap_path = os.path.join(SNAPSHOTS_DIR, f"{tool_name}.json")
    assert os.path.exists(snap_path), f"Snapshot file missing: {snap_path}"

    with open(snap_path, "r", encoding="utf-8") as f:
        snap = json.load(f)

    # 1. verify_natal_claims: dynamically pass fresh natal reference
    if tool_name == "verify_natal_claims":
        ref = NatalFactReference(**natal_calculation_reference["fact_reference"])
        claims = [NatalClaim(**c) for c in snap["input_claims"]]
        res = asyncio.run(m.verify_natal_claims(reference=ref, claims=claims))
        actual_output = {k: v for k, v in res.items() if k != "fact_reference"}
        assert_structure_backward_compatible(_to_json_compatible(actual_output), snap["output"])
        return

    # 2. verify_calculation_claims: dynamically pass fresh calculation reference
    if tool_name == "verify_calculation_claims":
        ref = CalculationReference(**natal_calculation_reference["calculation_reference"])
        claims = [CalculationClaim(**c) for c in snap["input_claims"]]
        res = asyncio.run(m.verify_calculation_claims(reference=ref, claims=claims))
        actual_output = {k: v for k, v in res.items() if k != "calculation_reference"}
        assert_structure_backward_compatible(_to_json_compatible(actual_output), snap["output"])
        return

    # 3. All other tools: reconstruct arguments
    args = dict(snap["input"])
    for p in ("person_a", "person_b"):
        if p in args and isinstance(args[p], dict):
            args[p] = m.BirthInput(**args[p])

    tool_fn = getattr(m, tool_name)
    res = asyncio.run(tool_fn(**args))

    # 4. Render tools: verify CallToolResult, image metadata and structuredContent
    if tool_name.startswith("render_"):
        assert isinstance(res, CallToolResult), f"Expected CallToolResult for {tool_name}"
        assert len(res.content) == 2, f"Expected 2 content items for {tool_name}"
        assert res.content[1].mimeType == "image/png"

        png_bytes = base64.b64decode(res.content[1].data)
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n", "Invalid PNG header"
        width = int.from_bytes(png_bytes[16:20], "big")
        height = int.from_bytes(png_bytes[20:24], "big")
        assert width == snap["image_meta"]["expected_width"]
        assert height == snap["image_meta"]["expected_height"]
        assert len(png_bytes) >= snap["image_meta"]["min_bytes"]

        actual_output = _to_json_compatible(res.structuredContent)
        expected_output = snap["output"]["structuredContent"]
        if tool_name == "render_natal_chart":
            actual_output = align_natal_output(actual_output, expected_output, render=True)
        assert_structure_backward_compatible(actual_output, expected_output)
        return

    # 5. Standard data calculation tools
    actual_output = _to_json_compatible(res)
    if tool_name == "calculate_natal_chart":
        actual_output = align_natal_output(actual_output, snap["output"])
    assert_structure_backward_compatible(actual_output, snap["output"])

