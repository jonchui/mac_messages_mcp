#!/usr/bin/env bash
set -euo pipefail

# Single-process MCP over HTTP/SSE for Tailscale or LAN (LaunchAgent-friendly).
# See: mac_messages_mcp/http_server.py, https://github.com/jonchui/mac_messages_mcp/issues/3

export PATH="$HOME/.local/bin:$PATH"
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [ -s "$NVM_DIR/nvm.sh" ]; then
  # shellcheck source=/dev/null
  . "$NVM_DIR/nvm.sh"
fi

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

export MCP_TRANSPORT=sse
export FASTMCP_HOST="${FASTMCP_HOST:-0.0.0.0}"
export FASTMCP_PORT="${FASTMCP_PORT:-8000}"

# Prefer explicit env; else macOS Keychain (same service as legacy mcp-proxy).
KEYCHAIN_SERVICE="${MCP_HTTP_BEARER_KEYCHAIN_SERVICE:-mac-messages-mcp/api-key}"
KEYCHAIN_ACCOUNT="${MCP_HTTP_BEARER_KEYCHAIN_ACCOUNT:-$USER}"
if [ -z "${MAC_MESSAGES_MCP_BEARER_TOKEN:-}" ] && command -v security >/dev/null 2>&1; then
  MAC_MESSAGES_MCP_BEARER_TOKEN="$(
    security find-generic-password -a "$KEYCHAIN_ACCOUNT" -s "$KEYCHAIN_SERVICE" -w 2>/dev/null || true
  )"
  export MAC_MESSAGES_MCP_BEARER_TOKEN
fi

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
DEPLOYED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
  BRANCH="$branch" \
  COMMIT="$commit" \
  COMMIT_SUBJECT="$commit_subject" \
  STATE="$dirty" \
  PUBLIC_PORT="$FASTMCP_PORT" \
  python3 - <<'PY' >"$REPO_DIR/.runtime/deployed.json"
import json
import os

payload = {
    "deployed_at": os.environ.get("DEPLOYED_AT", "unknown"),
    "branch": os.environ.get("BRANCH", "unknown"),
    "commit": os.environ.get("COMMIT", "unknown"),
    "commit_subject": os.environ.get("COMMIT_SUBJECT", "unknown"),
    "state": os.environ.get("STATE", "unknown"),
    "public_port": int(os.environ.get("PUBLIC_PORT", "0")),
    "transport": "sse",
    "process_model": "single_uvicorn",
}
print(json.dumps(payload))
PY

echo "mac-messages-mcp HTTP: host=$FASTMCP_HOST port=$FASTMCP_PORT auth=$([ -n "${MAC_MESSAGES_MCP_BEARER_TOKEN:-}" ] && echo bearer || echo none)"
exec uv run --project "$REPO_DIR" python -m mac_messages_mcp.server
