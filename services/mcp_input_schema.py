"""Advertise scalar unions without coercible first-match branches in MCP discovery."""
from mcp.server.fastmcp import FastMCP


def preserve_scalar_unions(schema):
    for key in ("properties", "$defs"):
        for child in schema.get(key, {}).values():
            preserve_scalar_unions(child)
    for key in ("items", "additionalProperties"):
        child = schema.get(key)
        if isinstance(child, dict):
            preserve_scalar_unions(child)
    choices = schema.get("anyOf", [])
    for choice in choices:
        preserve_scalar_unions(choice)
    if not choices:
        return
    primitives = {"null", "string", "number", "integer", "boolean"}
    if all(set(choice) == {"type"} and isinstance(choice["type"], str)
           and choice["type"] in primitives for choice in choices):
        schema["type"] = [choice["type"] for choice in choices]
    elif len(choices) == 2 and choices[1] == {"type": "null"}:
        branch = choices[0]
        if (branch.get("type") not in ("string", "number", "integer")
                or not set(branch) <= {"type", "minimum", "maximum", "maxLength", "minLength"}):
            return
        # Numeric and length bounds apply only to their own instance types.
        schema.update(branch)
        schema["type"] = [branch["type"], "null"]
    else:
        return
    del schema["anyOf"]


class DiscoveryFastMCP(FastMCP):
    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            preserve_scalar_unions(tool.inputSchema)
        return tools
