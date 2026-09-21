"""
SHH 1.0 - Cloud AI Python Client SDK
Allows Cloud AI agents (OpenAI, Claude, LangChain, Custom Bots) to connect to local Windows machines.
"""

import json
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from shh.discovery.rendezvous import RendezvousManager


class SHHClient:
    """Client for Cloud AI to invoke tools on a remote Windows computer."""

    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.token = token

    @classmethod
    def from_board(cls, board_url_or_ticket: str) -> "SHHClient":
        """Initialize client by resolving connection metadata from a Public Board URL or Ticket."""
        meta = RendezvousManager.fetch(board_url_or_ticket)
        token = meta.get("token")
        
        # Determine best base_url
        endpoints = meta.get("endpoints", {})
        ipv4 = endpoints.get("ipv4") or meta.get("public_ipv4")
        ipv6 = endpoints.get("ipv6") or meta.get("public_ipv6")
        lan_ip = endpoints.get("lan_ip") or meta.get("lan_ip", "127.0.0.1")
        port = endpoints.get("http_port") or meta.get("port", 18888)

        # Prefer direct IPv4 or IPv6
        host = ipv4 or (f"[{ipv6}]" if ipv6 else lan_ip)
        base_url = meta.get("http_base_url") or f"http://{host}:{port}"
        
        return cls(base_url=base_url, token=token)

    @classmethod
    def from_ticket(cls, ticket: str) -> "SHHClient":
        return cls.from_board(ticket)

    def _request(self, method: str, endpoint: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 60.0) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        headers = {
            "User-Agent": "SHH-Cloud-Client/1.0",
            "Content-Type": "application/json"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        data_bytes = json.dumps(payload).encode("utf-8") if payload else None
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            err_raw = e.read().decode("utf-8", errors="replace")
            try:
                return json.loads(err_raw)
            except Exception:
                return {"success": False, "error": f"HTTP {e.code}: {err_raw}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- Tool Callers ---

    def call_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Invoke any tool by name with arbitrary parameters."""
        return self._request("POST", f"/api/tools/{tool_name}", kwargs)

    def exec_shell(self, command: str, cwd: Optional[str] = None, shell: str = "auto", timeout: int = 60) -> Dict[str, Any]:
        """Execute a shell command on the local Windows PC."""
        return self._request("POST", "/api/exec", {
            "command": command,
            "cwd": cwd,
            "shell": shell,
            "timeout": timeout
        }, timeout=float(timeout + 5))

    def read_file(self, path: str, start_line: Optional[int] = None, max_lines: Optional[int] = None, encoding: str = "utf-8") -> Dict[str, Any]:
        """Read a file from local disk."""
        return self.call_tool("file_read", path=path, start_line=start_line, max_lines=max_lines, encoding=encoding)

    def write_file(self, path: str, content: Optional[str] = None, content_base64: Optional[str] = None) -> Dict[str, Any]:
        """Write content to a file."""
        return self.call_tool("file_write", path=path, content=content, content_base64=content_base64)

    def edit_file(self, path: str, old_text: str, new_text: str) -> Dict[str, Any]:
        """Search and replace text in a file."""
        return self.call_tool("file_edit", path=path, old_text=old_text, new_text=new_text)

    def list_dir(self, path: Optional[str] = None, show_hidden: bool = False) -> Dict[str, Any]:
        """List files in directory."""
        return self.call_tool("file_list", path=path, show_hidden=show_hidden)

    def file_tree(self, path: Optional[str] = None, max_depth: int = 3) -> Dict[str, Any]:
        """Get visual tree of directory."""
        return self.call_tool("file_tree", path=path, max_depth=max_depth)

    def search_files(self, path: Optional[str] = None, filename_pattern: Optional[str] = None, content_regex: Optional[str] = None) -> Dict[str, Any]:
        """Search files by pattern or content."""
        return self.call_tool("file_search", path=path, filename_pattern=filename_pattern, content_regex=content_regex)

    def capture_screen(self, max_width: int = 1280, quality: int = 75, return_base64: bool = True) -> Dict[str, Any]:
        """Take a screenshot of the local Windows desktop for multimodal vision."""
        return self.call_tool("capture_screen", max_width=max_width, quality=quality, return_base64=return_base64)

    def get_screen_info(self) -> Dict[str, Any]:
        """Get screen resolution and open window positions."""
        return self.call_tool("get_screen_info")

    def list_processes(self, name_filter: Optional[str] = None, limit: int = 30) -> Dict[str, Any]:
        """List running processes."""
        return self.call_tool("list_processes", name_filter=name_filter, limit=limit)

    def kill_process(self, pid: Optional[int] = None, name: Optional[str] = None, force: bool = True) -> Dict[str, Any]:
        """Terminate a process."""
        return self.call_tool("kill_process", pid=pid, name=name, force=force)

    def start_process(self, command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        """Start a persistent background process."""
        return self.call_tool("start_process", command=command, cwd=cwd)

    def list_open_ports(self) -> Dict[str, Any]:
        """List open listening TCP ports."""
        return self.call_tool("list_open_ports")

    def proxy_http(self, url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None, body: Optional[str] = None) -> Dict[str, Any]:
        """Make an HTTP request from inside the local machine."""
        return self.call_tool("proxy_http_request", url=url, method=method, headers=headers, body=body)

    def get_system_info(self) -> Dict[str, Any]:
        """Get system hardware and environment specs."""
        return self.call_tool("get_system_info")

    def get_tools_schema(self) -> Dict[str, Any]:
        """Fetch OpenAI/Claude/MCP tool schemas from server."""
        return self._request("GET", "/api/tools")
