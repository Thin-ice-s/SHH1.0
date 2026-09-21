# SHH 1.0 (Smart Host Hub) - Windows AI 本地电脑控制与动态隧道桥梁

<div align="center">

```
   ███████╗██╗  ██╗██╗  ██╗     ██╗ ██████╗ 
   ██╔════╝██║  ██║██║  ██║    ███║██╔═████╗
   ███████╗███████║███████║    ╚██║██║██╔██║
   ╚════██║██╔══██║██╔══██║     ██║████╔╝██║
   ███████║██║  ██║██║  ██║     ██║╚██████╔╝
   ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝     ╚═╝ ╚═════╝ 
```

**专为无公网 IP、动态 IP 的 Windows 电脑打造的云端 AI 本地开发与控制桥梁**  
*零服务器依赖 · 公共告示板中继 · 自动 UPnP / STUN · SSH & MCP 双协议 · 多模态视觉截屏 · 完整工具大纲*

[特性亮点](#-特性亮点) • [架构原理](#-架构原理与零服务器设计) • [5秒快速开始](#-5秒快速开始-windows) • [工具大纲](#-ai-工具大纲-tool-manifest) • [Cloud AI 接入指南](#-cloud-ai-接入与提示词) • [MCP 协议集成](#-mcp-model-context-protocol-集成)

</div>

---

## 🌟 为什么需要 SHH 1.0？

在进行 AI 辅助软件开发时，云端 AI（如 ChatGPT、Claude 3.5/3.7 Sonnet、DeepSeek、自定义云端 Agent）通常运行在外部云服务器或 SaaS 平台中，**无法直接访问和操作开发者本地的 Windows 电脑环境**（无法执行本地测试、无法读写本地代码、无法查看本地运行的 Web 服务、无法看到屏幕报错弹窗）。

同时，绝大部分家庭/办公宽带**没有固定公网 IPv4 地址**，且开发者往往**不想自行购买或维护昂贵的公网云服务器 (VPS)**。

**SHH 1.0** 应运而生，它提供了一整套轻量、高效、零额外服务器成本的本地穿透与 AI 控制组件：
1. **零服务器公网穿透 (Public Board Rendezvous)**：无需购买 VPS，自动通过公共告示板 (dpaste / GitHub Gist / 动态票据) 与云端 AI 建立安全握手。
2. **多通道网络自适应**：自动结合 **IPv6 全球直连 + 路由器 UPnP 自动映射 + STUN NAT 探测**，打通双向网络。
3. **SSH + MCP 双协议支持**：既支持标准 SSH/SFTP 终端接入，又原生支持现代 AI **Model Context Protocol (MCP)** 和 **REST / WebSocket API**。
4. **多模态屏幕视觉识别**：内置高清桌面/窗口截屏与压缩转义组件，让大模型直接“看到” Windows 桌面、UI 元素与报错弹窗。
5. **完整工具大纲与系统提示词**：自动生成标准化 `TOOLS_MANIFEST.md`、`openai_tools.json`、`anthropic_tools.json` 与一键复制的 `AI_SYSTEM_PROMPT.md`。

---

## 🏗️ 架构原理与零服务器设计

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      本地 Windows 电脑 (无固定公网 IP)                 │
 │                                                                        │
 │  ┌──────────────────────────────────────────────────────────────────┐  │
 │  │ SHH 1.0 核心引擎                                                 │  │
 │  │  ├─ IP & STUN 探测器 (IPv4/IPv6/NAT 检测)                        │  │
 │  │  ├─ 路由器 UPnP 自动端口映射器                                   │  │
 │  │  ├─ 交互式 Web 控制台 (Dashboard: http://localhost:18888)        │  │
 │  │  ├─ 内置 SSH 服务 (Paramiko / 端口 2222)                         │  │
 │  │  └─ REST / MCP / WebSocket 服务端 (FastAPI: 端口 18888)          │  │
 │  └───────────────────┬──────────────────────────────────────────────┘  │
 │                      │ 挂载执行                                        │
 │  ┌───────────────────▼──────────────────────────────────────────────┐  │
 │  │ 本地执行工具箱 (Tools):                                          │  │
 │  │  ├─ Shell 执行 (PowerShell / CMD / WSL)                          │  │
 │  │  ├─ 文件管理 (读、写、修改、遍历、正则搜索、语法高亮)            │  │
 │  │  ├─ 进程管理 (任务列表、后台守护、终止进程)                      │  │
 │  │  ├─ 网络与端口 (端口扫描、本地 HTTP 代理请求)                    │  │
 │  │  ├─ 屏幕视觉 (桌面截屏、Base64 编码、多模态 Token 压缩)          │  │
 │  │  └─ 系统硬件 (CPU、内存、多磁盘分区、环境变量)                   │  │
 │  └──────────────────────────────────────────────────────────────────┘  │
 └──────────────────────┬─────────────────────────────────────────────────┘
                        │ 自动将动态 IP、端点与临时 Token 发布
                        ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │            公共告示板 / 握手信标 (Public Board Rendezvous)              │
 │   (免配置匿名 Paste: dpaste.org / GitHub Secret Gist / shh:// 票据)    │
 └──────────────────────┬─────────────────────────────────────────────────┘
                        │ AI 读取端点信息或通过票据直连
                        ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                云端 AI (ChatGPT / Claude / DeepSeek / Cloud Agent)     │
 │                                                                        │
 │  • 方式 1: 直接读取 System Prompt 发起 Tool-Calling (REST / MCP)       │
 │  • 方式 2: 使用 Python SDK (SHHClient.from_board(...)) 编程控制        │
 │  • 方式 3: 通过标准 SSH 终端执行命令与 SFTP 同步代码                   │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 5秒快速开始 (Windows)

### 1. 启动服务

进入项目根目录，选择以下任意一种方式启动：

- **方式 A (推荐双击运行)**:
  双击运行 **`start_shh.bat`** 或在 PowerShell 中运行 **`.\start_shh.ps1`**

- **方式 B (命令行启动)**:
  ```bash
  pip install -r requirements.txt
  python -m shh start
  ```

### 2. 启动输出概览

启动后控制台将显示精美的状态面板：

```
╔════════════════════════════════════════════════════════════════════════════╗
║                        SHH 1.0 服务已就绪 (READY)                         ║
╠════════════════════════════════════════════════════════════════════════════╣
║  🖥️  本地 Web 控制台:     http://localhost:18888                           ║
║  🌐 公共告示板 URL:      https://dpaste.org/xxxx.txt                      ║
║  🎫 一键连接票据:        shh://eyJzZXNzaW9uX2lkIjoi...                    ║
║  🔑 访问 Token:          0j_fK3m...                                       ║
║  🔒 SSH 终端连接:        ssh ai-agent@123.45.67.89 -p 2222                ║
║  🤖 MCP 协议端点:        http://123.45.67.89:18888/mcp                    ║
║  📑 工具大纲文件:        TOOLS_MANIFEST.md / AI_SYSTEM_PROMPT.md          ║
╚════════════════════════════════════════════════════════════════════════════╝
```

### 3. 让 AI 介入工作

1. 打开生成的 **`AI_SYSTEM_PROMPT.md`**（或在本地控制台 `http://localhost:18888` 中点击 **“复制 AI 系统提示词”**）。
2. 直接粘贴发送给你的云端 AI（如 ChatGPT、Claude、Dify 等）。
3. 云端 AI 即可通过接口或 SSH 实时操作你的本地 Windows 电脑！

---

## 🛠️ AI 工具大纲 (Tool Manifest)

SHH 1.0 为 AI 提供了开箱即用的全套本地开发与系统控制工具：

| 工具名称 | 所属分类 | 参数示例 | 功能说明 |
| :--- | :--- | :--- | :--- |
| **`shell_exec`** | `shell` | `command`, `cwd`, `shell`, `timeout` | 在本地 Windows 执行 PowerShell / CMD / WSL / Bash 命令 |
| **`file_read`** | `file` | `path`, `start_line`, `max_lines`, `encoding` | 读取本地文件内容，支持分行、分页与二进制 Base64 |
| **`file_write`** | `file` | `path`, `content`, `content_base64` | 创建或覆写文件，自动递归创建父目录 |
| **`file_edit`** | `file` | `path`, `old_text`, `new_text` | 搜索并精准替换文件内的文本代码块 |
| **`file_list`** | `file` | `path`, `show_hidden` | 遍历指定目录下的文件与子文件夹元数据 |
| **`file_tree`** | `file` | `path`, `max_depth` | 生成可视化的多层级目录树（自动过滤 node_modules 等） |
| **`file_search`** | `file` | `path`, `filename_pattern`, `content_regex` | 支持文件名 Glob 匹配与文件内容正则 Grep 搜索 |
| **`capture_screen`** | `vision` | `max_width`, `quality`, `save_path` | **截取桌面屏幕并转换为 Base64 图片，供多模态大模型视觉识别** |
| **`get_screen_info`** | `vision` | 无 | 获取屏幕分辨率与当前所有打开窗口的标题和坐标 |
| **`list_processes`** | `process` | `name_filter`, `limit` | 列出系统运行中的进程（PID、CPU%、内存占用、命令行） |
| **`kill_process`** | `process` | `pid`, `name`, `force` | 终止指定 PID 或指定名称的进程 |
| **`start_process`** | `process` | `command`, `cwd` | 启动本地持久化后台守护任务（如 `npm run dev`） |
| **`get_process_logs`**| `process` | `job_id` | 获取后台守护任务的运行状态与日志 |
| **`list_open_ports`** | `network` | 无 | 扫描本地正在监听的 TCP 端口及对应进程 |
| **`proxy_http_request`**| `network` | `url`, `method`, `headers`, `body` | 从本地直接向内部服务发起 HTTP 请求（如 `http://localhost:3000`） |
| **`get_system_info`** | `system` | 无 | 获取 CPU、物理内存、全部磁盘分区（C盘/D盘等）与网络接口 |
| **`get_env_vars`** | `system` | `key` | 获取系统环境变量或安全脱敏的环境变量全集 |

> 完整参数规格与 JSON Schema 请参阅 [TOOLS_MANIFEST.md](./TOOLS_MANIFEST.md)。

---

## 🌐 零服务器公共告示板 (Public Board) 原理

为了在**没有私有服务器**的情况下实现外部 AI 自动寻址：

1. **自动发布**：SHH 启动时自动获取当前宽带的动态 IPv4 / IPv6，并向匿名告示板（默认 `dpaste.org`，亦支持 GitHub Secret Gist 或自定义 Webhook）发布一个短暂过期的轻量 JSON 凭据。
2. **AI 读取**：云端程序仅需请求告示板 URL（或直接解析你提供的 `shh://` 票据），即可获取实时公网地址与端点端口。
3. **断网重连**：当家庭宽带动态 IP 发生漂移时，SHH 会自动刷新告示板，保证云端连接不中断。

---

## 💻 Cloud AI 客户端接入 (Python SDK)

如果你正在开发自己的云端 AI Agent 框架（如基于 LangChain、LlamaIndex 或自定义 Python 脚本），可以直接使用 SHH 客户端 SDK：

```python
from shh.client import SHHClient

# 1. 方式一：通过公共告示板或票据直连
client = SHHClient.from_board("https://dpaste.org/xxxx.txt")
# 或 client = SHHClient.from_ticket("shh://...")

# 2. 获取本地系统信息
info = client.get_system_info()
print("本地 OS:", info["os"]["system"])

# 3. 执行 PowerShell 命令
res = client.exec_shell("dir D:\\workspace")
print(res["stdout"])

# 4. 截取屏幕让视觉模型分析
screen = client.capture_screen(max_width=1280)
base64_img = screen["image_data_uri"] # 可直接作为多模态消息发给 GPT-4o / Claude

# 5. 代码文件写入与测试
client.write_file("C:/projects/demo/hello.py", content="print('AI Generated Code')")
exec_res = client.exec_shell("python C:/projects/demo/hello.py")
print(exec_res["stdout"])
```

---

## 🔌 MCP (Model Context Protocol) 集成

SHH 1.0 完美兼容 Anthropic 官方推出的 **MCP 协议**：

### 1. Claude Desktop 配置
在 Claude Desktop 的配置文件 `claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "shh-bridge": {
      "command": "python",
      "args": ["-m", "shh", "mcp"]
    }
  }
}
```

### 2. Cursor / Continue / Cline 接入
在 MCP 设置中选择 HTTP/SSE 模式，填入：
`http://<你的动态IP>:18888/mcp`

---

## 🔒 SSH 终端与 Windows 原生 OpenSSH 服务

SHH 1.0 同时提供两种 SSH 模式：
1. **内置零配置 SSH 服务**：默认在端口 `2222` 启动，跨平台无需额外配置。
   ```bash
   ssh ai-agent@<你的IP> -p 2222
   ```
2. **Windows 原生 OpenSSH 服务一键配置**：
   如果你希望使用 Windows 10/11 自带的官方 OpenSSH Server 服务，只需以管理员身份运行项目中的：
   ```powershell
   .\setup_windows_openssh.ps1
   ```

---

## 🧪 自动化测试与自检

项目包含完整的单元测试与端到端集成测试：

```bash
# 执行本地环境快速自检
python -m shh test

# 运行完整 pytest 测试套件
pytest -v
```

---

## 📄 开源许可证

本项目基于 [MIT License](./LICENSE) 协议开源。
