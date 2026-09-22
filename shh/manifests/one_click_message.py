"""
SHH 1.0 - One-Click AI Message Generator
Generates the single-message prompt with embedded Python controller and live tunnel URL.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from shh.config import SHHConfig
from shh.utils.win_helper import is_windows


def generate_ai_single_message(tunnel_url: str, config: SHHConfig) -> str:
    """Generate the single complete message for the user to copy-paste to Cloud AI."""
    code_template = f'''你好！你已被授权通过 SHH 1.0 桥梁连接并控制我的本地 Windows 电脑。请在你的 Python 环境中运行以下代码来连接我的电脑，并开始执行开发与控制任务：

```python
import urllib.request, json, base64, ssl

class RemoteWindows:
    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE

    def _call(self, endpoint, payload=None):
        url = f"{{self.base_url}}{{endpoint}}"
        headers = {{"User-Agent": "SHH-AI/1.0", "Content-Type": "application/json", "Authorization": f"Bearer {{self.token}}"}}
        body = json.dumps(payload or {{}}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120.0, context=self._ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def tools(self):
        """列出本机可用工具"""
        return self._call("/api/tools")

    def exec(self, cmd, cwd=None):
        """在 Windows 执行命令 (PowerShell / CMD)"""
        res = self._call("/api/exec", {{"command": cmd, "cwd": cwd}})
        return res.get("stdout") or res.get("stderr")

    def read_file(self, path):
        """读取 Windows 上的文件内容"""
        return self._call("/api/tools/file_read", {{"path": path}}).get("content", "")

    def write_file(self, path, content):
        """在 Windows 写入或修改文件"""
        return self._call("/api/tools/file_write", {{"path": path, "content": content}}).get("success", False)

    def file_tree(self, path=None, max_depth=3):
        """查看 Windows 目录树结构"""
        return self._call("/api/tools/file_tree", {{"path": path, "max_depth": max_depth}}).get("tree_view", "")

    def screenshot(self, save_path="desktop.jpg"):
        """截取 Windows 桌面屏幕图像 (供视觉分析)"""
        res = self._call("/api/tools/capture_screen", {{"max_width": 1280, "quality": 75, "return_base64": True}})
        b64 = res["image_data_uri"].split(",", 1)[1]
        data = base64.b64decode(b64)
        if save_path:
            with open(save_path, "wb") as f: f.write(data)
        return data

    def show_popup(self, message, title="AI Notification"):
        """在 Windows 桌面弹出提示窗口"""
        return self._call("/api/tools/show_popup", {{"message": message, "title": title}}).get("success", False)

    # ---------- 管理员 (Administrator) 能力 ----------
    def is_admin(self):
        """查询本机 SHH 是否以管理员权限运行"""
        return self._call("/api/tools/get_privilege_info")

    def admin_run(self, cmd, shell="cmd", timeout=120):
        """以管理员权限执行命令 (SHH 为管理员时静默执行，否则弹一次 UAC)"""
        res = self._call("/api/tools/run_admin_command", {{"command": cmd, "shell": shell, "timeout": timeout}})
        return res.get("stdout") or res.get("stderr") or res.get("error")

    def firewall(self, action="list", name="SHH 1.0 Rule", port=None):
        """管理 Windows 防火墙入站规则 (add / delete / list)"""
        return self._call("/api/tools/manage_firewall", {{"action": action, "name": name, "port": port}})

    def port_forward(self, action="list", listen_port=None, connect_host="127.0.0.1", connect_port=None):
        """管理 netsh 端口转发规则 (add / delete / list)"""
        return self._call("/api/tools/manage_port_forward", {{"action": action, "listen_port": listen_port, "connect_host": connect_host, "connect_port": connect_port}})

    def list_ports(self):
        """列出本地监听的端口"""
        return self._call("/api/tools/list_open_ports").get("open_ports", [])

    def proxy_http(self, url, method="GET", headers=None, body=None):
        """向本地 Web 服务发起 HTTP 请求测试 (如 localhost:3000)"""
        return self._call("/api/tools/proxy_http_request", {{"url": url, "method": method, "headers": headers, "body": body}})

    def get_system_info(self):
        """获取系统硬件与驱动器列表"""
        return self._call("/api/tools/get_system_info")

    # ---------- 大文件分块传输 (隧道稳定关键) ----------
    def _raw(self, method, url, headers=None, data=None, timeout=180):
        """底层原始二进制 HTTP 请求 (不走 base64/JSON，开销最小)"""
        hdrs = {{"User-Agent": "SHH-AI/1.1"}}
        if self.token: hdrs["X-SHH-Token"] = self.token
        if headers: hdrs.update(headers)
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        with urllib.request.urlopen(req, timeout=timeout, context=self._ctx) as resp:
            # HTTP 头名大小写不敏感(Starlette 会小写化)，统一转小写后查表
            return resp.status, {{k.lower(): v for k, v in resp.headers.items()}}, resp.read()

    RETRYABLE_HTTP = (408, 409, 425, 429, 500, 502, 503, 504, 522, 524)

    def _retry(self, fn, what="chunk", attempts=6):
        """单块失败自动重试(指数退避)；网络闪断重试，参数类错误立即报错"""
        import urllib.error
        delay, last = 1.5, None
        for i in range(1, attempts + 1):
            try:
                return fn()
            except urllib.error.HTTPError as e:
                if e.code not in self.RETRYABLE_HTTP:
                    detail = ""
                    try: detail = e.read(200).decode("utf-8", "replace")
                    except Exception: pass
                    raise RuntimeError("HTTP %s 不可重试错误 (%s): %s" % (e.code, what, detail))
                last = e
            except (TypeError, ValueError, KeyError) as e:
                raise RuntimeError("请求参数错误 (%s): %s" % (what, e))
            except Exception as e:
                last = e
            if i == attempts: break
            print("  [retry %d/%d] %s 失败(%s)，%.1fs 后重试" % (i, attempts, what, str(last)[:80], delay))
            time.sleep(delay); delay = min(delay * 1.8, 20)
        raise RuntimeError("%s 重试 %d 次后仍失败: %s" % (what, attempts, last))

    def upload(self, local_path, remote_path=None, chunk_size=524288, compress=True, resume=True):
        """把云端文件分块上传到我的 Windows 电脑 (支持断点续传/压缩/校验)"""
        import os, gzip, hashlib, urllib.parse, json, time
        remote_path = remote_path or os.path.basename(local_path)
        size = os.path.getsize(local_path)
        quoted = urllib.parse.quote(remote_path, safe="")
        start = 0
        if resume:
            st = self._call("/api/tools/file_stat", {{"path": remote_path}})
            start = int(st.get("size_bytes") or 0) if st.get("exists") else 0
        sent, t0 = start, time.time()
        with open(local_path, "rb") as fh:
            fh.seek(start)
            while sent < size:
                chunk = fh.read(chunk_size)
                if not chunk: break
                offset, digest = sent, hashlib.sha256(chunk).hexdigest()
                def _send(chunk=chunk, offset=offset, digest=digest):
                    body = gzip.compress(chunk, 5) if compress else chunk
                    h = {{"X-SHH-Path": quoted, "X-SHH-Offset": str(offset), "X-SHH-Sha256": digest,
                          "Content-Type": "application/octet-stream", "Content-Length": str(len(body))}}
                    if compress: h["X-SHH-Compress"] = "gzip"
                    if offset == 0: h["X-SHH-Truncate"] = "1"
                    status, _, raw = self._raw("POST", self.base_url + "/api/transfer/upload", h, body)
                    if status != 200: raise RuntimeError("HTTP %s: %s" % (status, raw[:150]))
                    res = json.loads(raw.decode("utf-8"))
                    if not res.get("success"): raise RuntimeError(res.get("error", "rejected"))
                    return res
                try:
                    self._retry(_send, "上传块 @%d" % offset)
                except Exception:
                    if not resume: raise
                    st = self._call("/api/tools/file_stat", {{"path": remote_path}})
                    actual = int(st.get("size_bytes") or 0) if st.get("exists") else 0
                    print("  [续传] 服务端已有 %d 字节，从该位置继续" % actual)
                    fh.seek(actual); sent = actual; continue
                sent += len(chunk)
                print("\\r  上传 %s: %d/%d (%.1f%%)" % (remote_path, sent, size, sent * 100.0 / size), end="")
        print()
        chk = self._call("/api/tools/file_checksum", {{"path": remote_path}})
        return {{"success": True, "remote_path": remote_path, "bytes_sent": sent,
                "remote_sha256": chk.get("sha256"), "elapsed": round(time.time() - t0, 2)}}

    def download(self, remote_path, local_path=None, chunk_size=524288, compress=True):
        """从我的 Windows 电脑分块下载文件 (支持断点续传/压缩/校验)"""
        import os, gzip, hashlib, urllib.parse, time
        local_path = local_path or os.path.basename(remote_path.replace("\\\\", "/"))
        quoted = urllib.parse.quote(remote_path, safe="")
        offset = os.path.getsize(local_path) if os.path.exists(local_path) else 0
        t0, total = time.time(), None
        with open(local_path, "ab" if offset else "wb") as fh:
            while True:
                def _fetch(offset=offset):
                    url = "%s/api/transfer/download?path=%s&offset=%d&length=%d&compress=%s" % (
                        self.base_url, quoted, offset, chunk_size, "gzip" if compress else "none")
                    status, h, body = self._raw("GET", url)
                    if status != 200: raise RuntimeError("HTTP %s: %s" % (status, body[:150]))
                    return h, body
                try:
                    h, body = self._retry(_fetch, "下载块 @%d" % offset)
                except Exception:
                    print("\\n  [中断] 已保存 %d 字节，再次调用 download() 可自动续传" % offset)
                    break
                total = int(h.get("x-shh-total-size") or 0)
                if h.get("x-shh-compressed") == "1": body = gzip.decompress(body)
                expect = h.get("x-shh-sha256")
                if expect and hashlib.sha256(body).hexdigest() != expect:
                    raise RuntimeError("块校验失败 @%d，请重试" % offset)
                if not body: break
                fh.write(body); offset += len(body)
                print("\\r  下载 %s: %d/%s (%.1f%%)" % (remote_path, offset, total or "?", offset * 100.0 / (total or 1)), end="")
                if h.get("x-shh-eof") == "1": break
        print()
        return {{"success": True, "local_path": local_path, "bytes_received": offset,
                "remote_size": total, "complete": (total is None) or (offset == total),
                "elapsed": round(time.time() - t0, 2)}}

    def put_text(self, remote_path, text):
        """写文本文件到我的电脑 (自动分块，任意大小都安全)"""
        import gzip, hashlib, urllib.parse
        raw = text.encode("utf-8"); quoted = urllib.parse.quote(remote_path, safe=""); sent = 0
        while True:
            chunk = raw[sent:sent + 524288]
            body = gzip.compress(chunk, 5)
            h = {{"X-SHH-Path": quoted, "X-SHH-Offset": str(sent), "X-SHH-Sha256": hashlib.sha256(chunk).hexdigest(),
                  "Content-Type": "application/octet-stream", "Content-Length": str(len(body)), "X-SHH-Compress": "gzip"}}
            if sent == 0: h["X-SHH-Truncate"] = "1"
            self._retry(lambda: self._raw("POST", self.base_url + "/api/transfer/upload", h, body), "put_text @%d" % sent)
            if not chunk: break
            sent += len(chunk)
            if sent >= len(raw): break
        return {{"success": True, "remote_path": remote_path, "bytes": len(raw)}}

    def get_text(self, remote_path, max_bytes=4194304):
        """读我的电脑上的文本文件 (自动分块)"""
        import gzip, urllib.parse
        quoted = urllib.parse.quote(remote_path, safe=""); offset = 0; parts = []
        while True:
            url = "%s/api/transfer/download?path=%s&offset=%d&length=524288&compress=gzip" % (self.base_url, quoted, offset)
            status, h, body = self._retry(lambda: self._raw("GET", url), "get_text @%d" % offset)
            if status != 200: raise RuntimeError("HTTP %s 读取失败: %s" % (status, remote_path))
            if h.get("x-shh-compressed") == "1": body = gzip.decompress(body)
            if not body: break
            parts.append(body); offset += len(body)
            if h.get("x-shh-eof") == "1" or offset >= max_bytes: break
        return b"".join(parts).decode("utf-8", errors="replace")

    def tunnel_status(self):
        """查询隧道健康状态 (地址是否固定、是否正在重连)"""
        return self._call("/api/health").get("tunnel", {{}})

# 🔗 1. 连接我的电脑 (URL 已内置，含动态隧道地址)
win = RemoteWindows("{tunnel_url}", "{config.token}")

# 💻 2. 测试运行 (查看系统信息与目录)
print("✔ 连接成功！系统信息:", win.get_system_info().get("os"))
print("🔐 权限状态:", win.is_admin().get("elevation_hint"))
print(win.exec("dir"))
```

**可用工具调用方式**：`win.exec()` 执行命令、`win.read_file()` / `win.write_file()` 读写文件、`win.file_tree()` 看目录、`win.screenshot()` 截图、`win.show_popup()` 弹窗、`win.admin_run()` 管理员命令、`win.firewall()` / `win.port_forward()` 端口与防火墙管理。

**大文件传输（重要）**：上传用 `win.upload(local_path, remote_path)`，下载用 `win.download(remote_path, local_path)`，小文本用 `win.put_text/get_text`。
它们会把文件切成 512KB 小块、逐块 gzip 压缩、每块 sha256 校验、失败自动重试并支持断点续传。
**千万不要**用 `file_write` 一次写入大文件（单包过大会导致隧道断链）；需要时先调 `win._call("/api/tools/file_transfer_info")` 查看当前安全上限。
隧道状态可随时用 `win.tunnel_status()` 查询（是否固定地址、是否在重连）。

请在连接成功后：先确认连接正常，然后等待我的下一步指令。若连接失败，请把完整报错贴给我。
'''
    return code_template.strip()


def copy_to_windows_clipboard(text: str) -> bool:
    """
    Copy arbitrary text to the Windows clipboard using PowerShell.
    Uses a temp file + Get-Content -Raw so any quotes / newlines / emoji are safe.
    """
    if not is_windows():
        return False

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix="shh_clip_", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as f:
            f.write(text)

        ps_cmd = (
            "[Console]::InputEncoding = [System.Text.Encoding]::UTF8; "
            "Get-Content -LiteralPath '%s' -Raw -Encoding UTF8 | Set-Clipboard"
        ) % tmp_path.replace("'", "''")

        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=25,
        )
        return proc.returncode == 0
    except Exception:
        return False
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
