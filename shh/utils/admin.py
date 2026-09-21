"""
SHH 1.0 - Windows Administrator (UAC) Privilege Helpers
Detect privilege level, request elevation, run elevated commands, firewall & portproxy.

All helpers are ASCII-safe and Python 3.8 compatible.
"""

import ctypes
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from shh.utils.logger import Logger
from shh.utils.win_helper import is_windows, safe_decode_output


# ----------------------------------------------------------------------------
# Privilege detection
# ----------------------------------------------------------------------------

def is_admin() -> bool:
    """Return True if the current process already runs with administrator rights."""
    try:
        if is_windows():
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        # POSIX: root check (useful for Linux/macOS dev machines)
        return hasattr(os, "geteuid") and os.geteuid() == 0
    except Exception:
        return False


def get_integrity_level() -> str:
    """Return Windows integrity level string: High / Medium / Low / Unknown."""
    if not is_windows():
        return "root" if is_admin() else "user"
    try:
        out = subprocess.run(
            ["whoami", "/groups"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=8,
        )
        text = safe_decode_output(out.stdout)
        if "S-1-16-16384" in text:
            return "System"
        if "S-1-16-12288" in text:
            return "High (Administrator)"
        if "S-1-16-8192" in text:
            return "Medium (Standard user)"
        if "S-1-16-4096" in text:
            return "Low"
    except Exception:
        pass
    return "Unknown"


def get_admin_status() -> Dict[str, Any]:
    """Full privilege report, safe to expose to AI agents."""
    status = {
        "is_windows": is_windows(),
        "is_admin": is_admin(),
        "user": os.environ.get("USERNAME") or os.environ.get("USER") or "unknown",
        "computer": os.environ.get("COMPUTERNAME") or "unknown",
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "elevation_hint": "",
    }
    if status["is_windows"]:
        status["integrity_level"] = get_integrity_level()
        if status["is_admin"]:
            status["elevation_hint"] = (
                "SHH is running AS ADMINISTRATOR. Elevated operations (firewall rules, "
                "netsh portproxy, service control, killing system processes) work directly."
            )
        else:
            status["elevation_hint"] = (
                "SHH is running as a STANDARD USER. Elevated operations will trigger a "
                "Windows UAC prompt on screen. Restart with start_shh_admin.bat for full rights."
            )
    else:
        status["integrity_level"] = get_integrity_level()
        status["elevation_hint"] = "Non-Windows host (no UAC)."

    status["recommended_launcher"] = "start_shh_admin.bat" if status["is_windows"] else "sudo python -m shh start"
    return status


def print_admin_status() -> Dict[str, Any]:
    """Print the privilege report with ASCII-only output."""
    status = get_admin_status()
    if status["is_admin"]:
        Logger.success(
            "Privilege level: ADMINISTRATOR (UAC elevated) | user=%s | integrity=%s"
            % (status["user"], status.get("integrity_level", "?"))
        )
    else:
        Logger.warning(
            "Privilege level: STANDARD USER | user=%s | integrity=%s"
            % (status["user"], status.get("integrity_level", "?"))
        )
        if status["is_windows"]:
            Logger.info("Tip: run start_shh_admin.bat to launch SHH with Administrator rights.")
    return status


# ----------------------------------------------------------------------------
# Self elevation (relaunch this process / a launcher script with UAC)
# ----------------------------------------------------------------------------

def elevate_self(py_args: Optional[List[str]] = None, keep_console: bool = True) -> bool:
    """
    Relaunch 'python -m shh <py_args>' inside a NEW elevated console window (UAC prompt).
    Returns True if the elevated process was launched, False if the user cancelled.
    """
    if not is_windows():
        Logger.error("elevate_self() is only available on Windows. Use sudo instead.")
        return False

    if is_admin():
        Logger.info("Already running as Administrator. No elevation needed.")
        return True

    if py_args is None:
        py_args = sys.argv[1:] or ["start"]

    arg_str = " ".join('"%s"' % a if " " in str(a) else str(a) for a in py_args)
    inner = '"%s" -m shh %s' % (sys.executable, arg_str)
    # cmd /k keeps the elevated console window open so the user can read errors.
    params = ('/k "%s"' % inner) if keep_console else ('/c "%s"' % inner)

    Logger.info("Requesting Administrator privileges (UAC prompt). Please click [Yes]...")
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", params, str(Path.cwd()), 1)
    except Exception as exc:
        Logger.error("ShellExecuteW elevation failed: %s" % exc)
        return False

    # ShellExecuteW returns >32 on success, <=32 on failure (5 = access denied / user said No)
    if isinstance(rc, int) and rc > 32:
        Logger.success("Elevated SHH instance launched in a new Administrator window.")
        return True
    Logger.warning("Elevation was cancelled or refused (code=%s). Continuing un-elevated." % rc)
    return False


def elevate_script(script_path: str, arguments: Optional[List[str]] = None) -> bool:
    """
    Relaunch a .bat / .ps1 / .exe with administrator rights through ShellExecute runas.
    Used by the Python side when it needs the launcher (not Python) to be elevated.
    """
    if not is_windows():
        return False
    path = Path(script_path)
    if not path.exists():
        Logger.error("Cannot elevate missing script: %s" % script_path)
        return False

    arg_str = " ".join(str(a) for a in (arguments or []))
    verb = "runas"
    file_to_run = str(path)
    if path.suffix.lower() == ".ps1":
        file_to_run = "powershell.exe"
        arg_str = '-NoProfile -ExecutionPolicy Bypass -File "%s" %s' % (str(path), arg_str)

    try:
        rc = ctypes.windll.shell32.ShellExecuteW(None, verb, file_to_run, arg_str, str(path.parent), 1)
    except Exception as exc:
        Logger.error("Elevation failed: %s" % exc)
        return False
    return isinstance(rc, int) and rc > 32


# ----------------------------------------------------------------------------
# Elevated command execution
# ----------------------------------------------------------------------------

def _run_direct(command: str, shell: str, timeout: int, cwd: Optional[str]) -> Dict[str, Any]:
    """Run command in the current (already elevated) context and capture output."""
    if is_windows():
        if shell == "powershell":
            cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]
        else:
            cmd = ["cmd.exe", "/d", "/c", command]
    else:
        cmd = ["/bin/bash", "-lc", command]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            cwd=cwd or None,
        )
        return {
            "success": True,
            "elevated_execution": "direct (inline, current process privileges)",
            "uac_prompt_shown": False,
            "exit_code": proc.returncode,
            "stdout": safe_decode_output(proc.stdout),
            "stderr": safe_decode_output(proc.stderr),
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Command timed out after %s seconds" % timeout,
            "elevated_execution": "direct",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "elevated_execution": "direct"}


