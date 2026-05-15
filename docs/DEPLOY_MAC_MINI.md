# Deploy: Mac mini (Tailscale / always-on MCP)

This repo’s **LaunchAgent** should run **`scripts/run_http_service.sh`** (single-process SSE). See [issue #3](https://github.com/jonchui/mac_messages_mcp/issues/3) and [PR #4](https://github.com/jonchui/mac_messages_mcp/pull/4).

## Prerequisites

- **SSH** to the mini as a user that owns the git clone and LaunchAgent (usually your macOS account).
- **Clone path** must match **`ProgramArguments`** and **`WorkingDirectory`** in `~/Library/LaunchAgents/com.jonchui.mac-messages-mcp.plist`.

### iCloud Drive and LaunchAgent (critical)

macOS often returns **`Operation not permitted` (exit 126)** when **LaunchAgent** runs **`/bin/bash …/run_http_service.sh`** from **`Library/Mobile Documents/`** (iCloud-synced “Desktop & Documents”). Login **SSH** works; **launchd** does not.

**Fix:** keep an **extra clone outside iCloud** for the daemon only, e.g. **`$HOME/src/mac_messages_mcp`**, and point the plist **`ProgramArguments`** + **`WorkingDirectory`** at that path (`PlistBuddy` or edit by hand). Use **git** to sync; keep iCloud copy for editor convenience if you want.

```bash
mkdir -p ~/src
git clone https://github.com/jonchui/mac_messages_mcp.git ~/src/mac_messages_mcp
cd ~/src/mac_messages_mcp && git checkout feat/tailscale-single-process-sse   # or main
# Then set LaunchAgent script + WorkingDirectory to this path and reload the plist.
```

- **Tailscale** on laptop + mini (or LAN) so you can use `100.x.x.x` or MagicDNS.

This Cursor/agent environment **does not** have your SSH keys or Tailscale DNS; **you** run the commands below from a trusted machine.

## One-shot deploy (from laptop)

Replace `USER`, `TAILSCALE_IP`, and the repo path with yours. The path must be the **actual clone** on the mini (match the plist `ProgramArguments` script path).

```bash
# From your laptop (replace user, IP, and quoted repo path on the mini):
ssh -o BatchMode=yes USER@TAILSCALE_IP \
  'bash "/Users/you/Library/Mobile Documents/com~apple~CloudDocs/code/mac_messages_mcp/scripts/deploy_mac_mini.sh" main'
```

Use branch `feat/tailscale-single-process-sse` until the single-process stack is merged to `main`.

Or SSH interactively, `cd` to the repo, and run `./scripts/deploy_mac_mini.sh main`.

## Deploy on the mini (logged in locally)

```bash
cd /path/to/mac_messages_mcp
./scripts/deploy_mac_mini.sh main
```

Optional:

```bash
export DEPLOY_OPERATOR="jc"
export MAC_MINI_SMOKE_TOKEN="your-bearer"   # if auth is enabled
```

## After deploy

- **Cursor / `mcp.json`:** `http://<tailscale-ip>:8000/sse` plus `Authorization: Bearer …` if you use a token.
- **Smoke:** `./scripts/status.sh` on the mini, or `curl http://127.0.0.1:8000/healthz`.

## Deploy history

Machine-readable log (append-only): [`deploy/history.jsonl`](../deploy/history.jsonl) (updated by `deploy_mac_mini.sh`).
