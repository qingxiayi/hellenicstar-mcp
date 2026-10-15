"""Cross-runtime compatibility check for natal aspect ordering.

The frozen snapshot checker compares lists by index. Natal aspects are ordered
by floating-point orb, so nearly equal orbs may trade places across runtimes.
This check compares each aspect with the same identity, then reuses every other
structural rule from the frozen checker. It does not change tool output.
"""

import asyncio
import json
from pathlib import Path

import pytest

import mcp_server as m
from tests.mcp_aspect_comparison import align_natal_output
from tests.test_backward_compat import (
    _to_json_compatible,
    assert_structure_backward_compatible,
)


SNAPSHOTS = Path(__file__).parent / "snapshots"


def _check_natal_output(actual, expected, *, render=False):
    actual = _to_json_compatible(actual)
    expected = _to_json_compatible(expected)
    actual = align_natal_output(actual, expected, render=render)
    assert_structure_backward_compatible(actual, expected)


@pytest.mark.parametrize("tool_name", ("calculate_natal_chart", "render_natal_chart"))
def test_natal_aspects_match_frozen_snapshot_by_identity(tool_name):
    snapshot = json.loads((SNAPSHOTS / f"{tool_name}.json").read_text(encoding="utf-8"))
    result = asyncio.run(getattr(m, tool_name)(**snapshot["input"]))
    if tool_name == "render_natal_chart":
        _check_natal_output(result.structuredContent,
                            snapshot["output"]["structuredContent"], render=True)
    else:
        _check_natal_output(result, snapshot["output"])


def test_alignment_preserves_each_aspects_applying_type():
    expected = [
        {"point1": "sun", "point2": "moon", "aspect": "合相", "angle": 0,
         "orb": 0.1, "exact_diff": 0.1, "applying": False,
         "involves_axis": False},
        {"point1": "sun", "point2": "mars", "aspect": "四分相", "angle": 90,
         "orb": 0.1, "exact_diff": 89.9, "applying": None,
         "involves_axis": False},
    ]
    _check_natal_output({"aspects": list(reversed(expected))}, {"aspects": expected})
    changed = [expected[1], dict(expected[0], applying=None)]
    with pytest.raises(AssertionError, match="applying changed"):
        _check_natal_output({"aspects": changed}, {"aspects": expected})
    with pytest.raises(AssertionError, match="identities or multiplicities"):
        _check_natal_output({"aspects": [expected[0], expected[0]]},
                            {"aspects": expected})
    shifted = [dict(expected[0], orb=0.10001), expected[1]]
    with pytest.raises(AssertionError, match="orb changed materially"):
        _check_natal_output({"aspects": shifted}, {"aspects": expected})
