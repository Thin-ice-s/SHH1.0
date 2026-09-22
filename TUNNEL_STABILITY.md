# SHH 1.0 隧道稳定性与固定地址指南

你的两个问题——**隧道经常断链**、**地址老变**——在 v1.1.0 里已经分开处理：

1. **断链**：是真实 bug，已修复（根因见下）。
2. **地址会变**：这不是 bug，而是「免费随机域名隧道」的固有机制。要**地址永不变**，必须用支持固定地址的通道（Tailscale / ngrok 静态域名 / Cloudflare 具名隧道）。三条路都免费、都不需要你自己的服务器。

---

## 一、断链的真正根因（已修复）

### 1. 管道缓冲区阻塞 —— 这是最大的元凶

旧代码用 `subprocess.PIPE` 抓 cloudflared 输出，**读到一行 URL 就不再读了**。
操作系统管道缓冲区只有 64 KB，cloudflared 日志写满 64 KB 后 `write()` 就会**永久阻塞**，
进程卡死、看起来就是「隧道突然没了」。

v1.1.0：`TunnelSupervisor` 用**常驻读取线程持续排空管道**（stdout+stderr 合并），
并把日志环形缓存（最多 400 行）供排障使用。
回归测试 `tests/test_tunnel_supervisor.py::test_supervisor_captures_url_and_drains_pipes`
会故意灌 160 KB 日志，验证进程不会卡死。

### 2. 进程死了没人管

旧代码拿到 URL 后就不再看那个进程，进程退出后隧道静默失效。

v1.1.0：守护线程每 3 秒检查一次进程；进程真的死了才重启，
并且**用同一个 provider、同一套参数**重启，重启采用指数退避（2s → 60s 封顶）。

### 3. 把「边缘重连」误当成「隧道挂了」

Cloudflare / ngrok 边缘会周期性重连，这是**正常现象**，cloudflared 会自己重连、
**域名完全不变**。旧逻辑一重试就可能换进程 → 换地址。

v1.1.0：区分两种状态：

| 状态 | 判定 | 动作 |
| :--- | :--- | :--- |
| 边缘重连 | 进程存活 + 健康探测失败 < 6 次 | **什么都不做**，只打印 `reconnecting`，地址保持不变 |
| 进程死亡 | `proc.poll() is not None` | 同 provider 重启；只有此时随机域名才可能变化，且会**写日志+改 `SEND_TO_AI.md`+弹告警**，绝不静默换地址 |
| 固定地址 provider 暂时不可达 | 进程存活 + `fixed=True` | **永不重启**（重启只会白等，地址本来就不会变） |

### 4. 空闲连接被掐

隧道/运营商对空闲 HTTP 连接有超时（常见 100 秒）。现在：
- uvicorn `timeout_keep_alive=65`（在我们这一侧先干净关闭，避免被 RST），
- 守护线程每 30 秒对**公网地址**做一次 `/api/health` 保活探测（同时验证端到端可用性），
- WebSocket 空闲 20 秒自动发心跳。

### 5. 大包把隧道打爆

单个超大请求（尤其是 base64 塞进 JSON）会导致边缘超时/重置、内存暴涨。
现在服务端有**硬熔断**：超过 `max_request_mb`（默认 48 MB）直接拒绝并提示改用分块，
单块上限 256 KiB（JSON）/ 8 MiB（原生二进制）。
详见 [`FILE_TRANSFER.md`](FILE_TRANSFER.md)。

---

## 二、地址会不会变？一张表说清楚

| Provider | 地址形态 | 地址稳定性 | 需要什么 |
| :--- | :--- | :--- | :--- |
| `tailscale` | `https://<机器名>.<你的tailnet>.ts.net` | ✅ **永久不变** | 免费 Tailscale 账号（无需域名） |
| `ngrok` | `https://<你设的>.ngrok-free.app` | ✅ **永久不变** | 免费 ngrok 账号 + 1 个静态域名 |
| `cloudflare_token` | 你在 CF 控制台配的域名 | ✅ **永久不变** | Cloudflare 账号 + 一个域名（可买最便宜域名） |
| `cloudflare_named` | 同上 | ✅ **永久不变** | 同上 |
| `cloudflare_quick` | `https://随机词.trycloudflare.com` | ⚠️ 进程活着期间不变；进程被杀则换新域名 | 无（默认，开箱即用） |
| `ssh_localhostrun` / `pinggy` | `https://随机词.lhr.life` 等 | ⚠️ 同上 | 无 |

