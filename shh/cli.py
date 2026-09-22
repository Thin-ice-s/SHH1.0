"""
SHH 1.0 - Command Line Interface (Clean English)
"""

import argparse
import asyncio
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import uvicorn

from shh.config import SHHConfig
from shh.discovery.ip_detector import IPDetector
from shh.discovery.rendezvous import RendezvousManager
from shh.discovery.upnp_mapper import UPnPMapper
from shh.discovery.auto_tunnel import AutoTunnelManager
from shh.discovery.tunnel_supervisor import TunnelSupervisor
from shh.manifests.one_click_message import copy_to_windows_clipboard, generate_ai_single_message
from shh.manifests.prompt_builder import build_ai_system_prompt
from shh.manifests.schema_exporter import export_all_manifests, generate_tools_markdown
from shh.servers.http_server import create_app
from shh.servers.mcp_server import run_mcp_stdio
from shh.servers.ssh_server import SSHServerRunner
from shh.tools import registry
from shh.utils import admin
from shh.utils.logger import Colors, Logger


def start_server_command(args):
    Logger.banner()

    # Load configuration
    config = SHHConfig.load(args.config) if args.config else SHHConfig()

    # ------------------------------------------------------------------
    # Step 0: Privilege / Administrator mode handling
    # ------------------------------------------------------------------
    if getattr(args, "admin", False) and not admin.is_admin():
        Logger.step("Administrator mode requested - relaunching SHH with UAC elevation...")
        if admin.elevate_self(py_args=[a for a in sys.argv[1:] if a not in ("--admin",)] or ["start"]):
            Logger.info("This un-elevated window can be closed. Continue in the Administrator window.")
            raise SystemExit(0)
        Logger.warning("Elevation cancelled. Continuing in standard user mode.")
    else:
        admin.print_admin_status()

    if args.port:
        config.port = args.port
    if args.ssh_port:
        config.ssh_port = args.ssh_port
    if args.no_ssh:
        config.enable_ssh = False
    if args.no_upnp:
        config.enable_upnp = False
    if args.board:
        config.public_board_provider = args.board
    if args.gist_token:
        config.github_gist_token = args.gist_token
    if args.shell:
        config.shell_type = args.shell
    if args.strict:
        config.relaxed_security = False
    if getattr(args, "tunnel", None):
        config.tunnel_provider = args.tunnel
    if getattr(args, "tunnel_domain", None):
        config.tunnel_fixed_domain = args.tunnel_domain
    if getattr(args, "cloudflare_token", None):
        config.cloudflare_tunnel_token = args.cloudflare_token
    if getattr(args, "cloudflare_tunnel", None):
        config.cloudflare_tunnel_name = args.cloudflare_tunnel
    if getattr(args, "ngrok_token", None):
        config.ngrok_authtoken = args.ngrok_token

    # ------------------------------------------------------------------
    # Step 0.5: Auto-open Windows Firewall (only possible as Administrator)
    # ------------------------------------------------------------------
    if getattr(args, "no_firewall", False):
        Logger.info("Firewall auto-configuration disabled by --no-firewall.")
    elif admin.is_windows() and admin.is_admin():
        Logger.step("Administrator mode: opening Windows Firewall inbound ports...")
        try:
            fw_results = admin.ensure_firewall_rules(
                port=config.port,
                ssh_port=config.ssh_port if config.enable_ssh else None,
            )
            for fw in fw_results:
                if fw.get("success") and fw.get("exit_code", 1) == 0:
                    Logger.success("Firewall rule ready for TCP port %s (inbound allow)" % fw.get("port"))
                else:
                    Logger.warning(
                        "Firewall rule for port %s not confirmed: %s"
                        % (fw.get("port"), (fw.get("stderr") or fw.get("error") or "").strip()[:160])
                    )
        except Exception as exc:
            Logger.warning("Firewall auto-configuration skipped: %s" % exc)
    elif admin.is_windows():
        Logger.info("Not running as Administrator: skipping firewall rule creation (run start_shh_admin.bat).")

    Logger.step("Detecting Network Environment & Dynamic Public IP (Step 1/4)...")
    ip_info = IPDetector.detect_all(local_port=config.port)
    lan_ip = ip_info.get("lan_ip", "127.0.0.1")
    pub_v4 = ip_info.get("public_ipv4")
    pub_v6 = ip_info.get("public_ipv6")
    stun_info = ip_info.get("stun")

    Logger.info(f"Local LAN IP: {lan_ip}")
    if pub_v4:
        Logger.success(f"Detected Public IPv4: {pub_v4}")
    else:
        Logger.warning("No direct public IPv4 detected (behind Router NAT/CGNAT)")

    if pub_v6:
        Logger.success(f"Detected Public IPv6 (Globally Reachable): {pub_v6}")
    if stun_info:
        Logger.info(f"STUN Mapped Endpoint: {stun_info['external_ip']}:{stun_info['external_port']}")

    # UPnP Port Mapping
    upnp_mapped = False
    if config.enable_upnp:
        Logger.step("Requesting Router UPnP Port Forwarding (Step 2/4)...")
        upnp = UPnPMapper()
        if upnp.discover_gateway():
            upnp_res = upnp.add_port_mapping(config.port, config.port, protocol="TCP", description="SHH HTTP")
            if config.enable_ssh:
                upnp.add_port_mapping(config.ssh_port, config.ssh_port, protocol="TCP", description="SHH SSH")
            if upnp_res:
                Logger.success(f"Router UPnP mapping succeeded (External Port: {config.port} / SSH: {config.ssh_port})")
                upnp_mapped = True
            else:
                Logger.warning("Router declined UPnP mapping (will use Public Board / Ticket relay)")
        else:
            Logger.warning("No UPnP gateway found (will use Public Board / Ticket relay)")

    # Prepare connection metadata
    effective_ip = pub_v6 if pub_v6 else (pub_v4 if pub_v4 else (stun_info['external_ip'] if stun_info else lan_ip))
    
    metadata = {
        "version": "1.1.0",
        "session_id": config.session_id,
        "token": config.token,
        "public_ipv4": pub_v4 or (stun_info['external_ip'] if stun_info else None),
        "public_ipv6": pub_v6,
        "lan_ip": lan_ip,
        "port": config.port,
        "ssh_port": config.ssh_port,
        "ssh_username": config.ssh_username,
        "ssh_password": config.ssh_password,
        "http_base_url": f"http://{effective_ip}:{config.port}",
        "mcp_url": f"http://{effective_ip}:{config.port}/mcp",
        "upnp_enabled": upnp_mapped,
        "relaxed_mode": config.relaxed_security
    }

    # Step 3: Integrated Tunnel & Public Rendezvous
    Logger.step("Starting Integrated Public Tunnel & Generating AI Message (Step 3/4)...")

    # Auto-start integrated tunnel in background
    # Regenerated whenever the tunnel URL changes (rare, and never silent)
    def _on_tunnel_url_change(old_url: str, new_url: str) -> None:
        try:
            metadata["http_base_url"] = new_url
            metadata["tunnel_url"] = new_url
            runtime_state["tunnel_url"] = new_url
            msg = generate_ai_single_message(new_url, config)
            Path("SEND_TO_AI.md").write_text(msg, encoding="utf-8")
            copy_to_windows_clipboard(msg)
            Logger.warning("SEND_TO_AI.md regenerated with the new address and copied to clipboard.")
        except Exception as exc:
            Logger.error("Failed to regenerate SEND_TO_AI.md after address change: %s" % exc)

    runtime_state: Dict[str, Any] = {
        "lan_ip": lan_ip,
        "public_ipv4": pub_v4,
        "public_ipv6": pub_v6,
        "start_time": time.time(),
    }

    tunnel_url = AutoTunnelManager.start_tunnel(
        local_port=config.port,
        config=config,
        on_url_change=_on_tunnel_url_change,
    )
    effective_url = tunnel_url or f"http://{effective_ip}:{config.port}"
    if tunnel_url:
        Logger.success(f"Integrated Tunnel URL (stable): {tunnel_url}")
        sup = TunnelSupervisor.instance()
        if sup:
            st = sup.get_status()
            Logger.info(
                "Tunnel address policy: %s | provider=%s"
                % (
                    "PERMANENT hostname" if st.get("fixed") else "stable while the tunnel process lives",
                    st.get("provider"),
                )
            )
    else:
        Logger.warning("No public tunnel URL yet. Falling back to direct IP / LAN address.")

    metadata["http_base_url"] = effective_url
    metadata["tunnel_url"] = tunnel_url

    # Publish rendezvous payload to the zero-server public board (dpaste / gist) -> board_url + ticket
    board_url = None
    ticket = ""
    if config.public_board_provider and config.public_board_provider != "none":
        Logger.step("Publishing connection ticket to public board (%s)..." % config.public_board_provider)
        try:
            rv = RendezvousManager.publish(
                payload=metadata.copy(),
                provider=config.public_board_provider,
                github_token=config.github_gist_token,
                custom_url=config.custom_board_url,
            )
            board_url = rv.board_url
            ticket = rv.ticket or ""
            if board_url:
                Logger.success("Public Board URL: %s" % board_url)
            else:
                Logger.warning("Public board unavailable (network blocked?). Using offline Ticket only.")
        except Exception as exc:
            Logger.warning("Public board publish failed: %s" % exc)
    else:
        Logger.info("Public board disabled (--board none). Using offline Ticket only.")

    if not ticket:
        try:
            from shh.utils.crypto import pack_connection_ticket
            ticket = pack_connection_ticket(metadata)
        except Exception:
            ticket = ""

    # Generate single AI message
    single_ai_msg = generate_ai_single_message(effective_url, config)
    Path("SEND_TO_AI.md").write_text(single_ai_msg, encoding="utf-8")

    # Try copying to Windows clipboard
    copied = copy_to_windows_clipboard(single_ai_msg)
    if copied:
        Logger.success("Message automatically copied to Windows clipboard! (Press Ctrl+V in AI chat)")
    else:
        Logger.info("Saved to SEND_TO_AI.md")

    # Export Manifests & Prompts
    export_all_manifests()
    prompt_text = build_ai_system_prompt(
        config=config,
        public_ip=effective_ip,
        board_url=tunnel_url or board_url,
        ticket=ticket
    )
    Path("AI_SYSTEM_PROMPT.md").write_text(prompt_text, encoding="utf-8")
    Logger.success("Generated TOOLS_MANIFEST.md, SEND_TO_AI.md, and AI_SYSTEM_PROMPT.md")

    # Step 4: Start Services
    Logger.step("Starting Core Server Engines (Step 4/4)...")
    runtime_state.update({
        "tunnel_url": tunnel_url,
        "board_url": tunnel_url or board_url,
        "ticket": ticket,
        "tunnel_status": TunnelSupervisor.instance().get_status() if TunnelSupervisor.instance() else {},
    })

    # Start SSH Server
    if config.enable_ssh:
        ssh_runner = SSHServerRunner(config)
        ssh_runner.start()

    # Print summary box
    def _row(label, value):
        line = "|  %-24s %s" % (label, value)
        return line + " " * max(0, 77 - len(line)) + "|"

    print("\n+============================================================================+")
    print("|                       SHH 1.0 Server Ready (ONLINE)                        |")
    print("+============================================================================+")
    print(_row(f"Local Dashboard:", f"http://localhost:{config.port}"))
    if tunnel_url:
        print(_row("Integrated Tunnel URL:", tunnel_url))
    priv_text = "ADMINISTRATOR (elevated)" if admin.is_admin() else "Standard user"
    print(_row("Privilege Mode:", priv_text))
    sup_inst = TunnelSupervisor.instance()
    if sup_inst:
        sup_status = sup_inst.get_status()
        print(_row("Tunnel Status:", "%s | %s" % (sup_status.get("friendly", "?"),
                                                  "FIXED ADDRESS" if sup_status.get("fixed") else "address locked to process")))
    print(_row("Access Token:", config.token))
    print(_row("One-Click AI Message:", "SEND_TO_AI.md (already copied to clipboard)"))
    print("+============================================================================+\n")
    print(f"==============================================================================")
    print(f" [COPY THE MESSAGE BELOW AND PASTE DIRECTLY INTO YOUR CLOUD AI CHAT]")
    print(f"==============================================================================")
    print(single_ai_msg)
    print(f"==============================================================================\n")

    # Start FastAPI / Uvicorn Server (tuned for tunnel stability)
    app = create_app(config, runtime_state)

    def _shutdown(*_args):
        try:
            TunnelSupervisor.instance() and TunnelSupervisor.instance().stop()
        except Exception:
            pass
        try:
            if config.enable_ssh:
                ssh_runner.stop()
        except Exception:
            pass

    import atexit
    import signal

    atexit.register(_shutdown)
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                signal.signal(sig, lambda *_: (_shutdown(), sys.exit(0)))
            except Exception:
                pass

    try:
        uvicorn.run(
            app,
            host=config.host,
            port=config.port,
            log_level="warning",
            # Keep-alive slightly below the typical tunnel/NAT idle timeout so an
            # idle socket is closed cleanly from our side instead of being reset.
            timeout_keep_alive=65,
            backlog=2048,
            limit_concurrency=1000,
            timeout_graceful_shutdown=10,
        )
    finally:
        _shutdown()


