#!/usr/bin/env bash
# Run Mac Messages MCP with OAuth 2.0 + optional SSL.
# Use this to connect the server to Claude.ai as a custom connector.
#
# Quick start (using ngrok for HTTPS):
#   Terminal A:  ./scripts/run-oauth-server.sh --ngrok
#   Terminal B:  ngrok http 8000   # copy the https URL
#   Then re-run: EXTERNAL_URL=https://abc123.ngrok.io ./scripts/run-oauth-server.sh
#
# With your own SSL cert:
#   EXTERNAL_URL=https://your-domain.com \
#     SSL_CERT=/path/to/cert.pem \
#     SSL_KEY=/path/to/key.pem \
#     ./scripts/run-oauth-server.sh

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ -z "$EXTERNAL_URL" ]; then
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Mac Messages MCP – OAuth Server"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "  EXTERNAL_URL is required. This is the public HTTPS URL that"
  echo "  Claude.ai will use to reach this server."
  echo ""
  echo "  Easiest option – ngrok HTTPS tunnel:"
  echo "    1. Install ngrok: https://ngrok.com/download"
  echo "    2. In a separate terminal:  ngrok http ${PORT:-8000}"
  echo "    3. Copy the Forwarding https://... URL, then:"
  echo "       EXTERNAL_URL=https://abc123.ngrok.io ./scripts/run-oauth-server.sh"
  echo ""
  echo "  With your own cert:"
  echo "    EXTERNAL_URL=https://your-domain.com \\"
  echo "      SSL_CERT=cert.pem SSL_KEY=key.pem \\"
  echo "      ./scripts/run-oauth-server.sh"
  echo ""
  exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Mac Messages MCP – OAuth Server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  External URL : $EXTERNAL_URL"
echo "  MCP endpoint : $EXTERNAL_URL/sse    ← paste this into Claude.ai"
echo "  Port         : ${PORT:-8000}"
echo ""

exec uv run python scripts/run_oauth_server.py
