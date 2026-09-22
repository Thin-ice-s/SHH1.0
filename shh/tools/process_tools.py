"""
SHH 1.0 - Process Management Tools
List, start, monitor, and terminate system processes and background tasks.
"""

import asyncio
import os
import signal
import subprocess
import time
from typing import Any, Dict, List, Optional

import psutil

from shh.tools.base import BaseTool, registry
from shh.utils.logger import Logger
from shh.utils.win_helper import is_windows, safe_decode_output


class BackgroundJobManager:
    """Manages long-running background processes (e.g. dev servers, watcher scripts)."""
    _jobs: Dict[str, Dict[str, Any]] = {}
    _counter: int = 0

    @classmethod
    def create_job(cls, command: str, proc: asyncio.subprocess.Process, cwd: str) -> str:
        cls._counter += 1
        job_id = f"job-{cls._counter:03d}"
        cls._jobs[job_id] = {
            "job_id": job_id,
            "command": command,
            "proc": proc,
            "pid": proc.pid,
            "cwd": cwd,
            "started_at": time.time(),
            "stdout_logs": [],
            "stderr_logs": [],
            "status": "running"
        }
        return job_id

    @classmethod
    def get_job(cls, job_id: str) -> Optional[Dict[str, Any]]:
        return cls._jobs.get(job_id)

    @classmethod
    def list_jobs(cls) -> List[Dict[str, Any]]:
        results = []
        for jid, info in cls._jobs.items():
            proc = info["proc"]
            is_running = proc.returncode is None
            results.append({
                "job_id": jid,
                "command": info["command"],
                "pid": info["pid"],
                "status": "running" if is_running else f"exited({proc.returncode})",
                "running_seconds": int(time.time() - info["started_at"])
            })
        return results

    @classmethod
    def stop_job(cls, job_id: str) -> bool:
        job = cls.get_job(job_id)
        if not job:
            return False
        proc = job["proc"]
        if proc.returncode is None:
            try:
                proc.terminate()
                return True
            except Exception:
                try:
                    proc.kill()
                    return True
                except Exception:
                    pass
        return False


class ListProcessesTool(BaseTool):
    name = "list_processes"
    description = "List active system processes with PID, name, CPU %, memory usage, and command line."
    category = "process"
    parameters = {
        "type": "object",
        "properties": {
            "name_filter": {
                "type": "string",
                "description": "Optional filter string to match against process name or cmdline (e.g. 'node', 'python', 'chrome')."
            },
            "limit": {
                "type": "integer",
                "default": 30,
                "description": "Maximum number of processes to return (sorted by memory usage)."
            }
        }
    }

    async def execute(self, name_filter: Optional[str] = None, limit: int = 30) -> Dict[str, Any]:
        processes = []
        filter_lower = name_filter.lower() if name_filter else None

        for proc in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent", "create_time"]):
            try:
                info = proc.info
                p_name = info.get("name") or ""
                p_pid = info.get("pid")
                
                if filter_lower and filter_lower not in p_name.lower():
                    continue

                mem_mb = round((info.get("memory_info").rss / (1024 * 1024)), 1) if info.get("memory_info") else 0

                processes.append({
                    "pid": p_pid,
                    "name": p_name,
                    "memory_mb": mem_mb,
                    "cpu_percent": info.get("cpu_percent") or 0.0
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        # Sort by memory usage descending
        processes.sort(key=lambda x: x["memory_mb"], reverse=True)
        top_procs = processes[:limit]

        return {
            "success": True,
            "total_matched": len(processes),
            "returned": len(top_procs),
            "processes": top_procs
        }


class KillProcessTool(BaseTool):
    name = "kill_process"
    description = "Terminate a running process by PID or process name."
    category = "process"
    parameters = {
        "type": "object",
        "properties": {
            "pid": {
                "type": "integer",
                "description": "Process ID to terminate."
            },
            "name": {
                "type": "string",
                "description": "Process name to terminate all matching instances (e.g. 'node.exe')."
            },
            "force": {
                "type": "boolean",
                "default": True,
                "description": "Whether to forcefully kill the process (SIGKILL / taskkill /F)."
            }
        }
    }

    async def execute(
        self,
        pid: Optional[int] = None,
        name: Optional[str] = None,
        force: bool = True
    ) -> Dict[str, Any]:
        Logger.tool_call("kill_process", {"pid": pid, "name": name})
        killed = []
        errors = []

        if pid:
            try:
                p = psutil.Process(pid)
                p_name = p.name()
                if force:
                    p.kill()
                else:
                    p.terminate()
                killed.append({"pid": pid, "name": p_name})
            except Exception as e:
                errors.append(f"PID {pid}: {str(e)}")

        elif name:
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    if p.info["name"] and p.info["name"].lower() == name.lower():
                        if force:
                            p.kill()
                        else:
                            p.terminate()
                        killed.append({"pid": p.info["pid"], "name": p.info["name"]})
                except Exception as e:
                    errors.append(f"Proc {p.info.get('pid')}: {str(e)}")

        else:
            return {"success": False, "error": "Either 'pid' or 'name' must be provided."}

        return {
            "success": len(killed) > 0,
            "killed_processes": killed,
            "errors": errors
        }


class StartBackgroundProcessTool(BaseTool):
    name = "start_process"
    description = "Start a persistent background process (e.g. dev server, npm run dev, python app.py) and return a job_id to monitor."
    category = "process"
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Command to run in background."
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for the process."
            }
        },
        "required": ["command"]
    }

    async def execute(self, command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        work_dir = os.path.abspath(cwd) if cwd else os.getcwd()
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir
            )
            job_id = BackgroundJobManager.create_job(command, proc, work_dir)
            return {
                "success": True,
                "job_id": job_id,
                "pid": proc.pid,
                "command": command,
                "status": "started",
                "message": f"Background process started with {job_id} (PID: {proc.pid})"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class GetProcessLogsTool(BaseTool):
    name = "get_process_logs"
    description = "Get status or active background jobs list."
    category = "process"
    parameters = {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "Job ID (e.g. 'job-001'). Omit to list all background jobs."
            }
        }
    }

    async def execute(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        if not job_id:
            return {
                "success": True,
                "background_jobs": BackgroundJobManager.list_jobs()
            }
        job = BackgroundJobManager.get_job(job_id)
        if not job:
            return {"success": False, "error": f"Job {job_id} not found."}
        proc = job["proc"]
        return {
            "success": True,
            "job_id": job_id,
            "command": job["command"],
            "pid": job["pid"],
            "is_running": proc.returncode is None,
            "exit_code": proc.returncode
        }


# Register process tools
registry.register(ListProcessesTool())
registry.register(KillProcessTool())
registry.register(StartBackgroundProcessTool())
registry.register(GetProcessLogsTool())
