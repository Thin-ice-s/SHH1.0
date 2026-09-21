"""
SHH 1.0 - Zero-Dependency Cloud AI Python Controller
Pure Python Standard Library (No pip install required).
Works out of the box in ChatGPT Code Interpreter, Claude Artifacts, Cloud Jupyter, and Custom Python Sandboxes.
"""

import base64
import json
import ssl
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Union


class RemoteWindows:
    """
    Zero-dependency Python client for Cloud AI to control a remote Windows computer.
    """

    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE

    @classmethod
    def connect(cls, ticket_or_url: str) -> "RemoteWindows":
        """
        Connect using a ticket (shh://...) or a Public Board URL (https://dpaste.org/...).
        """
        target = ticket_or_url.strip()

        # 1. If it's a shh:// ticket
        if target.startswith("shh://"):
            raw_b64 = target[6:]
            padding = 4 - (len(raw_b64) % 4)
            if padding != 4:
                raw_b64 += "=" * padding
            json_str = base64.urlsafe_b64decode(raw_b64.encode("utf-8")).decode("utf-8")
            data = json.loads(json_str)
            return cls._from_meta(data)

        # 2. If it's an HTTP URL (public board)
        if target.startswith("http://") or target.startswith("https://"):
            if "dpaste.org" in target and not target.endswith(".txt"):
                target = f"{target}.txt"
            req = urllib.request.Request(target, headers={"User-Agent": "SHH-AI-Cloud/1.0"})
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                text = resp.read().decode("utf-8")
                try:
                    data = json.loads(text)
                except Exception:
                    # Search for ticket inside text
                    for line in text.splitlines():
                        if "shh://" in line:
                            t_part = line[line.find("shh://"):].strip()
                            return cls.connect(t_part)
                    raise ValueError(f"Could not parse valid connection JSON from {target}")
                return cls._from_meta(data)

        # 3. Direct host/port
        return cls(base_url=target)

    @classmethod
    def _from_meta(cls, meta: Dict[str, Any]) -> "RemoteWindows":
        token = meta.get("token")
        endpoints = meta.get("endpoints", {})
        ipv4 = endpoints.get("ipv4") or meta.get("public_ipv4")
        ipv6 = endpoints.get("ipv6") or meta.get("public_ipv6")
        lan_ip = endpoints.get("lan_ip") or meta.get("lan_ip", "127.0.0.1")
        port = endpoints.get("http_port") or meta.get("port", 18888)

        # If base_url already constructed
        if meta.get("http_base_url"):
            base_url = meta["http_base_url"]
        else:
            host = ipv4 or (f"[{ipv6}]" if ipv6 else lan_ip)
            base_url = f"http://{host}:{port}"

        return cls(base_url=base_url, token=token)

    def _call(self, endpoint: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 60.0) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        headers = {
            "User-Agent": "SHH-ZeroDep-Client/1.0",
            "Content-Type": "application/json"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        # If calling /api/tools or /api/exec, always POST JSON
        is_post = endpoint.startswith("/api/tools") or endpoint.startswith("/api/exec") or payload is not None
        body_dict = payload if payload is not None else ({} if is_post else None)
        data_bytes = json.dumps(body_dict).encode("utf-8") if body_dict is not None else None
        
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST" if is_post else "GET")

        try:
            with urllib.request.urlopen(req, timeout=timeout, context=self._ctx) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_text = e.read().decode("utf-8", errors="replace")
            try:
                return json.loads(err_text)
            except Exception:
                return {"success": False, "error": f"HTTP {e.code}: {err_text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==========================================
    # 💻 Core Execution & System Operations
    # ==========================================

    def exec(self, command: str, cwd: Optional[str] = None, shell: str = "auto", timeout: int = 60) -> str:
        """
        Execute a shell command (PowerShell / CMD / WSL) on Windows and return stdout string.
        """
        res = self._call("/api/exec", {
            "command": command,
            "cwd": cwd,
            "shell": shell,
            "timeout": timeout
        }, timeout=float(timeout + 5))

        if not res.get("success"):
            stderr = res.get("stderr") or res.get("error") or "Unknown error"
            return f"[Error: exit_code={res.get('exit_code')}]\n{stderr}"
        return res.get("stdout", "")

    def exec_raw(self, command: str, cwd: Optional[str] = None, shell: str = "auto", timeout: int = 60) -> Dict[str, Any]:
        """Execute a command and return full metadata dictionary (stdout, stderr, exit_code, duration)."""
        return self._call("/api/exec", {"command": command, "cwd": cwd, "shell": shell, "timeout": timeout}, timeout=float(timeout + 5))

    # ==========================================
    # 📂 File Management Operations
    # ==========================================

    def read_file(self, path: str, start_line: Optional[int] = None, max_lines: Optional[int] = None) -> str:
        """Read text file from Windows."""
        res = self._call("/api/tools/file_read", {"path": path, "start_line": start_line, "max_lines": max_lines})
        if not res.get("success"):
            raise FileNotFoundError(res.get("error"))
        return res.get("content", "")

    def write_file(self, path: str, content: str) -> bool:
        """Write or overwrite a file on Windows (creates parent directories automatically)."""
        res = self._call("/api/tools/file_write", {"path": path, "content": content})
        return res.get("success", False)

    def edit_file(self, path: str, old_text: str, new_text: str) -> bool:
        """Search and replace code block in a file."""
        res = self._call("/api/tools/file_edit", {"path": path, "old_text": old_text, "new_text": new_text})
        return res.get("success", False)

    def list_dir(self, path: Optional[str] = None) -> List[Dict[str, Any]]:
        """List files and folders in directory."""
        res = self._call("/api/tools/file_list", {"path": path})
        return res.get("items", [])

    def file_tree(self, path: Optional[str] = None, max_depth: int = 3) -> str:
        """Return visual ASCII tree structure of directory."""
        res = self._call("/api/tools/file_tree", {"path": path, "max_depth": max_depth})
        return res.get("tree_view", "")

    def search(self, path: Optional[str] = None, pattern: Optional[str] = None, grep: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search files by pattern (*.py) or content regex (grep)."""
        res = self._call("/api/tools/file_search", {"path": path, "filename_pattern": pattern, "content_regex": grep})
        return res.get("results", [])

    # ==========================================
    # 👁️ Vision & Multimodal Screen Capture
    # ==========================================

    def screenshot(self, save_local_cloud_path: Optional[str] = None, max_width: int = 1280) -> bytes:
        """
        Take a screenshot of the Windows desktop.
        Optionally saves it to a file in the Cloud AI's environment and returns raw JPEG bytes.
        """
        res = self._call("/api/tools/capture_screen", {"max_width": max_width, "quality": 75, "return_base64": True})
        if not res.get("success") or not res.get("image_data_uri"):
            raise RuntimeError(res.get("error", "Failed to capture screen"))

        b64_data = res["image_data_uri"].split(",", 1)[1]
        img_bytes = base64.b64decode(b64_data)

        if save_local_cloud_path:
            with open(save_local_cloud_path, "wb") as f:
                f.write(img_bytes)

        return img_bytes

    def screenshot_base64(self, max_width: int = 1280) -> str:
        """Return base64 data URI (data:image/jpeg;base64,...) for multimodal LLM message."""
        res = self._call("/api/tools/capture_screen", {"max_width": max_width, "quality": 75, "return_base64": True})
        return res.get("image_data_uri", "")

    # ==========================================
    # 🌐 Network, Ports & Processes
    # ==========================================

    def show_popup(self, message: str, title: str = "AI Notification") -> bool:
        """Display a native popup window / dialog on the user's Windows screen."""
        res = self._call("/api/tools/show_popup", {"message": message, "title": title})
        return res.get("success", False)

    def list_ports(self) -> List[Dict[str, Any]]:
        """List active listening ports on Windows."""
        res = self._call("/api/tools/list_open_ports")
        return res.get("open_ports", [])

    def proxy_http(self, url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None, body: Optional[str] = None) -> Dict[str, Any]:
        """Make HTTP request from inside Windows machine to a local dev server (e.g. localhost:3000)."""
        return self._call("/api/tools/proxy_http_request", {"url": url, "method": method, "headers": headers, "body": body})

    def list_processes(self, filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """List running processes on Windows."""
        res = self._call("/api/tools/list_processes", {"name_filter": filter})
        return res.get("processes", [])

    def start_background(self, command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        """Start long-running background process (e.g. dev server)."""
        return self._call("/api/tools/start_process", {"command": command, "cwd": cwd})

    def get_system_info(self) -> Dict[str, Any]:
        """Get CPU, RAM, OS, and disk drives info."""
        return self._call("/api/tools/get_system_info")


# Example test when run directly
if __name__ == "__main__":
    print("RemoteWindows Helper Module Ready.")