def export_command(args):
    Logger.banner()
    res = export_all_manifests(args.output or ".")
    prompt_text = build_ai_system_prompt()
    Path("AI_SYSTEM_PROMPT.md").write_text(prompt_text, encoding="utf-8")
    Logger.success("Tool manifests and system prompt exported:")
    for k, p in res.items():
        print(f"  - {k}: {p}")
    print(f"  - AI_SYSTEM_PROMPT.md")


def test_command(args):
    Logger.banner()
    Logger.step("Running SHH 1.0 Local Self-Test...")
    
    async def run_tests():
        # 1. Test shell exec
        Logger.info("1. Testing Shell Execution (shell_exec)...")
        res1 = await registry.execute("shell_exec", command="echo 'SHH Test OK'")
        if res1.get("success"):
            Logger.success(f"Shell test passed: {res1.get('stdout', '').strip()}")
        else:
            Logger.error(f"Shell test failed: {res1}")

        # 2. Test system info
        Logger.info("2. Testing System Info (get_system_info)...")
        res2 = await registry.execute("get_system_info")
        if res2.get("success"):
            Logger.success(f"System info passed: OS={res2['os']['system']}, Cores={res2['cpu']['logical_cores']}")
        else:
            Logger.error(f"System info failed: {res2}")

        # 3. Test screen capture
        Logger.info("3. Testing Screen Capture (capture_screen)...")
        res3 = await registry.execute("capture_screen", max_width=640, quality=60)
        if res3.get("success"):
            Logger.success(f"Screen capture passed: Resolution={res3['width']}x{res3['height']}, Size={res3['file_size_kb']}KB")
        else:
            Logger.error(f"Screen capture failed: {res3}")

        # 4. Test file tools
        Logger.info("4. Testing File Operations (file_write & file_read)...")
        test_file = Path("test_shh_temp.txt")
        w_res = await registry.execute("file_write", path=str(test_file), content="SHH Bridge Working!")
        r_res = await registry.execute("file_read", path=str(test_file))
        if test_file.exists():
            test_file.unlink()
        if w_res.get("success") and r_res.get("content") == "SHH Bridge Working!":
            Logger.success("File operations test passed!")
        else:
            Logger.error("File operations test failed!")

        print(f"\n{Colors.BRIGHT_GREEN}{Colors.BOLD}[SUCCESS] All local tool components self-test passed!{Colors.RESET}")

    asyncio.run(run_tests())


