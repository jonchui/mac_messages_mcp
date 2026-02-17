#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
SERVICE="${MCP_PROXY_API_KEY_KEYCHAIN_SERVICE:-mac-messages-mcp/api-key}"
ACCOUNT="${MCP_PROXY_API_KEY_KEYCHAIN_ACCOUNT:-$USER}"

API_KEY="${1:-}"
if [ -z "$API_KEY" ]; then
  printf "Enter API key to store in macOS Keychain: " >&2
  read -r -s API_KEY
  echo >&2
fi

if [ -z "$API_KEY" ]; then
  echo "❌ API key cannot be empty."
  exit 1
fi

security add-generic-password -U -a "$ACCOUNT" -s "$SERVICE" -w "$API_KEY" >/dev/null
echo "✅ Stored API key in Keychain (service=$SERVICE account=$ACCOUNT)"

echo "Syncing LaunchAgent template and restarting service..."
"$REPO_DIR/scripts/sync_launchagent.sh"
"$REPO_DIR/scripts/restart.sh"
