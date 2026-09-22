"""
SHH 1.0 - Zero-Server Public Board Rendezvous System
Publishes dynamic IP and connection keys to public boards so Cloud AI can discover and connect.
"""

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional

from shh.utils.crypto import pack_connection_ticket, unpack_connection_ticket
from shh.utils.logger import Logger


@dataclass
class RendezvousResult:
    provider: str
    board_url: Optional[str]
    ticket: str
    metadata: Dict[str, Any]
    success: bool
    error: Optional[str] = None


class RendezvousManager:
    @classmethod
    def publish_to_dpaste(cls, payload: Dict[str, Any], expiry_days: int = 1) -> Optional[str]:
        """Publish connection metadata to dpaste.org (free, no auth required)."""
        try:
            content = json.dumps(payload, indent=2, ensure_ascii=False)
            data = urllib.parse.urlencode({
                "content": content,
                "expiry_days": expiry_days,
                "title": f"SHH AI Bridge - {payload.get('session_id', 'session')}",
                "syntax": "json"
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://dpaste.org/api/",
                data=data,
                headers={"User-Agent": "SHH-Client/1.0", "Content-Type": "application/x-www-form-urlencoded"}
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status in (200, 201):
                    raw_url = resp.read().decode("utf-8").strip()
                    # Ensure .txt raw suffix for clean parsing by AI
                    if raw_url and not raw_url.endswith(".txt"):
                        return f"{raw_url}.txt"
                    return raw_url
        except Exception as e:
            Logger.warning(f"dpaste.org publish error: {e}")
        return None

    @classmethod
    def publish_to_gist(cls, payload: Dict[str, Any], github_token: str) -> Optional[str]:
        """Publish or update connection metadata in a GitHub Secret Gist."""
        try:
            content = json.dumps(payload, indent=2, ensure_ascii=False)
            body = {
                "description": f"SHH AI Bridge Rendezvous [{payload.get('session_id')}]",
                "public": False,
                "files": {
                    "shh_connection.json": {
                        "content": content
                    }
                }
            }
            req = urllib.request.Request(
                "https://api.github.com/gists",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "SHH-Bridge/1.0",
                    "Content-Type": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status in (200, 201):
                    data = json.loads(resp.read().decode("utf-8"))
                    raw_url = data.get("files", {}).get("shh_connection.json", {}).get("raw_url")
                    return raw_url or data.get("html_url")
        except Exception as e:
            Logger.warning(f"GitHub Gist publish error: {e}")
        return None

    @classmethod
    def publish_to_custom(cls, payload: Dict[str, Any], webhook_url: str) -> Optional[str]:
        """Publish to a custom HTTP webhook or Cloudflare Worker."""
        try:
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "SHH-Client/1.0"}
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status in (200, 201, 204):
                    return webhook_url
        except Exception as e:
            Logger.warning(f"Custom board publish error: {e}")
        return None

    @classmethod
    def publish(
        cls,
        payload: Dict[str, Any],
        provider: str = "dpaste",
        github_token: Optional[str] = None,
        custom_url: Optional[str] = None
    ) -> RendezvousResult:
        """
        Publish connection details and generate ticket.
        """
        payload["published_at"] = int(time.time())
        ticket = pack_connection_ticket(payload)

        board_url = None
        error = None

        if provider == "gist" and github_token:
            board_url = cls.publish_to_gist(payload, github_token)
        elif provider == "custom" and custom_url:
            board_url = cls.publish_to_custom(payload, custom_url)
        elif provider == "dpaste":
            board_url = cls.publish_to_dpaste(payload)

        # If primary provider failed or provider is none, fallback to dpaste or just ticket
        if not board_url and provider != "none":
            board_url = cls.publish_to_dpaste(payload)

        return RendezvousResult(
            provider=provider,
            board_url=board_url,
            ticket=ticket,
            metadata=payload,
            success=True,
            error=error
        )

    @classmethod
    def fetch(cls, board_url_or_ticket: str) -> Dict[str, Any]:
        """
        Fetch and parse connection payload from a Public Board URL, Raw JSON URL, or Ticket.
        """
        target = board_url_or_ticket.strip()

        # Check if it's a direct ticket
        if target.startswith("shh://"):
            return unpack_connection_ticket(target)

        # Check if it's a URL
        if target.startswith("http://") or target.startswith("https://"):
            # If dpaste without .txt, add .txt
            if "dpaste.org" in target and not target.endswith(".txt"):
                target = f"{target}.txt"
            
            req = urllib.request.Request(
                target,
                headers={"User-Agent": "SHH-AI-Client/1.0", "Accept": "application/json, text/plain"}
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                raw_text = resp.read().decode("utf-8")
                try:
                    return json.loads(raw_text)
                except json.JSONDecodeError:
                    # Maybe it's a ticket inside text
                    for line in raw_text.splitlines():
                        if "shh://" in line:
                            ticket_part = line[line.find("shh://"):].strip()
                            return unpack_connection_ticket(ticket_part)
                    raise ValueError(f"Could not parse valid JSON from {target}")

        raise ValueError("Invalid target format: must be shh:// ticket or http(s):// public board URL")
