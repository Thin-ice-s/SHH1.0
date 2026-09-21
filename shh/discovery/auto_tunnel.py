"""
SHH 1.0 - Fully Integrated Automatic Public Tunnel Engine
Auto-manages background tunnels (Cloudflare, Pinggy, Localhost.run) with zero manual intervention.
"""

import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from typing import Any, Dict, Optional, Tuple

from shh.utils.logger import Logger
from shh.utils.win_helper import is_windows


class AutoTunnelManager:
    """Integrated background tunnel daemon."""
    _active_tunnel: Optional[Dict[str, Any]] = None
    _proc: Optional[subprocess.Popen] = None

    @classmethod
    def get_cloudflared_path(cls) -> Optional[str]:
        """Find or verify cloudflared executable."""
        # 1. In current directory
        local_name = "cloudflared.exe" if is_windows() else "cloudflared"
        if os.path.exists(local_name):
            return os.path.abspath(local_name)

        # 2. In PATH
        in_path = shutil.which("cloudflared") or shutil.which("cloudflared.exe")
        if in_path:
            return in_path

        return None

    @classmethod
    def start_tunnel(cls, local_port: int = 18888, timeout: float = 15.0) -> Optional[str]:
        """
        Start the best available public tunnel in background and return the live HTTPS public URL.
        """
        # 1. Try Cloudflare Quick Tunnel (Best & Most Stable)
        cf_path = cls.get_cloudflared_path()
        if cf_path:
            Logger.info("Starting integrated Cloudflare Tunnel...")
            url = cls._start_cloudflared(cf_path, local_port, timeout=timeout)
            if url:
                return url

        # 2. Try native SSH reverse tunnel (localhost.run / pinggy)
        Logger.info("Trying integrated SSH reverse tunnel...")
        ssh_url = cls._start_ssh_tunnel(local_port, timeout=timeout)
        if ssh_url:
            return ssh_url

        return None

    @classmethod
    def _start_cloudflared(cls, cf_bin: str, local_port: int, timeout: float = 15.0) -> Optional[str]:
        try:
            cmd = [cf_bin, "tunnel", "--protocol", "http2", "--url", f"http://localhost:{local_port}", "--no-autoupdate"]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            cls._proc = proc

            start_t = time.time()
            tunnel_url = None

            for line in iter(proc.stderr.readline, ''):
                if not line:
                    if proc.poll() is not None:
                        break
                    continue
                match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if match:
                    tunnel_url = match.group(0)
                    break
                if time.time() - start_t > timeout:
                    break

            if tunnel_url:
                cls._active_tunnel = {
                    "provider": "cloudflare",
                    "url": tunnel_url,
                    "proc": proc
                }
                return tunnel_url
        except Exception as e:
            Logger.warning(f"Failed to start integrated cloudflared: {e}")
        return None

    @classmethod
    def _start_ssh_tunnel(cls, local_port: int, timeout: float = 12.0) -> Optional[str]:
        ssh_bin = shutil.which("ssh") or shutil.which("ssh.exe")
        if not ssh_bin:
            return None

        try:
            cmd = [
                ssh_bin,
                "-o", "StrictHostKeyChecking=no",
                "-o", "ServerAliveInterval=30",
                "-R", f"80:localhost:{local_port}",
                "nokey@localhost.run"
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            cls._proc = proc

            start_t = time.time()
            tunnel_url = None

            for line in iter(proc.stdout.readline, ''):
                if not line:
                    if proc.poll() is not None:
                        break
                    continue
                match = re.search(r"https://[a-zA-Z0-9.-]+\.lhr\.life", line)
                if match:
                    tunnel_url = match.group(0)
                    break
                if time.time() - start_t > timeout:
                    break

            if tunnel_url:
                cls._active_tunnel = {
                    "provider": "localhost.run",
                    "url": tunnel_url,
                    "proc": proc
                }
                return tunnel_url
        except Exception:
            pass
        return None

    @classmethod
    def stop(cls):
        if cls._proc:
            try:
                cls._proc.terminate()
            except Exception:
                try:
                    cls._proc.kill()
                except Exception:
                    pass
