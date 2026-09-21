"""
SHH 1.0 - One-Click AI Message Generator
Generates the single-message prompt with embedded Python controller and live tunnel URL.
"""

import subprocess
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
        with urllib.request.urlopen(req, timeout=60.0, context=self._ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))

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

    def list_ports(self):
        """列出本地监听的端口"""
        return self._call("/api/tools/list_open_ports").get("open_ports", [])

    def proxy_http(self, url, method="GET", headers=None, body=None):
        """向本地 Web 服务发起 HTTP 请求测试 (如 localhost:3000)"""
        return self._call("/api/tools/proxy_http_request", {{"url": url, "method": method, "headers": headers, "body": body}})

    def get_system_info(self):
        """获取系统硬件与驱动器列表"""
        return self._call("/api/tools/get_system_info")

# 🔗 1. 连接我的电脑
win = RemoteWindows("{tunnel_url}", "{config.token}")

# 💻 2. 测试运行 (查看系统信息与目录)
print("✔ 连接成功！系统信息:", win.get_system_info().get("os"))
print(win.exec("dir"))
```
'''
    return code_template.strip()


def copy_to_windows_clipboard(text: str) -> bool:
    """Copy text to Windows clipboard using PowerShell."""
    if is_windows():
        try:
            # Escape single quotes
            escaped = text.replace("'", "''")
            ps_cmd = f"Set-Clipboard -Value @'\n{text}\n'@"
            subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps_cmd], timeout=5)
            return True
        except Exception:
            pass
    return False
