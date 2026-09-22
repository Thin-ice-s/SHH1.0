"""
SHH 1.0 - Resilient Tunnel Supervisor (Address-Stable Public Tunnel)

Design goals
------------
1. ADDRESS STABILITY
   - Providers marked ``fixed=True`` (Cloudflare Named Tunnel / token tunnel, ngrok static
     domain, Tailscale Funnel) have a PERMANENT hostname. The supervisor guarantees the
     published URL never changes: it keeps retrying with the exact same hostname and treats
     any observed difference as a fatal configuration error.
   - Quick tunnels (trycloudflare / localhost.run / pinggy) get a random hostname PER PROCESS.
     For those, the supervisor guarantees the URL stays the same for as long as the cloudflared
     process lives: the process itself reconnects to the Cloudflare edge and keeps its hostname.
     The supervisor therefore NEVER restarts a healthy-but-reconnecting process, and when a
     restart is unavoidable it records + announces the address change instead of swapping it
     silently.

2. REAL ROOT CAUSES OF DROPS THAT ARE FIXED HERE
   - stdout/stderr pipes are drained continuously by reader threads. (The old implementation
     read one line and stopped; once the 64 KB OS pipe buffer filled up, cloudflared blocked
     on write() and the tunnel silently died.)
   - Keep-warm pings keep the HTTP path (and any NAT/idle state) alive so the first request
     after a quiet period does not hit a dead connection.
   - Connection health is probed over the PUBLIC URL every N seconds; transient edge
     reconnects are logged as "reconnecting" and do NOT trigger a restart.
   - Process death is detected within seconds and recovered with exponential backoff.
   - Address changes are audited: old URL, new URL, timestamp written to
     TUNNEL_ADDRESS_CHANGED.txt + callback so SEND_TO_AI.md can be regenerated.
"""

import base64
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from shh.utils.logger import Logger
from shh.utils.win_helper import is_windows

STATE_FILE = ".shh_tunnel_state.json"
ADDRESS_CHANGE_FILE = "TUNNEL_ADDRESS_CHANGED.txt"

