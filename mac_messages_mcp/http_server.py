"""
Single-process HTTP + SSE entry for remote MCP (Tailscale / LAN).

Mirrors ``FastMCP.run_sse_async`` (mcp SDK) Starlette routes, adds:
  - ``GET /healthz`` / ``GET /status``
  - optional Bearer / ``X-API-Key`` when ``MAC_MESSAGES_MCP_BEARER_TOKEN`` is set

See GitHub issue #3 (single supervised process vs gateway + mcp-proxy).
"""

from __future__ import annotations

import hmac
import json
import os
from pathlib import Path

import anyio
import uvicorn
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route

from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport


def _expected_bearer() -> str | None:
    tok = (
        os.environ.get("MAC_MESSAGES_MCP_BEARER_TOKEN")
        or os.environ.get("MCP_HTTP_BEARER_TOKEN")
        or os.environ.get("MCP_PROXY_API_KEY")
    )
    return tok.strip() if tok else None


def _load_deploy_info() -> dict:
    raw = os.environ.get("MAC_MESSAGES_DEPLOY_INFO", ".runtime/deployed.json")
    p = Path(raw)
    if not p.is_absolute():
        p = Path(os.getcwd()) / p
    if not p.exists():
        return {"status": "unknown", "message": "deploy metadata not found"}
    try:
        return json.loads(p.read_text())
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


class OptionalBearerMiddleware(BaseHTTPMiddleware):
    """If ``MAC_MESSAGES_MCP_BEARER_TOKEN`` (or aliases) is set, require auth on MCP paths."""

    _public_paths = frozenset({"/healthz", "/status"})

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in self._public_paths:
            return await call_next(request)

        expected = _expected_bearer()
        if not expected:
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        api_key = request.headers.get("x-api-key", "")
        token = ""
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        elif api_key:
            token = api_key.strip()

        if len(token) != len(expected) or not hmac.compare_digest(
            token.encode("utf-8"), expected.encode("utf-8")
        ):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="mac-messages-mcp"'},
            )
        return await call_next(request)


def build_starlette_app(fast_mcp: FastMCP) -> Starlette:
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await fast_mcp._mcp_server.run(
                streams[0],
                streams[1],
                fast_mcp._mcp_server.create_initialization_options(),
            )

    async def healthz(_: Request):
        return PlainTextResponse("ok")

    async def status(_: Request):
        return JSONResponse(_load_deploy_info())

    routes = [
        Route("/healthz", endpoint=healthz, methods=["GET"]),
        Route("/status", endpoint=status, methods=["GET"]),
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Mount("/messages/", app=sse.handle_post_message),
    ]

    app = Starlette(debug=fast_mcp.settings.debug, routes=routes)
    app.add_middleware(OptionalBearerMiddleware)
    return app


def serve_sse_http(fast_mcp: FastMCP) -> None:
    """Run extended SSE app under Uvicorn (single process)."""

    async def _serve() -> None:
        starlette_app = build_starlette_app(fast_mcp)
        config = uvicorn.Config(
            starlette_app,
            host=fast_mcp.settings.host,
            port=fast_mcp.settings.port,
            log_level=fast_mcp.settings.log_level.lower(),
        )
        server = uvicorn.Server(config)
        await server.serve()

    anyio.run(_serve)
