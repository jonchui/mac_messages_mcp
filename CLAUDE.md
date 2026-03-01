# Mac Messages MCP – Claude Code Instructions

## Shell

Use **`zsh`** — call it directly in the Bash tool. oh-my-zsh loads
automatically and puts all Homebrew tools on PATH.

```bash
zsh -c 'gh pr create ...'
zsh -c 'which gh'    # → /opt/homebrew/bin/gh
```

Never declare a tool missing just because bare `bash` can't find it.

## Project layout

| Path | Purpose |
|------|---------|
| `mac_messages_mcp/server.py` | FastMCP server – tool definitions |
| `mac_messages_mcp/messages.py` | SQLite queries against chat.db |
| `scripts/run_oauth_server.py` | OAuth 2.0 + SSL wrapper (for Claude.ai) |
| `scripts/setup-host.sh` | One-shot Mac host setup (Homebrew → runner) |
| `scripts/deploy.sh` | Called by CI to restart the launchd service |
| `scripts/health-check.sh` | Polls `/.well-known/oauth-authorization-server` |
| `config/launchd/` | launchd plist templates (prod :8000, sandbox :8001) |
| `config/cloudflared.yml` | Cloudflare Tunnel config template |
| `.github/workflows/deploy.yml` | GitHub Actions CI/CD pipeline |

## Environments

| Branch | Port | Deployed to |
|--------|------|-------------|
| `main` | 8000 | `https://messages.DOMAIN.com` |
| `sandbox` | 8001 | `https://sandbox.DOMAIN.com` |
| local | 8002 | `http://localhost:8002` |

## Key constraints

- The MCP server **must run on macOS** – it reads `~/Library/Messages/chat.db`.
  It cannot run on a Linux VPS.
- The GitHub Actions self-hosted runner on the Mac makes **outbound-only**
  connections to GitHub. No inbound ports or webhooks are needed.
- `Full Disk Access` must be granted in System Settings to the terminal /
  runner process for the Messages DB to be readable.

## Creating PRs

Use `gh pr create` via zsh. The feature branch naming convention used by
Claude Code sessions is `claude/<description>-<session-suffix>`.
Merge order: feature branch → `sandbox` → `main`.
