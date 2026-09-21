"""
SHH 1.0 - Terminal Logger & Banner Utility (Clean ASCII for Windows)
"""

import sys
from datetime import datetime


class Colors:
    RESET = ""
    BOLD = ""
    DIM = ""

    RED = ""
    GREEN = ""
    YELLOW = ""
    BLUE = ""
    MAGENTA = ""
    CYAN = ""
    WHITE = ""

    BRIGHT_GREEN = ""
    BRIGHT_YELLOW = ""
    BRIGHT_BLUE = ""
    BRIGHT_MAGENTA = ""
    BRIGHT_CYAN = ""
    BRIGHT_WHITE = ""


class Logger:
    @staticmethod
    def _timestamp():
        return datetime.now().strftime("%H:%M:%S")

    @classmethod
    def info(cls, msg: str):
        print(f"[{cls._timestamp()}] [INFO] {msg}")

    @classmethod
    def success(cls, msg: str):
        print(f"[{cls._timestamp()}] [SUCCESS] {msg}")

    @classmethod
    def warning(cls, msg: str):
        print(f"[{cls._timestamp()}] [WARN] {msg}")

    @classmethod
    def error(cls, msg: str):
        print(f"[{cls._timestamp()}] [ERROR] {msg}", file=sys.stderr)

    @classmethod
    def step(cls, title: str, step_num: int = None, total_steps: int = None):
        prefix = f"[{step_num}/{total_steps}] " if step_num and total_steps else ">>> "
        print(f"\n{prefix}{title}")

    @classmethod
    def tool_call(cls, tool_name: str, args: dict = None):
        args_str = f" args={args}" if args else ""
        print(f"[{cls._timestamp()}] [TOOL CALL] {tool_name}{args_str}")

    @classmethod
    def banner(cls):
        art = """
=============================================================
 SHH 1.0 - Smart Host Hub (Windows AI Remote Bridge & Tunnel)
 Zero-Server Rendezvous | SSH & MCP Dual Protocol | Vision AI
=============================================================
"""
        print(art)
