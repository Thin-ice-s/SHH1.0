"""
SHH 1.0 - Live-server transfer tests (REAL sockets, not TestClient)

Why this file exists: FastAPI's TestClient normalises header handling, so a client that
looked up ``X-SHH-Compressed`` (upper case) passed every TestClient test while the real
uvicorn/Starlette server lower-cases custom header names. Against a real socket that
mismatch silently wrote gzip bytes to disk (every 512 KB chunk grew by ~178 bytes).

These tests therefore talk to a genuine uvicorn server over TCP.
"""

import hashlib
import os
import socket
import threading
import time

import pytest

from shh.config import SHHConfig
from shh.servers.http_server import create_app

uvicorn = pytest.importorskip("uvicorn")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_bridge(tmp_path_factory):
    from shh.client.cloud_client import SHHClient

    port = _free_port()
    config = SHHConfig()
    config.relaxed_security = True
    app = create_app(config, {"start_time": time.time(), "tunnel_url": "https://live.trycloudflare.com"})

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                break
        except OSError:
            time.sleep(0.2)
    else:
        pytest.fail("uvicorn did not start")

    yield "http://127.0.0.1:%d" % port, config, tmp_path_factory.mktemp("live")

    server.should_exit = True
    thread.join(timeout=10)


def test_real_http_chunked_roundtrip_with_compression(live_bridge):
    """The exact scenario that was broken: gzip chunks over a real socket."""
    base, _cfg, workdir = live_bridge
    from shh.client.cloud_client import SHHClient

    client = SHHClient(base, None)
    payload = os.urandom(1200 * 1024)                # 1.2 MB, incompressible on purpose
    local = workdir / "payload.bin"
    local.write_bytes(payload)

    up = client.upload(str(local), str(workdir / "remote.bin"), chunk_size=512 * 1024, compress=True)
    assert up["sha256_match"] is True, up
    assert (workdir / "remote.bin").read_bytes() == payload, "uploaded bytes differ (header case bug?)"

    out = workdir / "back.bin"
    if out.exists():
        out.unlink()
    down = client.download(str(workdir / "remote.bin"), str(out), chunk_size=512 * 1024, compress=True)
    assert down["complete"] is True, down
    assert out.read_bytes() == payload, "downloaded bytes differ (header case bug?)"
    assert hashlib.sha256(out.read_bytes()).hexdigest() == hashlib.sha256(payload).hexdigest()


def test_real_http_text_helpers(live_bridge):
    base, _cfg, workdir = live_bridge
    from shh.client.cloud_client import SHHClient

    client = SHHClient(base, None)
    text = "SHH line\n" * 20000                      # ~180 KB
    target = str(workdir / "notes.txt")
    client.put_text(target, text)
    assert client.get_text(target) == text


def test_real_http_upload_resumes_from_existing_size(live_bridge):
    """Simulate a dropped tunnel: half the file is on the server, then resume."""
    base, _cfg, workdir = live_bridge
    from shh.client.cloud_client import SHHClient

    client = SHHClient(base, None)
    payload = os.urandom(1024 * 1024)
    local = workdir / "resume_src.bin"
    local.write_bytes(payload)
    remote = workdir / "resume_dst.bin"
    remote.write_bytes(payload[:400_000])            # pretend the first chunks already landed

    res = client.upload(str(local), str(remote), chunk_size=200_000, compress=False)
    assert remote.read_bytes() == payload
    assert res["sha256_match"] is True


def test_health_endpoint_over_real_socket(live_bridge):
    base, _cfg, _ = live_bridge
    import json
    import urllib.request

    with urllib.request.urlopen(base + "/api/health", timeout=10) as resp:
        body = json.loads(resp.read().decode())
    assert body["status"] == "ok"
    assert body["tools"] > 0
