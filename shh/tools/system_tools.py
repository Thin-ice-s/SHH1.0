"""
SHH 1.0 - System Information & Environment Tools
Inspect hardware, memory, disk partitions, network interfaces, and show UI notifications.
"""

import os
import platform
import socket
import subprocess
import threading
from typing import Any, Dict, List, Optional

import psutil

from shh.tools.base import BaseTool, registry
from shh.utils.logger import Logger
from shh.utils.win_helper import get_windows_drives, is_windows


class ShowPopupTool(BaseTool):
    name = "show_popup"
    description = "Display a native Windows popup dialog / message box on the user's screen."
    category = "system"
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "default": "AI Notification",
                "description": "Title of the popup window."
            },
            "message": {
                "type": "string",
                "description": "Message text to display in the popup."
            }
        },
        "required": ["message"]
    }

    async def execute(self, message: str, title: str = "AI Notification") -> Dict[str, Any]:
        Logger.tool_call("show_popup", {"title": title, "message": message})
        
        def _show():
            if is_windows():
                try:
                    import ctypes
                    # MB_OK (0x0) | MB_ICONINFORMATION (0x40) | MB_SYSTEMMODAL (0x1000)
                    ctypes.windll.user32.MessageBoxW(0, message, title, 0x40 | 0x1000)
                    return
                except Exception:
                    pass
                # Fallback PowerShell MessageBox
                try:
                    ps_cmd = f'[System.Windows.Forms.MessageBox]::Show("{message}", "{title}")'
                    subprocess.run(["powershell.exe", "-Command", f"Add-Type -AssemblyName System.Windows.Forms; {ps_cmd}"], timeout=15)
                    return
                except Exception:
                    pass
            Logger.info(f"[POPUP NOTIFICATION] {title}: {message}")

        # Run non-blocking in background thread so API doesn't hang while waiting for user to click OK
        threading.Thread(target=_show, daemon=True).start()

        return {
            "success": True,
            "title": title,
            "message": message,
            "status": "displayed"
        }


class GetSystemInfoTool(BaseTool):
    name = "get_system_info"
    description = "Retrieve comprehensive system hardware, OS version, CPU, RAM, disk space, and network info."
    category = "system"
    parameters = {
        "type": "object",
        "properties": {}
    }

    async def execute(self) -> Dict[str, Any]:
        # Memory
        mem = psutil.virtual_memory()
        mem_info = {
            "total_gb": round(mem.total / (1024 ** 3), 2),
            "available_gb": round(mem.available / (1024 ** 3), 2),
            "used_percent": mem.percent
        }

        # Disk
        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2),
                    "used_percent": usage.percent
                })
            except Exception:
                continue

        # CPU
        cpu_info = {
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "cpu_percent": psutil.cpu_percent(interval=0.1)
        }

        # Network
        net_info = {}
        for iface_name, addrs in psutil.net_if_addrs().items():
            net_info[iface_name] = [a.address for a in addrs if a.family in (socket.AF_INET, socket.AF_INET6)]

        return {
            "success": True,
            "os": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "architecture": platform.machine(),
                "node_name": platform.node(),
                "is_windows": is_windows()
            },
            "cpu": cpu_info,
            "memory": mem_info,
            "disks": disks,
            "workspace": os.getcwd(),
            "drives": get_windows_drives() if is_windows() else ["/"]
        }


class GetEnvVarsTool(BaseTool):
    name = "get_env_vars"
    description = "Get system environment variables or query a specific environment variable."
    category = "system"
    parameters = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Specific environment variable name to query (e.g. 'PATH', 'PYTHONPATH', 'USER'). Omit for all safe variables."
            }
        }
    }

    async def execute(self, key: Optional[str] = None) -> Dict[str, Any]:
        if key:
            val = os.environ.get(key)
            return {
                "success": True,
                "key": key,
                "value": val,
                "found": val is not None
            }

        # Filter sensitive credentials if any
        safe_env = {}
        sensitive_keywords = {"password", "secret", "token", "key", "auth", "credential"}
        for k, v in os.environ.items():
            if any(kw in k.lower() for kw in sensitive_keywords):
                safe_env[k] = "[REDACTED]"
            else:
                safe_env[k] = v

        return {
            "success": True,
            "total_vars": len(safe_env),
            "environment_variables": safe_env
        }


# Register system tools
registry.register(ShowPopupTool())
registry.register(GetSystemInfoTool())
registry.register(GetEnvVarsTool())