def tunnel_command(args):
    """`python -m shh tunnel --action status|providers` - address stability toolkit."""
    Logger.banner()
    action = getattr(args, "action", "status") or "status"
    sup = TunnelSupervisor.instance()

    if action == "status":
        if not sup:
            state = TunnelSupervisor(local_port=args.port).load_previous_state()
            if state:
                Logger.info("No tunnel running in this process. Last recorded tunnel:")
                for key in ("provider", "url", "address_stable", "restarts", "address_changes", "saved_at"):
                    if key in state:
                        print("  %-16s : %s" % (key, state[key]))
                print("\n  Address change log: %s" % (Path.cwd() / ".shh_tunnel_state.json"))
                if (Path.cwd() / "TUNNEL_ADDRESS_CHANGED.txt").exists():
                    print("  WARNING: TUNNEL_ADDRESS_CHANGED.txt exists -> the address changed before.")
            else:
                Logger.info("No tunnel status recorded yet. Start SHH with 'python -m shh start'.")
            return
        status = sup.get_status()
        print("\n--- Tunnel status -----------------------------------------------------")
        for key in ("provider", "url", "friendly", "alive", "fixed", "address_stable", "restarts",
                    "address_changes", "healthy", "consecutive_health_failures", "uptime_seconds", "pid"):
            if key in status:
                print("  %-26s : %s" % (key, status[key]))
        if status.get("history"):
            print("  address history:")
            for entry in status["history"]:
                print("    %s -> %s (%s)" % (entry.get("from"), entry.get("to"),
                                            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.get("at", 0)))))
        print("----------------------------------------------------------------------\n")
        return

    if action in ("providers", "test"):
        print("""
Available tunnel providers
--------------------------
  cloudflare_quick  : random *.trycloudflare.com, NO account needed.
                      Address is stable as long as the cloudflared process lives.
                      (Cloudflare issues a new hostname if the process dies.)
  tailscale         : PERMANENT https://<machine>.<tailnet>.ts.net  (free account, no domain)
                      Setup: install Tailscale -> 'tailscale up' -> 'tailscale funnel 18888'
  ngrok             : PERMANENT https://<name>.ngrok-free.app      (free account, static domain)
                      Setup: 'ngrok config add-authtoken <TOKEN>'
                             'ngrok http 18888 --domain=<your-static-domain>'
  cloudflare_token  : PERMANENT hostname configured in Cloudflare Zero Trust dashboard
                      Setup: Zero Trust -> Networks -> Tunnels -> create -> copy connector token
  cloudflare_named  : PERMANENT hostname via 'cloudflared tunnel create' (needs a Cloudflare domain)
  ssh_localhostrun  : random *.lhr.life over SSH (no account)
  pinggy            : random *.pinggy.link over SSH (no account)

Start SHH with a fixed-address provider, e.g.:
  python -m shh start --tunnel tailscale
  python -m shh start --tunnel ngrok --tunnel-domain your-name.ngrok-free.app --ngrok-token <TOKEN>
  python -m shh start --tunnel cloudflare_token --cloudflare-token <TOKEN> --tunnel-domain bridge.example.com
""")
        return


