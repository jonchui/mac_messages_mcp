#!/usr/bin/env python3
"""
List tools and resources from the Mac Messages MCP server.
Use stdio (default) or --url for HTTP/SSE.

Examples:
  uv run python scripts/list_tools.py
  uv run python scripts/list_tools.py --url http://localhost:8000/sse
"""
import argparse
import asyncio
import json
import os
import sys

# Add project root so mac_messages_mcp is importable when using stdio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def list_via_stdio():
    """Spawn server via stdio and list tools (no HTTP server needed)."""
    from mcp.client.stdio import stdio_client
    from mcp.client.stdio import StdioServerParameters
    from mcp.client.session import ClientSession

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mac_messages_mcp.server"],
        env={**os.environ, "MCP_TRANSPORT": "stdio"},
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            resources_result = await session.list_resources()
            return tools_result, resources_result


async def list_via_sse(url: str, api_key: str | None = None):
    """Connect to running HTTP/SSE server and list tools."""
    from mcp.client.sse import sse_client
    from mcp.client.session import ClientSession

    headers = {"X-API-Key": api_key} if api_key else None
    async with sse_client(url, headers=headers) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            resources_result = await session.list_resources()
            return tools_result, resources_result


def main():
    parser = argparse.ArgumentParser(description="List Mac Messages MCP tools and resources")
    parser.add_argument(
        "--url",
        default=None,
        help="SSE endpoint (e.g. http://localhost:8000/sse). If not set, uses stdio (spawns server).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of a readable summary.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Optional X-API-Key header to send when using --url.",
    )
    args = parser.parse_args()

    async def run():
        if args.url:
            tools_result, resources_result = await list_via_sse(args.url, args.api_key)
        else:
            tools_result, resources_result = await list_via_stdio()

        if args.json:
            print(json.dumps({
                "tools": tools_result.model_dump() if hasattr(tools_result, "model_dump") else tools_result,
                "resources": resources_result.model_dump() if hasattr(resources_result, "model_dump") else resources_result,
            }, indent=2, default=str))
            return

        # Readable summary
        print("=== Mac Messages MCP – Tools ===\n")
        tools = getattr(tools_result, "tools", []) or []
        for t in tools:
            name = getattr(t, "name", str(t))
            desc = (getattr(t, "description", None) or "").strip() or "(no description)"
            print(f"  • {name}")
            print(f"    {desc}")
            print()

        print("=== Resources (templates) ===\n")
        resources = getattr(resources_result, "resources", []) or []
        for r in resources:
            uri = getattr(r, "uri", None) or getattr(r, "uriTemplate", str(r))
            name = getattr(r, "name", "") or uri
            print(f"  • {name}")
            print(f"    {uri}")
            print()

        print(f"Total: {len(tools)} tools, {len(resources)} resources")

    asyncio.run(run())


if __name__ == "__main__":
    main()
