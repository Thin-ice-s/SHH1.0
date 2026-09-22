"""
SHH 1.0 - Chunked / Resumable Transfer Client (for the cloud AI side)

Every transfer is split into small chunks so that:
  * a dropped tunnel only costs ONE chunk (auto-retried at the same offset),
  * request bodies stay far below tunnel/edge limits (no more crashed uploads),
  * transfers can RESUME from wherever they stopped (offset = current remote size),
  * integrity is verified per chunk and per file (sha256).

Requires only the standard library. Mix into any client exposing:
    self.base_url, self.token
"""

import base64
import gzip
import hashlib
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_CHUNK = 512 * 1024          # 512 KiB per chunk: fast and tunnel-safe
RETRY_ATTEMPTS = 6


class ChunkedTransferMixin:
    """Adds upload/download/put_text/get_text to a client with _call()/_raw()."""

    # ------------------------------------------------------------------ plumbing
    def _raw(self, method: str, url: str, headers=None, data=None, timeout=180):
        """Low-level HTTP request against the SHH bridge (raw / non-JSON endpoints)."""
        hdrs = {"User-Agent": "SHH-AI/1.1"}
        if self.token:
            hdrs["X-SHH-Token"] = self.token
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read()
            # HTTP header names are case-insensitive: Starlette lower-cases custom
            # headers, so normalise here and always look them up in lower case.
            hdrs_out = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, hdrs_out, body

    # HTTP status codes worth retrying (the tunnel/edge blinking, not our request being wrong)
    RETRYABLE_HTTP = (408, 409, 425, 429, 500, 502, 503, 504, 522, 524)

    def _retry(self, fn, what: str = "chunk", attempts: int = RETRY_ATTEMPTS):
        """
        Run fn() with exponential backoff - the tunnel may blink, the transfer must not die.

        Only TRANSIENT failures are retried. A permanent error (bad path, chunk too large,
        401/413, programming error) is raised immediately so the caller gets a fast, clear
        message instead of waiting through pointless backoff.
        """
        delay = 1.5
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                return fn()
            except urllib.error.HTTPError as exc:
                if exc.code not in self.RETRYABLE_HTTP:
                    detail = ""
                    try:
                        detail = exc.read(200).decode("utf-8", "replace")
                    except Exception:
                        pass
                    raise RuntimeError("HTTP %s (not retryable) on %s: %s" % (exc.code, what, detail))
                last_error = exc
            except (TypeError, ValueError, KeyError) as exc:
                raise RuntimeError("invalid request while trying to %s: %s" % (what, exc))
            except Exception as exc:            # network error, timeout, connection reset ...
                last_error = exc

            if attempt == attempts:
                break
            wait = min(delay, 20)
            print("  [retry %d/%d] %s failed (%s) - waiting %.1fs"
                  % (attempt, attempts, what, str(last_error)[:90], wait))
            time.sleep(wait)
            delay *= 1.8
        raise RuntimeError("%s failed after %d attempts: %s" % (what, attempts, last_error))

    def _remote_size(self, remote_path: str) -> int:
        """Current size of the remote file (used to resume)."""
        try:
            res = self._call("/api/tools/file_stat", {"path": remote_path})
            return int(res.get("size_bytes") or 0) if res.get("exists") else 0
        except Exception:
            return 0

    # ------------------------------------------------------------------ upload
    def upload(self, local_path: str, remote_path: str = None, chunk_size: int = DEFAULT_CHUNK,
               compress: bool = True, resume: bool = True, progress: bool = True) -> dict:
        """
        Upload a local file to the remote (Windows) machine in resumable chunks.

        local_path  : file on the AI side
        remote_path : destination on the Windows machine (defaults to the same file name)
        compress    : gzip each chunk (great for text/source/log files, ~3-5x smaller)
        resume      : if the remote file is shorter, continue from its size
        """
        remote_path = remote_path or os.path.basename(local_path)
        size = os.path.getsize(local_path)
        quoted = urllib.parse.quote(remote_path, safe="")
        start = self._remote_size(remote_path) if resume else 0
        if start > size:
            start = 0

        sent = start
        chunk_index = 0
        started = time.time()
        with open(local_path, "rb") as fh:
            fh.seek(start)
            while sent < size:
                chunk = fh.read(chunk_size)
                if not chunk:
                    break
                raw_len = len(chunk)
                offset = sent
                digest = hashlib.sha256(chunk).hexdigest()

                def _send(chunk=chunk, offset=offset, digest=digest):
                    body = gzip.compress(chunk, 5) if compress else chunk
                    headers = {
                        "X-SHH-Path": quoted,
                        "X-SHH-Offset": str(offset),
                        "X-SHH-Sha256": digest,
                        "Content-Type": "application/octet-stream",
                        "Content-Length": str(len(body)),
                    }
                    if compress:
                        headers["X-SHH-Compress"] = "gzip"
                    if offset == 0:
                        headers["X-SHH-Truncate"] = "1"
                    status, _, resp_body = self._raw(
                        "POST", self.base_url + "/api/transfer/upload", headers, body
                    )
                    if status not in (200, 201):
                        raise RuntimeError("HTTP %s: %s" % (status, resp_body[:200]))
                    payload = json.loads(resp_body.decode("utf-8"))
                    if not payload.get("success"):
                        raise RuntimeError(payload.get("error", "upload rejected"))
                    return payload

                try:
                    self._retry(_send, "upload chunk @%d" % offset)
                except Exception:
                    # Network died mid-chunk: re-sync with the server and continue from there
                    if not resume:
                        raise
                    actual = self._remote_size(remote_path)
                    print("  [resume] remote size is %d bytes, continuing from there" % actual)
                    fh.seek(actual)
                    sent = actual
                    continue

                sent += raw_len
                chunk_index += 1
                if progress and (chunk_index % 16 == 0 or sent >= size):
                    pct = sent * 100.0 / size if size else 100.0
                    print("  uploading %s: %.1f%% (%d/%d bytes)" % (remote_path, pct, sent, size), flush=True)
        if progress:
            print("  upload finished: %s" % remote_path, flush=True)

        verify = self._call("/api/tools/file_checksum", {"path": remote_path})
        local_hasher = hashlib.sha256()
        with open(local_path, "rb") as _fh:
            for block in iter(lambda: _fh.read(1024 * 1024), b""):
                local_hasher.update(block)
        local_sha = local_hasher.hexdigest()
        ok = bool(verify.get("sha256")) and verify.get("sha256") == local_sha
        return {
            "success": ok,
            "remote_path": remote_path,
            "bytes_sent": sent,
            "local_size": size,
            "remote_sha256": verify.get("sha256"),
            "local_sha256": local_sha,
            "sha256_match": local_sha == verify.get("sha256"),
            "elapsed_seconds": round(time.time() - started, 2),
        }

    # ---------------------------------------------------------------- download
    def download(self, remote_path: str, local_path: str = None, chunk_size: int = DEFAULT_CHUNK,
                 compress: bool = True, progress: bool = True) -> dict:
        """Download a file from the Windows machine in resumable chunks (raw binary)."""
        local_path = local_path or os.path.basename(remote_path.replace("\\", "/"))
        quoted = urllib.parse.quote(remote_path, safe="")
        offset = os.path.getsize(local_path) if os.path.exists(local_path) else 0
        total = None
        chunk_index = 0
        started = time.time()

        mode = "ab" if offset else "wb"
        with open(local_path, mode) as fh:
            while True:
                def _fetch(offset=offset):
                    url = "%s/api/transfer/download?path=%s&offset=%d&length=%d&compress=%s" % (
                        self.base_url, quoted, offset, chunk_size, "gzip" if compress else "none"
                    )
                    status, headers, body = self._raw("GET", url)
                    if status != 200:
                        raise RuntimeError("HTTP %s: %s" % (status, body[:200]))
                    return headers, body

                try:
                    headers, body = self._retry(_fetch, "download chunk @%d" % offset)
                except Exception:
                    if progress:
                        print("\n  [resume] stopping at %d bytes; call download() again to continue" % offset)
                    break

                total = int(headers.get("x-shh-total-size") or 0)
                if headers.get("x-shh-compressed") == "1":
                    body = gzip.decompress(body)
                expect = headers.get("x-shh-sha256")
                if expect and hashlib.sha256(body).hexdigest() != expect:
                    raise RuntimeError("chunk checksum mismatch at offset %d - retry" % offset)

                if not body:
                    break
                fh.write(body)
                offset += len(body)
                chunk_index += 1
                if progress and (chunk_index % 16 == 0 or headers.get("x-shh-eof") == "1"):
                    pct = (offset * 100.0 / total) if total else 0
                    print("  downloading %s: %.1f%% (%d/%s bytes)"
                          % (remote_path, pct, offset, total or "?"), flush=True)
                if headers.get("x-shh-eof") == "1":
                    break
        if progress:
            print("  download finished: %s" % local_path, flush=True)

        return {
            "success": True,
            "remote_path": remote_path,
            "local_path": local_path,
            "bytes_received": offset,
            "remote_size": total,
            "complete": (total is None) or (offset == total),
            "elapsed_seconds": round(time.time() - started, 2),
        }

    # ------------------------------------------------------------ text helpers
    def put_text(self, remote_path: str, text: str, compress: bool = True) -> dict:
        """Write a text file on the Windows machine (chunked, so any size is safe)."""
        raw = text.encode("utf-8")
        quoted = urllib.parse.quote(remote_path, safe="")
        sent = 0
        while sent < len(raw) or sent == 0:
            chunk = raw[sent:sent + DEFAULT_CHUNK]
            body = gzip.compress(chunk, 5) if compress else chunk
            headers = {
                "X-SHH-Path": quoted,
                "X-SHH-Offset": str(sent),
                "X-SHH-Sha256": hashlib.sha256(chunk).hexdigest(),
                "Content-Length": str(len(body)),
                "Content-Type": "application/octet-stream",
            }
            if compress:
                headers["X-SHH-Compress"] = "gzip"
            if sent == 0:
                headers["X-SHH-Truncate"] = "1"
            self._retry(lambda: self._raw("POST", self.base_url + "/api/transfer/upload", headers, body),
                        "put_text chunk @%d" % sent)
            if not chunk:
                break
            sent += len(chunk)
        return {"success": True, "remote_path": remote_path, "bytes": len(raw)}

    def get_text(self, remote_path: str, max_bytes: int = 4 * 1024 * 1024) -> str:
        """Read a text file from the Windows machine (chunked, safe for big logs)."""
        quoted = urllib.parse.quote(remote_path, safe="")
        offset = 0
        parts = []
        while True:
            url = "%s/api/transfer/download?path=%s&offset=%d&length=%d&compress=gzip" % (
                self.base_url, quoted, offset, DEFAULT_CHUNK
            )
            status, headers, body = self._retry(lambda: self._raw("GET", url), "get_text chunk @%d" % offset)
            if status != 200:
                raise RuntimeError("HTTP %s while reading %s" % (status, remote_path))
            if headers.get("x-shh-compressed") == "1":
                body = gzip.decompress(body)
            if not body:
                break
            parts.append(body)
            offset += len(body)
            if headers.get("x-shh-eof") == "1" or offset >= max_bytes:
                break
        return b"".join(parts).decode("utf-8", errors="replace")

    # ------------------------------------------------------------------ status
    def transfer_info(self) -> dict:
        """Ask the bridge for its current safe chunk limits."""
        return self._call("/api/tools/file_transfer_info")
