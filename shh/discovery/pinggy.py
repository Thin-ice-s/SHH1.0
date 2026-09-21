"""
SHH 1.0 - Pinggy & Ngrok Free Tunnel Launcher
Pinggy provides instant HTTP / HTTPS tunnel via simple SSH port forwarding without downloading any binary.
"""

import shutil
import subprocess
import time
import re
from shh.utils.logger import Logger


def start_pinggy_tunnel(local_port: int = 18888):
    """
    Start Pinggy free tunnel via native Windows SSH.
    """
    ssh_cmd = f"ssh -p 443 -R0:localhost:{local_port} a.pinggy.io"
    print(f"To start Pinggy Tunnel, run in PowerShell:\n{ssh_cmd}")
