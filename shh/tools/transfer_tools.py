"""
SHH 1.0 - Resumable Chunked File Transfer Tools

WHY THIS EXISTS
---------------
Sending a whole file in one request (especially base64 inside JSON) makes the request body
huge. Big bodies are exactly what kills tunnels:

  * Cloudflare / tunnel edges buffer or time out large uploads (100 s / 100 MB limits),
  * the tunnel connection gets reset mid-upload and the entire transfer is lost,
  * the agent process spikes memory and can be OOM-killed.

The fix is to move files in SMALL, VERIFIABLE, RESUMABLE CHUNKS so a dropped tunnel only
costs one chunk (which is retried automatically) instead of the whole file.

Tools provided
--------------
  file_stat            - size / mtime / quick hash, used to plan chunking and to resume
  file_upload_chunk    - write one chunk at an explicit offset (create / append / resume)
  file_download_chunk  - read one chunk at an explicit offset (base64 or utf-8 text)
  file_checksum        - sha256 / md5 of a whole file (integrity verification)
  file_transfer_info   - chunking plan + hard limits, so the AI never sends an oversized packet
"""

import base64
import hashlib
import gzip
import os
from pathlib import Path
from typing import Any, Dict, Optional

from shh.tools.base import BaseTool, registry
from shh.utils.logger import Logger

# Absolute hard ceiling for a single JSON/base64 chunk (decoded bytes).
# Anything bigger is what makes tunnels drop, so it is rejected with a clear message.
HARD_MAX_CHUNK_BYTES = 4 * 1024 * 1024          # 4 MiB (config default is 256 KiB)
DEFAULT_CHUNK_BYTES = 256 * 1024                # 256 KiB
DEFAULT_DOWNLOAD_CHUNK_BYTES = 512 * 1024       # 512 KiB


def _max_chunk() -> int:
    """Effective per-chunk limit, from config.json when present."""
    try:
        from shh.config import SHHConfig
        cfg = SHHConfig.load()
        value = int(getattr(cfg, "max_chunk_bytes", DEFAULT_CHUNK_BYTES) or DEFAULT_CHUNK_BYTES)
        return max(4096, min(value, HARD_MAX_CHUNK_BYTES))
    except Exception:
        return DEFAULT_CHUNK_BYTES


def _sha256(path: Path, block_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(block_size)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


class FileStatTool(BaseTool):
    name = "file_stat"
    description = (
        "Get metadata of a local file (size, mtime, sha256). Use it before/while transferring to "
        "plan chunk offsets and to RESUME an interrupted upload/download."
    )
    category = "transfer"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path on the local computer."},
            "hash": {
                "type": "boolean",
                "default": False,
                "description": "Also compute the full sha256 of the file (slower for big files).",
            },
        },
        "required": ["path"],
    }

    async def execute(self, path: str, hash: bool = False) -> Dict[str, Any]:
        file_path = Path(path).expanduser()
        if not file_path.exists():
            return {"success": True, "exists": False, "path": str(file_path), "size_bytes": 0}
        if file_path.is_dir():
            return {
                "success": False,
                "error": "Path is a directory. Use file_list / file_tree for directories.",
                "path": str(file_path),
            }
        stat = file_path.stat()
        result: Dict[str, Any] = {
            "success": True,
            "exists": True,
            "path": str(file_path.resolve()),
            "size_bytes": stat.st_size,
            "modified": stat.st_mtime,
            "is_file": True,
            "recommended_chunk_bytes": min(_max_chunk(), max(64 * 1024, stat.st_size)),
            "chunk_count": (stat.st_size + _max_chunk() - 1) // _max_chunk() if stat.st_size else 0,
        }
        if hash:
            result["sha256"] = _sha256(file_path)
        return result


