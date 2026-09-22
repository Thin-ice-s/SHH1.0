"""
SHH 1.0 - Automatic Public Tunnel (stable, supervised)

This module is now a thin, backwards-compatible façade over
``shh.discovery.tunnel_supervisor.TunnelSupervisor``, which owns the tunnel process:

  * drains the tunnel process pipes (a full 64 KB pipe silently blocks cloudflared),
  * restarts the SAME provider with exponential backoff if the process dies,
  * never swaps the public URL for transient edge reconnects,
  * audits and announces address changes instead of silently changing them,
  * keep-warm health probes over the public URL.
"""

from typing import Any, Dict, Optional

from shh.config import SHHConfig
from shh.discovery.tunnel_supervisor import TunnelSupervisor
from shh.utils.logger import Logger


class AutoTunnelManager:
    """Backwards-compatible wrapper used by the CLI."""

    @classmethod
    def get_cloudflared_path(cls) -> Optional[str]:
        return TunnelSupervisor._which("cloudflared")

    @classmethod
    def start_tunnel(
        cls,
        local_port: int = 18888,
        timeout: float = 25.0,
        config: Optional[SHHConfig] = None,
        on_url_change=None,
    ) -> Optional[str]:
        """Start (or reuse) the supervised public tunnel and return its URL."""
        cfg = config or SHHConfig()
        supervisor = TunnelSupervisor.create(
            local_port=local_port,
            provider=getattr(cfg, "tunnel_provider", "auto"),
            fixed_domain=getattr(cfg, "tunnel_fixed_domain", None),
            cloudflare_tunnel_name=getattr(cfg, "cloudflare_tunnel_name", None),
            cloudflare_tunnel_token=getattr(cfg, "cloudflare_tunnel_token", None),
            ngrok_authtoken=getattr(cfg, "ngrok_authtoken", None),
            health_interval=float(getattr(cfg, "tunnel_health_interval", 30.0) or 30.0),
            on_url_change=on_url_change,
        )

        previous = supervisor.load_previous_state()
        if previous and previous.get("url"):
            Logger.info(
                "Previous tunnel address on record: %s (provider=%s, stable=%s)"
                % (previous.get("url"), previous.get("provider"), previous.get("address_stable"))
            )

        return supervisor.start(timeout=timeout)

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        inst = TunnelSupervisor.instance()
        return inst.get_status() if inst else {"active": False}

    @classmethod
    def stop(cls) -> None:
        inst = TunnelSupervisor.instance()
        if inst:
            inst.stop()
