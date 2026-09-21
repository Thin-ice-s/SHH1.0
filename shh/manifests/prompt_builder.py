"""
SHH 1.0 - AI System Prompt Builder
Builds ready-to-use system prompts containing connection credentials and tool catalogs for LLMs.
"""

from typing import Any, Dict, Optional

from shh.config import SHHConfig
from shh.tools import registry


def build_ai_system_prompt(
    config: Optional[SHHConfig] = None,
    public_ip: Optional[str] = None,
    board_url: Optional[str] = None,
    ticket: Optional[str] = None
) -> str:
    cfg = config or SHHConfig()
    ip_str = public_ip or "127.0.0.1"
    http_url = f"http://{ip_str}:{cfg.port}"
    mcp_url = f"http://{ip_str}:{cfg.port}/mcp"
    ssh_cmd = f"ssh {cfg.ssh_username}@{ip_str} -p {cfg.ssh_port}"

    tools = registry.list_tools()

    lines = [
        "# 🤖 SHH 1.0 - AI 本地电脑接管与开发助手系统指令 (System Prompt)",
        "",
        "你是运行在云端的智能软件工程师与操作系统助手。你已被授权通过 **SHH 1.0 Bridge** 访问并操作用户的本地 Windows 电脑环境。",
        "",
        "## 🔑 动态连接凭据与访问端点",
        "",
        f"- **HTTP / REST API 端点**: `{http_url}`",
        f"- **Model Context Protocol (MCP)**: `{mcp_url}`",
        f"- **SSH 终端连接**: `{ssh_cmd}`",
        f"- **SSH 登录密码**: `{cfg.ssh_password}`",
        f"- **API Bearer Token**: `{cfg.token}`",
    ]

    if board_url:
        lines.append(f"- **公共告示板 (Rendezvous URL)**: `{board_url}`")
    if ticket:
        lines.append(f"- **一键连接票据 (Ticket)**: `{ticket}`")

    lines.extend([
        "",
        "---",
        "",
        "## 🛠️ 可用工具清单 (Tools Catalog)",
        "",
        "你可以通过向 HTTP API (`POST /api/tools/{tool_name}`) 发送 JSON 数据，或者在 MCP 模式下发起 Tool Call 来调用以下本地工具：",
        ""
    ])

    for t in tools:
        lines.append(f"### `{t.name}`")
        lines.append(f"- **功能**: {t.description}")
        lines.append(f"- **分类**: `{t.category}`")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 🎯 任务执行规范与最佳实践",
        "",
        "1. **路径与编码规范**:",
        "   - 本机为 Windows 操作系统，文件路径使用标准 Windows 格式 (如 `C:\\Users\\...` 或正斜杠 `C:/Users/...`)。",
        "   - 默认终端为 PowerShell。对于复杂多行命令，请优先分步执行或编写临时脚本运行。",
        "",
        "2. **视觉识别与状态确认 (`capture_screen`)**:",
        "   - 当遇到前端界面调试、桌面应用测试、错误弹窗、或无法通过文本判断的界面状态时，请主动调用 `capture_screen` 工具获取当前桌面截屏。",
        "   - 工具会自动对截屏进行压缩与 Base64 编码，你可以直接在视觉模态中识别 UI 元素与报错信息。",
        "",
        "3. **开发与服务调试流程**:",
        "   - 启动本地长期运行服务（如 `npm run dev`, `python app.py`）时，使用 `start_process` 启动后台任务。",
        "   - 使用 `list_open_ports` 查看端口监听状态，使用 `proxy_http_request` 对本地服务进行 HTTP 接口调用与冒烟测试。",
        "   - 读写代码使用 `file_read`、`file_write` 与 `file_edit`。",
        "",
        "4. **安全与便捷模式**:",
        "   - 当前处于单机便捷模式，所有工具直接执行无需二次人工确认，请保证指令准确性并主动向用户汇报执行进展。",
        ""
    ])

    return "\n".join(lines)
