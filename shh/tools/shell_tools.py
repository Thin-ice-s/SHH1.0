"""
SHH 1.0 - Shell Execution Tools
Supports PowerShell, CMD, Bash, and WSL with timeout, streaming, and directory control.
"""

import asyncio
import os
import shlex
import subprocess
import time
from typing import Any, Dict, Optional

from shh.tools.base import BaseTool, registry
from shh.utils.logger import Logger
from shh.utils.win_helper import is_windows, safe_decode_output


class ShellExecTool(BaseTool):
    name = "shell_exec"
    description = "Execute a command in PowerShell, CMD, Bash, or WSL on the local Windows computer and return stdout, stderr, exit code."
    category = "shell"
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The command string to execute (e.g. 'dir', 'npm test', 'git status', 'python main.py')."
            },
            "cwd": {
                "type": "string",
                "description": "Working directory to execute command in. Defaults to current workspace."
            },
            "shell": {
                "type": "string",
                "enum": ["powershell", "cmd", "bash", "wsl", "auto"],
                "default": "auto",
                "description": "Shell type to execute in. 'powershell' (PowerShell), 'cmd' (Windows CMD), 'bash' (Git Bash / Linux bash), 'wsl' (WSL2), or 'auto'."
            },
            "timeout": {
                "type": "integer",
                "default": 60,
                "description": "Maximum execution time in seconds before terminating the process (default 60s)."
            }
        },
        "required": ["command"]
    }

    async def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        shell: str = "auto",
        timeout: int = 60
    ) -> Dict[str, Any]:
        Logger.tool_call("shell_exec", {"command": command[:80], "cwd": cwd, "shell": shell})
        start_time = time.time()

        # Resolve working directory
        work_dir = os.path.abspath(cwd) if cwd else os.getcwd()
        if not os.path.exists(work_dir):
            return {
                "success": False,
                "exit_code": -1,
                "error": f"Working directory does not exist: {work_dir}",
                "stdout": "",
                "stderr": f"Directory not found: {work_dir}",
                "duration_ms": 0
            }

        # Resolve shell command
        cmd_args = []
        is_win = is_windows()

        if shell == "auto":
            shell = "powershell" if is_win else "bash"

        if shell == "powershell":
            ps_bin = "powershell.exe" if is_win else "pwsh"
            cmd_args = [ps_bin, "-NoProfile", "-NonInteractive", "-Command", command]
        elif shell == "cmd":
            cmd_args = ["cmd.exe", "/c", command]
        elif shell == "wsl":
            cmd_args = ["wsl.exe", "-e", "bash", "-c", command]
        elif shell == "bash":
            cmd_args = ["/bin/bash", "-c", command] if not is_win else ["bash.exe", "-c", command]
        else:
            cmd_args = [command]

        try:
            # Run async subprocess
            if is_win and shell in ("powershell", "cmd"):
                proc = await asyncio.create_subprocess_shell(
                    " ".join(cmd_args) if isinstance(cmd_args, list) else cmd_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=work_dir
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    *cmd_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=work_dir
                )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=float(timeout))
                exit_code = proc.returncode
                duration_ms = int((time.time() - start_time) * 1000)

                stdout_text = safe_decode_output(stdout_bytes)
                stderr_text = safe_decode_output(stderr_bytes)

                return {
                    "success": exit_code == 0,
                    "exit_code": exit_code,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "cwd": work_dir,
                    "shell": shell,
                    "duration_ms": duration_ms
                }
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
                return {
                    "success": False,
                    "exit_code": -9,
                    "error": f"Command timed out after {timeout} seconds.",
                    "stdout": "",
                    "stderr": f"Execution timed out ({timeout}s)",
                    "cwd": work_dir,
                    "duration_ms": int((time.time() - start_time) * 1000)
                }

        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "error": str(e),
                "stdout": "",
                "stderr": str(e),
                "cwd": work_dir,
                "duration_ms": int((time.time() - start_time) * 1000)
            }


# Register shell tools
registry.register(ShellExecTool())
