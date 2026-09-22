# SHH 1.0 大文件传输：分块 + 续传 + 校验

> 结论先说：**大文件必须分块传。**

---

## 一、为什么大包会把隧道搞崩

一次请求里塞进整个文件（尤其是 base64 放进 JSON，体积还会膨胀 33%）会造成：

| 现象 | 原因 |
| :--- | :--- |
| 上传到一半隧道断掉 | 隧道/边缘对单请求体积与时长有硬限制（Cloudflare 免费版 100 MB / 100 秒），超时即 524/重置 |
| 断掉后整个文件白传 | 单包传输没有断点，只能从头再来 |
| SHH 进程内存暴涨甚至被杀 | uvicorn 需要把整个请求体读进内存；base64 再翻倍 |
| 断链后连接池被污染 | 半截的 TCP 会话残留在隧道里，后续请求一起受影响 |

所以 v1.1.0 把「大包」从物理上变成不可能：**服务端硬熔断 + 客户端强制分块**。

---

## 二、安全上限（服务端强制）

| 项目 | 默认值 | 配置键 | 说明 |
| :--- | :--- | :--- | :--- |
| JSON/base64 单块 | 256 KiB | `max_chunk_bytes` | `file_upload_chunk` / `file_download_chunk` |
| 单块绝对上限 | 4 MiB | 硬编码 `HARD_MAX_CHUNK_BYTES` | 超过直接报错并给出对策 |
| 原生二进制单块 | 8 MiB | `max_raw_chunk_bytes` | `/api/transfer/upload` |
| 任意请求体上限 | 48 MB | `max_request_mb` | 超过返回 HTTP 413 + 处理建议 |
| 客户端默认分块 | 512 KiB | — | 客户端自动使用，可调 |

查看当前生效值：

```powershell
python -m shh transfer                  # 打印全部限制
python -m shh transfer --path D:\big.iso  # 针对具体文件给出分块方案
```

或者让云端 AI 调：`file_transfer_info` 工具 / `GET /api/transfer/info`。

---

## 三、云端 AI 怎么用（推荐写法，已内置于一键消息）

```python
win = RemoteWindows("https://xxx.trycloudflare.com", "<TOKEN>")

# 上传：自动分块 + gzip + 每块 sha256 + 失败重试 + 断点续传
win.upload("D:/big_dataset.zip", "C:/work/big_dataset.zip")   # 20 GB 也没问题

# 下载
win.download("C:/work/logs/app.log", "app.log")

# 小文本（同样自动分块）
win.put_text("C:/work/config.json", json.dumps(cfg))
print(win.get_text("C:/work/app.log"))
```

特性：
- **分块 512 KiB**，每块独立 gzip（文本类通常省 3-5 倍流量）
- **每块 sha256 校验**（服务端逐块核对，损坏自动重传该块）
- **失败自动重试**：指数退避 1.5s → 20s，最多 6 次；网络类错误才重试，参数类错误立刻报错
- **断点续传**：续传时先 `file_stat` 取服务端已有大小，从该 offset 继续；下载则从本地文件大小继续
- **整文件校验**：结束时对比两端 sha256（`sha256_match: true`）

---

## 四、底层 HTTP 协议（自己写客户端时看这里）

### 上传（原生二进制，最快）

```
POST /api/transfer/upload
X-SHH-Path: <URL 编码后的绝对路径>
X-SHH-Offset: <本块起始字节偏移>
X-SHH-Truncate: 1        # 仅在 offset=0 时发送，表示覆盖写入
X-SHH-Compress: gzip     # 可选：请求体是 gzip 压缩的
X-SHH-Sha256: <原始（压缩前）数据的 sha256>
X-SHH-Token: <token>
Content-Type: application/octet-stream

<原始字节 / gzip 字节>
```

响应：

```json
{ "success": true, "offset": 524288, "bytes_written": 524288,
  "next_offset": 1048576, "file_size": 1048576, "sha256_chunk": "..." }
```

### 下载（原生二进制，支持 gzip）

```
GET /api/transfer/download?path=<URL编码路径>&offset=<n>&length=<≤8MiB>&compress=gzip
```

响应头：

| 头 | 含义 |
| :--- | :--- |
| `X-SHH-Offset` | 本块起始偏移 |
| `X-SHH-Next-Offset` | 下一块偏移 |
| `X-SHH-Total-Size` | 文件总大小 |
| `X-SHH-Eof` | `1` = 已到文件末尾，可以停止循环 |
| `X-SHH-Sha256` | **解压后**本块的 sha256（客户端按此校验） |
| `X-SHH-Compressed` | `1` = 响应体是 gzip |

> ⚠️ HTTP 头名大小写不敏感（Starlette 会小写化）。客户端请统一转小写后查表 —— 
> 这正是 v1.1.0 修掉的一个真实 bug：大写查表取不到 `X-SHH-Compressed`，
> 结果把 gzip 字节当原始数据写盘，每 512 KiB 多出约 178 字节。

### 工具版（JSON，适合小文件或不想写原生 HTTP 时）

- `file_stat(path)` → `size_bytes`（**续传的锚点**）
- `file_upload_chunk(path, offset, data_base64|data_text, compress, truncate, sha256_chunk)`
- `file_download_chunk(path, offset, max_bytes, as_text, compress)`
- `file_checksum(path)` → `sha256` / `md5`
- `file_transfer_info()` → 当前策略与上限

### 健康检查

```
GET /api/health      # 隧道地址、固定地址与否、重连状态、工具数量
```

---

## 五、断链了怎么办

| 场景 | 正确做法 |
| :--- | :--- |
| 传输中途报错/超时 | **什么都不用改**，重新调用 `upload()` / `download()`，会从断点继续 |
| 反复在同一 offset 失败 | 该块太大或网络抖动太严重 → 把 `chunk_size` 降到 128 KiB 再试 |
| 服务端返回 413 | 单块超限 → 减小 `chunk_size`（错误信息里已给出建议） |
| 服务端返回 409 + `retry: true` | 该块 sha256 不匹配 → 重传同一 offset 即可 |
| 隧道健康检查显示 `reconnecting` | 等 10-30 秒重试；地址不会变，**不要**重启 SHH |

---

## 六、实测数据（v1.1.0，本机回环）

| 场景 | 结果 |
| :--- | :--- |
| 20 MB 上传（512 KiB 分块 + gzip） | sha256 两端一致 ✅ |
| 上传过程中注入 2 次连接重置 | 自动重试，最终文件完整 ✅ |
| 20 MB 下载 | 3,145,728 → 20,971,520 字节逐块校验通过 ✅ |
| **下载中真的杀掉服务进程再重启** | 已落盘 3 MB → 续传完成，sha256 一致 ✅ |
| 单次 50 MB 大包 | 被拒绝（413 / 连接提前断开），**服务仍然健康** ✅ |
| 管道阻塞回归测试（160 KB 日志洪流） | 隧道进程不再卡死 ✅ |
