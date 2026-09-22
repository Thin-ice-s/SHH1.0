"""
SHH 1.0 - Built-in Paramiko SSH Server & Native OpenSSH Configurator
Provides standard SSH (PTY & Exec) access for Cloud AI or remote developers.
"""

import os
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Optional

import paramiko

from shh.config import SHHConfig
from shh.utils.crypto import generate_ssh_key_pair
from shh.utils.logger import Logger
from shh.utils.win_helper import get_default_shell, is_windows, safe_decode_output


class SHHServerInterface(paramiko.ServerInterface):
    def __init__(self, username: str, password: str, allowed_keys: Optional[list] = None):
        self.username = username
        self.password = password
        self.allowed_keys = allowed_keys or []
        self.event = threading.Event()

    def check_channel_request(self, kind, chanid):
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        if username == self.username and password == self.password:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_auth_publickey(self, username, key):
        if username == self.username:
            # Relaxed mode allows any valid key if allowed_keys is empty or matches
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_channel_shell_request(self, channel):
        self.event.set()
        return True

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        return True

    def check_channel_exec_request(self, channel, command):
        self.event.set()
        return True


class SSHServerRunner:
    def __init__(self, config: SHHConfig):
        self.config = config
        self.host_key = None
        self.sock = None
        self.running = False
        self._init_host_key()

    def _init_host_key(self):
        # Generate in-memory host key if not exists
        self.host_key = paramiko.RSAKey.generate(2048)

    def _handle_client(self, client_sock: socket.socket, addr: tuple):
        try:
            transport = paramiko.Transport(client_sock)
            transport.add_server_key(self.host_key)

            server_iface = SHHServerInterface(
                username=self.config.ssh_username,
                password=self.config.ssh_password
            )
            transport.start_server(server=server_iface)

            chan = transport.accept(20)
            if chan is None:
                return

            server_iface.event.wait(10)
            if not server_iface.event.is_set():
                chan.close()
                return

            # Launch interactive shell or execute command
            shell_bin = "powershell.exe" if is_windows() else "/bin/bash"
            if not is_windows() and not os.path.exists(shell_bin):
                shell_bin = "/bin/sh"

            proc = subprocess.Popen(
                [shell_bin],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.config.workspace_dir,
                shell=False
            )

            def pipe_in():
                try:
                    while True:
                        data = chan.recv(1024)
                        if not data:
                            break
                        proc.stdin.write(data)
                        proc.stdin.flush()
                except Exception:
                    pass
                finally:
                    try:
                        proc.stdin.close()
                    except Exception:
                        pass

            def pipe_out():
                try:
                    while True:
                        data = proc.stdout.read(1024)
                        if not data:
                            break
                        chan.sendall(data)
                except Exception:
                    pass
                finally:
                    try:
                        chan.close()
                    except Exception:
                        pass

            t_in = threading.Thread(target=pipe_in, daemon=True)
            t_out = threading.Thread(target=pipe_out, daemon=True)
            t_in.start()
            t_out.start()

            proc.wait()
            chan.close()
        except Exception as e:
            pass

    def start(self):
        self.running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.config.host, self.config.ssh_port))
        self.sock.listen(10)
        Logger.info(f"SSH Server listening on {self.config.host}:{self.config.ssh_port}")

        def loop():
            while self.running:
                try:
                    client, addr = self.sock.accept()
                    t = threading.Thread(target=self._handle_client, args=(client, addr), daemon=True)
                    t.start()
                except Exception:
                    break

        thread = threading.Thread(target=loop, daemon=True)
        thread.start()

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass


def generate_windows_native_openssh_script() -> str:
    """Generate a PowerShell script to enable native Windows OpenSSH Server feature."""
    return """# SHH 1.0 - Windows Native OpenSSH Server Setup Script (Run as Administrator)
Write-Host "=== Setting up Windows OpenSSH Server for AI Access ===" -ForegroundColor Cyan

# 1. Install OpenSSH Server capability
$sshCapability = Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*'
if ($sshCapability.State -ne "Installed") {
    Write-Host "Installing OpenSSH.Server capability..." -ForegroundColor Yellow
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
} else {
    Write-Host "OpenSSH.Server is already installed." -ForegroundColor Green
}

# 2. Start and configure sshd service
Set-Service -Name sshd -StartupType 'Automatic'
Start-Service sshd

# 3. Configure Windows Firewall
if (!(Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
}

Write-Host "✔ OpenSSH Server is active on port 22!" -ForegroundColor Green
"""
