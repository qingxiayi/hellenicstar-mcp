"""The envelope reports audited provenance without changing calculation facts."""

import asyncio
import json

import pytest

import mcp_server as m
from algorithm_registry import get_algorithm_entry
from services.mcp_envelope import calculation_envelope, registered_tools
from services.mcp_result_facts import CalculationClaim, CalculationReference, fingerprint, lookup
from versioning import get_version_info


BIRTH = dict(year=1990, month=4, day=15, hour=18, minute=0,
             location_id="gn:2988507", house_system="placidus")


def test_every_exposed_tool_has_an_audited_classification():
    names = {tool.name for tool in asyncio.run(m.mcp.list_tools())}
    assert len(names) == 42
    assert names == registered_tools()


def test_natal_envelope_reuses_registry_and_does_not_change_reference():
    result = asyncio.run(m.calculate_natal_chart(**BIRTH))
    envelope = result["calculation_envelope"]

    assert envelope["schema_version"] == "calculation-envelope-v1"
    assert envelope["tool"] == "calculate_natal_chart"
    assert envelope["versions"] == get_version_info()
    assert envelope["provenance"]["coverage"] == "partial"
    assert envelope["provenance"]["execution_path"] == "UNKNOWN"
    registered = envelope["provenance"]["registered_algorithms"]
    assert {entry["key"] for entry in registered} == {
        "planetary_longitudes", "axes_and_placidus_houses",
        "whole_sign_houses", "lunar_nodes", "chiron",
    }
    for entry in registered:
        source = get_algorithm_entry(entry["key"])
        assert entry["source"] == source["source"]
        assert entry["implementation"] == source["implementation"]
        assert entry["version_history"] == "UNKNOWN"

    reference = result["calculation_reference"]
    assert fingerprint(result) == reference["fingerprint"]
    with pytest.raises(KeyError):
        lookup(result, "/calculation_envelope/versions/engine_version")

    claim = CalculationClaim(quote="太阳所在宫位", path="/planets/0/house",
                             value=result["planets"][0]["house"])
    verified = asyncio.run(m.verify_calculation_claims(
        reference=CalculationReference(**reference), claims=[claim]))
    assert verified["counts"]["supported"] == 1
    assert verified["calculation_envelope"]["provenance"]["source_tool"] == "calculate_natal_chart"


def test_render_envelope_preserves_image_and_text_consistency():
    result = asyncio.run(m.render_natal_chart(**BIRTH))
    assert len(result.content) == 2
    assert result.content[1].mimeType == "image/png"
    assert json.loads(result.content[0].text) == result.structuredContent
    assert result.structuredContent["calculation_envelope"]["tool"] == "render_natal_chart"
    assert result.structuredContent["calculation_envelope"]["provenance"]["source_tool"] == "calculate_natal_chart"
    assert "calculation_envelope" not in result.structuredContent["calculation_source"]


def test_independent_tools_do_not_claim_the_natal_implementations():
    for tool in ("get_current_sky", "calculate_aspect_windows"):
        provenance = calculation_envelope(tool, {})["provenance"]
        assert provenance["coverage"] == "unregistered"
        assert provenance["registered_algorithms"] == []
    for tool in ("search_birthplace", "resolve_birth_coordinates"):
        provenance = calculation_envelope(tool, {})["provenance"]
        assert provenance["coverage"] == "not_applicable"
        assert provenance["registered_algorithms"] == []


def test_clarification_is_unchanged():
    result = asyncio.run(m.calculate_natal_chart(year=1990))
    assert result["status"] == "needs_clarification"
    assert "calculation_envelope" not in result
