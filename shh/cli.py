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

import uvicorn

from shh.config import SHHConfig
from shh.discovery.ip_detector import IPDetector
from shh.discovery.rendezvous import RendezvousManager
from shh.discovery.upnp_mapper import UPnPMapper
from shh.discovery.auto_tunnel import AutoTunnelManager
from shh.manifests.one_click_message import copy_to_windows_clipboard, generate_ai_single_message
from shh.manifests.prompt_builder import build_ai_system_prompt
from shh.manifests.schema_exporter import export_all_manifests, generate_tools_markdown
from shh.servers.http_server import create_app
from shh.servers.mcp_server import run_mcp_stdio
from shh.servers.ssh_server import SSHServerRunner
from shh.tools import registry
from shh.utils.logger import Colors, Logger


def start_server_command(args):
    Logger.banner()

    # Load configuration
    config = SHHConfig.load(args.config) if args.config else SHHConfig()
    
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
        "version": "1.0.0",
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
    tunnel_url = AutoTunnelManager.start_tunnel(local_port=config.port)
    effective_url = tunnel_url or f"http://{effective_ip}:{config.port}"

    metadata["http_base_url"] = effective_url
    metadata["tunnel_url"] = tunnel_url

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
    runtime_state = {
        "lan_ip": lan_ip,
        "public_ipv4": pub_v4,
        "public_ipv6": pub_v6,
        "tunnel_url": tunnel_url,
        "board_url": tunnel_url or board_url,
        "ticket": ticket,
        "start_time": time.time()
    }

    # Start SSH Server
    if config.enable_ssh:
        ssh_runner = SSHServerRunner(config)
        ssh_runner.start()

    # Print summary box
    print(f"\n+============================================================================+")
    print(f"|                       SHH 1.0 Server Ready (ONLINE)                        |")
    print(f"+============================================================================+")
    print(f"|  Local Dashboard:         http://localhost:{config.port}")
    if tunnel_url:
        print(f"|  Integrated Tunnel URL:   {tunnel_url}")
    print(f"|  Access Token:            {config.token}")
    print(f"|  One-Click AI Message:    SEND_TO_AI.md (Already in your clipboard!)")
    print(f"+============================================================================+\n")
    print(f"==============================================================================")
    print(f" [COPY THE MESSAGE BELOW AND PASTE DIRECTLY INTO YOUR CLOUD AI CHAT]")
    print(f"==============================================================================")
    print(single_ai_msg)
    print(f"==============================================================================\n")

    # Start FastAPI / Uvicorn Server
    app = create_app(config, runtime_state)
    uvicorn.run(app, host=config.host, port=config.port, log_level="warning")


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
    elif args.command == "export":
        export_command(args)
    elif args.command == "test":
        test_command(args)
    elif args.command == "mcp":
        run_mcp_stdio()


if __name__ == "__main__":
    main()
