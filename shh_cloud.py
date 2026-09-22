"""
SHH 1.0 - Zero-Dependency Cloud AI Python Controller
Pure Python Standard Library (No pip install required).
Works out of the box in ChatGPT Code Interpreter, Claude Artifacts, Cloud Jupyter, and Custom Python Sandboxes.
"""

import base64
import json
import os
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

    # ==========================================
    # 📦 Chunked / resumable file transfer
    #   Small chunks = a dropped tunnel costs one chunk, not the whole file.
    #   Never send a big file through file_write: large packets kill tunnels.
    # ==========================================

    RETRYABLE_HTTP = (408, 409, 425, 429, 500, 502, 503, 504, 522, 524)
    CHUNK = 512 * 1024

    def _raw(self, method: str, url: str, headers=None, data=None, timeout=180):
        """Low-level raw HTTP call (no base64/JSON overhead) - used by upload/download."""
        import ssl
        hdrs = {"User-Agent": "SHH-ZeroDep-Client/1.1"}
        if self.token:
            hdrs["X-SHH-Token"] = self.token
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        with urllib.request.urlopen(req, timeout=timeout, context=self._ctx) as resp:
            body = resp.read()
            # header names are case-insensitive (Starlette lower-cases them)
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body

    def _retry(self, fn, what: str = "chunk", attempts: int = 6):
        """Retry transient failures only; permanent errors fail fast with a clear message."""
        delay, last = 1.5, None
        for i in range(1, attempts + 1):
            try:
                return fn()
            except urllib.error.HTTPError as exc:
                if exc.code not in self.RETRYABLE_HTTP:
                    detail = ""
                    try:
                        detail = exc.read(200).decode("utf-8", "replace")
                    except Exception:
                        pass
                    raise RuntimeError("HTTP %s (not retryable) on %s: %s" % (exc.code, what, detail))
                last = exc
            except (TypeError, ValueError, KeyError) as exc:
                raise RuntimeError("invalid request while trying to %s: %s" % (what, exc))
            except Exception as exc:
                last = exc
            if i == attempts:
                break
            print("  [retry %d/%d] %s failed (%s) - waiting %.1fs" % (i, attempts, what, str(last)[:80], delay))
            time.sleep(delay)
            delay = min(delay * 1.8, 20)
        raise RuntimeError("%s failed after %d attempts: %s" % (what, attempts, last))

    def _remote_size(self, remote_path: str) -> int:
        res = self._call("/api/tools/file_stat", {"path": remote_path})
        return int(res.get("size_bytes") or 0) if res.get("exists") else 0

    def upload(self, local_path: str, remote_path: str = None, chunk_size: int = None,
               compress: bool = True, resume: bool = True, progress: bool = True) -> Dict[str, Any]:
        """Upload a local file to the Windows machine in resumable, compressed chunks."""
        import gzip, hashlib, urllib.parse
        chunk_size = chunk_size or self.CHUNK
        remote_path = remote_path or os.path.basename(local_path)
        size = os.path.getsize(local_path)
        quoted = urllib.parse.quote(remote_path, safe="")
        sent = self._remote_size(remote_path) if resume else 0
        if sent > size:
            sent = 0
        started = time.time()
        with open(local_path, "rb") as fh:
            fh.seek(sent)
            while sent < size:
                chunk = fh.read(chunk_size)
                if not chunk:
                    break
                offset, digest = sent, hashlib.sha256(chunk).hexdigest()

                def _send(chunk=chunk, offset=offset, digest=digest):
                    payload = gzip.compress(chunk, 5) if compress else chunk
                    hdrs = {
                        "X-SHH-Path": quoted,
                        "X-SHH-Offset": str(offset),
                        "X-SHH-Sha256": digest,
                        "Content-Type": "application/octet-stream",
                        "Content-Length": str(len(payload)),
                    }
                    if compress:
                        hdrs["X-SHH-Compress"] = "gzip"
                    if offset == 0:
                        hdrs["X-SHH-Truncate"] = "1"
                    status, _, raw = self._raw("POST", self.base_url + "/api/transfer/upload", hdrs, payload)
                    if status != 200:
                        raise RuntimeError("HTTP %s: %s" % (status, raw[:150]))
                    return json.loads(raw.decode("utf-8"))

                try:
                    self._retry(_send, "upload chunk @%d" % offset)
                except Exception:
                    if not resume:
                        raise
                    actual = self._remote_size(remote_path)
                    print("  [resume] remote already has %d bytes, continuing" % actual)
                    fh.seek(actual)
                    sent = actual
                    continue
                sent += len(chunk)
                if progress:
                    print("  uploading %s: %.1f%% (%d/%d)" % (remote_path, sent * 100.0 / size, sent, size))
        chk = self._call("/api/tools/file_checksum", {"path": remote_path})
        return {"success": True, "remote_path": remote_path, "bytes_sent": sent,
                "remote_sha256": chk.get("sha256"), "elapsed_seconds": round(time.time() - started, 2)}

    def download(self, remote_path: str, local_path: str = None, chunk_size: int = None,
                 compress: bool = True, progress: bool = True) -> Dict[str, Any]:
        """Download a file from the Windows machine in resumable chunks (raw binary)."""
        import gzip, hashlib, urllib.parse
        chunk_size = chunk_size or self.CHUNK
        local_path = local_path or os.path.basename(remote_path.replace("\\", "/"))
        quoted = urllib.parse.quote(remote_path, safe="")
        offset = os.path.getsize(local_path) if os.path.exists(local_path) else 0
        total, started = None, time.time()
        with open(local_path, "ab" if offset else "wb") as fh:
            while True:
                def _fetch(offset=offset):
                    url = "%s/api/transfer/download?path=%s&offset=%d&length=%d&compress=%s" % (
                        self.base_url, quoted, offset, chunk_size, "gzip" if compress else "none")
                    status, hdrs, body = self._raw("GET", url)
                    if status != 200:
                        raise RuntimeError("HTTP %s: %s" % (status, body[:150]))
                    return hdrs, body

                try:
                    hdrs, body = self._retry(_fetch, "download chunk @%d" % offset)
                except Exception:
                    print("\n  [interrupted] %d bytes saved; call download() again to resume" % offset)
                    break
                total = int(hdrs.get("x-shh-total-size") or 0)
                if hdrs.get("x-shh-compressed") == "1":
                    body = gzip.decompress(body)
                expect = hdrs.get("x-shh-sha256")
                if expect and hashlib.sha256(body).hexdigest() != expect:
                    raise RuntimeError("chunk checksum mismatch at offset %d - retry" % offset)
                if not body:
                    break
                fh.write(body)
                offset += len(body)
                if progress:
                    print("  downloading %s: %d/%s" % (remote_path, offset, total or "?"))
                if hdrs.get("x-shh-eof") == "1":
                    break
        return {"success": True, "local_path": local_path, "bytes_received": offset,
                "remote_size": total, "complete": (total is None) or (offset == total),
                "elapsed_seconds": round(time.time() - started, 2)}

    def put_text(self, remote_path: str, text: str) -> Dict[str, Any]:
        """Write a text file on the Windows machine (chunked - any size is safe)."""
        import gzip, hashlib, urllib.parse
        raw = text.encode("utf-8")
        quoted = urllib.parse.quote(remote_path, safe="")
        sent = 0
        while True:
            chunk = raw[sent:sent + self.CHUNK]
            payload = gzip.compress(chunk, 5)
            hdrs = {"X-SHH-Path": quoted, "X-SHH-Offset": str(sent),
                    "X-SHH-Sha256": hashlib.sha256(chunk).hexdigest(),
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(len(payload)), "X-SHH-Compress": "gzip"}
            if sent == 0:
                hdrs["X-SHH-Truncate"] = "1"
            self._retry(lambda: self._raw("POST", self.base_url + "/api/transfer/upload", hdrs, payload),
                        "put_text @%d" % sent)
            if not chunk:
                break
            sent += len(chunk)
            if sent >= len(raw):
                break
        return {"success": True, "remote_path": remote_path, "bytes": len(raw)}

    def get_text(self, remote_path: str, max_bytes: int = 4 * 1024 * 1024) -> str:
        """Read a text file from the Windows machine (chunked)."""
        import gzip, urllib.parse
        quoted = urllib.parse.quote(remote_path, safe="")
        offset, parts = 0, []
        while True:
            url = "%s/api/transfer/download?path=%s&offset=%d&length=%d&compress=gzip" % (
                self.base_url, quoted, offset, self.CHUNK)
            status, hdrs, body = self._retry(lambda: self._raw("GET", url), "get_text @%d" % offset)
            if status != 200:
                raise RuntimeError("HTTP %s reading %s" % (status, remote_path))
            if hdrs.get("x-shh-compressed") == "1":
                body = gzip.decompress(body)
            if not body:
                break
            parts.append(body)
            offset += len(body)
            if hdrs.get("x-shh-eof") == "1" or offset >= max_bytes:
                break
        return b"".join(parts).decode("utf-8", errors="replace")

    def tunnel_status(self) -> Dict[str, Any]:
        """Tunnel health: fixed address? reconnecting? provider? (from /api/health)"""
        return self._call("/api/health").get("tunnel", {})


# Example test when run directly
if __name__ == "__main__":
    print("RemoteWindows Helper Module Ready.")