def _run_via_uac(command: str, shell: str, timeout: int, cwd: Optional[str]) -> Dict[str, Any]:
    """
    Launch an elevated child process through UAC and capture its output.
    A tiny wrapper .cmd redirects stdout/stderr/exit-code to temp files, because
    'Start-Process -Verb RunAs' itself cannot redirect streams.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="shh_elev_"))
    wrapper = tmpdir / "elev_run.cmd"
    out_file = tmpdir / "out.txt"
    err_file = tmpdir / "err.txt"
    rc_file = tmpdir / "rc.txt"

    work_dir = cwd or str(Path.cwd())
    if shell == "powershell":
        body = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "%s"' % command.replace('"', '\\"')
    else:
        body = command

    wrapper_text = (
        "@echo off\r\n"
        "chcp 65001 >nul 2>&1\r\n"
        'cd /d "%s"\r\n'
        "%s > \"%s\" 2> \"%s\"\r\n"
        'set "SHH_RC=%%ERRORLEVEL%%"\r\n'
        '>"%s" echo %%SHH_RC%%\r\n'
    ) % (work_dir, body, out_file, err_file, rc_file)
    wrapper.write_text(wrapper_text, encoding="utf-8", errors="replace")

    ps_cmd = (
        "Start-Process -FilePath 'cmd.exe' "
        "-ArgumentList '/c','\"%s\"' "
        "-WorkingDirectory '%s' -Verb RunAs -Wait"
    ) % (str(wrapper), str(tmpdir))

    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout + 15,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Elevated command timed out (UAC prompt may still be waiting on screen)",
            "uac_prompt_shown": True,
        }
    except Exception as exc:
        return {"success": False, "error": "UAC launch failed: %s" % exc, "uac_prompt_shown": True}

    # Give the elevated process a moment to flush the temp files
    for _ in range(10):
        if rc_file.exists():
            break
        time.sleep(0.3)

    def _read(p: Path) -> str:
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

    rc_text = _read(rc_file).strip()
    if not rc_file.exists():
        return {
            "success": False,
            "error": "Elevated process did not start. The UAC prompt was probably declined.",
            "uac_prompt_shown": True,
            "stdout": _read(out_file),
            "stderr": _read(err_file),
        }

    try:
        exit_code = int(rc_text.splitlines()[-1].strip())
    except Exception:
        exit_code = -1

    return {
        "success": True,
        "elevated_execution": "uac-elevated child process",
        "uac_prompt_shown": True,
        "exit_code": exit_code,
        "stdout": _read(out_file),
        "stderr": _read(err_file),
    }


def run_admin_command(
    command: str,
    shell: str = "cmd",
    timeout: int = 120,
    cwd: Optional[str] = None,
    allow_uac_prompt: bool = True,
) -> Dict[str, Any]:
    """
    Execute a command with administrator rights.
    - If SHH already runs elevated: runs immediately (no prompt).
    - Otherwise on Windows: triggers ONE UAC prompt and runs in an elevated child process.
    """
    if not command or not command.strip():
        return {"success": False, "error": "command must not be empty"}

    if not is_windows():
        return _run_direct(command, shell, timeout, cwd)

    if is_admin():
        return _run_direct(command, shell, timeout, cwd)

    if not allow_uac_prompt:
        return {
            "success": False,
            "error": (
                "SHH is not running as Administrator and allow_uac_prompt=False. "
                "Restart SHH with start_shh_admin.bat for silent elevated execution."
            ),
            "is_admin": False,
        }
    return _run_via_uac(command, shell, timeout, cwd)


# ----------------------------------------------------------------------------
# Windows Firewall helpers (need admin)
# ----------------------------------------------------------------------------

def add_firewall_rule(name: str, port: int, protocol: str = "TCP", action: str = "allow") -> Dict[str, Any]:
    if not is_windows():
        return {"success": False, "error": "Windows Firewall is only available on Windows hosts."}
    cmd = (
        'netsh advfirewall firewall add rule name="%s" dir=in action=%s protocol=%s localport=%d'
        % (name, action.upper(), protocol.upper(), int(port))
    )
    res = run_admin_command(cmd, shell="cmd", timeout=60)
    res["rule_name"] = name
    res["port"] = port
    return res


def remove_firewall_rule(name: str) -> Dict[str, Any]:
    if not is_windows():
        return {"success": False, "error": "Windows Firewall is only available on Windows hosts."}
    cmd = 'netsh advfirewall firewall delete rule name="%s"' % name
    return run_admin_command(cmd, shell="cmd", timeout=60)


def list_firewall_rules(keyword: str = "SHH") -> Dict[str, Any]:
    if not is_windows():
        return {"success": False, "error": "Windows Firewall is only available on Windows hosts."}
    cmd = 'netsh advfirewall firewall show rule name=all'
    res = run_admin_command(cmd, shell="cmd", timeout=90)
    if res.get("success") and res.get("stdout"):
        lines = res["stdout"].splitlines()
        blocks, current = [], []
        for line in lines:
            if line.strip() == "" and current:
                blocks.append("\n".join(current))
                current = []
            else:
                current.append(line)
        if current:
            blocks.append("\n".join(current))
        filtered = [b for b in blocks if keyword.lower() in b.lower()]
        res["matching_rule_count"] = len(filtered)
        res["matching_rules"] = filtered[:40]
        res.pop("stdout", None)
    return res


def ensure_firewall_rules(port: int, ssh_port: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Idempotently allow inbound TCP for the SHH HTTP port and SSH port.
    Only meaningful on Windows; returns [] when not applicable.
    """
    results: List[Dict[str, Any]] = []
    if not is_windows():
        return results

    targets = [("SHH 1.0 Bridge HTTP (port %d)" % port, port)]
    if ssh_port:
        targets.append(("SHH 1.0 Bridge SSH (port %d)" % ssh_port, ssh_port))

    for rule_name, rule_port in targets:
        res = add_firewall_rule(rule_name, rule_port)
        res["port"] = rule_port
        results.append(res)

    return results


