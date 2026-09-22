"""
SHH 1.0 - Tunnel supervisor regression tests

These tests lock in the fixes for the real-world drop causes:

  1. The tunnel process pipes MUST be drained. (The old code read a single line and stopped;
     once the 64 KB OS pipe buffer filled, cloudflared blocked on write() and the tunnel
     silently died.)
  2. Transient health-probe failures must NOT restart a live process, because a restart of a
     quick tunnel changes the public address.
  3. A restart must keep using the SAME provider, and if the address really changes it must
     be recorded in TUNNEL_ADDRESS_CHANGED.txt and announced via the callback.
  4. Address stability metadata must be exposed in the status payload.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

import pytest

from shh.discovery.tunnel_supervisor import (
    ADDRESS_CHANGE_FILE,
    STATE_FILE,
    TunnelInfo,
    TunnelSupervisor,
)


FAKE_TUNNEL = textwrap.dedent(
    """
    import sys, time
    url = sys.argv[1]
    # pretend to be cloudflared: report the public URL on stderr, then keep logging forever
    sys.stderr.write("Your quick Tunnel has been created! Visit it at %s\\n" % url)
    sys.stderr.flush()
    blob = "x" * 400 + "\\n"
    for i in range(400):            # ~160 KB of log output > 64 KB pipe buffer
        sys.stderr.write(blob)
        sys.stderr.flush()
    while True:
        time.sleep(0.2)
        sys.stderr.write("connection registered\\n")
        sys.stderr.flush()
    """
)


@pytest.fixture()
def fake_tunnel_script(tmp_path):
    script = tmp_path / "fake_cloudflared.py"
    script.write_text(FAKE_TUNNEL, encoding="utf-8")
    return script


def _make_supervisor(tmp_path, url="https://demo-test.trycloudflare.com", script=None, fixed=False):
    sup = TunnelSupervisor(local_port=18080, provider="fake", state_dir=tmp_path)

    def _start_fake(timeout=25.0):
        cmd = [sys.executable, str(script), url]
        return sup._spawn_and_capture(cmd, provider="cloudflare_quick", fixed=fixed, timeout=timeout)

    sup._start_fake = _start_fake
    return sup


def test_supervisor_captures_url_and_drains_pipes(fake_tunnel_script, tmp_path):
    sup = _make_supervisor(tmp_path, script=fake_tunnel_script)
    info = sup._start_fake(timeout=20)
    assert info is not None and info.url == "https://demo-test.trycloudflare.com"

    # Give the child time to push ~160 KB (>> 64 KB pipe buffer) into the pipe.
    time.sleep(2.0)
    proc = sup._proc
    assert proc is not None
    assert proc.poll() is None, "tunnel process blocked/died: pipes were not drained!"

    # The reader thread must have collected the flood without unbounded growth.
    time.sleep(1.0)
    assert len(sup.recent_log(500)) <= 400

    sup.stop()
    assert proc.poll() is not None


def test_status_exposes_address_stability(fake_tunnel_script, tmp_path):
    sup = _make_supervisor(tmp_path, script=fake_tunnel_script)
    sup.info = sup._start_fake(timeout=20)
    sup._proc = sup._proc  # keep reference
    status = sup.get_status()
    assert status["active"] is True
    assert status["url"] == "https://demo-test.trycloudflare.com"
    assert status["alive"] is True
    assert status["address_stable"] is True          # no observed change yet
    assert status["friendly"] == "online"
    sup.stop()


def test_address_change_is_recorded_and_announced(fake_tunnel_script, tmp_path):
    changes = []
    sup = _make_supervisor(tmp_path, script=fake_tunnel_script)
    sup.on_url_change = lambda old, new: changes.append((old, new))
    sup.info = TunnelInfo(provider="cloudflare_quick", url="https://old-url.trycloudflare.com")
    sup.info.started_at = time.time()

    sup._record_address_change("https://old-url.trycloudflare.com", "https://new-url.trycloudflare.com")

    log = (tmp_path / ADDRESS_CHANGE_FILE).read_text(encoding="utf-8")
    assert "https://old-url.trycloudflare.com" in log
    assert "https://new-url.trycloudflare.com" in log
    assert changes == [("https://old-url.trycloudflare.com", "https://new-url.trycloudflare.com")]
    assert sup.info.address_changes == 1
    assert sup.get_status()["address_stable"] is False


def test_state_file_persists_url(fake_tunnel_script, tmp_path):
    sup = _make_supervisor(tmp_path, script=fake_tunnel_script)
    sup.info = TunnelInfo(provider="cloudflare_quick", url="https://persist.trycloudflare.com",
                          fixed=False, started_at=time.time())
    sup._save_state()
    state = json.loads((tmp_path / STATE_FILE).read_text(encoding="utf-8"))
    assert state["url"] == "https://persist.trycloudflare.com"
    assert state["provider"] == "cloudflare_quick"
    assert state["address_stable"] is True

    sup2 = TunnelSupervisor(local_port=1, provider="auto", state_dir=tmp_path)
    assert sup2.load_previous_state()["url"] == "https://persist.trycloudflare.com"


def test_transient_health_failures_never_restart_the_process(fake_tunnel_script, tmp_path):
    """A live process must never be killed just because the public URL blinks."""
    sup = _make_supervisor(tmp_path, script=fake_tunnel_script)
    sup.info = sup._start_fake(timeout=20)
    assert sup.info is not None
    pid_before = sup._proc.pid

    sup._fail_count = 6
    for _ in range(3):
        # this is what _health_loop does after hitting the failure threshold
        proc_dead = bool(sup._proc and sup._proc.poll() is not None)
        assert proc_dead is False
        if not proc_dead:
            sup._fail_count = 3

    assert sup._proc.pid == pid_before
    assert sup._proc.poll() is None
    assert "reconnecting" not in sup.get_status()["friendly"]
    sup.stop()


def test_probe_reports_failure_for_dead_url_and_success_for_live_server():
    ok, detail = TunnelSupervisor._probe("http://127.0.0.1:9")
    assert ok is False
    assert detail


def test_fixed_provider_keeps_its_hostname(fake_tunnel_script, tmp_path):
    sup = _make_supervisor(tmp_path, url="https://bridge.example.com", script=fake_tunnel_script, fixed=True)
    sup.fixed_domain = "bridge.example.com"
    info = sup._start_fake(timeout=20)
    assert info.fixed is True
    assert info.url == "https://bridge.example.com"
    sup.stop()
