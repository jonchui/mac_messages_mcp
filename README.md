# Mac Messages MCP

A Python bridge for interacting with the macOS Messages app using MCP (Multiple Context Protocol). 

[![PyPI Downloads](https://static.pepy.tech/badge/mac-messages-mcp)](https://pepy.tech/projects/mac-messages-mcp)

[![Trust Score](https://archestra.ai/mcp-catalog/api/badge/quality/carterlasalle/mac_messages_mcp)](https://archestra.ai/mcp-catalog/carterlasalle__mac_messages_mcp)

![a-diagram-of-a-mac-computer-with-the-tex_FvvnmbaBTFeKy6F2GMlLqA_IfCBMgJARcia1WTH7FaqwA](https://github.com/user-attachments/assets/dbbdaa14-fadd-434d-a265-9e0c0071c11d)

[![Verified on MseeP](https://mseep.ai/badge.svg)](https://mseep.ai/app/fdc62324-6ac9-44e2-8926-722d1157759a)


<a href="https://glama.ai/mcp/servers/gxvaoc9znc">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/gxvaoc9znc/badge" />
</a>

## Quick Install

### For Cursor Users

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-light.svg)](https://cursor.com/en/install-mcp?name=mac-messages-mcp&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtYWMtbWVzc2FnZXMtbWNwIl19)

*Click the button above to automatically add Mac Messages MCP to Cursor*

### For Claude Desktop Users

See the [Integration section](#integration) below for setup instructions.

## Features

- **Universal Message Sending**: Automatically sends via iMessage or SMS/RCS based on recipient availability
- **Smart Fallback**: Seamless fallback to SMS when iMessage is unavailable (perfect for Android users)
- **Message Reading**: Read recent messages from the macOS Messages app
- **Contact Filtering**: Filter messages by specific contacts or phone numbers
- **Fuzzy Search**: Search through message content with intelligent matching
- **iMessage Detection**: Check if recipients have iMessage before sending
- **Cross-Platform**: Works with both iPhone/Mac users (iMessage) and Android users (SMS/RCS)

## Prerequisites

- macOS (tested on macOS 11+)
- Python 3.10+
- **uv package manager**

### Installing uv

If you're on Mac, install uv using Homebrew:

```bash
brew install uv
```

Otherwise, follow the installation instructions on the [uv website](https://github.com/astral-sh/uv).

⚠️ **Do not proceed before installing uv**

## Installation

### Full Disk Access Permission

⚠️ This application requires **Full Disk Access** permission for your terminal or application to access the Messages database. 

To grant Full Disk Access:
1. Open **System Preferences/Settings** > **Security & Privacy/Privacy** > **Full Disk Access**
2. Click the lock icon to make changes
3. Add your terminal app (Terminal, iTerm2, etc.) or Claude Desktop/Cursor to the list
4. Restart your terminal or application after granting permission

## Integration

### Claude Desktop Integration

1. Go to **Claude** > **Settings** > **Developer** > **Edit Config** > **claude_desktop_config.json**
2. Add the following configuration:

```json
{
    "mcpServers": {
        "messages": {
            "command": "uvx",
            "args": [
                "mac-messages-mcp"
            ]
        }
    }
}
```

### Cursor Integration

#### Option 1: One-Click Install (Recommended)

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-light.svg)](https://cursor.com/en/install-mcp?name=mac-messages-mcp&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtYWMtbWVzc2FnZXMtbWNwIl19)

#### Option 2: Manual Setup

Go to **Cursor Settings** > **MCP** and paste this as a command:

```
uvx mac-messages-mcp
```

⚠️ Only run one instance of the MCP server (either on Cursor or Claude Desktop), not both

### Remote MCP clients (HTTP/SSE)

To access the server from a remote MCP client (another machine, Docker, or Cursor using a URL), run it over HTTP with SSE:

```bash
# From the project directory (requires uv)
export PATH="$HOME/.local/bin:$PATH"
cd /path/to/mac_messages_mcp
MCP_TRANSPORT=sse FASTMCP_HOST=0.0.0.0 FASTMCP_PORT=8000 uv run python -m mac_messages_mcp.server
```

Or use the script:

```bash
./scripts/run_http.sh
```

Then point your remote client at:

- **Same machine:** `http://localhost:8000` (SSE endpoint: `/sse`)
- **Other machine on LAN:** `http://<this-mac-ip>:8000` (replace with your Mac’s IP)

Override host/port with `FASTMCP_HOST` and `FASTMCP_PORT` if needed. Binding to `0.0.0.0` exposes the service on all interfaces; use `127.0.0.1` for local-only access.

### Docker Container Integration

If you need to connect to `mac-messages-mcp` from a Docker container, you can either run the server with `MCP_TRANSPORT=sse` as above and use `http://host.docker.internal:8000`, or use the `mcp-proxy` package to bridge the stdio-based server to HTTP.

#### Setup Instructions

1. **Install Node.js (for `npx`) on your macOS host** if needed (npx comes with Node):
   ```bash
   # Option A: via nvm (no admin required)
   curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
   # then open a new terminal or: source ~/.nvm/nvm.sh
   nvm install --lts
   ```
   Or install from [nodejs.org](https://nodejs.org) or use Homebrew: `brew install node`.

2. **Start the proxy server:**
```bash
# Recommended (local source checkout)
npx mcp-proxy --host 0.0.0.0 --port 8000 -- uv run python -m mac_messages_mcp.server

# If you installed mcp-proxy globally:
mcp-proxy --host 0.0.0.0 --port 8000 -- uv run python -m mac_messages_mcp.server
```

> Note: `uvx mac-messages-mcp` may currently fail due to a published package/sdk
> mismatch (`FastMCP.__init__() got an unexpected keyword argument 'description'`).
> Use the local `uv run python -m mac_messages_mcp.server` command above until a new release is published.

3. **Connect from Docker:**
Your Docker container can now connect to:
- URL: `http://host.docker.internal:8000/mcp` (on macOS/Windows)
- URL: `http://<host-ip>:8000/mcp` (on Linux)

4. **Docker Compose example:**
```yaml
version: '3.8'
services:
  your-app:
    image: your-image
    environment:
      MCP_MESSAGES_URL: "http://host.docker.internal:8000/mcp"
    extra_hosts:
      - "host.docker.internal:host-gateway"  # For Linux hosts
```

5. **Running multiple MCP servers:**
```bash
# Terminal 1 - Messages MCP on port 8001
npx mcp-proxy --host 0.0.0.0 --port 8001 -- uv run python -m mac_messages_mcp.server

# Terminal 2 - Another MCP server on port 8002
npx mcp-proxy --host 0.0.0.0 --port 8002 -- uvx another-mcp-server
```

**Note:** Binding to `0.0.0.0` exposes the service to all network interfaces. In production, consider using more restrictive host bindings and adding authentication.


### Option 1: Install from PyPI

```bash
uv pip install mac-messages-mcp
```

### Option 2: Install from source

```bash
# Clone the repository
git clone https://github.com/carterlasalle/mac_messages_mcp.git
cd mac_messages_mcp

# Install dependencies
uv install -e .
```


## Testing and listing tools

To see what tools (skills) the server exposes and confirm it’s working:

```bash
# List tools by spawning the server via stdio (no HTTP server needed)
uv run python scripts/list_tools.py

# If the server is already running over HTTP (e.g. on port 8000)
uv run python scripts/list_tools.py --url http://localhost:8000/sse
```

Use `--json` for raw JSON output.

**Tools provided:** `tool_get_recent_messages`, `tool_send_message`, `tool_find_contact`, `tool_check_db_access`, `tool_check_contacts`, `tool_check_addressbook`, `tool_get_chats`, `tool_check_imessage_availability`, `tool_fuzzy_search_messages`.  
**Resources:** `messages://recent/{hours}`, `messages://contact/{contact}/{hours}`.

## Local "prod-like" workflow

If your local machine is effectively production, use these helper scripts:

```bash
# Restart live service and verify endpoints
./scripts/restart.sh

# Full diagnostics (launchctl, listeners, endpoint probes, logs)
./scripts/status.sh
```

You can also query deployment metadata directly:

```bash
curl http://<host>:8000/status
```

This returns JSON including the currently deployed commit hash and deploy timestamp.
It also includes the first line of the deployed commit message as `commit_subject`.

### Optional Git hook workflow

Tracked hooks live in `.githooks/` and can be installed with:

```bash
./scripts/install_hooks.sh
```

After installation, every commit can enforce and restart live service:

- `pre-commit`: blocks commit if unstaged or untracked files exist
- `post-commit`: runs `./scripts/restart.sh`

If you change hook behavior, edit `.githooks/*` and re-run `./scripts/install_hooks.sh`.

### LaunchAgent template (tracked)

The LaunchAgent config is tracked as a template at:

```bash
deploy/launchagents/com.jonchui.mac-messages-mcp.plist.template
```

To sync the template into your local `~/Library/LaunchAgents` file:

```bash
./scripts/sync_launchagent.sh
```

`pre-commit` automatically runs this sync **only when the template file is included in the commit**.

### API key storage (no secrets in git)

Do not put live API keys in tracked files. This repo keeps `MCP_PROXY_API_KEY` empty in the template.

Store the real key in macOS Keychain instead:

```bash
./scripts/set_api_key.sh "sk-..."
```

At startup, `scripts/start_mcp_proxy.sh` loads `MCP_PROXY_API_KEY` from env first, then falls back to Keychain service `mac-messages-mcp/api-key` for account `$USER`.

Set/rotate key locally (or over SSH):

```bash
./scripts/set_api_key.sh "sk-..."
# or remotely
ssh <user>@<mac-mini-host> 'cd "/Users/jonchui/Library/Mobile Documents/com~apple~CloudDocs/code/mac_messages_mcp" && ./scripts/set_api_key.sh "sk-..."'
```

Read current key from Keychain (same user account):

```bash
security find-generic-password -a "$USER" -s "mac-messages-mcp/api-key" -w
```

If run via SSH, the login keychain must be unlocked for that user session.

### API key auth smoke test (redacted)

```bash
# Valid key -> 200 OK and SSE stream
curl -i -H "X-API-Key: [REDACTED]" http://76.155.10.223:8000/sse
HTTP/1.1 200 OK
content-type: text/event-stream
event: endpoint
data: /messages?sessionId=<...>
event: message
data: {"jsonrpc":"2.0","method":"notifications/message","params":{"data":"SSE Connection established","level":"info"}}

# Invalid/truncated key -> 401 Unauthorized
curl -i -H "X-API-Key: [REDACTED]" http://76.155.10.223:8000/sse
HTTP/1.1 401 Unauthorized
{"error":{"code":401,"message":"Unauthorized: Invalid or missing API key"},"id":null,"jsonrpc":"2.0"}
```

## Usage

### Smart Message Delivery

Mac Messages MCP automatically handles message delivery across different platforms:

- **iMessage Users** (iPhone, iPad, Mac): Messages sent via iMessage
- **Android Users**: Messages automatically fall back to SMS/RCS
- **Mixed Groups**: Optimal delivery method chosen per recipient

```python
# Send to iPhone user - uses iMessage
send_message("+1234567890", "Hey! This goes via iMessage")

# Send to Android user - automatically uses SMS
send_message("+1987654321", "Hey! This goes via SMS") 

# Check delivery method before sending
check_imessage_availability("+1234567890")  # Returns availability status
```

### As a Module

```python
from mac_messages_mcp import get_recent_messages, send_message

# Get recent messages
messages = get_recent_messages(hours=48)
print(messages)

# Send a message (automatically chooses iMessage or SMS)
result = send_message(recipient="+1234567890", message="Hello from Mac Messages MCP!")
print(result)  # Shows whether sent via iMessage or SMS
```

### As a Command-Line Tool

```bash
# Run the MCP server directly
mac-messages-mcp
```

## Development

### Versioning

This project uses semantic versioning. See [VERSIONING.md](VERSIONING.md) for details on how the versioning system works and how to release new versions.

To bump the version:

```bash
python scripts/bump_version.py [patch|minor|major]
```

## Security Notes

This application accesses the Messages database directly, which contains personal communications. Please use it responsibly and ensure you have appropriate permissions.

[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/carterlasalle-mac-messages-mcp-badge.png)](https://mseep.ai/app/carterlasalle-mac-messages-mcp)

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 
## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=carterlasalle/mac_messages_mcp&type=Date)](https://www.star-history.com/#carterlasalle/mac_messages_mcp&Date)
