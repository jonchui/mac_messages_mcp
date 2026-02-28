#!/usr/bin/env bash
# scripts/deploy.sh <branch>
#
# Restarts the launchd service for the given branch environment.
# Called by GitHub Actions after tests pass.
#
# Branch → launchd service:
#   main    → com.mac-messages-mcp.prod
#   sandbox → com.mac-messages-mcp.sandbox

set -euo pipefail

BRANCH="${1:-sandbox}"

if [[ "$BRANCH" == "main" ]]; then
  ENV="prod"
  PORT=8000
else
  ENV="sandbox"
  PORT=8001
fi

SERVICE="com.mac-messages-mcp.${ENV}"

echo "▶ Deploying branch '${BRANCH}' → environment '${ENV}' (port ${PORT})"

# Reload the launchd plist in case it changed, then restart
launchctl unload "$HOME/Library/LaunchAgents/${SERVICE}.plist" 2>/dev/null || true
launchctl load   "$HOME/Library/LaunchAgents/${SERVICE}.plist"
launchctl start  "${SERVICE}" 2>/dev/null || true

echo "✓ Service '${SERVICE}' restarted"
