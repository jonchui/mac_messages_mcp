#!/usr/bin/env python3
"""
Sample MCP client: lists tools and calls tool_get_recent_messages (and optionally
tool_check_db_access) against the Mac Messages MCP server.

Use this to verify the server works locally, independent of Poke or other clients.

Usage (from repo root):
  # Test via stdio (spawns the server process)
  uv run python scripts/test_mcp_client.py

  # Test via HTTP/SSE (server must already be running, e.g. behind mcp-proxy)
  uv run python scripts/test_mcp_client.py http://localhost:8000/sse

  # With bearer token (e.g. for remote proxy)
  uv run python scripts/test_mcp_client.py https://your-host/sse --header "Authorization: Bearer YOUR_TOKEN"
"""

import argparse
import sys
from pathlib import Path

# Add project root so we can run as script
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import anyio
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client


async def run_tests(read_stream, write_stream):
    """List tools and call a couple of sample tools."""
    async with ClientSession(read_stream, write_stream) as session:
        await session.initialize()
        caps = session.get_server_capabilities()
        print("Server initialized.")
        if caps:
            print("  Capabilities:", caps.model_dump(exclude_none=True))

        # List tools
        result = await session.list_tools()
        names = [t.name for t in result.tools]
        print(f"\nTools ({len(names)}): {names}")

        # Call tool_check_db_access (no args, good sanity check)
        print("\n--- Calling tool_check_db_access ---")
        r = await session.call_tool("tool_check_db_access", {})
        if r.isError:
            print("Error:", r.content)
        else:
            for block in r.content:
                if hasattr(block, "text") and block.text:
                    print(block.text)

        # Call tool_get_recent_messages
        print("\n--- Calling tool_get_recent_messages(hours=24) ---")
        r = await session.call_tool("tool_get_recent_messages", {"hours": 24})
        if r.isError:
            print("Error:", r.content)
        else:
            for block in r.content:
                if hasattr(block, "text") and block.text:
                    text = block.text
                    print(text[:2000] + "..." if len(text) > 2000 else text)

        print("\nDone. Server and tools work locally.")


async def main_stdio():
    """Run server as subprocess and talk over stdio."""
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mac_messages_mcp.server"],
    )
    async with stdio_client(server) as (read_stream, write_stream):
        await run_tests(read_stream, write_stream)


async def main_sse(url: str, headers: dict | None = None):
    """Connect to server over HTTP SSE."""
    async with sse_client(url, headers=headers) as (read_stream, write_stream):
        await run_tests(read_stream, write_stream)


def parse_headers(header_args: list[str]) -> dict:
    out = {}
    for h in header_args:
        if ":" in h:
            k, v = h.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def cli():
    parser = argparse.ArgumentParser(
        description="Test Mac Messages MCP server: list tools and call sample tools."
    )
    parser.add_argument(
        "url",
        nargs="?",
        default=None,
        help="Optional SSE URL (e.g. http://localhost:8000/sse). If omitted, use stdio (spawn server).",
    )
    parser.add_argument(
        "--header",
        "-H",
        action="append",
        default=[],
        metavar="Header: Value",
        help="HTTP header for SSE (e.g. 'Authorization: Bearer TOKEN'). Can repeat.",
    )
    args = parser.parse_args()
    headers = parse_headers(args.header) if args.header else None

    if args.url:
        anyio.run(
            lambda: main_sse(args.url, headers),
            backend="asyncio",
        )
    else:
        anyio.run(
            lambda: main_stdio(),
            backend="asyncio",
        )


if __name__ == "__main__":
    try:
        cli()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nError: {e}", file=sys.stderr)
        if "401" in str(e):
            print(
                "Tip: If the proxy uses API key auth, run with:\n"
                "  --header 'Authorization: Bearer YOUR_TOKEN'\n"
                "  or --header 'X-API-Key: YOUR_TOKEN'",
                file=sys.stderr,
            )
        sys.exit(1)
