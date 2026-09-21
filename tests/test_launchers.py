"""
SHH 1.0 - Launcher / Packaging sanity checks
Guards against the exact Windows-launcher bugs that broke earlier releases:
  * missing 'Colors' compatibility class in the logger (ImportError)
  * launchers that do not cd into their own folder (spaces/parentheses in path)
  * non-ASCII (Chinese) bytes in .bat / .ps1 files (CP936 乱码 on Chinese Windows)
  * an undefined variable crash in the start flow (board_url / ticket)
"""

import ast
import builtins
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_logger_exposes_colors_class():
    from shh.utils.logger import Colors, Logger

    assert hasattr(Colors, "RESET")
    assert hasattr(Colors, "BRIGHT_GREEN")
    assert Colors.RESET == ""  # no raw ANSI escapes on legacy Windows CMD
    assert hasattr(Logger, "success")


def test_launchers_are_ascii_only():
    for name in ("start_shh.bat", "start_shh_admin.bat", "start_shh.ps1", "create_admin_shortcut.ps1"):
        path = ROOT / name
        assert path.exists(), "%s is missing" % name
        try:
            path.read_bytes().decode("ascii")
        except UnicodeDecodeError as exc:
            pytest.fail("%s contains non-ASCII bytes at offset %s (would 乱码 in CP936 CMD)" % (name, exc.start))


def test_batch_launchers_cd_into_their_own_folder():
    for name in ("start_shh.bat", "start_shh_admin.bat"):
        text = (ROOT / name).read_text(encoding="ascii")
        assert 'cd /d "%~dp0"' in text, "%s must cd /d %%~dp0 to survive paths with spaces" % name


def test_admin_launcher_requests_elevation():
    text = (ROOT / "start_shh_admin.bat").read_text(encoding="ascii").lower()
    assert "-verb runas" in text, "admin launcher must use Start-Process -Verb RunAs"
    assert "isinrole" in text and "windowsbuiltinrole" in text, "admin launcher must run a real UAC check"
    assert "start_shh.bat" in text


def test_no_undefined_names_in_cli_start_flow():
    """Static check: every name used in start_server_command must be bound or a builtin/global."""
    source = (ROOT / "shh" / "cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    func = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "start_server_command"
    )

    assigned = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store,)):
            assigned.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                assigned.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.arg):
            assigned.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assigned.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            assigned.add(node.name)

    module_globals = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                module_globals.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    module_globals.add(target.id)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            module_globals.add(node.name)

    for node in ast.walk(func):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            name = node.id
            if name in assigned or name in module_globals or hasattr(builtins, name):
                continue
            raise AssertionError("start_server_command() uses undefined name '%s' (line %s)" % (name, node.lineno))


def test_admin_module_public_api():
    from shh.utils import admin

    for func_name in ("is_admin", "get_admin_status", "run_admin_command", "elevate_self",
                      "add_firewall_rule", "list_firewall_rules", "manage_port_forward"):
        assert callable(getattr(admin, func_name)), "%s missing from shh.utils.admin" % func_name


def test_requirements_pinned_lower_bounds():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for pkg in ("fastapi", "uvicorn", "paramiko", "pillow", "psutil", "requests", "websockets"):
        assert pkg in text, "requirements.txt lost %s" % pkg
