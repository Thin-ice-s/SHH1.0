"""
SHH 1.0 - HTTP, REST, WebSocket & MCP Server
High-performance async server for Cloud AI communication and local dashboard.
"""

import asyncio
import io
import json
import time
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
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
        version="1.0.0"
    )

    # Enable CORS for cloud requests and browser previews
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
            "version": "1.0.0",
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
                        "version": "1.0.0"
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
                data = await websocket.receive_json()
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
