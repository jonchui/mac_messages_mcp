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
BACKEND_HOST="${MCP_PROXY_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${MCP_PROXY_BACKEND_PORT:-8001}"

# Set to 1 to expose through tunnel.gla.ma (recommended if router forwarding is hard)
USE_TUNNEL="${MCP_PROXY_TUNNEL:-1}"
TUNNEL_SUBDOMAIN="${MCP_PROXY_TUNNEL_SUBDOMAIN:-}"

# Optional API key. If empty, proxy runs without auth.
API_KEY="${MCP_PROXY_API_KEY:-}"
REPLACE_EXISTING="${MCP_PROXY_REPLACE_EXISTING:-0}"

# If something is already bound to this port, either replace it (opt-in)
# or exit cleanly to avoid duplicate-process churn.
existing_pid="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true)"
if [ -n "$existing_pid" ]; then
  existing_cmd="$(ps -p "$existing_pid" -o command= 2>/dev/null || true)"
  if echo "$existing_cmd" | grep -q "mcp_gateway.py\|mcp-proxy"; then
    if [ "$REPLACE_EXISTING" = "1" ]; then
      kill "$existing_pid" 2>/dev/null || true
      sleep 1
    else
      echo "Service already running on port $PORT (pid $existing_pid); exiting."
      exit 0
    fi
  else
    echo "Port $PORT already in use by another process (pid $existing_pid)."
    exit 1
  fi
fi

# Record what is being launched as "deployed now" metadata.
mkdir -p "$REPO_DIR/.runtime"
GIT_BIN="$(command -v git || true)"
if [ -z "$GIT_BIN" ] && [ -x /usr/bin/git ]; then
  GIT_BIN="/usr/bin/git"
fi
branch="$("$GIT_BIN" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
commit="$("$GIT_BIN" rev-parse --short HEAD 2>/dev/null || echo unknown)"
commit_subject="$("$GIT_BIN" log -1 --pretty=%s 2>/dev/null || echo unknown)"
if [ -n "$("$GIT_BIN" status --porcelain 2>/dev/null || true)" ]; then
  dirty="dirty"
else
  dirty="clean"
fi
if [ "$commit" != "unknown" ] || [ ! -f "$REPO_DIR/.runtime/deployed.json" ]; then
  DEPLOYED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
  BRANCH="$branch" \
  COMMIT="$commit" \
  COMMIT_SUBJECT="$commit_subject" \
  STATE="$dirty" \
  PUBLIC_PORT="$PORT" \
  PROXY_BACKEND="$BACKEND_HOST:$BACKEND_PORT" \
  python3 - <<'PY' > "$REPO_DIR/.runtime/deployed.json"
import json
import os

payload = {
    "deployed_at": os.environ.get("DEPLOYED_AT", "unknown"),
    "branch": os.environ.get("BRANCH", "unknown"),
    "commit": os.environ.get("COMMIT", "unknown"),
    "commit_subject": os.environ.get("COMMIT_SUBJECT", "unknown"),
    "state": os.environ.get("STATE", "unknown"),
    "public_port": int(os.environ.get("PUBLIC_PORT", "0")),
    "proxy_backend": os.environ.get("PROXY_BACKEND", "unknown"),
}
print(json.dumps(payload))
PY
fi

CMD=(mcp-proxy --host "$BACKEND_HOST" --port "$BACKEND_PORT")
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
echo "public_host=$HOST public_port=$PORT backend_host=$BACKEND_HOST backend_port=$BACKEND_PORT mode=$SERVER_MODE tunnel=$USE_TUNNEL subdomain=$TUNNEL_SUBDOMAIN auth=$([ -n "$API_KEY" ] && echo enabled || echo disabled)"

"${CMD[@]}" &
proxy_pid=$!

cleanup() {
  kill "$proxy_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

exec uv run python scripts/mcp_gateway.py --host "$HOST" --port "$PORT" --target "http://$BACKEND_HOST:$BACKEND_PORT" --deploy-info "$REPO_DIR/.runtime/deployed.json"
