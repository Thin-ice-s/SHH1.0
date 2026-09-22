"""
Unit Tests for SHH 1.0 Tools
"""

import asyncio
import os
from pathlib import Path
import pytest

from shh.tools import registry


def run_async(coro):
    return asyncio.run(coro)


def test_registry_has_all_tools():
    names = registry.list_names()
    expected = [
        "shell_exec", "file_read", "file_write", "file_edit", "file_list",
        "file_tree", "file_search", "list_processes", "kill_process",
        "start_process", "get_process_logs", "list_open_ports",
        "proxy_http_request", "capture_screen", "get_screen_info",
        "get_system_info", "get_env_vars"
    ]
    for exp in expected:
        assert exp in names, f"Missing tool {exp}"


def test_shell_exec():
    res = run_async(registry.execute("shell_exec", command="echo 'Hello SHH'"))
    assert res["success"] is True
    assert "Hello SHH" in res["stdout"]
    assert res["exit_code"] == 0


def test_file_operations(tmp_path):
    fpath = str(tmp_path / "sample.txt")
    
    # Write
    w_res = run_async(registry.execute("file_write", path=fpath, content="line 1\nline 2\nline 3\n"))
    assert w_res["success"] is True
    assert w_res["lines_written"] == 3

    # Read
    r_res = run_async(registry.execute("file_read", path=fpath, start_line=2, max_lines=1))
    assert r_res["success"] is True
    assert r_res["content"].strip() == "line 2"

    # Edit
    e_res = run_async(registry.execute("file_edit", path=fpath, old_text="line 2", new_text="line TWO"))
    assert e_res["success"] is True

    # Verify Edit
    r2_res = run_async(registry.execute("file_read", path=fpath))
    assert "line TWO" in r2_res["content"]

    # List
    l_res = run_async(registry.execute("file_list", path=str(tmp_path)))
    assert l_res["success"] is True
    assert len(l_res["items"]) >= 1

    # Search
    s_res = run_async(registry.execute("file_search", path=str(tmp_path), content_regex="TWO"))
    assert s_res["success"] is True
    assert s_res["matches_found"] >= 1


def test_system_and_screen():
    sys_res = run_async(registry.execute("get_system_info"))
    assert sys_res["success"] is True
    assert "cpu" in sys_res
    assert "memory" in sys_res

    screen_res = run_async(registry.execute("capture_screen", max_width=640, quality=50))
    assert screen_res["success"] is True
    assert screen_res["width"] > 0
    assert screen_res["image_data_uri"].startswith("data:image/jpeg;base64,")


def test_process_tools():
    proc_res = run_async(registry.execute("list_processes", limit=5))
    assert proc_res["success"] is True
    assert len(proc_res["processes"]) > 0


if __name__ == "__main__":
    test_registry_has_all_tools()
    test_shell_exec()
    print("All tool tests passed!")
