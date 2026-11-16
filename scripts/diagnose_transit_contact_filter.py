"""Verify full MCP contacts versus legacy collapse with real ephemeris.

This fixture is NOT a reconstruction or verification of any user's natal chart.
Run from the repository root with .venv/bin/python scripts/diagnose_transit_contact_filter.py.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import swisseph as swe
from services import mcp_extended, transit_natal, transit_utils, transit_lifetime


def main():
    seed = swe.julday(2029, 8, 14, 12)
    moving_lon, _ = transit_utils.body_position(swe.PLUTO, seed)
    fixed_lon = (moving_lon + 180) % 360
    snapshot = SimpleNamespace(
        axes={}, planets={
            key: SimpleNamespace(longitude=fixed_lon if key == "chiron" else 0.0)
            for key in transit_natal.NATAL_POINT_ORDER if key not in transit_natal.AXES
        },
        context=SimpleNamespace(
            civil_dt="1990-01-01T00:00:00",
            snapshot=SimpleNamespace(tz_iana="UTC"),
        ),
    )
    full = transit_natal.compute_filtered_events(
        snapshot, swe.julday(2029, 1, 1, 0), swe.julday(2030, 1, 1, 0),
        planets=["pluto"], natal_points=["chiron"], aspects=[180],
        collapse_series=False,
    )
    # Replace only birth-input construction; query, filtering and serialization
    # are the real MCP service path. No root-finding/filtering is mocked.
    with patch.object(mcp_extended, "_validated", return_value=(
        {"birth_context": {"tz_iana": "UTC"}}, {},
    )), patch.object(mcp_extended, "_forecast_snapshot", return_value=snapshot):
        public = mcp_extended.transit_events_data(
            year=1990, month=1, day=1, hour=0, minute=0,
            location_id="synthetic-only", from_date="2029-01-01",
            to_date="2029-12-31", target_scope="points", planet="pluto",
        )
    assert len(full["events"]) == 3
    middle = full["events"][1]
    assert middle["direction"] == "retrograde"
    assert middle["exact_utc"].startswith("2029-08-14")
    assert public["status"] == "ok", public
    assert [e["contact"] for e in public["events"]] == ["1/3", "2/3", "3/3"]
    assert any(e["exact_utc"] == middle["exact_utc"] for e in public["events"])
    legacy = transit_lifetime.compute_range_events(
        snapshot, swe.julday(2029, 1, 1, 0), swe.julday(2030, 1, 1, 0),
        planet="pluto", target_scope="points",
    )
    assert [e["contact_index"] for e in legacy["events"]] == [1, 3]
    print(json.dumps({
        "fixture": "synthetic natal Chiron, not user chart",
        "fixed_longitude": fixed_lon,
        "unfiltered_events": [
            {key: e[key] for key in ("exact_utc", "direction", "contact_index", "contact_total")}
            for e in full["events"]
        ],
        "mcp_events": public["events"],
        "finding": "MCP retains all three contacts; shared legacy default still retains first/last",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
