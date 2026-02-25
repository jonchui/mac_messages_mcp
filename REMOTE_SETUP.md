# Remote Access Setup – Mac Messages MCP with Claude Code

Connect Claude Code to your Mac Messages MCP server securely over the internet
using HTTPS (via Caddy) and OAuth 2.1 authorization.

## Architecture

```
Claude Code ──HTTPS──▶ Caddy (Hostinger VPS) ──HTTP──▶ iMac:8000
                        (SSL/TLS termination)          (OAuth + MCP server)
```

- **iMac** – runs the MCP server + OAuth provider (must stay on Mac for iMessage)
- **VPS** – runs Caddy as HTTPS reverse proxy (stable public IP, auto-TLS)
- **OAuth 2.1** – built into the MCP server (no external auth service needed)

## Prerequisites

- A domain name (e.g. `mcp.yourdomain.com`) pointed at your Hostinger VPS IP
- Port 8000 forwarded through your Xfinity router to your iMac
- Python 3.10+ and [uv](https://docs.astral.sh/uv/) on your iMac
- Root/sudo access on the Hostinger VPS

## Step 1: Set up the VPS (Hostinger)

SSH into your VPS and run:

```bash
# Copy the setup script to your VPS, then:
sudo ./deployment/setup-vps.sh mcp.yourdomain.com YOUR_IMAC_PUBLIC_IP
```

This installs Caddy, configures HTTPS with automatic Let's Encrypt certificates,
and sets up the reverse proxy to your iMac.

### Finding your iMac's public IP

From your iMac:
```bash
curl -4 ifconfig.me
```

> **Tip:** If your Xfinity IP changes, use a Dynamic DNS service (DuckDNS,
> no-ip, etc.) and use the DynDNS hostname instead of the IP in the Caddyfile.

## Step 2: Start the MCP server (iMac)

```bash
cd ~/mac_messages_mcp

# Quick start:
./scripts/run-remote.sh https://mcp.yourdomain.com

# Or manually:
uv run python -m mac_messages_mcp.remote \
    --server-url https://mcp.yourdomain.com \
    --port 8000
```

### Auto-start on boot (optional)

1. Edit `deployment/imac-launchagent.plist`:
   - Set your `--server-url`
   - Set `WorkingDirectory` to your repo path
2. Install:
   ```bash
   cp deployment/imac-launchagent.plist ~/Library/LaunchAgents/com.macmessagesmcp.remote.plist
   launchctl load ~/Library/LaunchAgents/com.macmessagesmcp.remote.plist
   ```

## Step 3: Configure Claude Code

Add to your Claude Code MCP settings (`~/.claude/claude_code_config.json` or project config):

```json
{
  "mcpServers": {
    "messages": {
      "url": "https://mcp.yourdomain.com/sse"
    }
  }
}
```

When Claude Code first connects, it will:
1. Discover the OAuth endpoints automatically
2. Open your browser for authorization consent
3. You click **Approve** on the consent page
4. Claude Code receives a token and connects to MCP

## How it works

### OAuth 2.1 Flow

1. Claude Code → `GET /sse` → receives `401 Unauthorized`
2. Claude Code → `GET /.well-known/oauth-authorization-server` → discovers endpoints
3. Claude Code → `POST /register` → dynamic client registration
4. Claude Code → opens browser to `GET /authorize` → you see consent page
5. You click **Approve** → redirect back to Claude Code with auth code
6. Claude Code → `POST /token` → exchanges code for access token (PKCE verified)
7. Claude Code → `GET /sse` with `Authorization: Bearer <token>` → MCP connected

### Security

- **HTTPS**: Caddy handles TLS automatically via Let's Encrypt
- **OAuth 2.1 + PKCE**: Prevents token interception and replay attacks
- **Consent page**: You must explicitly approve each new client
- **Token expiry**: Access tokens expire after 24 hours
- **State persistence**: Tokens survive server restarts (`~/.mac-messages-mcp/`)

### Network path

```
Internet → VPS:443 (HTTPS/Caddy) → iMac:8000 (HTTP/MCP+OAuth)
```

The VPS-to-iMac leg is HTTP over the public internet. For additional security,
consider adding a WireGuard tunnel between VPS and iMac.

## Troubleshooting

**Can't reach the server:**
```bash
# Test from VPS:
curl http://YOUR_IMAC_PUBLIC_IP:8000/health

# Test HTTPS:
curl https://mcp.yourdomain.com/health
```

**Caddy not getting certificates:**
- Ensure ports 80 and 443 are open on VPS firewall
- Ensure DNS A record points to VPS IP
- Check: `sudo journalctl -u caddy`

**OAuth errors:**
- Clear state: `rm ~/.mac-messages-mcp/oauth_state.json`
- Check iMac logs: `tail -f /tmp/mac-messages-mcp-remote.stderr.log`

**Port forwarding not working:**
- Verify in Xfinity router admin (10.0.0.1): port 8000 → iMac local IP
- Test locally first: `curl http://localhost:8000/health`
