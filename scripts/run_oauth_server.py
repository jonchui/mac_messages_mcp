#!/usr/bin/env python3
"""Mac Messages MCP server with OAuth 2.0 authorization and optional SSL.

This script wraps the MCP server with:
  - OAuth 2.0 Authorization Code flow with PKCE (required by Claude.ai)
  - Dynamic client registration (RFC 7591)
  - Bearer token validation on all MCP endpoints
  - Optional TLS/SSL via uvicorn

Usage:
------
  # Simplest: run plain HTTP, let ngrok/Cloudflare provide HTTPS:
  EXTERNAL_URL=https://abc123.ngrok.io uv run python scripts/run_oauth_server.py
  # (In another terminal: ngrok http 8000)

  # With your own SSL cert + key:
  EXTERNAL_URL=https://your-domain.com \\
    SSL_CERT=/path/to/cert.pem \\
    SSL_KEY=/path/to/key.pem \\
    uv run python scripts/run_oauth_server.py

  # Custom port:
  PORT=9000 EXTERNAL_URL=https://your-domain.com:9000 \\
    uv run python scripts/run_oauth_server.py

Environment variables:
  EXTERNAL_URL   Public HTTPS URL clients (e.g. Claude.ai) will use  [REQUIRED]
  PORT           Local port to bind                                   [default: 8000]
  HOST           Local interface to bind                              [default: 0.0.0.0]
  SSL_CERT       Path to TLS certificate PEM file                     [optional]
  SSL_KEY        Path to TLS private key PEM file                     [optional]
  TOKEN_EXPIRY   Access token lifetime in seconds                     [default: 86400]

Connecting to Claude.ai:
  1. Start this server and ensure EXTERNAL_URL is reachable over HTTPS.
  2. In Claude.ai → Settings → Connections → Add custom connector
  3. Enter:  <EXTERNAL_URL>/sse
  4. Claude.ai will discover OAuth metadata and guide you through authorization.
"""

import base64
import hashlib
import html as html_module
import json
import logging
import os
import secrets
import sys
import time
from urllib.parse import parse_qs, urlencode

import anyio
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route

# ── Project path ───────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mac_messages_mcp.server import mcp  # noqa: E402
from mcp.server.sse import SseServerTransport  # noqa: E402

# ── Configuration ──────────────────────────────────────────────────────────────
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
EXTERNAL_URL = os.environ.get("EXTERNAL_URL", "").rstrip("/")
SSL_CERT = os.environ.get("SSL_CERT", "")
SSL_KEY = os.environ.get("SSL_KEY", "")
TOKEN_EXPIRY = int(os.environ.get("TOKEN_EXPIRY", str(24 * 3600)))

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mac_messages_mcp.oauth")

# ── In-memory OAuth stores ─────────────────────────────────────────────────────
# clients:    { client_id -> {"client_id", "client_name", "redirect_uris"} }
# auth_codes: { code -> {"client_id","redirect_uri","code_challenge","method","expires_at"} }
# tokens:     { token -> {"client_id", "expires_at"} }
_clients: dict[str, dict] = {}
_auth_codes: dict[str, dict] = {}
_tokens: dict[str, dict] = {}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _purge_expired() -> None:
    now = time.time()
    for store in (_auth_codes, _tokens):
        expired = [k for k, v in store.items() if v["expires_at"] < now]
        for k in expired:
            del store[k]


def _pkce_ok(verifier: str, challenge: str, method: str) -> bool:
    if method == "S256":
        digest = hashlib.sha256(verifier.encode()).digest()
        computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        return secrets.compare_digest(computed, challenge)
    if method == "plain":
        return secrets.compare_digest(verifier, challenge)
    return False


def _valid_token(token: str) -> bool:
    _purge_expired()
    return token in _tokens


async def _parse_body(request: Request) -> dict:
    """Parse JSON or URL-encoded form body without requiring python-multipart."""
    raw = await request.body()
    ct = request.headers.get("content-type", "")
    if "application/json" in ct:
        return json.loads(raw)
    # URL-encoded form (OAuth token requests, HTML form POSTs)
    parsed = parse_qs(raw.decode(), keep_blank_values=True)
    return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}