# ----------------------------------------------------------------------------
# netsh portproxy helpers (need admin) - local <-> LAN port forwarding
# ----------------------------------------------------------------------------

def manage_port_forward(action: str, listen_port: int, connect_host: str = "127.0.0.1",
                        connect_port: Optional[int] = None, listen_address: str = "0.0.0.0",
                        protocol: str = "v4tov4") -> Dict[str, Any]:
    """
    Manage 'netsh interface portproxy' rules -> lets the machine forward an inbound
    port to another local/LAN host:port (true port forwarding at OS level).
    """
    if not is_windows():
        return {"success": False, "error": "netsh portproxy is Windows only"}

    action = (action or "list").lower()
    if action == "list":
        return run_admin_command("netsh interface portproxy show all", shell="cmd", timeout=45)

    if action in ("add", "delete", "remove"):
        connect_port = connect_port or listen_port
        if action == "add":
            cmd = (
                "netsh interface portproxy add %s listenport=%d listenaddress=%s "
                "connectport=%d connectaddress=%s"
                % (protocol, int(listen_port), listen_address, int(connect_port), connect_host)
            )
            # portproxy needs the IP Helper service
            run_admin_command("sc config iphlpsvc start= auto", shell="cmd", timeout=30)
            run_admin_command("net start iphlpsvc", shell="cmd", timeout=30)
        else:
            cmd = (
                "netsh interface portproxy delete %s listenport=%d listenaddress=%s"
                % (protocol, int(listen_port), listen_address)
            )
        res = run_admin_command(cmd, shell="cmd", timeout=60)
        res["listen_port"] = listen_port
        res["connect"] = "%s:%d" % (connect_host, connect_port)
        return res

    return {"success": False, "error": "Unknown action '%s'. Use: add | delete | list" % action}
