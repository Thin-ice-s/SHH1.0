"""
SHH 1.0 - Stdio MCP (Model Context Protocol) Server
Enables direct integration with Claude Desktop, Cursor, Zed, Continue, and Cline via standard input/output.
"""

import asyncio
import json
import sys
from typing import Any, Dict, Optional

from shh.tools import registry
from shh.utils.logger import Logger


class MCPServerStdio:
    def __init__(self):
        self.running = False

    async def run(self):
        self.running = True
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while self.running:
            try:
                line = await reader.readline()
                if not line:
                    break
                
                raw_str = line.decode("utf-8").strip()
                if not raw_str:
                    continue

                try:
                    req = json.loads(raw_str)
                except json.JSONDecodeError:
                    continue

                resp = await self.handle_request(req)
                if resp is not None:
                    out_line = json.dumps(resp) + "\n"
                    sys.stdout.write(out_line)
                    sys.stdout.flush()

            except Exception as e:
                # Avoid printing to stdout in stdio mode, write to stderr
                sys.stderr.write(f"MCP Error: {str(e)}\n")
                sys.stderr.flush()

    async def handle_request(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        jsonrpc = req.get("jsonrpc", "2.0")
        method = req.get("method")
        msg_id = req.get("id")
        params = req.get("params", {})

        # Notifications without id
        if msg_id is None and method == "notifications/initialized":
            return None

        if method == "initialize":
            return {
                "jsonrpc": jsonrpc,
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False}
                    },
                    "serverInfo": {
                        "name": "SHH-Windows-Bridge",
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


def run_mcp_stdio():
    server = MCPServerStdio()
    asyncio.run(server.run())
