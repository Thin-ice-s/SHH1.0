"""
SHH 1.0 - HTTP, REST, WebSocket & MCP Server
High-performance async server for Cloud AI communication and local dashboard.
"""

import asyncio
import gzip
import hashlib
import io
import json
import os
import time
import urllib.parse
import zlib
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel

from shh.config import SHHConfig
from shh.manifests.prompt_builder import build_ai_system_prompt
from shh.manifests.schema_exporter import generate_tools_markdown
from shh.servers.dashboard import get_dashboard_html
from shh.tools import registry
from shh.utils.logger import Logger


def create_app(config: SHHConfig, runtime_state: Optional[Dict[str, Any]] = None) -> FastAPI:
    state = runtime_state or {}
    app = FastAPI(
        title="SHH 1.0 - AI Remote Bridge & Tunnel",
        description="Connects Cloud AI Agents to Local Windows Computer via Dynamic Tunnel & MCP",
        version="1.1.0"
    )

    # Enable CORS for cloud requests and browser previews
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Hard request-body guard: a single oversized packet is what makes
    # tunnels drop, so reject it early with an actionable message
    # instead of buffering megabytes and crashing the connection.
    # ------------------------------------------------------------------
    max_request_bytes = int(getattr(config, "max_request_mb", 48) or 48) * 1024 * 1024

    @app.middleware("http")
    async def body_size_guard(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            declared = request.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > max_request_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "success": False,
                        "error": "Request body is %.1f MB which exceeds the safe limit of %d MB."
                                 % (int(declared) / (1024 * 1024), max_request_bytes // (1024 * 1024)),
                        "fix": "Split the payload: use file_upload_chunk (256 KiB chunks) or the raw "
                               "POST /api/transfer/upload endpoint (8 MiB chunks).",
                        "tools": ["file_upload_chunk", "file_download_chunk", "file_stat", "file_transfer_info"],
                    },
                )
        return await call_next(request)

    # Auth check helper
    def verify_auth(
        authorization: Optional[str] = Header(None),
        token: Optional[str] = Query(None)
    ):
        if config.relaxed_security:
            return True
        expected = config.token
        if token and token == expected:
            return True
        if authorization:
            scheme, _, param = authorization.partition(" ")
            if (scheme.lower() == "bearer" and param == expected) or authorization == expected:
                return True
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid SHH access token")

    # --- Routes ---

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return get_dashboard_html()

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        return get_dashboard_html()

    @app.get("/api/info")
    async def get_info():
        return {
            "session_id": config.session_id,
            "version": "1.1.0",
            "host": config.host,
            "port": config.port,
            "ssh_port": config.ssh_port,
            "ssh_username": config.ssh_username,
            "token": config.token,
            "relaxed_security": config.relaxed_security,
            "lan_ip": state.get("lan_ip", "127.0.0.1"),
            "public_ipv4": state.get("public_ipv4"),
            "public_ipv6": state.get("public_ipv6"),
            "board_url": state.get("board_url"),
            "ticket": state.get("ticket"),
            "uptime_seconds": int(time.time() - state.get("start_time", time.time()))
        }

    @app.get("/api/health")
    async def health():
        """Tiny, fast liveness probe used by the tunnel watchdog and keep-warm pings."""
        tunnel = state.get("tunnel_status", {})
        try:
            # Live tunnel status (address stability, reconnects, restarts) while supervised
            from shh.discovery.tunnel_supervisor import TunnelSupervisor
            inst = TunnelSupervisor.instance()
            if inst:
                tunnel = inst.get_status()
                state["tunnel_url"] = tunnel.get("url")
        except Exception:
            pass
        return {
            "status": "ok",
            "version": "1.1.0",
            "session_id": config.session_id,
            "uptime_seconds": int(time.time() - state.get("start_time", time.time())),
            "tunnel_url": state.get("tunnel_url"),
            "tunnel": tunnel,
            "tools": len(registry.list_tools()),
            "time": time.time(),
        }

    @app.get("/api/manifest")
    async def get_manifest(type: str = Query("markdown", enum=["markdown", "prompt", "openai", "anthropic", "mcp"])):
        if type == "prompt":
            prompt = build_ai_system_prompt(
                config=config,
                public_ip=state.get("public_ipv4") or state.get("lan_ip"),
                board_url=state.get("board_url"),
                ticket=state.get("ticket")
            )
            return PlainTextResponse(prompt, media_type="text/markdown")
        elif type == "markdown":
            return PlainTextResponse(generate_tools_markdown(), media_type="text/markdown")
        elif type == "openai":
            return registry.export_all_schemas()["openai"]
        elif type == "anthropic":
            return registry.export_all_schemas()["anthropic"]
        elif type == "mcp":
            return registry.export_all_schemas()["mcp"]

    @app.get("/api/tools")
    async def list_tools():
        tools = []
        for t in registry.list_tools():
            tools.append({
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "parameters": t.parameters
            })
        return {
            "success": True,
            "count": len(tools),
            "tools": tools,
            "schemas": registry.export_all_schemas()
        }

    class ToolExecRequest(BaseModel):
        arguments: Dict[str, Any] = {}

    @app.api_route("/api/tools/{tool_name}", methods=["GET", "POST"])
    async def execute_tool(tool_name: str, req: Optional[Dict[str, Any]] = None):
        payload = req or {}
        args = payload.get("arguments", payload) if "arguments" in payload and len(payload) == 1 else payload
        result = await registry.execute(tool_name, **args)
        return result

    class FastExecRequest(BaseModel):
        command: str
        cwd: Optional[str] = None
        shell: str = "auto"
        timeout: int = 60

    @app.post("/api/exec")
    async def fast_exec(req: FastExecRequest):
        return await registry.execute(
            "shell_exec",
            command=req.command,
            cwd=req.cwd,
            shell=req.shell,
            timeout=req.timeout
        )

    @app.get("/api/screenshot")
    async def get_screenshot(format: str = Query("jpeg", enum=["jpeg", "json"]), max_width: int = 1280):
        res = await registry.execute("capture_screen", max_width=max_width, return_base64=True)
        if format == "json":
            return res
        # If binary jpeg requested
        if res.get("success") and res.get("image_data_uri"):
            import base64
            b64_part = res["image_data_uri"].split(",", 1)[1]
            raw_bytes = base64.b64decode(b64_part)
            return Response(content=raw_bytes, media_type="image/jpeg")
        return res


    # ------------------------------------------------------------------
    # Raw binary streaming transfers (no base64, no JSON => much lower overhead)
    # These are the fastest and most tunnel-friendly way to move big files.
    # ------------------------------------------------------------------
    raw_chunk_limit = int(getattr(config, "max_raw_chunk_bytes", 8 * 1024 * 1024) or 8 * 1024 * 1024)

    def _auth_header_ok(request: Request) -> bool:
        """Token check for raw (non-JSON) endpoints; relaxed mode allows everything."""
        if config.relaxed_security:
            return True
        supplied = (
            request.headers.get("x-shh-token")
            or request.headers.get("authorization", "").replace("Bearer ", "").strip()
            or request.query_params.get("token")
            or ""
        )
        return supplied == config.token

    def _decode_path_header(raw: str) -> str:
        """Paths arrive URL-quoted so Windows / Chinese / spaced paths survive HTTP."""
        if not raw:
            return raw
        try:
            return urllib.parse.unquote(raw)
        except Exception:
            return raw

    @app.post("/api/transfer/upload")
    async def transfer_upload(request: Request):
        """
        Stream a raw binary chunk straight to disk (no full-body buffering).

        Headers:
          X-SHH-Path      : URL-quoted destination path (required)
          X-SHH-Offset    : byte offset to write at (default 0)
          X-SHH-Truncate  : 1/true => overwrite from scratch
          X-SHH-Compress  : gzip => body is gzip-compressed
          X-SHH-Sha256    : sha256 of the DECODED chunk (optional integrity check)
          X-SHH-Token     : access token (when not in relaxed mode)
        """
        if not _auth_header_ok(request):
            raise HTTPException(status_code=401, detail="Unauthorized: invalid SHH access token")

        raw_path = request.headers.get("x-shh-path") or request.query_params.get("path") or ""
        path = _decode_path_header(raw_path)
        if not path:
            return JSONResponse(status_code=400, content={"success": False, "error": "Missing X-SHH-Path header"})

        offset = int(request.headers.get("x-shh-offset") or request.query_params.get("offset") or 0)
        truncate = (request.headers.get("x-shh-truncate") or "").lower() in ("1", "true", "yes")
        compress = (request.headers.get("x-shh-compress") or "").lower()
        expected_sha = (request.headers.get("x-shh-sha256") or "").strip().lower()

        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > raw_chunk_limit:
            return JSONResponse(status_code=413, content={
                "success": False,
                "error": "Chunk of %s bytes exceeds the raw chunk limit of %d bytes. Split it further."
                         % (declared, raw_chunk_limit),
                "max_raw_chunk_bytes": raw_chunk_limit,
            })

        file_path = Path(path).expanduser()
        file_path.parent.mkdir(parents=True, exist_ok=True)

        sha = hashlib.sha256()
        written = 0
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS) if compress == "gzip" else None

        try:
            with open(file_path, "wb" if truncate else "r+b" if file_path.exists() else "wb") as fh:
                fh.seek(offset)
                async for piece in request.stream():
                    if not piece:
                        continue
                    data = decompressor.decompress(piece) if decompressor else piece
                    if data:
                        sha.update(data)
                        fh.write(data)
                        written += len(data)
                    if written > raw_chunk_limit * 4:
                        return JSONResponse(status_code=413, content={
                            "success": False,
                            "error": "Decompressed chunk exceeds the safe limit; split it into smaller chunks.",
                        })
                if decompressor:
                    tail = decompressor.flush()
                    if tail:
                        sha.update(tail)
                        fh.write(tail)
                        written += len(tail)
                fh.flush()
                os.fsync(fh.fileno())
        except Exception as exc:
            return JSONResponse(status_code=500, content={"success": False, "error": "Write failed: %s" % exc})

        actual_sha = sha.hexdigest()
        if expected_sha and expected_sha != actual_sha:
            return JSONResponse(status_code=409, content={
                "success": False,
                "error": "Chunk sha256 mismatch - retry this chunk at the same offset.",
                "retry": True,
                "offset": offset,
                "server_sha256": actual_sha,
            })

        return {
            "success": True,
            "path": str(file_path.resolve()),
            "offset": offset,
            "bytes_written": written,
            "next_offset": offset + written,
            "file_size": file_path.stat().st_size,
            "sha256_chunk": actual_sha,
        }

    @app.get("/api/transfer/download")
    async def transfer_download(
        request: Request,
        path: str = Query(..., description="File path on the local computer"),
        offset: int = Query(0, ge=0),
        length: int = Query(512 * 1024, ge=1, le=32 * 1024 * 1024),
        compress: str = Query("none", enum=["none", "gzip"]),
    ):
        """Stream raw bytes of one chunk (no base64). Loop offsets until X-SHH-Eof: 1."""
        if not _auth_header_ok(request):
            raise HTTPException(status_code=401, detail="Unauthorized: invalid SHH access token")

        file_path = Path(path).expanduser()
        if not file_path.exists() or not file_path.is_file():
            return JSONResponse(status_code=404, content={"success": False, "error": "File not found: %s" % path})

        size = file_path.stat().st_size
        if offset >= size:
            return Response(status_code=200, content=b"", headers={
                "X-SHH-Eof": "1", "X-SHH-Total-Size": str(size), "X-SHH-Offset": str(offset),
            })

        read_len = min(int(length), size - offset)
        with open(file_path, "rb") as fh:
            fh.seek(offset)
            blob = fh.read(read_len)

        headers = {
            "X-SHH-Offset": str(offset),
            "X-SHH-Next-Offset": str(offset + len(blob)),
            "X-SHH-Total-Size": str(size),
            "X-SHH-Eof": "1" if (offset + len(blob)) >= size else "0",
            "X-SHH-Sha256": hashlib.sha256(blob).hexdigest(),
            "Cache-Control": "no-store",
        }
        if compress == "gzip":
            body = gzip.compress(blob, 5)
            headers["X-SHH-Compressed"] = "1"
            headers["X-SHH-Raw-Size"] = str(len(blob))
            return Response(content=body, media_type="application/octet-stream", headers=headers)
        return Response(content=blob, media_type="application/octet-stream", headers=headers)

    @app.get("/api/transfer/info")
    async def transfer_info():
        """Advertise the safe transfer strategy and limits to the connecting AI."""
        return {
            "success": True,
            "max_json_chunk_bytes": int(getattr(config, "max_chunk_bytes", 262144)),
            "max_raw_chunk_bytes": raw_chunk_limit,
            "max_request_mb": int(getattr(config, "max_request_mb", 48)),
            "endpoints": {
                "upload_raw": "POST /api/transfer/upload (headers X-SHH-Path/Offset/Truncate/Compress/Sha256)",
                "download_raw": "GET /api/transfer/download?path=&offset=&length=&compress=gzip",
                "health": "GET /api/health",
            },
            "tools": ["file_stat", "file_upload_chunk", "file_download_chunk", "file_checksum", "file_transfer_info"],
        }

    # --- MCP (Model Context Protocol) JSON-RPC 2.0 Handler ---

    @app.post("/mcp")
    async def mcp_jsonrpc(req: Dict[str, Any]):
        jsonrpc = req.get("jsonrpc", "2.0")
        method = req.get("method")
        msg_id = req.get("id")
        params = req.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": jsonrpc,
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False}
                    },
                    "serverInfo": {
                        "name": "SHH-AI-Bridge",
                        "version": "1.1.0"
                    }
                }
            }

        elif method == "tools/list":
            tools = [t.to_mcp_schema() for t in registry.list_tools()]
            return {
                "jsonrpc": jsonrpc,
                "id": msg_id,
                "result": {"tools": tools}
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            exec_res = await registry.execute(tool_name, **arguments)
            return {
                "jsonrpc": jsonrpc,
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(exec_res, indent=2, ensure_ascii=False)
                        }
                    ],
                    "isError": not exec_res.get("success", True)
                }
            }

        elif method == "ping":
            return {"jsonrpc": jsonrpc, "id": msg_id, "result": {}}

        return {
            "jsonrpc": jsonrpc,
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method '{method}' not found"}
        }

    # --- WebSocket Interactive Terminal ---
    @app.websocket("/ws")
    async def websocket_terminal(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_json({
            "type": "welcome",
            "message": "Connected to SHH 1.0 WebSocket Terminal Bridge",
            "session_id": config.session_id
        })

        try:
            while True:
                try:
                    # Idle-timeout guard: tunnels drop idle sockets, so keep the
                    # connection warm with a heartbeat every 20 seconds.
                    data = await asyncio.wait_for(websocket.receive_json(), timeout=20.0)
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "ping", "time": time.time()})
                    continue

                msg_type = data.get("type")
                
                if msg_type == "exec":
                    cmd = data.get("command", "")
                    cwd = data.get("cwd")
                    res = await registry.execute("shell_exec", command=cmd, cwd=cwd)
                    await websocket.send_json({"type": "exec_result", "data": res})
                
                elif msg_type == "tool_call":
                    tool = data.get("tool")
                    args = data.get("args", {})
                    res = await registry.execute(tool, **args)
                    await websocket.send_json({"type": "tool_result", "tool": tool, "data": res})
                    
                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong", "time": time.time()})

        except WebSocketDisconnect:
            pass

    return app
