#!/usr/bin/env bash
# setup-vps.sh – Set up the Hostinger VPS as an HTTPS reverse proxy
#
# This script installs Caddy and configures it to reverse-proxy HTTPS
# traffic to your iMac where the MCP server runs.
#
# Run on your Hostinger VPS as root (or with sudo).
#
# Prerequisites:
#   - A domain name pointed at your VPS IP (e.g., mcp.yourdomain.com)
#   - Your iMac's public IP or a DynDNS hostname
#   - Port 8000 forwarded through your Xfinity router to your iMac
#
# Usage:
#   chmod +x setup-vps.sh
#   sudo ./setup-vps.sh mcp.yourdomain.com YOUR_IMAC_PUBLIC_IP

set -euo pipefail

DOMAIN="${1:?Usage: $0 <domain> <imac-ip-or-hostname>}"
IMAC_HOST="${2:?Usage: $0 <domain> <imac-ip-or-hostname>}"

echo "=== Mac Messages MCP – VPS Setup ==="
echo "Domain:    $DOMAIN"
echo "iMac host: $IMAC_HOST"
echo ""

# ---- Install Caddy ----
if ! command -v caddy &>/dev/null; then
    echo "Installing Caddy..."
    apt-get update -qq
    apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl

    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg

    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list

    apt-get update -qq
    apt-get install -y -qq caddy
    echo "Caddy installed."
else
    echo "Caddy already installed: $(caddy version)"
fi

# ---- Configure Caddy ----
echo "Writing Caddyfile..."
mkdir -p /var/log/caddy

cat > /etc/caddy/Caddyfile <<EOF
${DOMAIN} {
    reverse_proxy ${IMAC_HOST}:8000 {
        health_uri /health
        health_interval 30s
        health_timeout 5s
        flush_interval -1
    }

    header {
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        Referrer-Policy strict-origin-when-cross-origin
        -Server
    }

    log {
        output file /var/log/caddy/mcp-access.log {
            roll_size 10mb
            roll_keep 5
        }
    }
}
EOF

# ---- Firewall ----
if command -v ufw &>/dev/null; then
    echo "Configuring firewall (ufw)..."
    ufw allow 80/tcp   # HTTP (for ACME challenges)
    ufw allow 443/tcp  # HTTPS
    echo "Firewall rules added for ports 80 and 443."
fi

# ---- Start Caddy ----
echo "Starting Caddy..."
systemctl enable caddy
systemctl restart caddy

echo ""
echo "=== Setup complete ==="
echo ""
echo "Caddy is now running and will automatically obtain a TLS certificate"
echo "for ${DOMAIN} via Let's Encrypt."
echo ""
echo "Verify:"
echo "  curl https://${DOMAIN}/health"
echo ""
echo "Configure Claude Code with:"
echo '  {'
echo '    "mcpServers": {'
echo '      "messages": {'
echo "        \"url\": \"https://${DOMAIN}/sse\""
echo '      }'
echo '    }'
echo '  }'
echo ""
