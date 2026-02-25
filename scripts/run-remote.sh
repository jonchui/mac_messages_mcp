#!/usr/bin/env bash
# Run the Mac Messages MCP remote server (OAuth + SSE) on the iMac.
#
# This is the server that Claude Code connects to (via VPS reverse proxy).
#
# Usage:
#   ./scripts/run-remote.sh https://mcp.yourdomain.com
#   PORT=9000 ./scripts/run-remote.sh https://mcp.yourdomain.com

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

SERVER_URL="${1:?Usage: $0 <public-server-url> (e.g., https://mcp.yourdomain.com)}"
PORT="${PORT:-8000}"

echo "=== Mac Messages MCP – Remote Server ==="
echo "Public URL:  ${SERVER_URL}"
echo "Local port:  ${PORT}"
echo "State dir:   ~/.mac-messages-mcp/"
echo ""
echo "OAuth endpoints:"
echo "  Discovery: ${SERVER_URL}/.well-known/oauth-authorization-server"
echo "  Register:  ${SERVER_URL}/register"
echo "  Authorize: ${SERVER_URL}/authorize"
echo "  Token:     ${SERVER_URL}/token"
echo ""
echo "MCP endpoint:"
echo "  SSE:       ${SERVER_URL}/sse"
echo ""

exec uv run python -m mac_messages_mcp.remote \
    --server-url "$SERVER_URL" \
    --port "$PORT"
