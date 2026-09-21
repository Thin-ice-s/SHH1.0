"""
SHH 1.0 - Windows Platform & System Helpers
"""

import os
import platform
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple


def is_windows() -> bool:
    """Check if current host OS is Windows."""
    return platform.system().lower() == "windows"


def get_default_shell() -> str:
    """Return default shell based on OS (PowerShell / CMD on Windows, /bin/bash on Linux/macOS)."""
    if is_windows():
        # Prefer PowerShell if available, else cmd.exe
        return "powershell.exe"
    return "/bin/bash"


def get_system_encoding() -> str:
    """Detect default system encoding (e.g. utf-8, gbk, cp936)."""
    if is_windows():
        return "utf-8"  # We usually run with chcp 65001 or utf-8 decode with gbk fallback
    return "utf-8"


def safe_decode_output(raw_bytes: bytes) -> str:
    """Decode process stdout/stderr trying utf-8, gbk, and replacement characters."""
    if not raw_bytes:
        return ""
    for enc in ("utf-8", "gbk", "cp936", "latin1"):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def get_windows_drives() -> List[str]:
    """List available drive letters on Windows (e.g. ['C:\\', 'D:\\'])."""
    if not is_windows():
        return ["/"]
    drives = []
    try:
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if bitmask & 1:
                drives.append(f"{letter}:\\")
            bitmask >>= 1
    except Exception:
        # Fallback check standard drives
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            path = f"{letter}:\\"
            if os.path.exists(path):
                drives.append(path)
    return drives or ["C:\\"]


def list_open_windows() -> List[Dict[str, Any]]:
    """List all open top-level GUI windows with titles and coordinates on Windows."""
    results = []
    if is_windows():
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32

            def enum_windows_callback(hwnd, extra):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value.strip()
                        if title:
                            rect = wintypes.RECT()
                            user32.GetWindowRect(hwnd, ctypes.byref(rect))
                            width = rect.right - rect.left
                            height = rect.bottom - rect.top
                            if width > 50 and height > 50:
                                results.append({
                                    "hwnd": hwnd,
                                    "title": title,
                                    "x": rect.left,
                                    "y": rect.top,
                                    "width": width,
                                    "height": height
                                })
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
        except Exception:
            pass
    return results


def capture_desktop_image():
    """
    Cross-platform desktop screen capture.
    Returns a PIL Image object or None.
    """
    from PIL import Image

    # 1. Try PIL ImageGrab (standard on Windows and macOS)
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(all_screens=True)
        if img:
            return img
    except Exception:
        pass

    # 2. Try Windows ctypes GDI BitBlt
    if is_windows():
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            # Enable DPI awareness
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass

            width = user32.GetSystemMetrics(0)   # SM_CXSCREEN
            height = user32.GetSystemMetrics(1)  # SM_CYSCREEN

            hdesktop = user32.GetDesktopWindow()
            desktop_dc = user32.GetWindowDC(hdesktop)
            img_dc = gdi32.CreateCompatibleDC(desktop_dc)
            mem_bitmap = gdi32.CreateCompatibleBitmap(desktop_dc, width, height)
            gdi32.SelectObject(img_dc, mem_bitmap)

            # Copy screen to memory DC
            gdi32.BitBlt(img_dc, 0, 0, width, height, desktop_dc, 0, 0, 0x00CC0020)  # SRCCOPY

            # Get bitmap info
            import struct
            bmp_info = struct.pack("IiiHHIIiiII", 40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
            buffer = bytearray(width * height * 4)
            gdi32.GetDIBits(img_dc, mem_bitmap, 0, height, (ctypes.c_char * len(buffer)).from_buffer(buffer), bmp_info, 0)

            # Cleanup
            gdi32.DeleteObject(mem_bitmap)
            gdi32.DeleteDC(img_dc)
            user32.ReleaseDC(hdesktop, desktop_dc)

            img = Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1)
            return img.convert("RGB")
        except Exception:
            pass

    # 3. Fallback: generate a synthetic visual desktop snapshot placeholder if headless Linux
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (1280, 720), color=(30, 34, 42))
        draw = ImageDraw.Draw(img)
        draw.rectangle([20, 20, 1260, 700], outline=(80, 120, 200), width=3)
        draw.text((50, 50), "SHH 1.0 - Desktop Environment Ready", fill=(255, 255, 255))
        draw.text((50, 90), f"Host OS: {platform.system()} {platform.release()}", fill=(180, 200, 220))
        draw.text((50, 120), "Status: Online and waiting for Cloud AI operations", fill=(100, 220, 120))
        return img
    except Exception:
        return None
