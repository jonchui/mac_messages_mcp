#!/usr/bin/env bash
set -euo pipefail

# Ensure user-level toolchains are available in launchd shells.
export PATH="$HOME/.local/bin:$PATH"
export NVM_DIR="$HOME/.nvm"
if [ -s "$NVM_DIR/nvm.sh" ]; then
  . "$NVM_DIR/nvm.sh"
fi

REPO_DIR="/Users/jonchui/Library/Mobile Documents/com~apple~CloudDocs/code/mac_messages_mcp"
cd "$REPO_DIR"

HOST="${MCP_PROXY_HOST:-0.0.0.0}"
PORT="${MCP_PROXY_PORT:-8000}"
SERVER_MODE="${MCP_PROXY_SERVER_MODE:-both}"

# Set to 1 to expose through tunnel.gla.ma (recommended if router forwarding is hard)
USE_TUNNEL="${MCP_PROXY_TUNNEL:-1}"
TUNNEL_SUBDOMAIN="${MCP_PROXY_TUNNEL_SUBDOMAIN:-}"

# Optional API key. If empty, proxy runs without auth.
API_KEY="${MCP_PROXY_API_KEY:-}"

CMD=(mcp-proxy --host "$HOST" --port "$PORT")
if [ "$SERVER_MODE" = "sse" ] || [ "$SERVER_MODE" = "stream" ]; then
  CMD+=(--server "$SERVER_MODE")
fi

if [ -n "$API_KEY" ]; then
  CMD+=(--apiKey "$API_KEY")
fi

if [ "$USE_TUNNEL" = "1" ]; then
  CMD+=(--tunnel)
  if [ -n "$TUNNEL_SUBDOMAIN" ]; then
    CMD+=(--tunnelSubdomain "$TUNNEL_SUBDOMAIN")
  fi
fi

CMD+=(-- uv run python -m mac_messages_mcp.server)

echo "Starting MCP proxy..."
echo "host=$HOST port=$PORT mode=$SERVER_MODE tunnel=$USE_TUNNEL subdomain=$TUNNEL_SUBDOMAIN auth=$([ -n "$API_KEY" ] && echo enabled || echo disabled)"
exec "${CMD[@]}"
