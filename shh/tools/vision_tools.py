"""
SHH 1.0 - Screen Capture & Multimodal Vision Tools
Takes screenshots, downscales for LLM token efficiency, encodes to base64 data URIs, and inspects windows.
"""

import base64
import io
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from shh.tools.base import BaseTool, registry
from shh.utils.logger import Logger
from shh.utils.win_helper import capture_desktop_image, is_windows, list_open_windows


class CaptureScreenTool(BaseTool):
    name = "capture_screen"
    description = "Capture the desktop screen, compress/downscale to save tokens, and return as base64 image for multimodal AI vision models (GPT-4o, Claude 3.5 Sonnet, Gemini)."
    category = "vision"
    parameters = {
        "type": "object",
        "properties": {
            "max_width": {
                "type": "integer",
                "default": 1280,
                "description": "Maximum width in pixels for downscaling (preserves aspect ratio, reduces AI token consumption). Set 0 for native resolution."
            },
            "quality": {
                "type": "integer",
                "default": 75,
                "description": "JPEG compression quality (1-100, default: 75)."
            },
            "save_path": {
                "type": "string",
                "description": "Optional file path to save the screenshot on disk (e.g. 'screenshot.jpg')."
            },
            "return_base64": {
                "type": "boolean",
                "default": True,
                "description": "Whether to return the base64 data URL in the response (default: True)."
            }
        }
    }

    async def execute(
        self,
        max_width: int = 1280,
        quality: int = 75,
        save_path: Optional[str] = None,
        return_base64: bool = True
    ) -> Dict[str, Any]:
        Logger.tool_call("capture_screen", {"max_width": max_width, "quality": quality, "save_path": save_path})

        img = capture_desktop_image()
        if img is None:
            return {"success": False, "error": "Failed to capture screen image."}

        orig_w, orig_h = img.size

        # Downscale if max_width is specified and image exceeds it
        if max_width and max_width > 0 and orig_w > max_width:
            ratio = max_width / float(orig_w)
            new_h = int(float(orig_h) * ratio)
            img = img.resize((max_width, new_h), Image.Resampling.LANCZOS)

        current_w, current_h = img.size

        # Compress to JPEG
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
        img_bytes = buf.getvalue()
        size_kb = round(len(img_bytes) / 1024, 1)

        b64_str = base64.b64encode(img_bytes).decode("utf-8")
        data_uri = f"data:image/jpeg;base64,{b64_str}"

        # Save to file if requested
        saved_file = None
        if save_path:
            out_p = Path(save_path).expanduser().resolve()
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_bytes(img_bytes)
            saved_file = str(out_p)

        return {
            "success": True,
            "width": current_w,
            "height": current_h,
            "original_width": orig_w,
            "original_height": orig_h,
            "file_size_kb": size_kb,
            "format": "image/jpeg",
            "saved_path": saved_file,
            "image_data_uri": data_uri if return_base64 else None,
            "base64_preview": b64_str[:60] + "..." if return_base64 else None
        }


class GetScreenInfoTool(BaseTool):
    name = "get_screen_info"
    description = "Get information about display resolution, open application windows, and UI element positions."
    category = "vision"
    parameters = {
        "type": "object",
        "properties": {}
    }

    async def execute(self) -> Dict[str, Any]:
        windows = list_open_windows()
        img = capture_desktop_image()
        res_w, res_h = img.size if img else (0, 0)

        return {
            "success": True,
            "resolution": {"width": res_w, "height": res_h},
            "is_windows": is_windows(),
            "open_windows_count": len(windows),
            "open_windows": windows[:20]  # Top 20 windows
        }


# Register vision tools
registry.register(CaptureScreenTool())
registry.register(GetScreenInfoTool())
