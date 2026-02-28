# CLAUDE.md — Mac Messages MCP

This file provides guidance for AI assistants working in this repository.

---

## Project Overview

**mac-messages-mcp** is a Python package that implements the [Model Context Protocol (MCP)](https://modelcontextprotocol.io) to bridge AI assistants (Claude Desktop, Cursor) with the macOS Messages app. It reads from the Messages SQLite database (`chat.db`) and sends messages via AppleScript automation.

- **PyPI name**: `mac-messages-mcp`
- **Current version**: see `mac_messages_mcp/__init__.py` (`__version__`) and `pyproject.toml`
- **Requires**: Python 3.10+, macOS 11+, Full Disk Access permission for the app running the server
- **Entry points**: `mac-messages-mcp` and `mac_messages_mcp` (both call `mac_messages_mcp.server:run_server`)

---

## Repository Structure

```
mac_messages_mcp/
├── mac_messages_mcp/
│   ├── __init__.py       # Public API exports + __version__
│   ├── messages.py       # All business logic (DB queries, AppleScript, contact lookup)
│   └── server.py         # MCP server — registers tools/resources via FastMCP
├── tests/
│   ├── test_messages.py       # Unit tests (mock-based)
│   └── test_integration.py    # Integration tests (no real DB required)
├── scripts/
│   ├── bump_version.py        # Interactive semantic version bump tool
│   ├── run-http-proxy.sh      # Expose server over HTTP/SSE (ngrok helper)
│   └── test_mcp_client.py     # Standalone MCP client for manual testing
├── docs/
│   └── chat_db_schema.md      # Messages SQLite schema reference
├── .github/workflows/
│   └── publish.yml            # CI: publish to PyPI on `v*` git tags
├── main.py                    # Thin entry-point wrapper
├── pyproject.toml             # Package config, deps, tool settings
├── uv.lock                    # Locked dependencies (managed by uv)
└── CHANGELOG.md               # Semantic versioning history
```

---

## Architecture

The codebase has three clear layers:

### 1. Business Logic — `mac_messages_mcp/messages.py`

All database access, AppleScript execution, contact resolution, and message sending logic lives here. Key responsibilities:

| Area | Key Functions |
|---|---|
| **DB access** | `query_messages_db()`, `query_addressbook_db()`, `get_messages_db_path()` |
| **Message retrieval** | `get_recent_messages()`, `get_unread_messages()`, `fuzzy_search_messages()` |
| **Contact lookup** | `get_addressbook_contacts()`, `get_cached_contacts()`, `find_contact_by_name()`, `get_contact_name()` |
| **Phone normalization** | `normalize_phone_number()`, `find_handle_by_phone()`, `find_handles_by_phone()` |
| **Message sending** | `send_message()` (public), `_send_message_to_recipient()`, `_send_message_direct()`, `_send_message_sms()` |
| **iMessage check** | `_check_imessage_availability()` |
| **AppleScript** | `run_applescript()` |
| **Diagnostics** | `check_messages_db_access()`, `check_addressbook_access()` |

### 2. MCP Server — `mac_messages_mcp/server.py`

Registers 9 tools and 2 resources using `FastMCP`. All tools accept a `ctx: Context` first argument (FastMCP convention) and return `str`. Logging goes to stderr.

**Registered tools:**

| Tool name | Purpose |
|---|---|
| `tool_get_recent_messages` | Messages from last N hours, optional contact filter |
| `tool_send_message` | Send to phone/email/name/group chat ID |
| `tool_find_contact` | Fuzzy contact lookup |
| `tool_check_db_access` | Diagnose Messages DB permissions |
| `tool_check_contacts` | List AddressBook contacts |
| `tool_check_addressbook` | Diagnose AddressBook permissions |
| `tool_get_chats` | List named group chats with IDs |
| `tool_check_imessage_availability` | Check if recipient supports iMessage |
| `tool_get_unread_messages` | Get unread messages (macOS-version dependent) |
| `tool_fuzzy_search_messages` | Content search with similarity threshold |

**Registered resources:**

- `messages://recent/{hours}`
- `messages://contact/{contact}/{hours}`

### 3. Public API — `mac_messages_mcp/__init__.py`

Re-exports the most commonly needed functions from `messages.py` for library consumers. The `__version__` string is the canonical version source for runtime queries; `pyproject.toml` is the source for packaging.

---

## Key Conventions and Patterns

### Type Annotations

All functions must have complete type annotations. mypy is configured with strict settings:

```toml
[tool.mypy]
disallow_untyped_defs = true
disallow_incomplete_defs = true
warn_return_any = true
```

### Code Formatting

- **Black** with `line-length = 88`, `target-version = ["py310"]`
- **isort** with `profile = "black"` (compatible sort order)
- Run before committing: `black mac_messages_mcp/ tests/` and `isort mac_messages_mcp/ tests/`

### Error Handling

- Tool functions in `server.py` always catch `Exception` and return a descriptive error string — never raise to the MCP framework.
- Business logic functions in `messages.py` may raise; callers (tools) handle errors.
- Input validation (empty strings, out-of-range values, overflow) happens at the tool layer before calling into business logic.

### Logging

All logging uses the stdlib `logging` module directed to **stderr** (never stdout, which is reserved for MCP protocol communication):

```python
logging.basicConfig(stream=sys.stderr)
logger = logging.getLogger("mac_messages_mcp")
```

### Contact Resolution Flow

`send_message()` resolves recipients in priority order:
1. `contact:N` selection index from a prior search
2. Phone number (digits + `+- ()`)
3. Email address (`@` present)
4. Fuzzy name match against AddressBook

### Timestamp Handling

Messages database stores timestamps as **Apple epoch nanoseconds** (seconds since 2001-01-01). Always convert using:
- Apple epoch offset: `978307200` seconds (difference between Unix epoch 1970-01-01 and Apple epoch 2001-01-01)
- Some older rows store seconds; the code handles both formats

### iMessage / SMS Fallback Strategy

1. Try iMessage first (`_send_message_direct` with `preferred_service = "iMessage"`)
2. If unavailable for phone numbers, fall back to SMS/RCS via `_send_message_sms()`
3. Group chats always use iMessage (no SMS fallback)

### Contact Cache

`get_cached_contacts()` caches AddressBook results with a **5-minute TTL** to avoid repeated DB queries. The cache is module-level (`_contacts_cache`, `_contacts_cache_time`).

---

## Development Setup

```bash
# Install uv (required)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create venv and install with dev dependencies
uv venv
uv pip install -e ".[dev]"

# Or install from PyPI
uv pip install mac-messages-mcp
```

macOS permissions required on the machine running the server:
- **Full Disk Access** for the terminal/app (to read `~/Library/Messages/chat.db`)
- **Contacts access** for AddressBook queries (optional but recommended)

---

## Running the Server

```bash
# stdio mode (default, used by Claude Desktop / Cursor)
mac-messages-mcp

# Via Python
python -m mac_messages_mcp.server

# HTTP proxy (for remote access via ngrok/tunnel)
./scripts/run-http-proxy.sh

# Manual testing client
python scripts/test_mcp_client.py
```

---

## Testing

```bash
# Run all tests
pytest

# Run only unit tests
pytest tests/test_messages.py

# Run only integration tests
pytest tests/test_integration.py

# With verbose output
pytest -v
```

**Unit tests** (`test_messages.py`): mock `subprocess.Popen` and `os.path.expanduser`; test `run_applescript()`, `get_messages_db_path()`, `query_messages_db()`.

**Integration tests** (`test_integration.py`): validate input validation (negative hours, overflow, empty search terms, threshold out of range), import correctness, contact selection format, and SMS fallback logic — without requiring real database access.

Tests do **not** require macOS or Full Disk Access to run.

---

## Versioning and Release

Version is stored in two places (kept in sync):
- `pyproject.toml`: `version = "X.Y.Z"`
- `mac_messages_mcp/__init__.py`: `__version__ = "X.Y.Z"`

### Bumping the version

```bash
python scripts/bump_version.py patch   # 0.7.3 → 0.7.4
python scripts/bump_version.py minor   # 0.7.3 → 0.8.0
python scripts/bump_version.py major   # 0.7.3 → 1.0.0
```

The script updates both files interactively, optionally commits, and optionally creates a git tag.

### Publishing to PyPI

Publishing is automated via `.github/workflows/publish.yml`. To trigger a release:

```bash
git tag v0.7.4
git push origin v0.7.4
```

The workflow:
1. Extracts the version from the tag
2. Updates both version files via `sed`
3. Builds with `uv build`
4. Publishes to PyPI with `uv publish` using the `PYPI_API_TOKEN` secret

Do **not** manually publish; always use the tag-based CI workflow.

---

## Database Schema Reference

The Messages SQLite database is at `~/Library/Messages/chat.db`. Key tables:

| Table | Purpose |
|---|---|
| `message` | Message content, timestamps, read status, service type |
| `handle` | Participant identifiers (phone/email) and service |
| `chat` | Conversation metadata (group display names, chat identifiers) |
| `chat_message_join` | Many-to-many: messages ↔ chats |
| `chat_handle_join` | Many-to-many: participants ↔ chats |
| `attachment` | Media attachments with MIME types |

Critical columns:
- `message.date` — Apple epoch nanoseconds; `NULL` or `0` for some system messages
- `message.is_from_me` — `1` if sent by user, `0` if received
- `message.date_read` — `NULL` means unread (macOS-version dependent)
- `message.attributedBody` — Binary rich text; decoded by `extract_body_from_attributed()`
- `handle.service` — `"iMessage"` or `"SMS"`
- `chat.chat_identifier` — Unique ID used when sending to group chats

See `docs/chat_db_schema.md` for the full schema.

---

## Common Pitfalls

- **`thefuzz` import**: The package is `thefuzz` (not `fuzzywuzzy`). Always `from thefuzz import fuzz, process`.
- **Apple epoch**: Never use Unix epoch directly against the Messages DB. Always subtract/add `978307200`.
- **stdout purity**: The MCP stdio transport reads stdout. Any `print()` outside of MCP responses will corrupt the protocol. Use `logger.info()` / `logger.error()` to stderr only.
- **Group chat sending**: Pass `group_chat=True` and use the `chat_identifier` from `tool_get_chats`, not a contact name.
- **macOS version differences**: `message.date_read` behavior varies. `tool_get_unread_messages` documents this caveat; prefer `tool_get_recent_messages` for reliability across versions.
- **Version sync**: `pyproject.toml` and `__init__.py` must always have the same version string. Use `scripts/bump_version.py` rather than editing manually.