class FileUploadChunkTool(BaseTool):
    name = "file_upload_chunk"
    description = (
        "Upload ONE chunk of a file to an exact byte offset. Chunks keep request bodies small so the "
        "tunnel cannot be overloaded. Set offset=0 to start (or use truncate=true to overwrite); "
        "keep calling with the SAME file and increasing offsets to append. Returns next_offset so "
        "the transfer can resume precisely after a dropped tunnel."
    )
    category = "transfer"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Destination file path on the local computer."},
            "offset": {
                "type": "integer",
                "default": 0,
                "description": "Byte offset where this chunk must be written (0 = start of file).",
            },
            "data_base64": {
                "type": "string",
                "description": "Base64 of the chunk (use for binary files). Max ~256 KiB decoded per call.",
            },
            "data_text": {
                "type": "string",
                "description": "Plain text chunk (utf-8). Use instead of data_base64 for text files.",
            },
            "compress": {
                "type": "boolean",
                "default": False,
                "description": "Set true if the payload is gzip-compressed (client should set this for text).",
            },
            "truncate": {
                "type": "boolean",
                "default": False,
                "description": "Truncate the destination file before writing (start of a new upload).",
            },
            "sha256_chunk": {
                "type": "string",
                "description": "Optional sha256 of the DECODED chunk; verified server-side.",
            },
        },
        "required": ["path"],
    }

    async def execute(self, path: str, offset: int = 0, data_base64: Optional[str] = None,
                      data_text: Optional[str] = None, compress: bool = False,
                      truncate: bool = False, sha256_chunk: Optional[str] = None) -> Dict[str, Any]:
        limit = _max_chunk()

        if data_base64 is None and data_text is None:
            return {"success": False, "error": "Provide data_base64 or data_text."}

        try:
            if data_base64 is not None:
                raw = base64.b64decode(data_base64)
            else:
                raw = (data_text or "").encode("utf-8")
        except Exception as exc:
            return {"success": False, "error": "Invalid payload: %s" % exc}

        if compress:
            try:
                raw = gzip.decompress(raw)
            except Exception as exc:
                return {"success": False, "error": "Payload marked compress=true but gzip decode failed: %s" % exc}

        if len(raw) > HARD_MAX_CHUNK_BYTES:
            return {
                "success": False,
                "error": (
                    "Chunk is %d bytes which exceeds the hard limit of %d bytes. "
                    "Large packets crash tunnels - split into chunks of <= %d bytes."
                    % (len(raw), HARD_MAX_CHUNK_BYTES, limit)
                ),
                "max_chunk_bytes": limit,
            }

        if sha256_chunk:
            actual = hashlib.sha256(raw).hexdigest()
            if actual.lower() != sha256_chunk.lower():
                return {
                    "success": False,
                    "error": "Chunk sha256 mismatch (expected %s, got %s) - retry this chunk."
                             % (sha256_chunk, actual),
                    "retry": True,
                    "offset": offset,
                }

        file_path = Path(path).expanduser()
        file_path.parent.mkdir(parents=True, exist_ok=True)

        mode = "wb" if truncate else "r+b"
        if not truncate and not file_path.exists():
            mode = "wb"

        try:
            with open(file_path, mode) as f:
                f.seek(int(offset))
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
        except Exception as exc:
            return {"success": False, "error": "Write failed: %s" % exc, "offset": offset}

        next_offset = int(offset) + len(raw)
        file_size = file_path.stat().st_size
        return {
            "success": True,
            "path": str(file_path.resolve()),
            "bytes_written": len(raw),
            "offset": int(offset),
            "next_offset": next_offset,
            "file_size": file_size,
            "sha256_chunk": hashlib.sha256(raw).hexdigest(),
        }


