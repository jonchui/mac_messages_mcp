#!/usr/bin/env bash
set -euo pipefail

LABEL="com.jonchui.mac-messages-mcp"
PORT="${1:-8000}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
API_KEY="${MCP_PROXY_API_KEY:-}"

echo "Stopping stale MCP processes (if any)..."
pkill -f "mcp-proxy" 2>/dev/null || true
pkill -f "uv run python -m mac_messages_mcp.server" 2>/dev/null || true

echo "Restarting LaunchAgent: $LABEL"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
sleep 2

echo
echo "Repo revision:"
if command -v git >/dev/null 2>&1; then
  (
    cd "$REPO_DIR"
    branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
    sha="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
      dirty="dirty"
    else
      dirty="clean"
    fi
    echo "branch=$branch commit=$sha state=$dirty"
    mkdir -p .runtime
    cat > .runtime/deployed.json <<EOF
{"deployed_at":"$(date -u +"%Y-%m-%dT%H:%M:%SZ")","branch":"$branch","commit":"$sha","state":"$dirty","public_port":$PORT}
EOF
  )
else
  echo "git not found"
fi

echo
echo "LaunchAgent status:"
launchctl print "gui/$(id -u)/$LABEL" | awk '
  /state = / || /pid = / || /MCP_PROXY_PORT =>/ || /MCP_PROXY_SERVER_MODE =>/ || /MCP_PROXY_TUNNEL =>/
'

echo
echo "Listening on TCP $PORT:"
lsof -nP -iTCP:"$PORT" -sTCP:LISTEN || true

echo
echo "Endpoint probes:"
if [[ -n "$API_KEY" ]]; then
  curl -sS -i --max-time 4 -H "X-API-Key: $API_KEY" "http://127.0.0.1:$PORT/mcp" | sed -n '1,10p' || true
  echo "---"
  curl -sS -i --max-time 4 -H "X-API-Key: $API_KEY" "http://127.0.0.1:$PORT/sse" | sed -n '1,12p' || true
else
  curl -sS -i --max-time 4 "http://127.0.0.1:$PORT/mcp" | sed -n '1,10p' || true
  echo "---"
  curl -sS -i --max-time 4 "http://127.0.0.1:$PORT/sse" | sed -n '1,12p' || true
fi

echo
echo "Tip: run ./scripts/status.sh for full diagnostics and logs."
