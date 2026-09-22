"""
SHH 1.0 - Port Forwarding & Network Proxy Tools
Scan local ports, proxy HTTP requests to local services (e.g. localhost:3000, 8080).
"""

import asyncio
import socket
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

import psutil

from shh.tools.base import BaseTool, registry
from shh.utils.logger import Logger


class ListOpenPortsTool(BaseTool):
    name = "list_open_ports"
    description = "List all active TCP listening ports and the processes bound to them on the local computer."
    category = "network"
    parameters = {
        "type": "object",
        "properties": {}
    }

    async def execute(self) -> Dict[str, Any]:
        ports = []
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.status == "LISTEN":
                    pid = conn.pid
                    pname = ""
                    if pid:
                        try:
                            pname = psutil.Process(pid).name()
                        except Exception:
                            pass
                    ports.append({
                        "ip": conn.laddr.ip,
                        "port": conn.laddr.port,
                        "pid": pid,
                        "process_name": pname
                    })
        except Exception as e:
            # Fallback scan common ports
            common = [80, 443, 3000, 5000, 5173, 8000, 8080, 8888, 9000, 18888]
            for p in common:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.1)
                res = sock.connect_ex(("127.0.0.1", p))
                sock.close()
                if res == 0:
                    ports.append({"ip": "127.0.0.1", "port": p, "pid": None, "process_name": "unknown"})

        # Deduplicate & sort
        seen = set()
        unique_ports = []
        for p in ports:
            key = (p["ip"], p["port"])
            if key not in seen:
                seen.add(key)
                unique_ports.append(p)
        unique_ports.sort(key=lambda x: x["port"])

        return {
            "success": True,
            "total_open_ports": len(unique_ports),
            "open_ports": unique_ports
        }


class ProxyHTTPRequestTool(BaseTool):
    name = "proxy_http_request"
    description = "Make an HTTP request from inside the local machine to a local dev server (e.g. http://localhost:3000/api) and return the response."
    category = "network"
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Target URL (e.g. 'http://localhost:3000/api/users', 'http://127.0.0.1:8000/docs')."
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"],
                "default": "GET",
                "description": "HTTP Method."
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP request headers dictionary."
            },
            "body": {
                "type": "string",
                "description": "Optional request body string (JSON/text)."
            },
            "timeout": {
                "type": "integer",
                "default": 10,
                "description": "Request timeout in seconds."
            }
        },
        "required": ["url"]
    }

    async def execute(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
        timeout: int = 10
    ) -> Dict[str, Any]:
        Logger.tool_call("proxy_http_request", {"method": method, "url": url})
        try:
            req_headers = headers or {}
            data_bytes = body.encode("utf-8") if body else None
            req = urllib.request.Request(url, data=data_bytes, headers=req_headers, method=method)
            with urllib.request.urlopen(req, timeout=float(timeout)) as resp:
                status_code = resp.status
                resp_headers = dict(resp.getheaders())
                raw_body = resp.read()
                try:
                    body_text = raw_body.decode("utf-8")
                except UnicodeDecodeError:
                    import base64
                    body_text = base64.b64encode(raw_body).decode("utf-8")

                return {
                    "success": True,
                    "status_code": status_code,
                    "headers": resp_headers,
                    "body": body_text
                }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            return {
                "success": False,
                "status_code": e.code,
                "error": f"HTTP Error {e.code}: {e.reason}",
                "body": err_body
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Connection error: {str(e)}"
            }


# Register port tools
registry.register(ListOpenPortsTool())
registry.register(ProxyHTTPRequestTool())
