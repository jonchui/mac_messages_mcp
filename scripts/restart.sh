#!/usr/bin/env bash
set -euo pipefail

LABEL="com.jonchui.mac-messages-mcp"
PORT="${1:-8000}"

echo "Stopping stale MCP processes (if any)..."
pkill -f "mcp-proxy" 2>/dev/null || true
pkill -f "uv run python -m mac_messages_mcp.server" 2>/dev/null || true

echo "Restarting LaunchAgent: $LABEL"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
sleep 2

echo
echo "LaunchAgent status:"
launchctl print "gui/$(id -u)/$LABEL" | awk '
  /state = / || /pid = / || /MCP_PROXY_PORT =>/ || /MCP_PROXY_SERVER_MODE =>/ || /MCP_PROXY_TUNNEL =>/
'

echo
echo "Listening on TCP $PORT:"
lsof -nP -iTCP:"$PORT" -sTCP:LISTEN || true

echo
echo "Tip: run ./scripts/status.sh for full diagnostics."
