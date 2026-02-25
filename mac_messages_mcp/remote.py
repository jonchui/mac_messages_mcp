"""
Remote MCP server with OAuth 2.1 authorization.

Runs the Mac Messages MCP server over SSE/HTTP with full OAuth 2.1 auth,
enabling secure remote access from Claude Code and other MCP clients.

Architecture:
    This server runs on the iMac (where iMessage lives) and exposes:
    - OAuth 2.1 endpoints for authorization
    - SSE transport for MCP protocol

    A reverse proxy (Caddy) on a VPS handles HTTPS termination and
    forwards traffic to this server.

Usage:
    uv run python -m mac_messages_mcp.remote \\
        --server-url https://mcp.yourdomain.com \\
        --port 8000
"""

import argparse
import html
import logging
import os
import sys
import urllib.parse

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp.server.sse import SseServerTransport

from mac_messages_mcp.oauth import OAuthProvider
from mac_messages_mcp.server import mcp as fastmcp_instance

logger = logging.getLogger("mac_messages_mcp.remote")

# ---------------------------------------------------------------------------
# HTML template for OAuth authorization consent page
# ---------------------------------------------------------------------------
AUTHORIZE_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Authorize MCP Access</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f5f5f7;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .card {{
            background: white;
            border-radius: 16px;
            padding: 40px;
            max-width: 440px;
            width: 100%;
            box-shadow: 0 4px 24px rgba(0,0,0,0.08);
        }}
        .icon {{ font-size: 2.5em; margin-bottom: 16px; }}
        h1 {{ font-size: 1.3em; margin-bottom: 12px; color: #1d1d1f; }}
        .client {{ color: #0066cc; font-weight: 600; }}
        p {{ color: #6e6e73; line-height: 1.5; margin-bottom: 16px; font-size: 0.95em; }}
        .warning {{
            background: #fff3cd;
            border: 1px solid #ffc107;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 20px;
            font-size: 0.85em;
            color: #856404;
        }}
        .actions {{ display: flex; gap: 12px; margin-top: 24px; }}
        button {{
            flex: 1;
            padding: 12px 24px;
            border-radius: 10px;
            border: none;
            cursor: pointer;
            font-size: 1em;
            font-weight: 500;
            transition: background 0.2s;
        }}
        .approve {{ background: #0066cc; color: white; }}
        .approve:hover {{ background: #0052a3; }}
        .deny {{ background: #f0f0f0; color: #333; }}
        .deny:hover {{ background: #e0e0e0; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">&#x1f4ac;</div>
        <h1>Authorize MCP Access</h1>
        <p>
            <span class="client">{client_name}</span> is requesting access to
            your <strong>Mac Messages MCP</strong> server.
        </p>
        <div class="warning">
            This grants access to read and send iMessages on your behalf.
            Only approve if you initiated this connection.
        </div>
        <form method="POST" action="/authorize">
            <input type="hidden" name="client_id" value="{client_id}">
            <input type="hidden" name="redirect_uri" value="{redirect_uri}">
            <input type="hidden" name="code_challenge" value="{code_challenge}">
            <input type="hidden" name="code_challenge_method" value="{code_challenge_method}">
            <input type="hidden" name="state" value="{state}">
            <input type="hidden" name="scope" value="{scope}">
            <div class="actions">
                <button type="submit" name="action" value="deny" class="deny">Deny</button>
                <button type="submit" name="action" value="approve" class="approve">Approve</button>
            </div>
        </form>
    </div>
</body>
</html>"""


async def _parse_form(request: Request) -> dict[str, str]:
    """Parse application/x-www-form-urlencoded body without python-multipart."""
    body = (await request.body()).decode("utf-8")
    parsed = urllib.parse.parse_qs(body, keep_blank_values=True)
    return {k: v[0] for k, v in parsed.items()}


def _make_auth_middleware(oauth: OAuthProvider, app: ASGIApp) -> ASGIApp:
    """Wrap an ASGI app to require a valid Bearer token."""

    async def middleware(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            auth_value = headers.get(b"authorization", b"").decode()

            if not auth_value.startswith("Bearer "):
                response = Response(
                    status_code=401,
                    headers={
                        "WWW-Authenticate": "Bearer",
                    },
                )
                await response(scope, receive, send)
                return

            token_str = auth_value[7:]
            if not oauth.validate_token(token_str):
                response = Response(
                    status_code=401,
                    headers={
                        "WWW-Authenticate": 'Bearer error="invalid_token"',
                    },
                )
                await response(scope, receive, send)
                return

        await app(scope, receive, send)

    return middleware


def create_app(
    server_url: str,
    persist_path: str | None = None,
) -> Starlette:
    """Create the Starlette ASGI application with OAuth + MCP SSE."""

    oauth = OAuthProvider(server_url=server_url, persist_path=persist_path)

    # SSE transport: clients connect to GET /sse, send messages to POST /messages/
    sse_transport = SseServerTransport("/messages/")
    mcp_server = fastmcp_instance._mcp_server

    # ------------------------------------------------------------------
    # OAuth endpoints
    # ------------------------------------------------------------------

    async def well_known_oauth(request: Request) -> JSONResponse:
        """OAuth 2.0 Authorization Server Metadata (RFC 8414)."""
        return JSONResponse(oauth.get_server_metadata())

    async def well_known_resource(request: Request) -> JSONResponse:
        """OAuth Protected Resource Metadata (RFC 9728)."""
        return JSONResponse(oauth.get_resource_metadata())

    async def register(request: Request) -> JSONResponse:
        """Dynamic Client Registration (RFC 7591)."""
        try:
            body = await request.json()
            result = oauth.register_client(body)
            return JSONResponse(result, status_code=201)
        except Exception as e:
            logger.warning(f"Client registration failed: {e}")
            return JSONResponse({"error": str(e)}, status_code=400)

    async def authorize_get(request: Request) -> HTMLResponse:
        """Show the authorization consent page."""
        client_id = request.query_params.get("client_id", "")
        redirect_uri = request.query_params.get("redirect_uri", "")
        code_challenge = request.query_params.get("code_challenge", "")
        code_challenge_method = request.query_params.get(
            "code_challenge_method", "S256"
        )
        state = request.query_params.get("state", "")
        scope = request.query_params.get("scope", "mcp")

        client = oauth.clients.get(client_id)
        client_name = client.client_name if client else "Unknown Client"

        page = AUTHORIZE_PAGE.format(
            client_name=html.escape(client_name or "Unknown Client"),
            client_id=html.escape(client_id),
            redirect_uri=html.escape(redirect_uri),
            code_challenge=html.escape(code_challenge),
            code_challenge_method=html.escape(code_challenge_method),
            state=html.escape(state),
            scope=html.escape(scope),
        )
        return HTMLResponse(page)

    async def authorize_post(request: Request) -> Response:
        """Handle consent form submission – issue auth code or deny."""
        form = await _parse_form(request)
        action = form.get("action", "deny")
        client_id = form.get("client_id", "")
        redirect_uri = form.get("redirect_uri", "")
        code_challenge = form.get("code_challenge", "")
        code_challenge_method = form.get("code_challenge_method", "S256")
        state = form.get("state", "")
        scope = form.get("scope", "mcp")

        if action == "deny":
            params = urllib.parse.urlencode(
                {"error": "access_denied", "state": state}
            )
            return Response(
                status_code=302,
                headers={"Location": f"{redirect_uri}?{params}"},
            )

        try:
            code = oauth.create_authorization_code(
                client_id=client_id,
                redirect_uri=redirect_uri,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
                scope=scope,
            )
            params = urllib.parse.urlencode({"code": code, "state": state})
            return Response(
                status_code=302,
                headers={"Location": f"{redirect_uri}?{params}"},
            )
        except ValueError as e:
            params = urllib.parse.urlencode(
                {
                    "error": "server_error",
                    "error_description": str(e),
                    "state": state,
                }
            )
            return Response(
                status_code=302,
                headers={"Location": f"{redirect_uri}?{params}"},
            )

    async def token_endpoint(request: Request) -> JSONResponse:
        """Token endpoint – exchange authorization code for access token."""
        try:
            content_type = request.headers.get("content-type", "")
            if "json" in content_type:
                body = await request.json()
            else:
                body = await _parse_form(request)

            grant_type = body.get("grant_type")
            if grant_type != "authorization_code":
                return JSONResponse(
                    {"error": "unsupported_grant_type"}, status_code=400
                )

            result = oauth.exchange_code(
                code=body.get("code", ""),
                client_id=body.get("client_id", ""),
                redirect_uri=body.get("redirect_uri", ""),
                code_verifier=body.get("code_verifier", ""),
            )
            return JSONResponse(result)

        except ValueError as e:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": str(e)},
                status_code=400,
            )

    # ------------------------------------------------------------------
    # MCP SSE endpoints (auth-protected)
    # ------------------------------------------------------------------

    async def handle_sse(request: Request) -> Response:
        """SSE endpoint – requires valid Bearer token."""
        auth_header = request.headers.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            return Response(
                status_code=401,
                headers={
                    "WWW-Authenticate": "Bearer",
                },
            )

        token_str = auth_header[7:]
        if not oauth.validate_token(token_str):
            return Response(
                status_code=401,
                headers={
                    "WWW-Authenticate": 'Bearer error="invalid_token"',
                },
            )

        logger.info("Authenticated SSE connection established")
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp_server.run(
                streams[0],
                streams[1],
                mcp_server.create_initialization_options(),
            )

    # Wrap the messages endpoint with auth middleware
    authed_messages = _make_auth_middleware(
        oauth, sse_transport.handle_post_message
    )

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "server": "Mac Messages MCP"})

    # ------------------------------------------------------------------
    # Assemble routes
    # ------------------------------------------------------------------

    routes = [
        # Health
        Route("/health", health, methods=["GET"]),
        # OAuth discovery
        Route(
            "/.well-known/oauth-authorization-server",
            well_known_oauth,
            methods=["GET"],
        ),
        Route(
            "/.well-known/oauth-protected-resource",
            well_known_resource,
            methods=["GET"],
        ),
        # OAuth flow
        Route("/register", register, methods=["POST"]),
        Route("/authorize", authorize_get, methods=["GET"]),
        Route("/authorize", authorize_post, methods=["POST"]),
        Route("/token", token_endpoint, methods=["POST"]),
        # MCP (SSE transport, auth-protected)
        Route("/sse", handle_sse),
        Mount("/messages/", app=authed_messages),
    ]

    app = Starlette(routes=routes)
    return app


def main():
    """CLI entry point for the remote MCP server."""
    parser = argparse.ArgumentParser(
        description="Mac Messages MCP – Remote Server (OAuth + SSE)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Run on iMac, proxied through Caddy on VPS:
  uv run python -m mac_messages_mcp.remote \\
      --server-url https://mcp.yourdomain.com --port 8000

  # Local development / testing:
  uv run python -m mac_messages_mcp.remote \\
      --server-url http://localhost:8000 --port 8000
""",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)",
    )
    parser.add_argument(
        "--server-url",
        required=True,
        help=(
            "Public URL of this server as seen by clients "
            "(e.g. https://mcp.yourdomain.com). "
            "Used in OAuth metadata and redirect URIs."
        ),
    )
    parser.add_argument(
        "--state-dir",
        default=os.path.expanduser("~/.mac-messages-mcp"),
        help="Directory for persistent state (default: ~/.mac-messages-mcp)",
    )
    args = parser.parse_args()

    persist_path = os.path.join(args.state_dir, "oauth_state.json")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    logger.info(f"Starting remote MCP server on {args.host}:{args.port}")
    logger.info(f"Public URL: {args.server_url}")
    logger.info(f"State directory: {args.state_dir}")

    app = create_app(
        server_url=args.server_url,
        persist_path=persist_path,
    )

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
