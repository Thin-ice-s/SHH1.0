"""
SHH 1.0 - Zero-Config Public Tunnel Providers (NAT Traversal)
Provides free, zero-server tunnels (TryCloudflare, Pinggy, Localhost.run) when router has no public port.
"""

import asyncio
import os
import platform
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from typing import Any, Dict, Optional

from shh.utils.logger import Logger
from shh.utils.win_helper import is_windows


class TunnelProvider:
    """Manages automatic outbound tunnel creation for 100% NAT/CGNAT traversal."""

    @classmethod
    def start_trycloudflare_tunnel(cls, local_port: int = 18888, timeout: float = 15.0) -> Optional[Dict[str, Any]]:
        """
        Start Cloudflare Quick Tunnel (TryCloudflare) without account or domain.
        Returns the public https://*.trycloudflare.com URL.
        """
        cloudflared_bin = shutil.which("cloudflared") or shutil.which("cloudflared.exe")
        
        # If not installed, check local directory or download standalone binary
        if not cloudflared_bin:
            local_bin = "cloudflared.exe" if is_windows() else "cloudflared"
            if os.path.exists(local_bin):
                cloudflared_bin = os.path.abspath(local_bin)

        if not cloudflared_bin:
            Logger.info("cloudflared binary not found locally. (You can place cloudflared.exe in project folder for instant 1-click HTTPS tunnel)")
            return None

        try:
            cmd = [cloudflared_bin, "tunnel", "--url", f"http://localhost:{local_port}", "--no-autoupdate"]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            tunnel_url = None
            start_t = time.time()

            # cloudflared prints URL to stderr
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
                Logger.success(f"TryCloudflare Public Tunnel active: {tunnel_url}")
                return {
                    "provider": "trycloudflare",
                    "public_url": tunnel_url,
                    "proc": proc
                }
        except Exception as e:
            Logger.warning(f"TryCloudflare error: {e}")
        return None

    @classmethod
    def start_ssh_reverse_tunnel(cls, local_port: int = 18888, timeout: float = 12.0) -> Optional[Dict[str, Any]]:
        """
        Start free SSH reverse tunnel via localhost.run or pinggy (no login required).
        """
        ssh_bin = shutil.which("ssh") or shutil.which("ssh.exe")
        if not ssh_bin:
            return None

        # Try localhost.run (standard SSH port 80/443 forward)
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
                Logger.success(f"SSH Reverse Public Tunnel active: {tunnel_url}")
                return {
                    "provider": "localhost.run",
                    "public_url": tunnel_url,
                    "proc": proc
                }
        except Exception as e:
            pass
        return None