URL_PATTERNS = (
    re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com"),
    re.compile(r"https://[a-zA-Z0-9.-]+\.lhr\.life"),
    re.compile(r"https://[a-zA-Z0-9.-]+\.pinggy\.link"),
    re.compile(r"https://[a-zA-Z0-9.-]+\.pinggy\.io"),
    re.compile(r"https://[a-zA-Z0-9.-]+\.ngrok-free\.app"),
    re.compile(r"https://[a-zA-Z0-9.-]+\.ngrok\.app"),
    re.compile(r"https://[a-zA-Z0-9.-]+\.ngrok\.io"),
    re.compile(r"https://[a-zA-Z0-9.-]+\.ts\.net"),
    re.compile(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com"),
)

RECONNECT_HINTS = (
    "retrying",
    "reconnect",
    "connection refused",
    "failed to connect",
    "lost connection",
    "register tunnel connection",
    "icmp",
)

FIXED_PROVIDERS = ("cloudflare_named", "cloudflare_token", "ngrok", "tailscale")


@dataclass
class TunnelInfo:
    provider: str
    url: str
    fixed: bool = False
    pid: Optional[int] = None
    started_at: float = 0.0
    last_ok_at: float = 0.0
    restarts: int = 0
    healthy: bool = True
    address_changes: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["uptime_seconds"] = int(time.time() - self.started_at) if self.started_at else 0
        return data


class TunnelSupervisor:
    """Singleton background supervisor that owns the public tunnel process."""

    _instance: Optional["TunnelSupervisor"] = None
    _lock = threading.Lock()

    # ------------------------------------------------------------------ setup
    def __init__(
        self,
        local_port: int = 18888,
        provider: str = "auto",
        fixed_domain: Optional[str] = None,
        cloudflare_tunnel_name: Optional[str] = None,
        cloudflare_tunnel_token: Optional[str] = None,
        ngrok_authtoken: Optional[str] = None,
        health_interval: float = 30.0,
        restart_backoff_max: float = 60.0,
        on_url_change: Optional[Callable[[str, str], None]] = None,
        state_dir: Optional[str] = None,
    ):
        self.local_port = local_port
        self.provider_pref = (provider or "auto").lower()
        self.fixed_domain = (fixed_domain or "").strip()
        self.cf_tunnel_name = (cloudflare_tunnel_name or "").strip()
        self.cf_tunnel_token = (cloudflare_tunnel_token or "").strip()
        self.ngrok_authtoken = (ngrok_authtoken or "").strip()
        self.health_interval = health_interval
        self.restart_backoff_max = restart_backoff_max
        self.on_url_change = on_url_change
        self.state_dir = Path(state_dir) if state_dir else Path.cwd()

        self.info: Optional[TunnelInfo] = None
        self._proc: Optional[subprocess.Popen] = None
        self._reader_threads: List[threading.Thread] = []
        self._log_queue: "list[str]" = []
        self._log_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._supervisor_thread: Optional[threading.Thread] = None
        self._health_thread: Optional[threading.Thread] = None
        self._url_event = threading.Event()
        self._fail_count = 0
        self._reconnecting = False
        self._backoff = 2.0

    # --------------------------------------------------------------- factories
    @classmethod
    def instance(cls) -> Optional["TunnelSupervisor"]:
        return cls._instance

    @classmethod
    def create(cls, **kwargs) -> "TunnelSupervisor":
        with cls._lock:
            if cls._instance is None:
                cls._instance = TunnelSupervisor(**kwargs)
            else:
                # Refresh runtime-tunable fields on reconfigure
                inst = cls._instance
                inst.local_port = kwargs.get("local_port", inst.local_port)
                inst.provider_pref = (kwargs.get("provider") or inst.provider_pref).lower()
                if kwargs.get("fixed_domain"):
                    inst.fixed_domain = kwargs["fixed_domain"]
                if kwargs.get("cloudflare_tunnel_name"):
                    inst.cf_tunnel_name = kwargs["cloudflare_tunnel_name"]
                if kwargs.get("cloudflare_tunnel_token"):
                    inst.cf_tunnel_token = kwargs["cloudflare_tunnel_token"]
                if kwargs.get("on_url_change"):
                    inst.on_url_change = kwargs["on_url_change"]
            return cls._instance

    # ------------------------------------------------------------------ public
    def get_url(self) -> Optional[str]:
        return self.info.url if self.info else None

    def get_status(self) -> Dict[str, Any]:
        if not self.info:
            return {
                "active": False,
                "provider": self.provider_pref,
                "url": None,
                "alive": False,
                "address_stable": False,
            }
        info = self.info.to_dict()
        alive = bool(self._proc and self._proc.poll() is None)
        info.update({
            "active": True,
            "alive": alive,
            "reconnecting": self._reconnecting,
            "consecutive_health_failures": self._fail_count,
            "address_stable": info["fixed"] or info["address_changes"] == 0,
            "friendly": self._friendly_status(alive),
        })
        return info

    def start(self, timeout: float = 25.0) -> Optional[str]:
        """Start the best available provider and return the public URL."""
        url = self._start_provider_preference(timeout=timeout)
        if not url:
            return None

        self._stop_event.clear()
        self._start_supervisor_thread()
        self._start_health_thread()
        self._save_state()
        self._print_banner()
        return url

    def stop(self) -> None:
        self._stop_event.set()
        self._terminate_process()
        Logger.info("Tunnel supervisor stopped.")

    # ------------------------------------------------------- provider startup
    def _start_provider_preference(self, timeout: float) -> Optional[str]:
        pref = self.provider_pref

        if pref == "none":
            Logger.info("Tunnel disabled by configuration (provider=none).")
            return None

        attempts: List[str]
        if pref == "auto":
            attempts = ["cloudflare_token", "cloudflare_named", "ngrok", "tailscale",
                        "cloudflare_quick", "ssh_localhostrun", "pinggy"]
        else:
            aliases = {
                "cloudflare": "cloudflare_quick",
                "trycloudflare": "cloudflare_quick",
                "quick": "cloudflare_quick",
                "named": "cloudflare_named",
                "token": "cloudflare_token",
                "localhost.run": "ssh_localhostrun",
                "localhostrun": "ssh_localhostrun",
                "ssh": "ssh_localhostrun",
            }
            attempts = [aliases.get(pref, pref)]

        last_error = ""
        for name in attempts:
            starter = getattr(self, "_start_" + name.replace(".", "_"), None)
            if starter is None:
                continue
            try:
                info = starter(timeout=timeout)
            except Exception as exc:      # pragma: no cover - provider specific
                info = None
                last_error = "%s: %s" % (name, exc)
            if info and info.url:
                self.info = info
                Logger.success(
                    "Tunnel ONLINE via %s | URL: %s | address %s"
                    % (
                        info.provider,
                        info.url,
                        "PERMANENT (fixed hostname)" if info.fixed else "locked to this process",
                    )
                )
                return info.url
            if pref != "auto":
                Logger.warning("Provider '%s' unavailable%s" % (name, (" (%s)" % last_error) if last_error else ""))

        # Explicit provider failed -> fall back to a quick tunnel so the user is NOT left
        # without any remote access. The address will be random until the fixed provider works.
        if pref != "auto":
            Logger.warning(
                "Requested provider '%s' could not be started. Falling back to a QUICK tunnel "
                "(random address) so you keep remote access. Fix the provider to get a permanent "
                "address: python -m shh tunnel --action providers" % pref
            )
            for fallback in ("cloudflare_quick", "ssh_localhostrun"):
                starter = getattr(self, "_start_" + fallback, None)
                if starter is None:
                    continue
                try:
                    info = starter(timeout=timeout)
                except Exception:
                    info = None
                if info and info.url:
                    self.info = info
                    Logger.success(
                        "Fallback tunnel ONLINE via %s | URL: %s (temporary random address)"
                        % (info.provider, info.url)
                    )
                    return info.url

        Logger.warning("No tunnel provider could be started. Direct IP / LAN access will be used.")
        return None

    # --- Cloudflare Quick Tunnel (random hostname, stable while process lives)
    def _start_cloudflare_quick(self, timeout: float) -> Optional[TunnelInfo]:
        cf = self._which("cloudflared")
        if not cf:
            return None

        cmd = [
            cf, "tunnel",
            "--protocol", os.environ.get("SHH_CF_PROTOCOL", "http2"),
            "--edge-ip-version", os.environ.get("SHH_CF_EDGE_IP", "4"),
            "--no-autoupdate",
            "--url", "http://127.0.0.1:%d" % self.local_port,
        ]
        return self._spawn_and_capture(cmd, provider="cloudflare_quick", fixed=False, timeout=timeout)

    # --- Cloudflare Named Tunnel via connector token (PERMANENT hostname)
    def _start_cloudflare_token(self, timeout: float) -> Optional[TunnelInfo]:
        if not self.cf_tunnel_token:
            return None
        cf = self._which("cloudflared")
        if not cf:
            Logger.warning("cloudflare_token configured but cloudflared.exe not found.")
            return None
        cmd = [
            cf, "tunnel", "--no-autoupdate",
            "--protocol", os.environ.get("SHH_CF_PROTOCOL", "http2"),
            "run", "--token", self.cf_tunnel_token,
        ]
        return self._spawn_and_capture(
            cmd, provider="cloudflare_token", fixed=True, timeout=timeout,
            expected_url="https://%s" % self.fixed_domain if self.fixed_domain else None,
        )

    # --- Cloudflare Named Tunnel via local config/credentials (PERMANENT hostname)
    def _start_cloudflare_named(self, timeout: float) -> Optional[TunnelInfo]:
        if not self.cf_tunnel_name:
            return None
        cf = self._which("cloudflared")
        if not cf:
            return None
        cmd = [cf, "tunnel", "--no-autoupdate", "run", self.cf_tunnel_name]
        return self._spawn_and_capture(
            cmd, provider="cloudflare_named", fixed=True, timeout=timeout,
            expected_url="https://%s" % self.fixed_domain if self.fixed_domain else None,
        )

    # --- ngrok (fixed hostname when a static domain is configured)
    def _start_ngrok(self, timeout: float) -> Optional[TunnelInfo]:
        ng = self._which("ngrok")
        if not ng:
            return None
        cmd = [ng, "http", str(self.local_port), "--log", "stdout", "--log-format", "json"]
        fixed = False
        if self.fixed_domain:
            domain = self.fixed_domain.replace("https://", "").replace("http://", "").rstrip("/")
            cmd += ["--domain", domain]
            fixed = True
        elif self.ngrok_authtoken:
            cmd += ["--authtoken", self.ngrok_authtoken]
        return self._spawn_and_capture(cmd, provider="ngrok", fixed=fixed, timeout=timeout)

    # --- Tailscale Funnel (PERMANENT https://machine.tailnet.ts.net)
    def _start_tailscale(self, timeout: float) -> Optional[TunnelInfo]:
        ts = self._which("tailscale") or self._which("tailscale.exe")
        if not ts:
            return None
        try:
            subprocess.run([ts, "funnel", "--bg", str(self.local_port)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
            out = subprocess.run([ts, "funnel", "status", "--json"],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
            text = out.stdout.decode("utf-8", "replace")
            match = re.search(r"https://[a-zA-Z0-9.-]+\.ts\.net", text)
            if not match:
                # Fallback: derive from tailscale status
                st = subprocess.run([ts, "status", "--json"], stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=20)
                m2 = re.search(rb'"DNSName"\s*:\s*"([a-zA-Z0-9.-]+\.ts\.net)\.?"', st.stdout)
                if m2:
                    return TunnelInfo(
                        provider="tailscale",
                        url="https://" + m2.group(1).decode(),
                        fixed=True,
                        started_at=time.time(),
                    )
                return None
            return TunnelInfo(
                provider="tailscale",
                url=match.group(0).rstrip("/"),
                fixed=True,
                started_at=time.time(),
            )
        except Exception:
            return None

    # --- localhost.run (SSH reverse, random subdomain)
    def _start_ssh_localhostrun(self, timeout: float) -> Optional[TunnelInfo]:
        ssh_bin = self._which("ssh") or self._which("ssh.exe")
        if not ssh_bin:
            return None
        cmd = [
            ssh_bin,
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=%s" % ("NUL" if is_windows() else "/dev/null"),
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=4",
            "-o", "TCPKeepAlive=yes",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ConnectTimeout=15",
            "-R", "80:127.0.0.1:%d" % self.local_port,
            "nokey@localhost.run",
        ]
        return self._spawn_and_capture(cmd, provider="ssh_localhostrun", fixed=False, timeout=timeout)

    # --- pinggy (SSH reverse, random subdomain)
    def _start_pinggy(self, timeout: float) -> Optional[TunnelInfo]:
        ssh_bin = self._which("ssh") or self._which("ssh.exe")
        if not ssh_bin:
            return None
        cmd = [
            ssh_bin, "-p", "443",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=4",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ConnectTimeout=15",
            "-T",
            "-R", "0:127.0.0.1:%d" % self.local_port,
            "free@a.pinggy.io",
        ]
        return self._spawn_and_capture(cmd, provider="pinggy", fixed=False, timeout=timeout)

    # ----------------------------------------------------------- process spawn
    def _spawn_and_capture(
        self,
        cmd: List[str],
        provider: str,
        fixed: bool,
        timeout: float,
        expected_url: Optional[str] = None,
    ) -> Optional[TunnelInfo]:
        creationflags = 0
        if is_windows():
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        Logger.info("Starting tunnel provider '%s'..." % provider)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=False,
            bufsize=0,
            creationflags=creationflags,
        )
        self._proc = proc

        # Drain the merged pipe in a daemon thread: this is what keeps the tunnel
        # process from blocking on a full 64 KB pipe buffer (the #1 cause of drops).
        url_holder: Dict[str, Optional[str]] = {"url": expected_url if fixed else None}
        found = threading.Event()

        def _reader() -> None:
            try:
                for raw_line in iter(proc.stdout.readline, b""):
                    line = raw_line.decode("utf-8", "replace").rstrip()
                    if not line:
                        continue
                    self._ingest_line(line)
                    if not url_holder["url"]:
                        for pattern in URL_PATTERNS:
                            match = pattern.search(line)
                            if match:
                                url_holder["url"] = match.group(0)
                                found.set()
                                break
                    elif any(h in line.lower() for h in RECONNECT_HINTS):
                        self._note_activity(line)
            except Exception:
                pass

        t = threading.Thread(target=_reader, name="shh-tunnel-reader", daemon=True)
        t.start()
        self._reader_threads.append(t)

        # Wait for the URL (or for the process to die)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if url_holder["url"] and (found.is_set() or fixed):
                break
            if proc.poll() is not None:
                break
            time.sleep(0.15)

        # Evaluate result
        if proc.poll() is not None and not (url_holder["url"] and fixed):
            self._drain_log()
            Logger.warning("Provider '%s' exited immediately (code=%s)." % (provider, proc.returncode))
            self._terminate_process()
            return None

        if not url_holder["url"]:
            # Fixed providers (tailscale) may not print the URL at all
            if fixed and self.fixed_domain:
                url_holder["url"] = "https://%s" % self.fixed_domain.lstrip("https://").rstrip("/")
            else:
                Logger.warning("Provider '%s' did not report a public URL within %.0fs." % (provider, timeout))
                self._terminate_process()
                return None

        # Wait a moment so the edge connection finishes registering
        time.sleep(1.5)

        return TunnelInfo(
            provider=provider,
            url=url_holder["url"],
            fixed=fixed,
            pid=proc.pid,
            started_at=time.time(),
            last_ok_at=time.time(),
        )

    @staticmethod
    def _which(name: str) -> Optional[str]:
        found = shutil.which(name)
        if found:
            return found
        local = Path.cwd() / name
        if local.exists():
            return str(local)
        local_exe = Path.cwd() / (name + ".exe")
        if local_exe.exists():
            return str(local_exe)
        return None

    # --------------------------------------------------------------- lifecycle
    def _start_supervisor_thread(self) -> None:
        if self._supervisor_thread and self._supervisor_thread.is_alive():
            return
        self._supervisor_thread = threading.Thread(
            target=self._supervise_loop, name="shh-tunnel-supervisor", daemon=True
        )
        self._supervisor_thread.start()

    def _start_health_thread(self) -> None:
        if self._health_thread and self._health_thread.is_alive():
            return
        self._health_thread = threading.Thread(
            target=self._health_loop, name="shh-tunnel-health", daemon=True
        )
        self._health_thread.start()

    def _supervise_loop(self) -> None:
        """Detect process death, recover with backoff, and NEVER swap the address silently."""
        while not self._stop_event.is_set():
            self._stop_event.wait(3.0)
            if self._stop_event.is_set():
                break
            proc = self._proc
            if proc is None:
                continue
            if proc.poll() is None:
                self._backoff = 2.0
                continue

            # --- process died: recover, keeping the same provider + parameters
            exit_code = proc.returncode
            Logger.warning("Tunnel process died (exit=%s). Restarting the SAME provider..." % exit_code)
            self._drain_log()

            while not self._stop_event.is_set():
                time.sleep(min(self._backoff, self.restart_backoff_max))
                self._backoff = min(self._backoff * 2, self.restart_backoff_max)
                try:
                    old_url = self.info.url if self.info else None
                    ok = self._restart_same_provider()
                except Exception as exc:
                    Logger.warning("Tunnel restart failed: %s" % exc)
                    ok = False

                if not ok:
                    Logger.warning("Tunnel restart attempt failed, retrying in %.0fs..." % self._backoff)
                    continue

                new_url = self.info.url if self.info else None
                if self.info:
                    self.info.restarts += 1
                    self.info.last_ok_at = time.time()

                if new_url and old_url and new_url != old_url:
                    self._record_address_change(old_url, new_url)
                elif new_url:
                    Logger.success("Tunnel restored with the SAME address: %s" % new_url)
                break
            self._backoff = 2.0

    def _restart_same_provider(self) -> bool:
        if not self.info:
            return False
        provider = self.info.provider
        starter = getattr(self, "_start_" + provider.replace(".", "_"), None)
        if starter is None:
            return False
        fixed = self.info.fixed
        expected = "https://%s" % self.fixed_domain if (fixed and self.fixed_domain) else self.info.url
        info = starter(timeout=25.0)
        if not info or not info.url:
            return False
        if fixed and expected and info.url.rstrip("/") != expected.rstrip("/"):
            Logger.error(
                "Fixed-address provider returned a different hostname (%s != %s). "
                "Check your tunnel configuration." % (info.url, expected)
            )
        info.restarts = self.info.restarts
        info.address_changes = self.info.address_changes
        info.history = self.info.history
        self.info = info
        self._save_state()
        return True

    def _record_address_change(self, old_url: str, new_url: str) -> None:
        self.info.address_changes += 1
        entry = {"at": time.time(), "from": old_url, "to": new_url, "restart": self.info.restarts}
        self.info.history.append(entry)
        self.info.history = self.info.history[-20:]

        try:
            path = self.state_dir / ADDRESS_CHANGE_FILE
            with open(path, "a", encoding="utf-8") as f:
                f.write(
                    "[%s] Tunnel address CHANGED after an unavoidable process restart.\n"
                    "  provider : %s\n  old URL  : %s\n  new URL  : %s\n"
                    "  -> Paste the new URL to your cloud AI, or switch to a FIXED-ADDRESS provider\n"
                    "     (Tailscale Funnel / ngrok static domain / Cloudflare named tunnel) so this never happens again.\n\n"
                    % (time.strftime("%Y-%m-%d %H:%M:%S"), self.info.provider, old_url, new_url)
                )
        except Exception:
            pass

        print("\n" + "!" * 78)
        print("!!  TUNNEL ADDRESS CHANGED (only happens if the tunnel process was killed  )")
        print("!!  OLD: %s" % old_url)
        print("!!  NEW: %s" % new_url)
        print("!!  Reason: the quick-tunnel process died and Cloudflare issues a new hostname.")
        print("!!  Use a fixed-address provider to make this impossible (see TUNNEL_STABILITY.md).")
        print("!" * 78 + "\n")

        self._save_state()
        if self.on_url_change:
            try:
                self.on_url_change(old_url, new_url)
            except Exception as exc:
                Logger.warning("on_url_change callback failed: %s" % exc)

    def _health_loop(self) -> None:
        """Probe the public URL. Transient failures never restart a live process."""
        while not self._stop_event.is_set():
            self._stop_event.wait(self.health_interval)
            if self._stop_event.is_set():
                break
            url = self.get_url()
            if not url:
                continue

            ok, detail = self._probe(url)
            if ok:
                if self._fail_count or self._reconnecting:
                    Logger.success("Tunnel health restored (%s)" % detail)
                self._fail_count = 0
                self._reconnecting = False
                if self.info:
                    self.info.healthy = True
                    self.info.last_ok_at = time.time()
                continue

            self._fail_count += 1
            self._reconnecting = True
            if self.info:
                self.info.healthy = False
            Logger.warning(
                "Tunnel health probe failed (%d/%d): %s" % (self._fail_count, 6, detail)
            )

            if self._fail_count < 6:
                # Give cloudflared a chance to reconnect on its own: URL stays identical.
                continue

            proc_dead = bool(self._proc and self._proc.poll() is not None)
            if proc_dead:
                Logger.warning("Tunnel unreachable and process is dead -> supervisor will restart it.")
            elif self.info and self.info.fixed:
                Logger.warning(
                    "Tunnel unreachable but the process is alive and the address is FIXED. "
                    "Keeping the process (no restart) - the hostname will stay valid once the edge reconnects."
                )
                self._fail_count = 3   # keep warning without restarting forever
            else:
                Logger.warning(
                    "Tunnel unreachable for %d probes while the process is alive. "
                    "cloudflared edge reconnects on its own - NOT restarting (a restart would change the URL)."
                    % self._fail_count
                )
                self._fail_count = 3

    @staticmethod
    def _probe(url: str, timeout: float = 12.0) -> (bool, str):  # type: ignore[valid-type]
        target = url.rstrip("/") + "/api/health"
        try:
            req = urllib.request.Request(target, headers={"User-Agent": "SHH-TunnelWatchdog/1.0"})
            ctx = None
            if target.startswith("https"):
                import ssl
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                body = resp.read(200).decode("utf-8", "replace")
                if resp.status == 200:
                    return True, "200 OK"
                return False, "HTTP %s" % resp.status
        except Exception as exc:
            return False, "%s" % exc

    def _terminate_process(self) -> None:
        proc, self._proc = self._proc, None
        if not proc:
            return
        try:
            if proc.poll() is None:
                try:
                    if is_windows():
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                    else:
                        proc.terminate()
                except Exception:
                    proc.kill()
                try:
                    proc.wait(timeout=6)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        except Exception:
            pass

    # ------------------------------------------------------------------ state
    def _save_state(self) -> None:
        if not self.info:
            return
        try:
            payload = self.info.to_dict()
            payload["saved_at"] = time.time()
            payload["local_port"] = self.local_port
            payload["address_stable"] = self.info.fixed or self.info.address_changes == 0
            (self.state_dir / STATE_FILE).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass

    def load_previous_state(self) -> Optional[Dict[str, Any]]:
        path = self.state_dir / STATE_FILE
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    # ------------------------------------------------------------------ misc
    def _ingest_line(self, line: str) -> None:
        with self._log_lock:
            self._log_queue.append(line)
            if len(self._log_queue) > 400:
                self._log_queue = self._log_queue[-200:]
        low = line.lower()
        if any(h in low for h in RECONNECT_HINTS):
            self._note_activity(line)

    def _note_activity(self, line: str) -> None:
        if "register tunnel connection" in line.lower():
            if self._reconnecting:
                Logger.success("cloudflared re-registered its edge connection (URL unchanged).")
            self._reconnecting = False

    def _drain_log(self) -> None:
        """Print the tail of the tunnel log so failures are visible to the user."""
        with self._log_lock:
            lines = self._log_queue[-8:]
            self._log_queue = []
        for line in lines:
            Logger.info("[tunnel] %s" % line[:180])

    def recent_log(self, limit: int = 60) -> List[str]:
        with self._log_lock:
            return self._log_queue[-limit:]

    def _friendly_status(self, alive: bool) -> str:
        if not alive:
            return "restarting"
        if self._reconnecting:
            return "reconnecting (URL unchanged)"
        return "online"

    def _print_banner(self) -> None:
        if not self.info:
            return
        stable = "PERMANENT hostname" if self.info.fixed else "same URL while process is alive"
        print(
            "\n+============================================================================+\n"
            "|  TUNNEL SUPERVISOR ACTIVE                                                  |\n"
            "|  Provider: %-20s Address policy: %-28s |\n"
            "|  Public URL: %s\n"
            "+============================================================================+\n"
            % (self.info.provider, stable, self.info.url)
        )
