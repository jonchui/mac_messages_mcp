#!/usr/bin/env bash
set -euo pipefail

LABEL="com.jonchui.mac-messages-mcp"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
OUT_LOG="$HOME/Library/Logs/mac-messages-mcp.out.log"
ERR_LOG="$HOME/Library/Logs/mac-messages-mcp.err.log"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

PORT="${1:-8000}"
API_KEY="${MCP_PROXY_API_KEY:-}"

echo "== MCP Service Status =="
echo "Label: $LABEL"
echo "Plist: $PLIST"
echo

echo "-- git revision --"
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
  )
else
  echo "git not found"
fi
echo

if launchctl print "gui/$(id -u)/$LABEL" >/tmp/mcp_status.$$ 2>/dev/null; then
  echo "-- launchctl --"
  awk '
    /state = / || /pid = / || /MCP_PROXY_PORT =>/ || /MCP_PROXY_SERVER_MODE =>/ || /MCP_PROXY_TUNNEL =>/ || /MCP_PROXY_HOST =>/
  ' /tmp/mcp_status.$$
else
  echo "-- launchctl --"
  echo "Service not loaded."
fi
rm -f /tmp/mcp_status.$$
echo

echo "-- listening socket --"
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN; then
  :
else
  echo "No process is listening on TCP $PORT."
fi
echo

echo "-- local endpoint probe --"
if [[ -n "$API_KEY" ]]; then
  curl -sS -i --max-time 4 -H "X-API-Key: $API_KEY" "http://127.0.0.1:$PORT/mcp" | sed -n '1,10p' || true
  echo "---"
  curl -sS -i --max-time 4 -H "X-API-Key: $API_KEY" "http://127.0.0.1:$PORT/sse" | sed -n '1,12p' || true
else
  curl -sS -i --max-time 4 "http://127.0.0.1:$PORT/mcp" | sed -n '1,10p' || true
  echo "---"
  curl -sS -i --max-time 4 "http://127.0.0.1:$PORT/sse" | sed -n '1,12p' || true
  echo "(Tip: set MCP_PROXY_API_KEY env var before running for authenticated probe.)"
fi
echo

echo "-- last log lines (out) --"
tail -n 20 "$OUT_LOG" 2>/dev/null || echo "No out log yet."
echo
echo "-- last log lines (err) --"
tail -n 20 "$ERR_LOG" 2>/dev/null || echo "No err log yet."

