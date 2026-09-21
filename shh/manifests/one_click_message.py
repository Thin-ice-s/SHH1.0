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

# 🔗 1. 连接我的电脑 (URL 已内置，含动态隧道地址)
win = RemoteWindows("{tunnel_url}", "{config.token}")

# 💻 2. 测试运行 (查看系统信息与目录)
print("✔ 连接成功！系统信息:", win.get_system_info().get("os"))
print("🔐 权限状态:", win.is_admin().get("elevation_hint"))
print(win.exec("dir"))
```

**可用工具调用方式**：`win.exec()` 执行命令、`win.read_file()` / `win.write_file()` 读写文件、`win.file_tree()` 看目录、`win.screenshot()` 截图、`win.show_popup()` 弹窗、`win.admin_run()` 管理员命令、`win.firewall()` / `win.port_forward()` 端口与防火墙管理。需要完整工具列表时调用 `win.tools()` 或 `win._call("/api/tools")`。

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
