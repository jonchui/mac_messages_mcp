#!/usr/bin/env bash
# scripts/setup-services.sh
#
# One-time setup: installs launchd services for production and sandbox.
# Run this once on your Mac mini after cloning the repo.
#
# What it does:
#   1. Asks for your domain names
#   2. Fills in the plist templates with your repo path, uv path, and URLs
#   3. Installs plists to ~/Library/LaunchAgents/
#   4. Loads (starts) both services
#   5. Creates a logs/ directory
#
# Re-run any time you want to change the URLs.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
PLIST_TEMPLATE_DIR="$REPO_ROOT/config/launchd"

# ── Detect uv ─────────────────────────────────────────────────────────────────
UV_PATH="$(command -v uv 2>/dev/null || true)"
if [[ -z "$UV_PATH" ]]; then
  echo "Error: 'uv' not found in PATH. Install it: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Mac Messages MCP – Service Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Detected:"
echo "  Repo : $REPO_ROOT"
echo "  uv   : $UV_PATH"
echo ""

# ── Prompt for URLs ───────────────────────────────────────────────────────────
echo "Enter your Cloudflare Tunnel HTTPS URLs (no trailing slash)."
echo "  Example prod    : https://messages.yourdomain.com"
echo "  Example sandbox : https://sandbox.yourdomain.com"
echo ""

read -rp "Production URL  : " PROD_URL
read -rp "Sandbox URL     : " SANDBOX_URL

if [[ -z "$PROD_URL" || -z "$SANDBOX_URL" ]]; then
  echo "Error: both URLs are required."
  exit 1
fi

# ── Create logs directory ─────────────────────────────────────────────────────
mkdir -p "$REPO_ROOT/logs"

# ── Generate plists ───────────────────────────────────────────────────────────
install_plist() {
  local template="$1"
  local dest="$2"

  sed \
    -e "s|__REPO_PATH__|${REPO_ROOT}|g" \
    -e "s|__UV_PATH__|${UV_PATH}|g" \
    -e "s|__PROD_EXTERNAL_URL__|${PROD_URL}|g" \
    -e "s|__SANDBOX_EXTERNAL_URL__|${SANDBOX_URL}|g" \
    "$template" > "$dest"

  echo "  Installed: $dest"
}

echo ""
echo "Installing launchd services..."

install_plist \
  "$PLIST_TEMPLATE_DIR/com.mac-messages-mcp.prod.plist" \
  "$LAUNCH_AGENTS/com.mac-messages-mcp.prod.plist"

install_plist \
  "$PLIST_TEMPLATE_DIR/com.mac-messages-mcp.sandbox.plist" \
  "$LAUNCH_AGENTS/com.mac-messages-mcp.sandbox.plist"

# ── Load services ─────────────────────────────────────────────────────────────
echo ""
echo "Loading services..."

for SVC in prod sandbox; do
  LABEL="com.mac-messages-mcp.${SVC}"
  launchctl unload "$LAUNCH_AGENTS/${LABEL}.plist" 2>/dev/null || true
  launchctl load   "$LAUNCH_AGENTS/${LABEL}.plist"
  echo "  Started: $LABEL"
done

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete!"
echo ""
echo "  Production  → port 8000  →  $PROD_URL/sse"
echo "  Sandbox     → port 8001  →  $SANDBOX_URL/sse"
echo ""
echo "  Logs: $REPO_ROOT/logs/"
echo ""
echo "  Check status:"
echo "    launchctl list | grep mac-messages-mcp"
echo ""
echo "  Next step: configure Cloudflare Tunnel (see config/cloudflared.yml)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
