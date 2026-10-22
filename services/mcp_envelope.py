"""Declared MCP provenance, kept separate from calculation facts.

The registry describes known dependencies of a tool, not the execution path of
an individual request. In particular, caches and ephemeris fallbacks are not
observed here. Unregistered techniques must never be attributed to one of the
five natal entries merely because they use the same ephemeris library.
"""

from algorithm_registry import get_algorithm_entry
from services.mcp_validation import RENDER_SOURCES
from versioning import get_version_info


SCHEMA_VERSION = "calculation-envelope-v1"

NATAL_SOURCE_TOOLS = frozenset({
    "calculate_natal_chart",
    "render_natal_chart",
    "render_jones_pattern",
    "calculate_classical_factors",
    "calculate_lots",
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
    "calculate_house_rulers",
    "calculate_zodiacal_releasing_l4",
    "calculate_lifetime_transit_summary",
    "calculate_sky_chart",
    "render_sky_chart",
    "render_transit_biwheel",
    "render_solar_arc_biwheel",
    "verify_natal_claims",
    "calculate_davison_chart",
    "render_davison_chart",
    "calculate_relocation_chart",
    "render_relocation_chart",
    "render_saturn_jupiter_cycles",
})

INDEPENDENT_CALCULATION_TOOLS = frozenset({
    "calculate_natal_salience",
    "calculate_natal_structure_graph",
    "scan_planetary_aspects",
    "get_current_sky",
    "calculate_aspect_windows",
    "calculate_lunar_return",
    "render_lunar_return_chart",
    "calculate_secondary_progressions",
    "render_secondary_progressions_chart",
    "calculate_timeline_synthesis",
})

UTILITY_TOOLS = frozenset({
    "search_birthplace",
    "resolve_birth_coordinates",
    "get_capabilities",
    "get_agent_protocol",
    "recommend_workflow",
})

DYNAMIC_SOURCE_TOOLS = frozenset({"verify_calculation_claims"})

REGISTERED_NATAL_KEYS = (
    "planetary_longitudes",
    "axes_and_placidus_houses",
    "whole_sign_houses",
    "lunar_nodes",
    "chiron",
)

_ENTRY_FIELDS = (
    "key", "source", "implementation", "file_path", "code_anchor",
    "code_location", "fallback", "precision", "version_history",
)


def registered_tools() -> frozenset[str]:
    """The provenance table is explicit; future tools must be audited first."""
    return (NATAL_SOURCE_TOOLS | INDEPENDENT_CALCULATION_TOOLS |
            UTILITY_TOOLS | DYNAMIC_SOURCE_TOOLS)


def _reference_tool(arguments: dict) -> str | None:
    reference = arguments.get("reference")
    if isinstance(reference, dict):
        return reference.get("tool")
    return getattr(reference, "tool", None)


def declared_provenance(tool: str, arguments: dict) -> dict:
    """Return the registered subset, without inferring a request's runtime path."""
    if tool not in registered_tools():
        raise ValueError(f"No audited provenance classification for {tool}")

    source_tool = (_reference_tool(arguments) if tool in DYNAMIC_SOURCE_TOOLS
                   else RENDER_SOURCES.get(tool, tool))
    if source_tool in NATAL_SOURCE_TOOLS:
        coverage = "partial"
        scope = "declared_dependencies"
        keys = REGISTERED_NATAL_KEYS
    elif source_tool in INDEPENDENT_CALCULATION_TOOLS:
        coverage = "unregistered"
        scope = "unregistered_calculation"
        keys = ()
    elif source_tool in UTILITY_TOOLS:
        coverage = "not_applicable"
        scope = "not_applicable"
        keys = ()
    else:
        coverage = "UNKNOWN"
        scope = "UNKNOWN"
        keys = ()

    entries = []
    for key in keys:
        entry = get_algorithm_entry(key)
        if entry is None:
            raise RuntimeError(f"Missing algorithm registry entry: {key}")
        entries.append({field: entry[field] for field in _ENTRY_FIELDS})

    provenance = {
        "scope": scope,
        "coverage": coverage,
        "registered_algorithms": entries,
        "execution_path": "UNKNOWN",
    }
    if tool in RENDER_SOURCES or tool in DYNAMIC_SOURCE_TOOLS:
        provenance["source_tool"] = source_tool

    return provenance


def calculation_envelope(tool: str, arguments: dict) -> dict:
    """Build a small, honest provenance description for one successful result."""
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": tool,
        "versions": get_version_info(),
        "provenance": declared_provenance(tool, arguments),
    }
