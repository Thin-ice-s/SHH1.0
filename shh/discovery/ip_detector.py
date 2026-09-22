"""
SHH 1.0 - Dynamic IP & NAT Detector
Detects Public IPv4, Public IPv6, Local LAN IP, and STUN NAT Mapping.
"""

import socket
import struct
import urllib.request
from typing import Any, Dict, List, Optional


class IPDetector:
    IPV4_SERVICES = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
        "https://ident.me",
        "https://checkip.amazonaws.com"
    ]

    IPV6_SERVICES = [
        "https://api6.ipify.org",
        "https://ident.me",
        "https://ipv6.icanhazip.com"
    ]

    STUN_SERVERS = [
        ("stun.l.google.com", 19302),
        ("stun.cloudflare.com", 3478),
        ("stun1.l.google.com", 19302)
    ]

    @classmethod
    def get_local_lan_ip(cls) -> str:
        """Get the primary local LAN IP address (e.g. 192.168.1.100)."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1.5)
            # Connect to a public DNS without sending actual data
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    @classmethod
    def get_public_ipv4(cls, timeout: float = 3.0) -> Optional[str]:
        """Fetch the public IPv4 address from multiple redundant endpoints."""
        for url in cls.IPV4_SERVICES:
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "curl/7.68.0"}
                )
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    ip = response.read().decode("utf-8").strip()
                    if ip and "." in ip and not ":" in ip:
                        return ip
            except Exception:
                continue
        return None

    @classmethod
    def get_public_ipv6(cls, timeout: float = 3.0) -> Optional[str]:
        """Fetch public IPv6 address if available."""
        for url in cls.IPV6_SERVICES:
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "curl/7.68.0"}
                )
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    ip = response.read().decode("utf-8").strip()
                    if ip and ":" in ip:
                        return ip
            except Exception:
                continue
        return None

    @classmethod
    def stun_nat_query(cls, local_port: int = 18888, timeout: float = 2.5) -> Optional[Dict[str, Any]]:
        """
        Perform a lightweight RFC 5389 / RFC 3489 STUN query to discover NAT mapped external IP & Port.
        """
        for server, port in cls.STUN_SERVERS:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(timeout)
                # Bind to same local port if possible (or ephemeral)
                try:
                    sock.bind(("", 0))
                except Exception:
                    pass

                # STUN Binding Request:
                # Type: 0x0001 (Binding Request)
                # Length: 0x0000
                # Magic Cookie: 0x2112A442
                # Transaction ID: 12 random bytes (96-bit)
                import os
                tx_id = os.urandom(12)
                magic_cookie = 0x2112A442
                header = struct.pack("!HHI12s", 0x0001, 0, magic_cookie, tx_id)

                sock.sendto(header, (server, port))
                data, _ = sock.recvfrom(2048)
                sock.close()

                if len(data) < 20:
                    continue

                msg_type, msg_len, res_magic, res_tx_id = struct.unpack("!HHI12s", data[:20])
                if msg_type != 0x0101 or res_tx_id != tx_id:
                    continue

                # Parse Attributes
                offset = 20
                while offset < 20 + msg_len and offset + 4 <= len(data):
                    attr_type, attr_len = struct.unpack("!HH", data[offset:offset+4])
                    attr_val = data[offset+4:offset+4+attr_len]
                    offset += 4 + attr_len
                    # Pad to 4 bytes
                    if attr_len % 4 != 0:
                        offset += 4 - (attr_len % 4)

                    # XOR-MAPPED-ADDRESS (0x0020)
                    if attr_type == 0x0020 and len(attr_val) >= 8:
                        _, family, xport = struct.unpack("!BBH", attr_val[:4])
                        real_port = xport ^ (magic_cookie >> 16)
                        if family == 0x01: # IPv4
                            xip = struct.unpack("!I", attr_val[4:8])[0]
                            real_ip_int = xip ^ magic_cookie
                            real_ip = socket.inet_ntoa(struct.pack("!I", real_ip_int))
                            return {
                                "stun_server": server,
                                "external_ip": real_ip,
                                "external_port": real_port
                            }
                    # MAPPED-ADDRESS (0x0001)
                    elif attr_type == 0x0001 and len(attr_val) >= 8:
                        _, family, mapped_port = struct.unpack("!BBH", attr_val[:4])
                        if family == 0x01:
                            mapped_ip = socket.inet_ntoa(attr_val[4:8])
                            return {
                                "stun_server": server,
                                "external_ip": mapped_ip,
                                "external_port": mapped_port
                            }
            except Exception:
                continue
        return None

    @classmethod
    def detect_all(cls, local_port: int = 18888) -> Dict[str, Any]:
        """Detect all networking attributes and return a consolidated report."""
        lan_ip = cls.get_local_lan_ip()
        pub_v4 = cls.get_public_ipv4()
        pub_v6 = cls.get_public_ipv6()
        stun_res = cls.stun_nat_query(local_port=local_port)

        return {
            "lan_ip": lan_ip,
            "public_ipv4": pub_v4,
            "public_ipv6": pub_v6,
            "stun": stun_res,
            "primary_ip": pub_v6 if pub_v6 else (pub_v4 if pub_v4 else lan_ip),
            "is_ipv6_available": bool(pub_v6)
        }
