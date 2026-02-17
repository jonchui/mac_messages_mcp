#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
src="$repo_root/deploy/launchagents/com.jonchui.mac-messages-mcp.plist.template"
dst="$HOME/Library/LaunchAgents/com.jonchui.mac-messages-mcp.plist"

if [ ! -f "$src" ]; then
  echo "❌ Missing template: $src"
  exit 1
fi

cp "$src" "$dst"
/usr/bin/plutil -lint "$dst" >/dev/null

echo "✅ Synced LaunchAgent template -> $dst"
echo "   (Run ./scripts/restart.sh to apply immediately.)"
