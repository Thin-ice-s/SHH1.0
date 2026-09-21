"""
SHH 1.0 - Configuration Manager
"""

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from shh.utils.crypto import generate_session_id, generate_session_token
from shh.utils.win_helper import get_default_shell, is_windows


@dataclass
class SHHConfig:
    # Network & Server
    host: str = "0.0.0.0"
    port: int = 18888
    ssh_port: int = 2222
    enable_ssh: bool = True
    enable_mcp: bool = True
    enable_http: bool = True
    enable_dashboard: bool = True

    # Security & Authentication
    token: str = field(default_factory=generate_session_token)
    session_id: str = field(default_factory=generate_session_id)
    ssh_username: str = "ai-agent"
    ssh_password: str = ""  # auto-filled from token if empty
    relaxed_security: bool = True

    # Execution & Environment
    workspace_dir: str = field(default_factory=lambda: str(Path.cwd()))
    shell_type: str = field(default_factory=lambda: "powershell" if is_windows() else "bash")
    exec_timeout: int = 60

    # Discovery & Public Board (Zero-Server)
    enable_upnp: bool = True
    public_board_provider: str = "dpaste"  # 'dpaste', 'gist', 'custom', 'none'
    github_gist_token: Optional[str] = None
    custom_board_url: Optional[str] = None
    board_ttl_hours: int = 24

    # Screen & Vision
    max_screen_width: int = 1280
    screen_jpeg_quality: int = 75

    def __post_init__(self):
        if not self.ssh_password:
            self.ssh_password = self.token[:16]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SHHConfig":
        valid_keys = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

    @classmethod
    def get_config_path(cls) -> Path:
        # Check current dir, then user home ~/.shh/config.json
        local_path = Path("shh_config.json")
        if local_path.exists():
            return local_path
        home_path = Path.home() / ".shh" / "config.json"
        return home_path

    @classmethod
    def load(cls, path: Optional[str] = None) -> "SHHConfig":
        config_path = Path(path) if path else cls.get_config_path()
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return cls.from_dict(data)
            except Exception:
                pass
        return cls()

    def save(self, path: Optional[str] = None) -> Path:
        config_path = Path(path) if path else Path("shh_config.json")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        return config_path
