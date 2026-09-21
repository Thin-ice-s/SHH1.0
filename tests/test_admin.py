"""
SHH 1.0 - Tests for the Administrator (UAC) mode helpers and tools.
"""

import asyncio

import pytest

from shh.tools import registry
from shh.utils import admin


def test_is_admin_returns_bool():
    assert isinstance(admin.is_admin(), bool)


def test_admin_status_fields():
    status = admin.get_admin_status()
    for key in ("is_windows", "is_admin", "user", "integrity_level", "elevation_hint", "recommended_launcher"):
        assert key in status, "missing key %s" % key
    assert isinstance(status["is_admin"], bool)


def test_run_admin_command_requires_command():
    res = admin.run_admin_command("")
    assert res["success"] is False
    assert "empty" in res["error"].lower() or "must not be" in res["error"].lower()


def test_run_admin_command_works_on_posix():
    if admin.is_windows():
        pytest.skip("POSIX-only direct execution path")
    res = admin.run_admin_command("echo SHH-ADMIN-OK")
    assert res["success"] is True
    assert "SHH-ADMIN-OK" in res["stdout"]


def test_uac_prompt_can_be_refused_without_admin():
    if admin.is_windows() and admin.is_admin():
        pytest.skip("machine already elevated")
    if not admin.is_windows():
        pytest.skip("UAC path is Windows only")
    res = admin.run_admin_command("echo hi", allow_uac_prompt=False)
    assert res["success"] is False
    assert res["is_admin"] is False


def test_port_forward_unknown_action():
    res = admin.manage_port_forward("bogus", listen_port=1234)
    assert res["success"] is False


def test_admin_tools_registered():
    for name in ("get_privilege_info", "run_admin_command", "manage_firewall", "manage_port_forward"):
        assert name in registry.list_names(), "%s tool not registered" % name


def test_privilege_info_tool_executes():
    res = asyncio.get_event_loop().run_until_complete(registry.execute("get_privilege_info"))
    assert res["success"] is True
    assert "is_admin" in res
    assert "supports" in res


def test_run_admin_command_tool_on_posix():
    if admin.is_windows():
        pytest.skip("POSIX-only direct execution path")
    res = asyncio.get_event_loop().run_until_complete(
        registry.execute("run_admin_command", command="echo SHH-TOOL-OK")
    )
    assert res["success"] is True
    assert "SHH-TOOL-OK" in res["stdout"]