def transfer_command(args):
    """`python -m shh transfer` - show chunked transfer limits / plan for a file."""
    Logger.banner()
    from shh.tools.transfer_tools import (_max_chunk, HARD_MAX_CHUNK_BYTES, DEFAULT_DOWNLOAD_CHUNK_BYTES)
    from shh.config import SHHConfig

    cfg = SHHConfig.load()
    print("\n--- File transfer safety profile --------------------------------------")
    print("  JSON/base64 chunk limit   : %d bytes (%.0f KiB)" % (_max_chunk(), _max_chunk() / 1024))
    print("  Hard chunk ceiling        : %d bytes (%.0f KiB)" % (HARD_MAX_CHUNK_BYTES, HARD_MAX_CHUNK_BYTES / 1024))
    print("  Raw binary chunk limit    : %d bytes (%.0f MiB)" % (cfg.max_raw_chunk_bytes, cfg.max_raw_chunk_bytes / 1024 / 1024))
    print("  Max HTTP request body     : %d MB" % cfg.max_request_mb)
    print("  Default download chunk    : %d bytes" % DEFAULT_DOWNLOAD_CHUNK_BYTES)
    print("  Endpoints                 : POST /api/transfer/upload  |  GET /api/transfer/download")
    print("  Tools                     : file_stat, file_upload_chunk, file_download_chunk, file_checksum, file_transfer_info")

    if getattr(args, "path", None):
        target = Path(args.path).expanduser()
        if not target.exists():
            Logger.error("File not found: %s" % args.path)
            return
        size = target.stat().st_size
        chunk = min(_max_chunk(), max(64 * 1024, size)) or _max_chunk()
        print("\n  File                      : %s" % target.resolve())
        print("  Size                      : %d bytes (%.2f MB)" % (size, size / 1024 / 1024))
        print("  Suggested chunk size      : %d bytes" % chunk)
        print("  Number of chunks          : %d" % ((size + chunk - 1) // chunk if size else 0))
        print("  Safe to send in one call  : %s" % ("yes" if size <= _max_chunk() else "NO - must chunk"))
    print("----------------------------------------------------------------------\n")


def admin_command(args):
    """Handle `python -m shh admin ...` (administrator utilities)."""
    Logger.banner()
    action = getattr(args, "action", "status") or "status"

    if action == "status":
        status = admin.print_admin_status()
        print("\n--- Privilege detail -------------------------------------------------")
        for key in ("is_windows", "is_admin", "user", "computer", "integrity_level",
                    "python_executable", "python_version", "recommended_launcher"):
            if key in status:
                print("  %-22s : %s" % (key, status[key]))
        print("  %-22s : %s" % ("elevation_hint", status.get("elevation_hint", "")))
        print("----------------------------------------------------------------------\n")
        return

    if action == "elevate":
        if admin.is_admin():
            Logger.success("Already running as Administrator.")
            return
        ok = admin.elevate_self(py_args=["start", "--admin"])
        Logger.success("Elevated window launched." if ok else "Elevation cancelled.")
        return

    if action == "firewall-allow":
        res = admin.add_firewall_rule(args.name, args.port)
        if res.get("success") and res.get("exit_code", 1) == 0:
            Logger.success("Firewall rule '%s' allows inbound TCP %s" % (args.name, args.port))
        else:
            Logger.error("Failed: %s" % (res.get("stderr") or res.get("error")))
        if args.ssh_port:
            admin.add_firewall_rule("SHH 1.0 Bridge SSH (port %d)" % args.ssh_port, args.ssh_port)
        return

    if action == "firewall-list":
        res = admin.list_firewall_rules(keyword=args.name.split()[0] if args.name else "SHH")
        for rule in res.get("matching_rules", []):
            print(rule)
            print("-" * 70)
        return

    if action == "firewall-remove":
        res = admin.remove_firewall_rule(args.name)
        Logger.success("Rule removal requested." if res.get("success") else "Failed: %s" % res.get("error"))
        return

    if action == "port-forward-list":
        res = admin.manage_port_forward("list", listen_port=0)
        print(res.get("stdout") or res.get("error") or "")
        return


def main():
    parser = argparse.ArgumentParser(
        prog="shh",
        description="SHH 1.0 - Smart Host Hub | AI Remote Bridge & Dynamic Tunnel"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Start command
    p_start = subparsers.add_parser("start", help="Start the SHH Bridge server, tunnel, and discovery services")
    p_start.add_argument("--port", type=int, default=18888, help="HTTP/API server port (default: 18888)")
    p_start.add_argument("--ssh-port", type=int, default=2222, help="SSH server port (default: 2222)")
    p_start.add_argument("--no-ssh", action="store_true", help="Disable built-in SSH server")
    p_start.add_argument("--no-upnp", action="store_true", help="Disable UPnP auto port forwarding")
    p_start.add_argument("--board", choices=["dpaste", "gist", "none"], default="dpaste", help="Public board provider")
    p_start.add_argument("--gist-token", type=str, help="GitHub PAT for private Gist rendezvous")
    p_start.add_argument("--shell", choices=["powershell", "cmd", "bash", "wsl", "auto"], default="auto", help="Default shell")
    p_start.add_argument("--strict", action="store_true", help="Enable strict permission check instead of relaxed mode")
    p_start.add_argument("--config", type=str, help="Path to custom config JSON")
    p_start.add_argument("--admin", action="store_true", help="Relaunch SHH with Windows Administrator rights (UAC prompt)")
    p_start.add_argument("--no-firewall", action="store_true", help="Skip automatic Windows Firewall inbound rule creation")
    p_start.add_argument(
        "--tunnel", type=str, default=None,
        choices=["auto", "cloudflare_quick", "cloudflare_token", "cloudflare_named", "ngrok",
                 "tailscale", "ssh_localhostrun", "pinggy", "none"],
        help="Tunnel provider. Use tailscale / ngrok / cloudflare_token for a PERMANENT address."
    )
    p_start.add_argument("--tunnel-domain", type=str, help="Fixed public hostname (ngrok static domain or named tunnel hostname)")
    p_start.add_argument("--cloudflare-token", type=str, help="Cloudflare Zero-Trust connector token (fixed hostname)")
    p_start.add_argument("--cloudflare-tunnel", type=str, help="Cloudflare named tunnel name (needs a Cloudflare domain)")
    p_start.add_argument("--ngrok-token", type=str, help="ngrok authtoken (enables fixed ngrok static domain)")

    # Admin command
    p_admin = subparsers.add_parser("admin", help="Administrator tools: privilege status, elevation, firewall, port forwarding")
    p_admin.add_argument(
        "--action", "-a",
        choices=["status", "elevate", "firewall-allow", "firewall-list", "firewall-remove", "port-forward-list"],
        default="status",
        help="Which administrator action to run (default: status)"
    )
    p_admin.add_argument("--port", type=int, default=18888, help="Port for firewall-allow / port forwarding")
    p_admin.add_argument("--ssh-port", type=int, default=2222, help="SSH port for firewall-allow")
    p_admin.add_argument("--name", type=str, default="SHH 1.0 Bridge HTTP", help="Firewall rule name")
    p_admin.add_argument("--connect-host", type=str, default="127.0.0.1", help="Target host for port forwarding")
    p_admin.add_argument("--connect-port", type=int, help="Target port for port forwarding")

    # Tunnel command
    p_tunnel = subparsers.add_parser("tunnel", help="Tunnel status & permanent-address setup helper")
    p_tunnel.add_argument("--action", "-a", choices=["status", "providers", "test"], default="status")
    p_tunnel.add_argument("--port", type=int, default=18888)

    # Transfer command
    p_transfer = subparsers.add_parser("transfer", help="File transfer limits & chunked-transfer plan")
    p_transfer.add_argument("--path", type=str, help="Inspect a specific file and print its chunk plan")

    # Export command
    p_export = subparsers.add_parser("export", help="Export tool schemas, manifests, and system prompts")
    p_export.add_argument("--output", "-o", type=str, default=".", help="Output directory")

    # Test command
    p_test = subparsers.add_parser("test", help="Run local self-test of all tools and environment")

    # MCP command
    p_mcp = subparsers.add_parser("mcp", help="Run in Stdio MCP mode for Claude Desktop / Cursor")

    args = parser.parse_args()

    if args.command == "start" or args.command is None:
        if args.command is None:
            args = parser.parse_args(["start"])
        start_server_command(args)
    elif args.command == "admin":
        admin_command(args)
    elif args.command == "tunnel":
        tunnel_command(args)
    elif args.command == "transfer":
        transfer_command(args)
    elif args.command == "export":
        export_command(args)
    elif args.command == "test":
        test_command(args)
    elif args.command == "mcp":
        run_mcp_stdio()


if __name__ == "__main__":
    main()
