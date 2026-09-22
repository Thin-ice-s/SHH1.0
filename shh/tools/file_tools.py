"""
SHH 1.0 - File Management Tools
Provides read, write, edit, tree, list, search, delete, copy, move capabilities.
"""

import base64
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from shh.tools.base import BaseTool, registry
from shh.utils.logger import Logger


class FileReadTool(BaseTool):
    name = "file_read"
    description = "Read file content from local disk. Supports text with line numbers/ranges or base64 binary encoding."
    category = "file"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to file (absolute or relative to workspace)."
            },
            "start_line": {
                "type": "integer",
                "description": "1-based starting line number (optional, for pagination)."
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum number of lines to return (optional)."
            },
            "encoding": {
                "type": "string",
                "default": "utf-8",
                "description": "File encoding ('utf-8', 'gbk', 'binary'). If 'binary', returns base64 string."
            }
        },
        "required": ["path"]
    }

    async def execute(
        self,
        path: str,
        start_line: Optional[int] = None,
        max_lines: Optional[int] = None,
        encoding: str = "utf-8"
    ) -> Dict[str, Any]:
        Logger.tool_call("file_read", {"path": path, "start_line": start_line, "max_lines": max_lines})
        file_path = Path(path).expanduser().resolve()
        if not file_path.exists():
            return {"success": False, "error": f"File does not exist: {path}"}
        if not file_path.is_file():
            return {"success": False, "error": f"Path is not a file: {path}"}

        size = file_path.stat().st_size

        if encoding.lower() == "binary":
            with open(file_path, "rb") as f:
                data = f.read()
            return {
                "success": True,
                "path": str(file_path),
                "is_binary": True,
                "size_bytes": size,
                "content_base64": base64.b64encode(data).decode("utf-8")
            }

        # Try reading as text
        raw_bytes = file_path.read_bytes()
        text = ""
        for enc in (encoding, "utf-8", "gbk", "cp936", "latin1"):
            try:
                text = raw_bytes.decode(enc)
                break
            except Exception:
                continue
        if not text and raw_bytes:
            text = raw_bytes.decode("utf-8", errors="replace")

        lines = text.splitlines(keepends=True)
        total_lines = len(lines)

        start = (start_line - 1) if (start_line and start_line > 0) else 0
        limit = max_lines if (max_lines and max_lines > 0) else total_lines
        selected_lines = lines[start:start + limit]

        return {
            "success": True,
            "path": str(file_path),
            "total_lines": total_lines,
            "returned_lines": len(selected_lines),
            "start_line": start + 1,
            "size_bytes": size,
            "content": "".join(selected_lines)
        }


class FileWriteTool(BaseTool):
    name = "file_write"
    description = "Create or overwrite a file with given text or base64 binary content. Creates parent folders automatically."
    category = "file"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to file (absolute or relative to workspace)."
            },
            "content": {
                "type": "string",
                "description": "Text content to write to the file."
            },
            "content_base64": {
                "type": "string",
                "description": "Optional base64 binary data if writing binary file."
            },
            "encoding": {
                "type": "string",
                "default": "utf-8",
                "description": "Text encoding to write (default: utf-8)."
            }
        },
        "required": ["path"]
    }

    async def execute(
        self,
        path: str,
        content: Optional[str] = None,
        content_base64: Optional[str] = None,
        encoding: str = "utf-8"
    ) -> Dict[str, Any]:
        Logger.tool_call("file_write", {"path": path, "size": len(content or content_base64 or "")})
        file_path = Path(path).expanduser().resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if content_base64:
            raw_bytes = base64.b64decode(content_base64)
            file_path.write_bytes(raw_bytes)
            return {
                "success": True,
                "path": str(file_path),
                "bytes_written": len(raw_bytes),
                "mode": "binary"
            }

        text = content or ""
        file_path.write_text(text, encoding=encoding)
        return {
            "success": True,
            "path": str(file_path),
            "bytes_written": len(text.encode(encoding)),
            "lines_written": len(text.splitlines()),
            "mode": "text"
        }


class FileEditTool(BaseTool):
    name = "file_edit"
    description = "Search and replace a specific text block within a file (exact or whitespace-tolerant match)."
    category = "file"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Target file path."
            },
            "old_text": {
                "type": "string",
                "description": "Text snippet to find and replace."
            },
            "new_text": {
                "type": "string",
                "description": "Replacement text snippet."
            }
        },
        "required": ["path", "old_text", "new_text"]
    }

    async def execute(self, path: str, old_text: str, new_text: str) -> Dict[str, Any]:
        Logger.tool_call("file_edit", {"path": path})
        file_path = Path(path).expanduser().resolve()
        if not file_path.exists() or not file_path.is_file():
            return {"success": False, "error": f"File does not exist: {path}"}

        content = file_path.read_text(encoding="utf-8", errors="replace")

        # 1. Exact match
        if old_text in content:
            updated = content.replace(old_text, new_text, 1)
            file_path.write_text(updated, encoding="utf-8")
            return {"success": True, "path": str(file_path), "match_mode": "exact", "message": "File updated successfully."}

        # 2. Normalize whitespace match
        def normalize_ws(s):
            return re.sub(r"\s+", " ", s).strip()

        norm_old = normalize_ws(old_text)
        lines = content.splitlines()
        norm_lines = [normalize_ws(l) for l in lines]

        # Simple fuzzy fallback: try matching with normalized line chunks
        chunk_len = len(old_text.splitlines())
        replaced = False
        for i in range(len(lines) - chunk_len + 1):
            block = "\n".join(lines[i:i + chunk_len])
            if normalize_ws(block) == norm_old:
                new_lines = lines[:i] + [new_text] + lines[i + chunk_len:]
                file_path.write_text("\n".join(new_lines), encoding="utf-8")
                replaced = True
                return {"success": True, "path": str(file_path), "match_mode": "normalized", "message": "File updated successfully."}

        return {
            "success": False,
            "error": "Target old_text not found in file. Please verify exact content."
        }


