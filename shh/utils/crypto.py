"""
SHH 1.0 - Cryptographic & Security Utilities
"""

import base64
import hashlib
import json
import os
import secrets
from typing import Any, Dict


def generate_session_token(length: int = 32) -> str:
    """Generate a high-entropy cryptographically secure random session token."""
    return secrets.token_urlsafe(length)


def generate_session_id() -> str:
    """Generate a short user-friendly session ID (e.g. shh-a1b2c3d4)."""
    return f"shh-{secrets.token_hex(4)}"


def generate_ssh_key_pair(comment: str = "shh-ai-bridge") -> Dict[str, str]:
    """
    Generate an RSA/Ed25519 SSH keypair using cryptography / paramiko.
    """
    try:
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        private_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode("utf-8")

        public_ssh = key.public_key().public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH
        ).decode("utf-8") + f" {comment}"

        return {
            "private_key": private_pem,
            "public_key": public_ssh
        }
    except Exception:
        # Fallback to paramiko RSAKey
        import io
        import paramiko
        key = paramiko.RSAKey.generate(2048)
        out = io.StringIO()
        key.write_private_key(out)
        private_pem = out.getvalue()
        public_ssh = f"{key.get_name()} {key.get_base64()} {comment}"
        return {
            "private_key": private_pem,
            "public_key": public_ssh
        }


def pack_connection_ticket(data: Dict[str, Any]) -> str:
    """Pack connection metadata into a compact URL-safe Base64 connection ticket."""
    json_str = json.dumps(data, separators=(",", ":"))
    encoded = base64.urlsafe_b64encode(json_str.encode("utf-8")).decode("utf-8").rstrip("=")
    return f"shh://{encoded}"


def unpack_connection_ticket(ticket: str) -> Dict[str, Any]:
    """Unpack a connection ticket string back into dictionary."""
    if ticket.startswith("shh://"):
        ticket = ticket[6:]
    # Pad base64 if needed
    padding = 4 - (len(ticket) % 4)
    if padding != 4:
        ticket += "=" * padding
    json_str = base64.urlsafe_b64decode(ticket.encode("utf-8")).decode("utf-8")
    return json.loads(json_str)