def _bearer_from(request: Request) -> str | None:
    """Extract Bearer token from Authorization header, or None."""
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


def _auth_error(description: str = "Bearer token required") -> Response:
    return Response(
        content=json.dumps({"error": "unauthorized", "error_description": description}),
        status_code=401,
        headers={"WWW-Authenticate": "Bearer", "Content-Type": "application/json"},
    )


def _invalid_token_error() -> Response:
    return Response(
        content=json.dumps({"error": "invalid_token", "error_description": "Token invalid or expired"}),
        status_code=401,
        headers={
            "WWW-Authenticate": 'Bearer error="invalid_token"',
            "Content-Type": "application/json",
        },
    )


# ── SSE transport ──────────────────────────────────────────────────────────────
_sse = SseServerTransport("/messages/")


# ── OAuth endpoints ────────────────────────────────────────────────────────────

async def well_known(request: Request) -> JSONResponse:
    """RFC 8414 – OAuth 2.0 Authorization Server Metadata."""
    base = EXTERNAL_URL
    return JSONResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
    })


async def oauth_register(request: Request) -> JSONResponse:
    """RFC 7591 – Dynamic Client Registration."""
    try:
        body = await _parse_body(request)
    except Exception:
        return JSONResponse({"error": "invalid_client_metadata"}, status_code=400)

    redirect_uris = body.get("redirect_uris", [])
    if not redirect_uris:
        return JSONResponse(
            {"error": "invalid_client_metadata", "error_description": "redirect_uris required"},
            status_code=400,
        )

    client_id = secrets.token_urlsafe(16)
    client_name = body.get("client_name", "Unknown Client")
    _clients[client_id] = {
        "client_id": client_id,
        "client_name": client_name,
        "redirect_uris": redirect_uris,
    }
    logger.info("OAuth client registered: %s (%s)", client_name, client_id)
    return JSONResponse(
        {
            "client_id": client_id,
            "client_name": client_name,
            "redirect_uris": redirect_uris,
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
        status_code=201,
    )


async def oauth_authorize(request: Request) -> Response:
    """Authorization endpoint – shows consent page (GET) or processes it (POST)."""
    if request.method == "GET":
        client_id = request.query_params.get("client_id", "")
        redirect_uri = request.query_params.get("redirect_uri", "")
        state = request.query_params.get("state", "")
        code_challenge = request.query_params.get("code_challenge", "")
        code_challenge_method = request.query_params.get("code_challenge_method", "S256")

        client = _clients.get(client_id)
        if not client:
            return HTMLResponse("<h1>Error</h1><p>Unknown client application.</p>", status_code=400)
        if redirect_uri not in client["redirect_uris"]:
            return HTMLResponse("<h1>Error</h1><p>Invalid redirect URI.</p>", status_code=400)

        esc = html_module.escape
        return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Mac Messages MCP – Authorize</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f5f5f7; min-height: 100vh;
      display: flex; align-items: center; justify-content: center; margin: 0;
    }}
    .card {{
      background: #fff; border-radius: 16px; padding: 36px 40px;
      box-shadow: 0 4px 24px rgba(0,0,0,.1); max-width: 440px; width: 100%;
    }}
    .icon {{ font-size: 40px; margin-bottom: 12px; }}
    h1 {{ font-size: 20px; font-weight: 600; margin: 0 0 6px; }}
    .subtitle {{ color: #6e6e73; font-size: 14px; margin-bottom: 24px; }}
    .perms {{
      background: #f5f5f7; border-radius: 10px; padding: 16px 20px;
      margin-bottom: 28px;
    }}
    .perms h2 {{ font-size: 13px; font-weight: 600; color: #333; margin: 0 0 8px; }}
    .perms ul {{ margin: 0; padding-left: 18px; font-size: 13px; color: #444; }}
    .perms li {{ margin-bottom: 4px; }}
    .btn-row {{ display: flex; gap: 12px; }}
    .btn {{
      flex: 1; padding: 12px 16px; border: none; border-radius: 10px;
      font-size: 15px; font-weight: 500; cursor: pointer; transition: opacity .15s;
    }}
    .btn:hover {{ opacity: .85; }}
    .btn-approve {{ background: #0071e3; color: #fff; }}
    .btn-deny {{ background: #e5e5ea; color: #1c1c1e; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">💬</div>
    <h1>Mac Messages MCP</h1>
    <p class="subtitle">
      <strong>{esc(client["client_name"])}</strong> is requesting access to your Mac Messages.
    </p>
    <div class="perms">
      <h2>This will allow the app to:</h2>
      <ul>
        <li>Read your Messages history</li>
        <li>Send iMessages and SMS on your behalf</li>
        <li>Access your Contacts</li>
      </ul>
    </div>
    <form method="POST" action="/oauth/authorize">
      <input type="hidden" name="client_id" value="{esc(client_id)}">
      <input type="hidden" name="redirect_uri" value="{esc(redirect_uri)}">
      <input type="hidden" name="state" value="{esc(state)}">
      <input type="hidden" name="code_challenge" value="{esc(code_challenge)}">
      <input type="hidden" name="code_challenge_method" value="{esc(code_challenge_method)}">
      <div class="btn-row">
        <button class="btn btn-approve" type="submit" name="action" value="approve">Allow</button>
        <button class="btn btn-deny" type="submit" name="action" value="deny">Deny</button>
      </div>
    </form>
  </div>
</body>
</html>""")

    if request.method == "POST":
        body = await _parse_body(request)
        action = body.get("action", "deny")
        client_id = body.get("client_id", "")
        redirect_uri = body.get("redirect_uri", "")
        state = body.get("state", "")
        code_challenge = body.get("code_challenge", "")
        code_challenge_method = body.get("code_challenge_method", "S256")

        client = _clients.get(client_id)
        if not client or redirect_uri not in client["redirect_uris"]:
            return HTMLResponse("<h1>Error</h1><p>Invalid request.</p>", status_code=400)

        if action == "deny":
            params = {"error": "access_denied"}
            if state:
                params["state"] = state
            return RedirectResponse(f"{redirect_uri}?{urlencode(params)}", status_code=302)

        # Issue auth code
        code = secrets.token_urlsafe(32)
        _auth_codes[code] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "expires_at": time.time() + 600,  # 10-minute window
        }
        params = {"code": code}
        if state:
            params["state"] = state
        logger.info("Authorization code issued for client: %s", client_id)
        return RedirectResponse(f"{redirect_uri}?{urlencode(params)}", status_code=302)

    return Response(status_code=405)


async def oauth_token(request: Request) -> JSONResponse:
    """Token endpoint – exchange authorization code for access token."""
    try:
        body = await _parse_body(request)
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    if body.get("grant_type") != "authorization_code":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    code = body.get("code", "")
    client_id = body.get("client_id", "")
    redirect_uri = body.get("redirect_uri", "")
    code_verifier = body.get("code_verifier", "")

    _purge_expired()
    code_data = _auth_codes.pop(code, None)  # single-use

    if not code_data:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "Authorization code invalid or expired"},
            status_code=400,
        )
    if code_data["client_id"] != client_id:
        return JSONResponse({"error": "invalid_client"}, status_code=401)
    if code_data["redirect_uri"] != redirect_uri:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "redirect_uri mismatch"},
            status_code=400,
        )
    if code_data.get("code_challenge"):
        if not code_verifier:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "code_verifier required"},
                status_code=400,
            )
        if not _pkce_ok(
            code_verifier,
            code_data["code_challenge"],
            code_data.get("code_challenge_method", "S256"),
        ):
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "PKCE verification failed"},
                status_code=400,
            )

    access_token = secrets.token_urlsafe(32)
    _tokens[access_token] = {"client_id": client_id, "expires_at": time.time() + TOKEN_EXPIRY}
    logger.info("Access token issued for client: %s", client_id)

    return JSONResponse({
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": TOKEN_EXPIRY,
    })


# ── Protected MCP endpoints ────────────────────────────────────────────────────

async def protected_sse(request: Request) -> Response | None:
    """SSE endpoint with Bearer token auth."""
    token = _bearer_from(request)
    if token is None:
        return _auth_error()
    if not _valid_token(token):
        return _invalid_token_error()
    # Authenticated – hand off to MCP SSE transport (streams directly to client)
    async with _sse.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp._mcp_server.run(
            streams[0],
            streams[1],
            mcp._mcp_server.create_initialization_options(),
        )


class _AuthedMessages:
    """ASGI wrapper that enforces Bearer auth before the SSE post-message handler."""

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            headers = {k.lower(): v for k, v in scope.get("headers", [])}
            auth = headers.get(b"authorization", b"").decode()
            if not auth.startswith("Bearer "):
                resp = Response(
                    content=json.dumps({"error": "unauthorized"}),
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer", "Content-Type": "application/json"},
                )
                await resp(scope, receive, send)
                return
            token = auth[7:]
            if not _valid_token(token):
                resp = Response(
                    content=json.dumps({"error": "invalid_token"}),
                    status_code=401,
                    headers={"Content-Type": "application/json"},
                )
                await resp(scope, receive, send)
                return
        await _sse.handle_post_message(scope, receive, send)


# ── App factory ────────────────────────────────────────────────────────────────

def _build_app() -> Starlette:
    return Starlette(
        routes=[
            # OAuth discovery + endpoints
            Route("/.well-known/oauth-authorization-server", well_known),
            Route("/oauth/register", oauth_register, methods=["POST"]),
            Route("/oauth/authorize", oauth_authorize, methods=["GET", "POST"]),
            Route("/oauth/token", oauth_token, methods=["POST"]),
            # MCP (protected)
            Route("/sse", endpoint=protected_sse),
            Mount("/messages/", app=_AuthedMessages()),
        ],
    )


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    if not EXTERNAL_URL:
        print(
            "ERROR: EXTERNAL_URL is required.\n"
            "  Set it to your public HTTPS URL, e.g.:\n"
            "    EXTERNAL_URL=https://abc123.ngrok.io uv run python scripts/run_oauth_server.py\n"
            "\n"
            "  For a quick HTTPS tunnel: run 'ngrok http 8000' in another terminal,\n"
            "  then re-run this script with the ngrok HTTPS URL.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not EXTERNAL_URL.startswith("https://"):
        logger.warning(
            "EXTERNAL_URL does not start with https://. "
            "Claude.ai requires HTTPS for custom connectors. "
            "Use ngrok, Cloudflare Tunnel, or a reverse proxy with a TLS cert."
        )

    ssl_kwargs: dict = {}
    if SSL_CERT or SSL_KEY:
        if not SSL_CERT or not SSL_KEY:
            logger.error("Both SSL_CERT and SSL_KEY must be set together.")
            sys.exit(1)
        if not os.path.exists(SSL_CERT):
            logger.error("SSL_CERT file not found: %s", SSL_CERT)
            sys.exit(1)
        if not os.path.exists(SSL_KEY):
            logger.error("SSL_KEY file not found: %s", SSL_KEY)
            sys.exit(1)
        ssl_kwargs = {"ssl_certfile": SSL_CERT, "ssl_keyfile": SSL_KEY}
        logger.info("TLS enabled  cert=%s  key=%s", SSL_CERT, SSL_KEY)

    logger.info("Mac Messages MCP – OAuth server starting")
    logger.info("  External URL : %s", EXTERNAL_URL)
    logger.info("  MCP endpoint : %s/sse", EXTERNAL_URL)
    logger.info("  OAuth meta   : %s/.well-known/oauth-authorization-server", EXTERNAL_URL)
    logger.info("  Listening on : %s:%s", HOST, PORT)

    app = _build_app()
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="info", **ssl_kwargs)
    server = uvicorn.Server(config)
    anyio.run(server.serve)


if __name__ == "__main__":
    main()
