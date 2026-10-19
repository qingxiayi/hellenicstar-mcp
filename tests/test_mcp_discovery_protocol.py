"""Discovery is generated from the live registry; protocol surfaces share one document."""

import asyncio
from copy import deepcopy

import mcp_server as m
from algorithm_registry import list_algorithms
from services.mcp_agent_protocol import PROMPT_NAME, URI, protocol_text
from services.mcp_validation import validate_meta_output
from versioning import get_version_info


def test_capabilities_reflect_live_tools_and_algorithm_registry():
    capabilities = asyncio.run(m.get_capabilities())
    exposed = {tool.name: tool for tool in asyncio.run(m.mcp.list_tools())}
    listed = {row["name"]: row for row in capabilities["tools"]}

    assert capabilities["status"] == "ok"
    assert capabilities["schema_version"] == "mcp-capabilities-v1"
    assert capabilities["tool_count"] == len(exposed) == 44
    assert set(listed) == set(exposed)
    assert capabilities["algorithm_registry"] == list_algorithms()
    assert capabilities["versions"] == get_version_info()
    for name, tool in exposed.items():
        assert listed[name]["description"] == (tool.description or "")
        assert listed[name]["input_schema"] == tool.inputSchema

    natal_keys = set(list_algorithms())
    assert set(listed["calculate_natal_chart"]["registered_algorithm_keys"]) == natal_keys
    assert listed["get_current_sky"]["registered_algorithm_keys"] == []
    assert listed["calculate_aspect_windows"]["provenance_coverage"] == "unregistered"
    assert listed["get_capabilities"]["provenance_coverage"] == "not_applicable"
    assert "calculation_reference" not in capabilities
    assert validate_meta_output("get_capabilities", capabilities) == []


def test_discovery_contract_rejects_missing_tools_and_registry_drift():
    capabilities = asyncio.run(m.get_capabilities())
    wrong_count = deepcopy(capabilities)
    wrong_count["tool_count"] -= 1
    assert validate_meta_output("get_capabilities", wrong_count)[0]["rule"] == "count_matches_tools"

    wrong_registry = deepcopy(capabilities)
    del wrong_registry["algorithm_registry"]["lunar_nodes"]
    assert validate_meta_output("get_capabilities", wrong_registry)[0]["rule"] == "registry_matches_source"


def test_agent_protocol_tool_resource_and_prompt_share_exact_document():
    tool = asyncio.run(m.get_agent_protocol())
    resource = asyncio.run(m.mcp.read_resource(URI))
    prompt = asyncio.run(m.mcp.get_prompt(PROMPT_NAME))
    text = protocol_text()

    assert tool["status"] == "ok"
    assert tool["uri"] == URI
    assert tool["content"] == resource[0].content == prompt.messages[0].content.text == text
    assert "calculation_reference" not in tool
    assert tool["calculation_envelope"]["provenance"]["coverage"] == "not_applicable"
    assert validate_meta_output("get_agent_protocol", tool) == []
    assert any(str(item.uri) == URI for item in asyncio.run(m.mcp.list_resources()))
    assert any(item.name == PROMPT_NAME for item in asyncio.run(m.mcp.list_prompts()))
