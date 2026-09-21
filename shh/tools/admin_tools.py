"""
SHH 1.0 - Administrator / Elevation Tools
Lets the cloud AI inspect privilege level, run elevated commands, manage Windows
Firewall rules, and create OS-level port forwarding (netsh portproxy).
"""

from typing import Any, Dict, List, Optional

from shh.tools.base import BaseTool, registry
from shh.utils import admin
from shh.utils.logger import Logger
from shh.utils.win_helper import is_windows


class GetPrivilegeInfoTool(BaseTool):
    name = "get_privilege_info"
    description = (
        "Check whether the local SHH agent currently runs with Windows Administrator (UAC elevated) "
        "rights, and which operations are available without a UAC prompt."
    )
    category = "admin"
    parameters = {
        "type": "object",
        "properties": {},
    }

    async def execute(self) -> Dict[str, Any]:
        status = admin.get_admin_status()
        status["success"] = True
        status["supports"] = {
            "silent_elevated_commands": status["is_admin"],
            "firewall_rules": is_windows(),
            "netsh_port_forward": is_windows(),
            "requires_uac_prompt_now": (is_windows() and not status["is_admin"]),
        }
        return status


class RunAdminCommandTool(BaseTool):
    name = "run_admin_command"
    description = (
        "Execute a shell command with Windows Administrator rights (e.g. netsh, sc, reg, mklink, "
        "driver/service management, writing to C:\\Program Files, killing system processes). "
        "If SHH was started with start_shh_admin.bat it runs silently; otherwise ONE UAC prompt "
        "appears on the user's screen and must be approved."
    )
    category = "admin"
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Command line to execute with administrator privileges.",
            },
            "shell": {
                "type": "string",
                "enum": ["cmd", "powershell"],
                "default": "cmd",
                "description": "Which elevated shell to use.",
            },
            "timeout": {
                "type": "integer",
                "default": 120,
                "description": "Maximum seconds to wait for the command to finish.",
            },
            "cwd": {
                "type": "string",
                "description": "Optional working directory for the elevated command.",
            },
        },
        "required": ["command"],
    }

    async def execute(self, command: str, shell: str = "cmd", timeout: int = 120,
                      cwd: Optional[str] = None) -> Dict[str, Any]:
        Logger.tool_call("run_admin_command", {"command": command, "shell": shell})
        res = admin.run_admin_command(command, shell=shell, timeout=timeout, cwd=cwd)
        if res.get("success"):
            Logger.success(
                "Elevated command finished (exit=%s, mode=%s)"
                % (res.get("exit_code"), res.get("elevated_execution"))
            )
        else:
            Logger.error("Elevated command failed: %s" % res.get("error"))
        return res


class ManageFirewallTool(BaseTool):
    name = "manage_firewall"
    description = (
        "Add / delete / list Windows Firewall inbound rules with administrator rights "
        "(allow a local port so other machines or tunnels can reach it)."
    )
    category = "admin"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "delete", "list"],
                "default": "list",
                "description": "Firewall operation to perform.",
            },
            "name": {
                "type": "string",
                "description": "Rule name (used for add/delete, and as the list filter keyword).",
            },
            "port": {
                "type": "integer",
                "description": "Local TCP port to allow (required for action=add).",
            },
            "protocol": {
                "type": "string",
                "enum": ["TCP", "UDP"],
                "default": "TCP",
            },
        },
        "required": ["action"],
    }

    async def execute(self, action: str, name: str = "SHH 1.0 Rule", port: Optional[int] = None,
                      protocol: str = "TCP") -> Dict[str, Any]:
        Logger.tool_call("manage_firewall", {"action": action, "name": name, "port": port})
        action = (action or "list").lower()

        if not is_windows():
            return {"success": False, "error": "Windows Firewall is only available on Windows hosts."}

        if action == "list":
            return admin.list_firewall_rules(keyword=name or "SHH")

        if action == "add":
            if not port:
                return {"success": False, "error": "port is required when action=add"}
            return admin.add_firewall_rule(name, int(port), protocol=protocol)

        if action in ("delete", "remove"):
            return admin.remove_firewall_rule(name)

        return {"success": False, "error": "Unknown action '%s'. Use: add | delete | list" % action}


class ManagePortForwardTool(BaseTool):
    name = "manage_port_forward"
    description = (
        "Create / delete / list OS-level TCP port forwarding rules (netsh interface portproxy) so traffic "
        "arriving on a local port is forwarded to another local or LAN host:port. Requires Administrator."
    )
    category = "admin"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "delete", "list"],
                "default": "list",
            },
            "listen_port": {
                "type": "integer",
                "description": "Local port to listen on.",
            },
            "connect_host": {
                "type": "string",
                "default": "127.0.0.1",
                "description": "Target host to forward traffic to (IP or hostname).",
            },
            "connect_port": {
                "type": "integer",
                "description": "Target port (defaults to listen_port).",
            },
            "listen_address": {
                "type": "string",
                "default": "0.0.0.0",
                "description": "Local address to bind the listener to.",
            },
        },
        "required": ["action"],
    }

    async def execute(self, action: str, listen_port: Optional[int] = None,
                      connect_host: str = "127.0.0.1", connect_port: Optional[int] = None,
                      listen_address: str = "0.0.0.0") -> Dict[str, Any]:
        Logger.tool_call(
            "manage_port_forward",
            {"action": action, "listen_port": listen_port, "connect_host": connect_host},
        )
        action = (action or "list").lower()
        if action in ("add", "delete", "remove") and not listen_port:
            return {"success": False, "error": "listen_port is required when action=%s" % action}
        return admin.manage_port_forward(
            action=action,
            listen_port=int(listen_port or 0),
            connect_host=connect_host,
            connect_port=connect_port,
            listen_address=listen_address,
        )


# Register admin tools
registry.register(GetPrivilegeInfoTool())
registry.register(RunAdminCommandTool())
registry.register(ManageFirewallTool())
registry.register(ManagePortForwardTool())