class FileDownloadChunkTool(BaseTool):
    name = "file_download_chunk"
    description = (
        "Read ONE chunk of a local file from an exact byte offset and return it base64-encoded "
        "(or as utf-8 text). Small chunks are what keep tunnel transfers stable; loop over offsets "
        "until eof=true. Optionally gzip-compress the chunk to cut tunnel traffic ~3-5x for text."
    )
    category = "transfer"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Source file path on the local computer."},
            "offset": {"type": "integer", "default": 0, "description": "Byte offset to start reading."},
            "max_bytes": {
                "type": "integer",
                "default": 524288,
                "description": "Max raw bytes to return (clamped to the configured safe limit).",
            },
            "as_text": {
                "type": "boolean",
                "default": False,
                "description": "Return utf-8 text instead of base64 (only for text files).",
            },
            "compress": {
                "type": "boolean",
                "default": False,
                "description": "Gzip-compress the returned chunk (recommended for text/log files).",
            },
        },
        "required": ["path"],
    }

    async def execute(self, path: str, offset: int = 0, max_bytes: int = DEFAULT_DOWNLOAD_CHUNK_BYTES,
                      as_text: bool = False, compress: bool = False) -> Dict[str, Any]:
        file_path = Path(path).expanduser()
        if not file_path.exists() or not file_path.is_file():
            return {"success": False, "error": "File does not exist: %s" % path}

        limit = max(_max_chunk(), min(int(max_bytes), 2 * HARD_MAX_CHUNK_BYTES))
        size = file_path.stat().st_size
        offset = max(0, int(offset))
        if offset >= size:
            return {
                "success": True, "path": str(file_path.resolve()), "offset": offset,
                "eof": True, "size_bytes": size, "bytes_returned": 0,
            }

        read_len = min(limit, size - offset)
        with open(file_path, "rb") as f:
            f.seek(offset)
            raw = f.read(read_len)

        payload = gzip.compress(raw, 6) if compress else raw
        result: Dict[str, Any] = {
            "success": True,
            "path": str(file_path.resolve()),
            "offset": offset,
            "bytes_returned": len(raw),
            "next_offset": offset + len(raw),
            "eof": (offset + len(raw)) >= size,
            "size_bytes": size,
            "sha256_chunk": hashlib.sha256(raw).hexdigest(),
            "compressed": compress,
        }
        if as_text and not compress:
            result["text"] = raw.decode("utf-8", errors="replace")
        else:
            result["data_base64"] = base64.b64encode(payload).decode("ascii")
        return result


class FileChecksumTool(BaseTool):
    name = "file_checksum"
    description = "Compute the sha256 (and md5) checksum of a local file to verify a transfer completed intact."
    category = "transfer"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path on the local computer."},
        },
        "required": ["path"],
    }

    async def execute(self, path: str) -> Dict[str, Any]:
        file_path = Path(path).expanduser()
        if not file_path.exists() or not file_path.is_file():
            return {"success": False, "error": "File does not exist: %s" % path}

        sha = hashlib.sha256()
        md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            while True:
                block = f.read(1024 * 1024)
                if not block:
                    break
                sha.update(block)
                md5.update(block)

        return {
            "success": True,
            "path": str(file_path.resolve()),
            "size_bytes": file_path.stat().st_size,
            "sha256": sha.hexdigest(),
            "md5": md5.hexdigest(),
        }


class FileTransferInfoTool(BaseTool):
    name = "file_transfer_info"
    description = (
        "Explain the safe chunked-transfer strategy and the current hard size limits. "
        "Call this before moving big files so you never send an oversized packet that drops the tunnel."
    )
    category = "transfer"
    parameters = {"type": "object", "properties": {}}

    async def execute(self) -> Dict[str, Any]:
        return {
            "success": True,
            "strategy": "chunked + resumable + optional gzip",
            "json_chunk_limit_bytes": _max_chunk(),
            "hard_chunk_limit_bytes": HARD_MAX_CHUNK_BYTES,
            "fastest_path": {
                "download": "GET /api/transfer/download?path=<path>&offset=<n>&length=<bytes>  (raw binary, no base64)",
                "upload": "POST /api/transfer/upload  with headers X-SHH-Path / X-SHH-Offset / X-SHH-Compress (raw binary body)",
            },
            "tool_path": {
                "download": "file_download_chunk(path, offset, max_bytes, compress)",
                "upload": "file_upload_chunk(path, offset, data_base64|data_text, compress, truncate)",
                "resume": "file_stat(path) -> use size_bytes as the next offset",
            },
            "rules": [
                "Never send a whole file in one call - always chunk it.",
                "Retry a failed chunk at the same offset; the server verifies sha256 per chunk.",
                "Use compress=true for text/log/source files (3-5x less traffic).",
                "Use the raw /api/transfer endpoints for speed on large binary files.",
            ],
        }


registry.register(FileStatTool())
registry.register(FileUploadChunkTool())
registry.register(FileDownloadChunkTool())
registry.register(FileChecksumTool())
registry.register(FileTransferInfoTool())