class FileListTool(BaseTool):
    name = "file_list"
    description = "List files and directories inside a path with size, modified timestamp, and type."
    category = "file"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path (defaults to current workspace)."
            },
            "show_hidden": {
                "type": "boolean",
                "default": False,
                "description": "Whether to include hidden files (starting with .)."
            }
        }
    }

    async def execute(self, path: Optional[str] = None, show_hidden: bool = False) -> Dict[str, Any]:
        target_dir = Path(path or ".").expanduser().resolve()
        if not target_dir.exists() or not target_dir.is_dir():
            return {"success": False, "error": f"Directory does not exist: {path}"}

        items = []
        for p in sorted(target_dir.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if not show_hidden and p.name.startswith("."):
                continue
            try:
                stat = p.stat()
                items.append({
                    "name": p.name,
                    "path": str(p),
                    "is_dir": p.is_dir(),
                    "size_bytes": stat.st_size if p.is_file() else None,
                    "modified_time": int(stat.st_mtime)
                })
            except Exception:
                continue

        return {
            "success": True,
            "directory": str(target_dir),
            "total_items": len(items),
            "items": items
        }


class FileTreeTool(BaseTool):
    name = "file_tree"
    description = "Generate a formatted visual tree structure of a directory with depth limit and ignored patterns."
    category = "file"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Root directory path."
            },
            "max_depth": {
                "type": "integer",
                "default": 3,
                "description": "Maximum directory traversal depth (default: 3)."
            }
        }
    }

    async def execute(self, path: Optional[str] = None, max_depth: int = 3) -> Dict[str, Any]:
        root_dir = Path(path or ".").expanduser().resolve()
        if not root_dir.exists() or not root_dir.is_dir():
            return {"success": False, "error": f"Directory does not exist: {path}"}

        ignore_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode", "dist", "build"}
        tree_lines = [f"{root_dir.name}/"]

        def build_tree(current_dir: Path, prefix: str, current_depth: int):
            if current_depth > max_depth:
                return
            try:
                entries = sorted(list(current_dir.iterdir()), key=lambda x: (not x.is_dir(), x.name.lower()))
            except Exception:
                return

            filtered = [e for e in entries if e.name not in ignore_dirs and not e.name.startswith(".")]
            count = len(filtered)
            for idx, entry in enumerate(filtered):
                is_last = (idx == count - 1)
                connector = "└── " if is_last else "├── "
                suffix = "/" if entry.is_dir() else ""
                tree_lines.append(f"{prefix}{connector}{entry.name}{suffix}")
                if entry.is_dir():
                    extension = "    " if is_last else "│   "
                    build_tree(entry, prefix + extension, current_depth + 1)

        build_tree(root_dir, "", 1)
        return {
            "success": True,
            "root": str(root_dir),
            "tree_view": "\n".join(tree_lines)
        }


class FileSearchTool(BaseTool):
    name = "file_search"
    description = "Search for files by filename pattern (glob) or search file contents with regex grep."
    category = "file"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory to search within."
            },
            "filename_pattern": {
                "type": "string",
                "description": "Glob pattern for filename (e.g. '*.py', '*.json', 'config.*')."
            },
            "content_regex": {
                "type": "string",
                "description": "Regex pattern to grep file contents for."
            },
            "max_results": {
                "type": "integer",
                "default": 50,
                "description": "Maximum number of search results to return."
            }
        }
    }

    async def execute(
        self,
        path: Optional[str] = None,
        filename_pattern: Optional[str] = None,
        content_regex: Optional[str] = None,
        max_results: int = 50
    ) -> Dict[str, Any]:
        root_dir = Path(path or ".").expanduser().resolve()
        if not root_dir.exists() or not root_dir.is_dir():
            return {"success": False, "error": f"Directory does not exist: {path}"}

        ignore_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode", "dist", "build"}
        results = []
        compiled_regex = re.compile(content_regex, re.IGNORECASE) if content_regex else None

        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith(".")]
            for fname in filenames:
                if len(results) >= max_results:
                    break
                full_path = Path(dirpath) / fname
                
                # Check filename pattern
                if filename_pattern:
                    import fnmatch
                    if not fnmatch.fnmatch(fname, filename_pattern):
                        continue

                # Check content regex
                if compiled_regex:
                    try:
                        text = full_path.read_text(encoding="utf-8", errors="ignore")
                        matches = []
                        for lno, line in enumerate(text.splitlines(), start=1):
                            if compiled_regex.search(line):
                                matches.append({"line_number": lno, "line": line.strip()[:200]})
                                if len(matches) >= 5:
                                    break
                        if matches:
                            results.append({
                                "file": str(full_path),
                                "matches": matches
                            })
                    except Exception:
                        continue
                else:
                    results.append({
                        "file": str(full_path),
                        "size_bytes": full_path.stat().st_size
                    })

        return {
            "success": True,
            "search_root": str(root_dir),
            "matches_found": len(results),
            "results": results
        }


# Register file tools
registry.register(FileReadTool())
registry.register(FileWriteTool())
registry.register(FileEditTool())
registry.register(FileListTool())
registry.register(FileTreeTool())
registry.register(FileSearchTool())
