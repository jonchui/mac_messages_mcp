#!/usr/bin/env bash
# Run Mac Messages MCP over HTTP (SSE) for remote clients.
# Listens on 0.0.0.0:8000 by default. Override with FASTMCP_HOST / FASTMCP_PORT.
export PATH="${HOME}/.local/bin:${PATH}"
cd "$(dirname "$0")/.."
export MCP_TRANSPORT=sse
export FASTMCP_HOST="${FASTMCP_HOST:-0.0.0.0}"
export FASTMCP_PORT="${FASTMCP_PORT:-8000}"
echo "Starting Mac Messages MCP on http://${FASTMCP_HOST}:${FASTMCP_PORT} (SSE at /sse)"
exec uv run python -m mac_messages_mcp.server
