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

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-light.svg)](https://cursor.com/install-mcp?name=mac-messages-mcp&config=eyJjb21tYW5kIjoidXZ4IG1hYy1tZXNzYWdlcy1tY3AifQ%3D%3D)

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

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-light.svg)](https://cursor.com/install-mcp?name=mac-messages-mcp&config=eyJjb21tYW5kIjoidXZ4IG1hYy1tZXNzYWdlcy1tY3AifQ%3D%3D)

#### Option 2: Manual Setup

Go to **Cursor Settings** > **MCP** and paste this as a command:

```
uvx mac-messages-mcp
```

⚠️ Only run one instance of the MCP server (either on Cursor or Claude Desktop), not both

### Docker Container Integration

If you need to connect to `mac-messages-mcp` from a Docker container, you'll need to use the `mcp-proxy` package to bridge the stdio-based server to HTTP.

#### Setup Instructions

1. **Install mcp-proxy on your macOS host:**
```bash
npm install -g mcp-proxy
```

2. **Start the proxy server:**
```bash
# Using the published version
npx mcp-proxy --port 8000 -- uvx mac-messages-mcp

# Or using local development (if you encounter issues)
npx mcp-proxy --port 8000 -- uv run python -m mac_messages_mcp.server
```

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
npx mcp-proxy --port 8001 -- uvx mac-messages-mcp

# Terminal 2 - Another MCP server on port 8002
npx mcp-proxy --port 8002 -- uvx another-mcp-server
```

**Note:** Binding to `0.0.0.0` exposes the service to all network interfaces. In production, consider using more restrictive host bindings and adding authentication.

### Run locally for remote/WAN clients (e.g. Poke.com)

To use your Mac Messages MCP from the internet (Poke.com, other browsers, or apps that need an HTTP MCP URL), run the server on your Mac and expose it over HTTP, then make that URL reachable from the WAN.

**1. Install and run the HTTP proxy (on your Mac)**

From this repo (after `uv venv` and `uv pip install -e .`):

```bash
npm install -g mcp-proxy
npx mcp-proxy --port 8000 -- uv run python -m mac_messages_mcp.server
```

Or use the helper script (from repo root):

```bash
./scripts/run-http-proxy.sh
```

The proxy exposes:
- **Streamable HTTP:** `http://<your-host>:8000/mcp`
- **SSE:** `http://<your-host>:8000/sse`

**2. Expose to the internet**

- **Option A – Built-in tunnel (easiest):** mcp-proxy can create a public HTTPS URL for you. Run:
  ```bash
  npx mcp-proxy --port 8000 --tunnel -- uv run python -m mac_messages_mcp.server
  ```
  It will print a URL like `https://xxxxx.tunnel.gla.ma`. Use that as the base for Poke.com (e.g. `https://xxxxx.tunnel.gla.ma/sse`).

- **Option B – External tunnel (ngrok, etc.):** Use [ngrok](https://ngrok.com) or [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/). Start the proxy as in step 1, then in another terminal:
  ```bash
  ngrok http 8000
  ```
  Use the HTTPS URL ngrok gives you (e.g. `https://abc123.ngrok.io/sse`).

- **Option C – Port forward:** In your router, forward TCP port 8000 to your Mac’s LAN IP. Use your public IP or a DynDNS hostname.

**3. Connect from Poke.com (or other clients)**

- In [Poke.com Settings → Connections](https://poke.com/settings/connections), add an MCP server.
- **URL:** your public base URL + the path:
  - `https://<your-ngrok-or-host>/sse` (SSE), or  
  - `https://<your-ngrok-or-host>/mcp` (streamable HTTP)

Example: if ngrok shows `https://abc123.ngrok-free.app`, use `https://abc123.ngrok-free.app/sse`.

**Security:** Your Messages DB is only on your Mac; the proxy just forwards MCP over HTTP. Restrict who can reach the proxy (tunnel auth, firewall, or VPN) and prefer HTTPS (ngrok/tunnel) over plain port forwarding.

**4. Testing with Poke.com**

Poke only sees your chat; it doesn’t know to use your MCP connection unless you ask it to. **Name your connection** in Poke (e.g. “Mac Messages” or “Messages”) and then ask explicitly to use that connection’s tools.

**Example prompts that work:**

- *“Use my Mac Messages connection and run the tool to get my recent messages from the last 24 hours.”*
- *“Call the get recent messages tool from my Messages integration with hours=24.”*
- *“Using the Mac Messages connection: list my last 48 hours of iMessages.”*
- *“Use the Messages integration to search my messages for ‘dinner’ in the last 24 hours.”*
- *“With my Mac Messages connection, check if +1234567890 has iMessage.”*
- *“Send a message to [contact] saying ‘Hello’ using my Messages connection.”*

**Tools this server exposes (use these names when asking Poke):**

| Tool | What it does |
|------|----------------|
| `tool_get_recent_messages` | Get recent messages (params: `hours`, optional `contact`) |
| `tool_send_message` | Send a message (params: `recipient`, `message`, optional `group_chat`) |
| `tool_find_contact` | Find contact by name |
| `tool_fuzzy_search_messages` | Search message content (params: `search_term`, `hours`, `threshold`) |
| `tool_get_chats` | List group chats |
| `tool_check_imessage_availability` | Check if a number has iMessage |
| `tool_check_db_access` | Diagnose Messages DB access (useful if “no messages” or errors) |
| `tool_check_contacts` / `tool_check_addressbook` | List/diagnose contacts |

If Poke still says it can’t access messages, say: *“Use the [your connection name] integration’s tool_get_recent_messages tool with hours=24.”* If it still fails, run `tool_check_db_access` and ensure your Mac has given **Full Disk Access** to the app running the MCP server (Terminal or the process that runs `mcp-proxy`).

**Poke says “I don’t have access to that tool” or “I can’t see the tools”**

1. **Confirm your server exposes tools** – Use [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) with the **exact same URL and auth** you use in Poke:
   - Run: `npx @modelcontextprotocol/inspector`
   - In the UI: choose **streamable-http**, enter your MCP URL (e.g. `https://your-tunnel.or.host/sse` or `http://localhost:8000/sse`).
   - If you use a Bearer token in Poke, add it in Inspector (e.g. custom header `Authorization: Bearer YOUR_TOKEN` or the auth option Inspector offers).
   - Connect and open the **Tools** tab. You should see `tool_get_recent_messages`, `tool_send_message`, etc. Try calling `tool_get_recent_messages` with `hours: 24`.
   - **If Inspector lists and runs tools** → Your server and URL are fine; the problem is how Poke discovers or uses that connection. Try: refresh the connection in Poke (Settings → Connections → your integration → Refresh), start a **new** conversation, and ask e.g. *“Using my [integration name] connection, get my last 24 hours of messages.”* If it still never uses the tool, it may be a Poke limitation with custom MCP integrations.
   - **If Inspector does not list tools or connection fails** → Fix the server/proxy side: ensure the MCP proxy is running, the URL ends with `/sse` (or `/mcp`), and if you use auth, start the proxy with the same secret (e.g. `npx mcp-proxy --port 8000 --apiKey "YOUR_TOKEN" -- uv run python -m mac_messages_mcp.server`) and use that token in Poke’s API Key / auth field so Poke and the proxy match.

2. **Auth mismatch** – If Poke uses “Bearer token”, the proxy may expect an API key. Start the proxy with `--apiKey "your-secret"` and in Poke use the same value in the API Key field (if Poke sends it as `X-API-Key`) or ensure Poke sends the same token the proxy is configured to accept.

### Option 1: Install from PyPI

`uv` requires an active virtual environment (or `--system`). Create one, then install:

```bash
uv venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
uv pip install mac-messages-mcp
```

To install into the system Python instead: `uv pip install --system mac-messages-mcp`

### Option 2: Install from source

```bash
# Clone the repository
git clone https://github.com/carterlasalle/mac_messages_mcp.git
cd mac_messages_mcp

# Create a venv and install in editable mode
uv venv
uv pip install -e .
```

Then run with `uv run mac-messages-mcp` or `source .venv/bin/activate` and `mac-messages-mcp`.


## Testing the server locally (sample MCP queries)

To confirm the server and tools work **independent of Poke or other clients**, use one of these:

### 1. Sample MCP client script (repo)

From the repo (with proxy already running **without** `--apiKey` for a quick local test):

```bash
# Terminal 1: start proxy (no auth)
npx mcp-proxy --port 8000 -- uv run python -m mac_messages_mcp.server

# Terminal 2: run the test client
uv run python scripts/test_mcp_client.py http://localhost:8000/sse
```

The script lists tools and calls `tool_check_db_access` and `tool_get_recent_messages(hours=24)`. If the proxy uses API key auth, pass it:  
`uv run python scripts/test_mcp_client.py http://localhost:8000/sse --header "X-API-Key: YOUR_TOKEN"`.

### 2. Cursor

In **Cursor Settings → MCP**, add a server with command:

```text
uvx mac-messages-mcp
```

Or from the repo: `uv run mac-messages-mcp` (with “Execute in project directory” or run from the repo root). Then in a chat, ask e.g. “Use the Messages MCP to get my last 24 hours of messages.” Cursor will call the tools.

### 3. Claude Desktop

In **Claude → Settings → Developer → Edit Config**, add:

```json
"mcpServers": {
  "messages": {
    "command": "uvx",
    "args": ["mac-messages-mcp"]
  }
}
```

Restart Claude, then ask Claude to get your recent messages or send a message via the Messages integration.

If the script and Cursor/Claude all work but Poke does not, the issue is with how Poke invokes tools for custom MCP connections, not with this server.


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
