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

[特性亮点](#-特性亮点) • [架构原理](#-架构原理与零服务器设计) • [5秒快速开始](#-5秒快速开始-windows) • [管理员模式](#-管理员模式启动-administrator--uac) • [隧道稳定性](TUNNEL_STABILITY.md) • [文件传输](FILE_TRANSFER.md) • [工具大纲](#-ai-工具大纲-tool-manifest) • [MCP 协议集成](#-mcp-model-context-protocol-集成)

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
6. **管理员模式 (Administrator / UAC)**：`start_shh_admin.bat` 一键提权，自动放行防火墙端口、支持 `netsh portproxy` 端口转发、静默执行管理员命令与系统级进程管理。
7. **隧道守护 (Tunnel Supervisor)**：常驻排空管道 + 进程守护 + 指数退避重启 + 30 秒保活探测；边缘重连**不会**换地址，地址若真的变化会记录并告警，绝不静默切换。支持 Tailscale / ngrok / Cloudflare 具名隧道实现**永久固定地址**。
8. **分块续传文件传输 (Chunked Transfer)**：512 KiB 分块 + gzip + 逐块 sha256 + 自动重试 + 断点续传；服务端硬熔断超大单包（HTTP 413），从此大文件不再打崩隧道。

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

---

## 🛡️ 管理员模式启动 (Administrator / UAC)

需要访问 `netsh`、防火墙规则、`portproxy` 端口转发、服务管理、驱动级操作、结束系统进程、
写入 `C:\Program Files` 等受限区域时，请用**管理员模式**启动 SHH。

### 三种进入管理员模式的方式

| 方式 | 操作 | 说明 |
| :--- | :--- | :--- |
| **① 双击（推荐）** | 双击 **`start_shh_admin.bat`** | 自动检测权限 → 弹一次 UAC → 在**新的管理员窗口**中启动 SHH |
| **② 普通启动脚本带参数** | `start_shh.bat admin` | 同上，自动提权重启 |
| **③ 命令行 / PowerShell** | `python -m shh start --admin`<br>`.\start_shh.ps1 -Admin` | 由 Python / PowerShell 侧发起提权 |
| **④ 永久免右键** | `powershell -ExecutionPolicy Bypass -File .\create_admin_shortcut.ps1` | 在桌面创建带“以管理员身份运行”标记的快捷方式，以后双击即管理员启动 |

> ⚠️ UAC 弹窗是 Windows 的强制安全机制，**无法绕过**（除非把 UAC 滑块调到最低）。
> 你只需要点一次“是”，提权后的 SHH 进程在整个运行期间都拥有管理员权限。

### 管理员模式自动带来什么

启动为管理员后，SHH 会自动完成这些原本会失败或受限的工作：

1. **自动放行 Windows 防火墙**：为 HTTP 端口（默认 18888）与 SSH 端口（默认 2222）添加入站 TCP 允许规则，
   让外部隧道/局域网设备能真正连进来（`netsh advfirewall firewall add rule`）。
   不想自动改防火墙时加 `--no-firewall`。
2. **AI 可静默执行管理员命令**：工具 `run_admin_command` 不再需要每次弹 UAC。
3. **OS 级端口转发生效**：`manage_port_forward`（`netsh interface portproxy`）可用，
   把外部端口转发到本机或局域网其它主机，并自动拉起 IP Helper 服务。
4. **进程 / 服务 / 文件权限**：可以结束系统进程、操作服务、读写受保护目录。

### 相关命令速查

```bash
python -m shh admin --action status                 # 查看当前权限等级与能力
python -m shh admin --action elevate                # 请求提权并重启 SHH
python -m shh admin --action firewall-allow --port 18888 --ssh-port 2222
python -m shh admin --action firewall-list
python -m shh admin --action firewall-remove --name "SHH 1.0 Bridge HTTP (port 18888)"
python -m shh admin --action port-forward-list
```

### 云端 AI 侧调用示例（管理员能力）

```python
win.is_admin()                                   # {"is_admin": True, "elevation_hint": ...}
win.admin_run('netsh advfirewall firewall show rule name=all')   # 管理员命令
win.firewall("add", name="MyDevServer 3000", port=3000)          # 放行端口
win.port_forward("add", listen_port=8080, connect_host="192.168.1.50", connect_port=80)
win.port_forward("list")
```

> 若 SHH 是以**普通用户**启动的，调用上述工具时 Windows 会弹出一次 UAC 让用户确认；
> 以 `start_shh_admin.bat` 启动则全程静默。

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
║  🛡️  权限模式:            ADMINISTRATOR (elevated) / Standard user        ║
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

## 🔗 隧道稳定性与固定地址

隧道断链的真实根因（管道缓冲区阻塞、进程死了没人管、把边缘重连误判为隧道挂掉）
已在 v1.1.0 全部修复，并新增 `TunnelSupervisor` 守护引擎。

**地址会不会变？**

| Provider | 地址 | 稳定性 |
| :--- | :--- | :--- |
| `tailscale`（推荐，免费无需域名） | `https://<机器>.<tailnet>.ts.net` | ✅ 永久不变 |
| `ngrok` + 静态域名 | `https://<你的>.ngrok-free.app` | ✅ 永久不变 |
| `cloudflare_token` / `cloudflare_named` | 你自己的域名 | ✅ 永久不变 |
| `cloudflare_quick`（默认） | `https://随机.trycloudflare.com` | 进程活着期间不变；进程被杀才会换 |

```powershell
python -m shh tunnel --action status      # 当前地址 / provider / 重启次数 / 地址变更历史
python -m shh tunnel --action providers   # 各 provider 说明与固定地址配置命令
python -m shh start --tunnel tailscale    # 用永久固定地址启动
```

完整说明（含 Tailscale / ngrok / Cloudflare 三步配置、状态字段解释、排查顺序）：
见 **[TUNNEL_STABILITY.md](TUNNEL_STABILITY.md)**。

---

## 📦 大文件传输（分块续传）

单包大文件是隧道崩溃的另一半元凶，v1.1.0 用「客户端强制分块 + 服务端硬熔断」解决：

```python
win.upload("D:/big_dataset.zip", "C:/work/big_dataset.zip")  # 自动分块/gzip/sha256/重试/续传
win.download("C:/work/app.log", "app.log")
win.put_text("C:/work/config.json", json.dumps(cfg))
```

- 512 KiB 分块 + 逐块 gzip + 逐块 sha256 + 指数退避重试 + 断点续传 + 整文件校验
- 单块上限：JSON 256 KiB / 原生二进制 8 MiB；任意请求体 > 48 MB 直接 413 并给出对策
- 实测：20 MB 上传下载全通过；**下载途中杀掉服务进程再重启，可自动续传且 sha256 一致**
- 详细协议与实测数据：见 **[FILE_TRANSFER.md](FILE_TRANSFER.md)**

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
