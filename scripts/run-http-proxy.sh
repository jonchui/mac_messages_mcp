#!/usr/bin/env bash
# Run Mac Messages MCP behind mcp-proxy so it's reachable over HTTP (e.g. for Poke.com / WAN clients).
# From repo root: ./scripts/run-http-proxy.sh
# Requires: npm/npx, mcp-proxy (npm install -g mcp-proxy), and uv venv + uv pip install -e . in repo.

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PORT="${PORT:-8000}"

if ! command -v npx &>/dev/null; then
  echo "npx not found. Install Node.js/npm first."
  exit 1
fi

echo "Starting Mac Messages MCP HTTP proxy on port ${PORT}"
echo "  SSE:    http://<this-machine>:${PORT}/sse"
echo "  Stream: http://<this-machine>:${PORT}/mcp"
echo "Use ngrok or port forwarding to expose to the internet, then point Poke.com at the /sse or /mcp URL."
echo ""

exec npx mcp-proxy --port "$PORT" -- uv run python -m mac_messages_mcp.server
