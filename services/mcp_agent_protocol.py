"""One source document for the agent-protocol tool, resource and prompt."""

from pathlib import Path


URI = "hellenicstar://agent-protocol"
PROMPT_NAME = "hellenicstar_agent_protocol"
DOCUMENT_PATH = Path(__file__).resolve().parent.parent / "docs" / "mcp-agent-protocol.md"


def protocol_text() -> str:
    return DOCUMENT_PATH.read_text(encoding="utf-8")
