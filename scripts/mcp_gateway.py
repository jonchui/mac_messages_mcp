#!/usr/bin/env python3
"""
Small HTTP gateway in front of mcp-proxy:
- exposes /status on the public port
- proxies all other paths to mcp-proxy backend (supports SSE streaming)
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Iterable

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def filter_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    return {k: v for k, v in headers if k.lower() not in HOP_BY_HOP_HEADERS}


def load_deploy_info(path: Path) -> dict:
    if not path.exists():
        return {"status": "unknown", "message": "deploy metadata not found"}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        return {"status": "error", "message": f"failed reading deploy metadata: {exc}"}


def create_app(target_base: str, deploy_info_path: Path) -> Starlette:
    client = httpx.AsyncClient(timeout=None, follow_redirects=False)

    async def status_endpoint(_: Request) -> Response:
        return JSONResponse(load_deploy_info(deploy_info_path))

    async def proxy(request: Request) -> Response:
        target_url = f"{target_base}{request.url.path}"
        if request.url.query:
            target_url = f"{target_url}?{request.url.query}"

        req_headers = filter_headers(request.headers.items())
        body = await request.body()

        outbound = client.build_request(
            request.method,
            target_url,
            headers=req_headers,
            content=body if body else None,
        )
        upstream = await client.send(outbound, stream=True)

        resp_headers = filter_headers(upstream.headers.items())
        return StreamingResponse(
            upstream.aiter_raw(),
            status_code=upstream.status_code,
            headers=resp_headers,
            background=BackgroundTask(upstream.aclose),
        )

    async def health(_: Request) -> Response:
        return PlainTextResponse("ok")

    async def shutdown() -> None:
        await client.aclose()

    app = Starlette(
        routes=[
            Route("/healthz", health, methods=["GET"]),
            Route("/status", status_endpoint, methods=["GET"]),
            Route(
                "/{path:path}",
                proxy,
                methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
            ),
        ]
    )

    @app.on_event("shutdown")
    async def _on_shutdown() -> None:
        await shutdown()

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP gateway with /status endpoint")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--target", default="http://127.0.0.1:8001")
    parser.add_argument("--deploy-info", default=".runtime/deployed.json")
    args = parser.parse_args()

    deploy_info_path = Path(args.deploy_info)
    app = create_app(args.target.rstrip("/"), deploy_info_path)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
