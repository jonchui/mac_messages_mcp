#!/usr/bin/env bash
# =============================================================================
#  scripts/setup-host.sh
#
#  One-shot installer for Mac Messages MCP on any Mac.
#  Safe to re-run – checks before installing/configuring each component.
#
#  What it sets up:
#    1. Homebrew (if missing)
#    2. uv  – Python package manager
#    3. cloudflared – Cloudflare Tunnel (free HTTPS, no port forwarding)
#    4. gh  – GitHub CLI (used to fetch runner registration token)
#    5. Python dependencies  (uv sync)
#    6. launchd services     (prod :8000, sandbox :8001, auto-restart)
#    7. Cloudflare Tunnel    (routes your domain to the local ports)
#    8. GitHub Actions runner (self-hosted, polls GitHub – no inbound ports)
#
#  Usage:
#    cd /path/to/mac_messages_mcp
#    bash scripts/setup-host.sh
# =============================================================================

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log()  { echo -e "${CYAN}▶${RESET} $*"; }
ok()   { echo -e "${GREEN}✓${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET}  $*"; }
die()  { echo -e "${RED}✗${RESET}  $*" >&2; exit 1; }
hr()   { echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"; }

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env.host"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
PLIST_DIR="$REPO_ROOT/config/launchd"
RUNNER_DIR="$REPO_ROOT/actions-runner"

# ── Load saved config (if re-running) ────────────────────────────────────────
PROD_URL=""
SANDBOX_URL=""
GITHUB_REPO=""   # e.g.  owner/repo-name
CF_TUNNEL_NAME="mac-messages-mcp"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  warn "Loaded existing config from .env.host"
fi

# ── Helper: save a key=value to .env.host ─────────────────────────────────────
save_cfg() { grep -v "^${1}=" "$ENV_FILE" 2>/dev/null > "${ENV_FILE}.tmp" || true; echo "${1}=${2}" >> "${ENV_FILE}.tmp"; mv "${ENV_FILE}.tmp" "$ENV_FILE"; }

# ── Helper: prompt with a default ─────────────────────────────────────────────
ask() {
  local var_name="$1" prompt="$2" default="${3:-}"
  local current="${!var_name:-}"
  if [[ -n "$current" ]]; then
    read -rp "$(echo -e "${prompt} [${YELLOW}${current}${RESET}]: ")" input
    [[ -z "$input" ]] && input="$current"
  elif [[ -n "$default" ]]; then
    read -rp "$(echo -e "${prompt} (${default}): ")" input
    [[ -z "$input" ]] && input="$default"
  else
    read -rp "$(echo -e "${prompt}: ")" input
  fi
  printf -v "$var_name" '%s' "$input"
}

# ─────────────────────────────────────────────────────────────────────────────
hr
echo -e "${BOLD}  Mac Messages MCP – Host Setup${RESET}"
hr
echo ""

# ── STEP 1: macOS check ───────────────────────────────────────────────────────
log "Checking platform..."
[[ "$(uname)" == "Darwin" ]] || die "This script is macOS-only (requires macOS Messages + launchd)."
ARCH="$(uname -m)"                               # arm64 or x86_64
RUNNER_ARCH="$( [[ "$ARCH" == "arm64" ]] && echo arm64 || echo x64 )"
ok "macOS detected (${ARCH})"

# ── STEP 2: Homebrew ──────────────────────────────────────────────────────────
log "Checking Homebrew..."
if ! command -v brew &>/dev/null; then
  log "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Add brew to PATH for arm64 (Apple Silicon)
  if [[ "$ARCH" == "arm64" ]] && ! command -v brew &>/dev/null; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  fi
fi
ok "Homebrew $(brew --version | head -1)"

# ── STEP 3: uv ────────────────────────────────────────────────────────────────
log "Checking uv..."
if ! command -v uv &>/dev/null; then
  log "Installing uv..."
  brew install uv
fi
UV_PATH="$(command -v uv)"
ok "uv ${UV_PATH}"

# ── STEP 4: cloudflared ───────────────────────────────────────────────────────
log "Checking cloudflared..."
if ! command -v cloudflared &>/dev/null; then
  log "Installing cloudflared..."
  brew install cloudflared
fi
ok "cloudflared $(cloudflared --version 2>&1 | head -1)"

# ── STEP 5: gh CLI (optional but enables automatic runner token) ──────────────
log "Checking gh CLI..."
if ! command -v gh &>/dev/null; then
  log "Installing GitHub CLI (gh)..."
  brew install gh
fi
ok "gh $(gh --version | head -1)"

# ── STEP 6: Prompt for configuration ─────────────────────────────────────────
echo ""
hr
echo -e "${BOLD}  Configuration${RESET}"
hr
echo ""
echo "  Press Enter to keep the value shown in brackets."
echo ""

ask PROD_URL    "Production HTTPS URL (no trailing slash)"    "https://messages.yourdomain.com"
ask SANDBOX_URL "Sandbox HTTPS URL    (no trailing slash)"    "https://sandbox.yourdomain.com"
ask GITHUB_REPO "GitHub repo          (owner/repo)"

# Basic validation
[[ "$PROD_URL"    == https://* ]] || die "PROD_URL must start with https://"
[[ "$SANDBOX_URL" == https://* ]] || die "SANDBOX_URL must start with https://"
[[ "$GITHUB_REPO" == */* ]]       || die "GITHUB_REPO must be owner/repo-name"

# Persist config
touch "$ENV_FILE"
save_cfg PROD_URL    "$PROD_URL"
save_cfg SANDBOX_URL "$SANDBOX_URL"
save_cfg GITHUB_REPO "$GITHUB_REPO"
ok "Config saved to .env.host"

# ── STEP 7: Python dependencies ───────────────────────────────────────────────
echo ""
log "Syncing Python dependencies..."
cd "$REPO_ROOT"
uv sync
ok "Python dependencies up to date"

# ── STEP 8: launchd services ─────────────────────────────────────────────────
echo ""
hr
echo -e "${BOLD}  launchd Services${RESET}"
hr
echo ""
mkdir -p "$REPO_ROOT/logs"

install_plist() {
  local template="$1" dest="$2"
  sed \
    -e "s|__REPO_PATH__|${REPO_ROOT}|g" \
    -e "s|__UV_PATH__|${UV_PATH}|g" \
    -e "s|__PROD_EXTERNAL_URL__|${PROD_URL}|g" \
    -e "s|__SANDBOX_EXTERNAL_URL__|${SANDBOX_URL}|g" \
    "$template" > "$dest"
}

for ENV_NAME in prod sandbox; do
  LABEL="com.mac-messages-mcp.${ENV_NAME}"
  PLIST_SRC="$PLIST_DIR/${LABEL}.plist"
  PLIST_DST="$LAUNCH_AGENTS/${LABEL}.plist"

  install_plist "$PLIST_SRC" "$PLIST_DST"

  # Unload first (ignore error if not loaded)
  launchctl unload "$PLIST_DST" 2>/dev/null || true
  launchctl load   "$PLIST_DST"
  ok "Service loaded: ${LABEL}"
done

echo ""
warn "ACTION REQUIRED – Full Disk Access"
echo "  The Mac Messages server reads ~/Library/Messages/chat.db."
echo "  Grant Full Disk Access to Terminal (or iTerm2) in:"
echo "    System Settings → Privacy & Security → Full Disk Access"
echo "  Then restart this terminal and re-run the health check:"
echo "    ./scripts/health-check.sh sandbox"
echo ""
read -rp "  Press Enter once you have granted Full Disk Access (or skip for now)..."

# ── STEP 9: Cloudflare Tunnel ─────────────────────────────────────────────────
echo ""
hr
echo -e "${BOLD}  Cloudflare Tunnel${RESET}"
hr
echo ""

# Check if already authenticated
if ! cloudflared tunnel list &>/dev/null 2>&1; then
  log "Logging in to Cloudflare (opens browser)..."
  cloudflared tunnel login
fi

# Create tunnel if it doesn't exist
if ! cloudflared tunnel list 2>/dev/null | grep -q "$CF_TUNNEL_NAME"; then
  log "Creating Cloudflare Tunnel '${CF_TUNNEL_NAME}'..."
  cloudflared tunnel create "$CF_TUNNEL_NAME"
fi

CF_TUNNEL_ID="$(cloudflared tunnel list 2>/dev/null | grep "$CF_TUNNEL_NAME" | awk '{print $1}')"
save_cfg CF_TUNNEL_ID "$CF_TUNNEL_ID"
ok "Tunnel: ${CF_TUNNEL_NAME} (${CF_TUNNEL_ID})"

# Write cloudflared config for this host
CF_CONFIG="$HOME/.cloudflared/config.yml"
cat > "$CF_CONFIG" <<EOF
tunnel: ${CF_TUNNEL_ID}
credentials-file: ${HOME}/.cloudflared/${CF_TUNNEL_ID}.json

ingress:
  - hostname: ${PROD_URL#https://}
    service: http://localhost:8000
  - hostname: ${SANDBOX_URL#https://}
    service: http://localhost:8001
  - service: http_status:404
EOF
ok "Cloudflare config written to ${CF_CONFIG}"

# Route DNS (idempotent)
log "Configuring DNS routes (may already exist – errors here are safe to ignore)..."
cloudflared tunnel route dns "$CF_TUNNEL_NAME" "${PROD_URL#https://}"    2>/dev/null || warn "DNS route already exists for ${PROD_URL#https://}"
cloudflared tunnel route dns "$CF_TUNNEL_NAME" "${SANDBOX_URL#https://}" 2>/dev/null || warn "DNS route already exists for ${SANDBOX_URL#https://}"

# Install cloudflared as a system service (survives reboots)
if ! sudo launchctl list com.cloudflare.cloudflared &>/dev/null 2>&1; then
  log "Installing cloudflared as a system service (requires sudo)..."
  sudo cloudflared service install
  sudo launchctl start com.cloudflare.cloudflared
  ok "Cloudflare Tunnel service installed and started"
else
  ok "Cloudflare Tunnel service already running"
fi

# ── STEP 10: GitHub Actions self-hosted runner ────────────────────────────────
echo ""
hr
echo -e "${BOLD}  GitHub Actions Self-Hosted Runner${RESET}"
hr
echo ""

if [[ -d "$RUNNER_DIR" && -f "$RUNNER_DIR/.runner" ]]; then
  ok "Runner already configured at ${RUNNER_DIR}"
  # Ensure the runner service is running
  if [[ -f "$RUNNER_DIR/svc.sh" ]]; then
    cd "$RUNNER_DIR"
    STATUS="$(sudo ./svc.sh status 2>/dev/null | tail -1 || true)"
    if echo "$STATUS" | grep -qiE "not installed|stopped"; then
      log "Starting runner service..."
      sudo ./svc.sh install "$USER" 2>/dev/null || true
      sudo ./svc.sh start
    fi
    cd "$REPO_ROOT"
  fi
else
  # Get the latest runner version from GitHub API
  log "Fetching latest Actions runner release..."
  RUNNER_VERSION="$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'].lstrip('v'))")"
  RUNNER_PKG="actions-runner-osx-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz"
  RUNNER_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${RUNNER_PKG}"

  log "Downloading runner v${RUNNER_VERSION} (${RUNNER_ARCH})..."
  mkdir -p "$RUNNER_DIR"
  curl -fsSL "$RUNNER_URL" -o "/tmp/${RUNNER_PKG}"
  tar -xzf "/tmp/${RUNNER_PKG}" -C "$RUNNER_DIR"
  rm "/tmp/${RUNNER_PKG}"
  ok "Runner extracted to ${RUNNER_DIR}"

  # Get a registration token via gh CLI
  log "Fetching runner registration token..."
  if gh auth status &>/dev/null 2>&1; then
    REG_TOKEN="$(gh api "repos/${GITHUB_REPO}/actions/runners/registration-token" \
      --method POST -q .token)"
    log "Configuring runner..."
    cd "$RUNNER_DIR"
    ./config.sh \
      --url "https://github.com/${GITHUB_REPO}" \
      --token "$REG_TOKEN" \
      --name "$(hostname -s)-mac-messages-mcp" \
      --labels "self-hosted,macOS,${RUNNER_ARCH}" \
      --work "_work" \
      --unattended \
      --replace
    cd "$REPO_ROOT"
    ok "Runner configured"

    # Install as a user-level service so it starts on login
    log "Installing runner as a launch service (requires sudo)..."
    cd "$RUNNER_DIR"
    sudo ./svc.sh install "$USER"
    sudo ./svc.sh start
    cd "$REPO_ROOT"
    ok "Runner service started"
  else
    warn "gh CLI is not authenticated. Complete the runner setup manually:"
    echo ""
    echo "  1. Go to: https://github.com/${GITHUB_REPO}/settings/actions/runners/new"
    echo "     Select: macOS / ${RUNNER_ARCH}"
    echo "  2. Copy the ./config.sh command shown on that page and run it inside:"
    echo "       ${RUNNER_DIR}/"
    echo "  3. Then install as a service:"
    echo "       cd ${RUNNER_DIR} && sudo ./svc.sh install \$USER && sudo ./svc.sh start"
    echo ""
    read -rp "  Press Enter to continue once the runner is configured..."
  fi
fi

# ── STEP 11: Full Disk Access for runner ─────────────────────────────────────
echo ""
warn "ACTION REQUIRED – Full Disk Access for the runner"
echo "  The GitHub Actions runner spawns a child process (uv / Python) that"
echo "  needs Full Disk Access to read the Messages DB."
echo ""
echo "  Grant Full Disk Access to:"
echo "    • /usr/local/bin/uv  (or ~/.local/bin/uv)"
echo "    • ${RUNNER_DIR}/bin/Runner.Listener"
echo "  in: System Settings → Privacy & Security → Full Disk Access"
echo "  (Click '+', press ⌘⇧G, paste the path)"
echo ""
read -rp "  Press Enter once done (or skip for now)..."

# ── STEP 12: Health check ─────────────────────────────────────────────────────
echo ""
hr
echo -e "${BOLD}  Verifying Services${RESET}"
hr
echo ""
sleep 3   # give launchd a moment

for ENV_NAME in prod sandbox; do
  [[ "$ENV_NAME" == prod ]] && PORT=8000 || PORT=8001
  URL="http://localhost:${PORT}/.well-known/oauth-authorization-server"
  if curl -sf "$URL" -o /dev/null --max-time 5; then
    ok "${ENV_NAME} service is up (port ${PORT})"
  else
    warn "${ENV_NAME} service did not respond on port ${PORT}"
    echo "    Check logs: tail -f ${REPO_ROOT}/logs/${ENV_NAME}.err"
  fi
done

# ── STEP 13: Summary ─────────────────────────────────────────────────────────
echo ""
hr
echo -e "${BOLD}  Setup Complete${RESET}"
hr
echo ""
echo -e "  ${BOLD}Environments:${RESET}"
echo "    Production  → port 8000 → ${PROD_URL}/sse"
echo "    Sandbox     → port 8001 → ${SANDBOX_URL}/sse"
echo ""
echo -e "  ${BOLD}Services:${RESET}"
echo "    launchctl list | grep mac-messages-mcp"
echo "    sudo launchctl list com.cloudflare.cloudflared"
echo ""
echo -e "  ${BOLD}Logs:${RESET}"
echo "    tail -f ${REPO_ROOT}/logs/prod.err"
echo "    tail -f ${REPO_ROOT}/logs/sandbox.err"
echo ""
echo -e "  ${BOLD}CI/CD:${RESET}"
echo "    Push to 'sandbox' → auto-deploys to ${SANDBOX_URL}"
echo "    Push to 'main'    → auto-deploys to ${PROD_URL}"
echo ""
echo -e "  ${BOLD}Re-run this script${RESET} any time on a new Mac to replicate the setup."
hr
