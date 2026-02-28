#!/usr/bin/env bash
# scripts/health-check.sh <branch>
#
# Polls the OAuth metadata endpoint until the service answers or times out.

set -euo pipefail

BRANCH="${1:-sandbox}"
[[ "$BRANCH" == "main" ]] && PORT=8000 || PORT=8001

URL="http://localhost:${PORT}/.well-known/oauth-authorization-server"
MAX_WAIT=30

echo "▶ Health check: ${URL}"
for i in $(seq 1 "$MAX_WAIT"); do
  if curl -sf "$URL" -o /dev/null --max-time 2; then
    echo "✓ Service is up on port ${PORT} (${i}s)"
    exit 0
  fi
  sleep 1
done

echo "✗ Service did not respond on port ${PORT} after ${MAX_WAIT}s"
exit 1