**结论**：
- 想「地址永不变、持续工作」→ 用 **Tailscale Funnel**（最省事，不要域名）。
- 只想开箱即用 → 默认 `cloudflare_quick`；进程不退出地址就不会变，我们的守护进程不会主动重启它。

---

## 三、配置固定地址（三选一）

### 方案 A：Tailscale Funnel（推荐，免费、无需域名）

```powershell
# 1. 安装 Tailscale 并登录（免费账号）
winget install tailscale.tailscale
tailscale up

# 2. 开一条永久隧道（18888 换成你的 SHH 端口）
tailscale funnel --bg 18888

# 3. 看地址（形如 https://mypc.tailxxxx.ts.net）
tailscale funnel status
```

然后启动 SHH：

```powershell
python -m shh start --tunnel tailscale
```

这个 `https://mypc.tailxxxx.ts.net` **永远不变**，重启电脑、重启 SHH 都一样。

### 方案 B：ngrok 静态域名（免费账号，需在面板领 1 个静态域名）

```powershell
ngrok config add-authtoken <你的_AUTHTOKEN>
# 在 ngrok 控制台 Domains 页面领取一个静态域名，例如 my-bridge.ngrok-free.app

python -m shh start --tunnel ngrok --tunnel-domain my-bridge.ngrok-free.app --ngrok-token <你的_AUTHTOKEN>
```

### 方案 C：Cloudflare 具名隧道（有域名时最稳）

```powershell
cloudflared tunnel login
cloudflared tunnel create shh-bridge
cloudflared tunnel route dns shh-bridge bridge.你的域名.com
```

两种接法（任选）：

```powershell
# C1. 用 connector token（Zero Trust 面板 -> Networks -> Tunnels -> 创建 -> 复制 token）
python -m shh start --tunnel cloudflare_token --cloudflare-token <TOKEN> --tunnel-domain bridge.你的域名.com

# C2. 用本地凭据 + 隧道名
python -m shh start --tunnel cloudflare_named --cloudflare-tunnel shh-bridge --tunnel-domain bridge.你的域名.com
```

> 也可以把这些写进 `shh_config.json`（同名键：`tunnel_provider` / `tunnel_fixed_domain` /
> `cloudflare_tunnel_token` / `ngrok_authtoken` / `cloudflare_tunnel_name`），以后直接 `python -m shh start`。

---

## 四、随时自查

```powershell
python -m shh tunnel --action status     # 当前地址、provider、重启次数、地址变更历史
python -m shh tunnel --action providers  # 所有 provider 说明与固定地址配置命令
```

运行中也可以问你的云端 AI：

```python
win.tunnel_status()
# {'provider': 'tailscale', 'url': 'https://mypc.tailxxx.ts.net', 'fixed': True,
#  'friendly': 'online', 'address_stable': True, 'reconnects': ...}
```

或者直接访问 `https://<你的地址>/api/health`。

### 状态字段含义

| 字段 | 含义 |
| :--- | :--- |
| `friendly` | `online` / `reconnecting (URL unchanged)` / `restarting` |
| `fixed` | 该 provider 的地址是否永久固定 |
| `address_stable` | 到目前为止是否从未换过地址 |
| `restarts` | 进程死亡后自动重启的次数 |
| `address_changes` | 地址真实变更的次数（正常应为 0） |
| `history` | 每次地址变更的时间戳、旧地址、新地址 |

文件落地位置：
- `.shh_tunnel_state.json` —— 当前地址、provider、重启次数等快照
- `TUNNEL_ADDRESS_CHANGED.txt` —— **只**在地址真的变了时追加记录（附原因与对策）

---

## 五、还是不通？按这个顺序排查

1. `python -m shh tunnel --action status` 看 `alive` 是否为 `true`。
2. 浏览器/手机流量打开 `https://<你的地址>/api/health`：
   - 返回 JSON → 隧道没问题，问题在你的云端运行环境能否访问该域名（有些沙箱只放行白名单域名）。
   - `530 / 1033` → cloudflared 没连上边缘：检查代理/防火墙是否拦了出站 `7844/TCP`、`443`。
3. 看终端里 `[tunnel] ...` 日志尾部（守护进程会在进程死亡时自动打印最后 8 行）。
4. 网络环境有 SNI 过滤/DNS 污染时，改用 `SHH_CF_PROTOCOL=http2`（默认已是 http2）或换
   `--tunnel tailscale`。
5. 大文件传输中断：这是分块机制在起作用，重试即可（会自动续传），见 `FILE_TRANSFER.md`。
