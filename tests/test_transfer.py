"""
SHH 1.0 - Chunked / resumable file transfer tests

These tests exercise the REAL HTTP surface (FastAPI TestClient + a live uvicorn server for
the raw streaming paths) because the whole point of the transfer design is that big packets
must never reach the tunnel.
"""

import base64
import gzip
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from shh.config import SHHConfig
from shh.servers.http_server import create_app
from shh.tools import registry
from shh.tools.transfer_tools import (
    DEFAULT_CHUNK_BYTES,
    HARD_MAX_CHUNK_BYTES,
    FileDownloadChunkTool,
    FileUploadChunkTool,
)

try:
    from fastapi.testclient import TestClient
except Exception:      # pragma: no cover
    TestClient = None


@pytest.fixture()
def tmp_workdir(tmp_path):
    return tmp_path


# ------------------------------------------------------------------ unit level
def test_chunk_upload_and_download_roundtrip(tmp_path):
    import asyncio

    src = os.urandom(700 * 1024)          # 700 KiB -> 3 chunks of 256 KiB
    remote = tmp_path / "big.bin"

    upload = FileUploadChunkTool()
    download = FileDownloadChunkTool()

    offset = 0
    while offset < len(src):
        chunk = src[offset:offset + DEFAULT_CHUNK_BYTES]
        res = asyncio.run(
            upload.execute(
                path=str(remote),
                offset=offset,
                data_base64=base64.b64encode(chunk).decode(),
                truncate=(offset == 0),
                sha256_chunk=hashlib.sha256(chunk).hexdigest(),
            )
        )
        assert res["success"], res
        assert res["next_offset"] == offset + len(chunk)
        offset = res["next_offset"]

    assert remote.read_bytes() == src

    # read it back in chunks
    collected = b""
    offset = 0
    while True:
        res = asyncio.run(
            download.execute(path=str(remote), offset=offset, max_bytes=DEFAULT_CHUNK_BYTES)
        )
        assert res["success"], res
        collected += base64.b64decode(res["data_base64"])
        offset = res["next_offset"]
        if res["eof"]:
            break
    assert collected == src


def test_upload_chunk_detects_corruption(tmp_path):
    import asyncio

    res = asyncio.run(
        FileUploadChunkTool().execute(
            path=str(tmp_path / "x.bin"),
            offset=0,
            data_text="hello",
            sha256_chunk="deadbeef",
        )
    )
    assert res["success"] is False
    assert res.get("retry") is True


def test_oversized_single_packet_is_rejected(tmp_path):
    import asyncio

    huge = base64.b64encode(b"x" * (HARD_MAX_CHUNK_BYTES + 1024)).decode()
    res = asyncio.run(
        FileUploadChunkTool().execute(path=str(tmp_path / "huge.bin"), offset=0, data_base64=huge)
    )
    assert res["success"] is False
    assert "exceeds the hard limit" in res["error"]
    assert res["max_chunk_bytes"] > 0


def test_gzip_chunk_upload(tmp_path):
    import asyncio

    text = ("SHH tunnel stability test line\n" * 500).encode()
    res = asyncio.run(
        FileUploadChunkTool().execute(
            path=str(tmp_path / "log.txt"),
            offset=0,
            data_base64=base64.b64encode(gzip.compress(text)).decode(),
            compress=True,
            truncate=True,
        )
    )
    assert res["success"], res
    assert (tmp_path / "log.txt").read_bytes() == text


def test_transfer_tools_registered():
    for name in ("file_stat", "file_upload_chunk", "file_download_chunk",
                 "file_checksum", "file_transfer_info"):
        assert name in registry.list_names(), "%s missing" % name


def test_file_stat_supports_resume(tmp_path):
    import asyncio

    target = tmp_path / "resume.bin"
    target.write_bytes(b"A" * 1024)
    res = asyncio.run(registry.execute("file_stat", path=str(target)))
    assert res["exists"] is True
    assert res["size_bytes"] == 1024
    assert res["recommended_chunk_bytes"] >= 4096


def test_file_checksum_matches_hashlib(tmp_path):
    import asyncio

    target = tmp_path / "c.bin"
    data = os.urandom(300_000)
    target.write_bytes(data)
    res = asyncio.run(registry.execute("file_checksum", path=str(target)))
    assert res["sha256"] == hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------- HTTP surface
pytestmark = pytest.mark.skipif(TestClient is None, reason="fastapi TestClient unavailable")


@pytest.fixture()
def client():
    config = SHHConfig()
    config.relaxed_security = True
    app = create_app(config, {"start_time": time.time(), "tunnel_url": "https://demo.trycloudflare.com"})
    return TestClient(app), config


def test_health_endpoint(client):
    c, _ = client
    res = c.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "tools" in body


def test_body_size_guard_returns_413(client):
    c, cfg = client
    oversized = b"x" * (cfg.max_request_mb * 1024 * 1024 + 16)
    res = c.post("/api/tools/file_write", content=oversized,
                 headers={"Content-Type": "application/json"})
    assert res.status_code == 413
    body = res.json()
    assert "exceeds the safe limit" in body["error"]
    assert "file_upload_chunk" in body["fix"]


def test_raw_transfer_upload_and_download_endpoints(client, tmp_path):
    import urllib.parse

    c, _ = client
    target = tmp_path / "raw bin.dat"
    payload = os.urandom(400_000)
    quoted = urllib.parse.quote(str(target), safe="")

    # upload in two chunks
    half = len(payload) // 2
    for idx, piece in enumerate((payload[:half], payload[half:])):
        res = c.post(
            "/api/transfer/upload",
            content=piece,
            headers={
                "X-SHH-Path": quoted,
                "X-SHH-Offset": str(idx * half),
                "X-SHH-Sha256": hashlib.sha256(piece).hexdigest(),
                "X-SHH-Truncate": "1" if idx == 0 else "0",
                "Content-Type": "application/octet-stream",
            },
        )
        assert res.status_code == 200, res.text
        assert res.json()["success"] is True

    assert target.read_bytes() == payload

    # download chunk with gzip
    res = c.get("/api/transfer/download", params={
        "path": str(target), "offset": 0, "length": 100_000, "compress": "gzip",
    })
    assert res.status_code == 200
    assert res.headers["x-shh-compressed"] == "1"
    assert res.headers["x-shh-eof"] == "0"
    assert gzip.decompress(res.content) == payload[:100_000]
    assert hashlib.sha256(payload[:100_000]).hexdigest() == res.headers["x-shh-sha256"]


def test_raw_upload_rejects_chunk_over_limit(client, tmp_path):
    c, cfg = client
    import urllib.parse

    res = c.post(
        "/api/transfer/upload",
        content=b"x" * (cfg.max_raw_chunk_bytes + 1024),
        headers={"X-SHH-Path": urllib.parse.quote(str(tmp_path / "too.big"), safe=""),
                 "X-SHH-Offset": "0", "Content-Type": "application/octet-stream"},
    )
    assert res.status_code == 413


def test_transfer_info_endpoint(client):
    c, _ = client
    body = c.get("/api/transfer/info").json()
    assert body["max_json_chunk_bytes"] > 0
    assert "upload_raw" in body["endpoints"]
