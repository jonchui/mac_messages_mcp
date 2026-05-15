#!/usr/bin/env bash
set -euo pipefail
#
# Run on the Mac mini (after SSH or at the console) from any cwd — resolves repo via script path.
# Usage: ./scripts/deploy_mac_mini.sh [branch]   (default: main)
#
# Appends one JSON line to deploy/history.jsonl for audit trail.

BRANCH="${1:-main}"
SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

export PATH="${HOME}/.local/bin:${PATH}"

if ! command -v git >/dev/null 2>&1; then
  echo "❌ git not found" >&2
  exit 1
fi

echo "== deploy_mac_mini: repo=$REPO_DIR branch=$BRANCH =="
git fetch origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

SHORT_SHA="$(git rev-parse --short HEAD)"

if [ -x "$REPO_DIR/scripts/sync_launchagent.sh" ]; then
  echo "== sync LaunchAgent plist from template =="
  "$REPO_DIR/scripts/sync_launchagent.sh"
fi

echo "== restart LaunchAgent job =="
"$REPO_DIR/scripts/restart.sh"

mkdir -p "$REPO_DIR/deploy"
LOG="$REPO_DIR/deploy/history.jsonl"
TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
HOST="$(hostname -s || hostname || echo unknown)"
OPERATOR="${DEPLOY_OPERATOR:-$(whoami)}"
printf '%s\n' "{\"ts\":\"${TS}\",\"host\":\"${HOST}\",\"branch\":\"${BRANCH}\",\"commit\":\"${SHORT_SHA}\",\"operator\":\"${OPERATOR}\",\"path\":\"${REPO_DIR}\"}" >>"$LOG"
echo "== appended deploy record to $LOG =="
tail -n 3 "$LOG"

PORT="${FASTMCP_PORT:-8000}"
TOKEN="${MAC_MINI_SMOKE_TOKEN:-${MAC_MESSAGES_MCP_BEARER_TOKEN:-${MCP_PROXY_API_KEY:-}}}"
echo "== smoke: GET /healthz =="
set +e
if [[ -n "$TOKEN" ]]; then
  curl -sS -f --max-time 5 -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:${PORT}/healthz" && echo
else
  curl -sS -f --max-time 5 "http://127.0.0.1:${PORT}/healthz" && echo
fi
RC=$?
set -e
if [ "$RC" != 0 ]; then
  echo "⚠️  /healthz failed (RC=$RC). Check ~/Library/Logs/mac-messages-mcp.err.log and plist ProgramArguments path."
  exit "$RC"
fi
echo "✅ deploy_mac_mini complete"
