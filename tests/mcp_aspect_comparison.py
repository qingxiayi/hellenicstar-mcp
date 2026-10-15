"""Align natal aspects for snapshot checks without changing tool output."""

from collections import Counter


ASPECT_IDENTITY = ("point1", "point2", "aspect", "angle")
GEOMETRY_TOLERANCE_DEG = 1e-8


def aspect_key(row):
    return tuple(row[field] for field in ASPECT_IDENTITY)


def align_aspects(actual, expected):
    """Match the same aspect rows and reject missing, duplicate or changed rows."""
    actual_keys = [aspect_key(row) for row in actual]
    expected_keys = [aspect_key(row) for row in expected]
    assert Counter(actual_keys) == Counter(expected_keys), (
        "Natal aspect identities or multiplicities changed"
    )
    assert len(actual_keys) == len(set(actual_keys)), "Duplicate natal aspect identity"
    by_key = dict(zip(actual_keys, actual))
    aligned = [by_key[key] for key in expected_keys]
    for got, baseline in zip(aligned, expected):
        assert got["applying"] is baseline["applying"], (
            f"{aspect_key(got)} applying changed"
        )
        assert got["involves_axis"] is baseline["involves_axis"], (
            f"{aspect_key(got)} axis participation changed"
        )
        for field in ("orb", "exact_diff"):
            assert type(got[field]) is type(baseline[field]), (
                f"{aspect_key(got)} {field} type changed"
            )
            assert abs(got[field] - baseline[field]) <= GEOMETRY_TOLERANCE_DEG, (
                f"{aspect_key(got)} {field} changed materially"
            )
    return aligned


def align_natal_output(actual, expected, *, render=False):
    """Return a shallow copy aligned for a structural snapshot comparison."""
    actual = dict(actual)
    if render:
        source = dict(actual["calculation_source"])
        source["aspects"] = align_aspects(
            source["aspects"], expected["calculation_source"]["aspects"]
        )
        actual["calculation_source"] = source
    else:
        actual["aspects"] = align_aspects(actual["aspects"], expected["aspects"])
    return actual
