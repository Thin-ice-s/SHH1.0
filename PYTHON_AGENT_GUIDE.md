# 🐍 云端 AI (支持 Python 执行) 本地电脑控制指南

> **适用场景**：您的云端 AI 拥有 Python 代码执行环境（如 ChatGPT Code Interpreter、Claude Artifacts / Python Sandbox、自定义 Python Agent、LangChain、AutoGen、Jupyter Notebook 等）。

只需将以下提示词与 Python 代码模板直接复制并发送给您的云端 AI，AI 在其云端沙箱中执行 Python 代码，即可直接穿透控制您的本地 Windows 电脑！

---

## 📋 给云端 AI 的一键引导提示词 (直接复制发给 AI)

```markdown
你好！你已被授权通过 SHH 1.0 桥梁连接并控制我的本地 Windows 电脑。请在你的 Python 环境中运行以下代码来连接我的电脑，并开始执行后续开发与调试任务：

```python
# ========================================================
# 🤖 SHH 1.0 - Remote Windows Python Controller (Zero Dep)
# ========================================================
import urllib.request, urllib.parse, json, base64, ssl, time

class RemoteWindows:
    def __init__(self, base_url, token=None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE

    @classmethod
    def connect(cls, ticket_or_url):
        target = ticket_or_url.strip()
        if target.startswith("shh://"):
            raw_b64 = target[6:]
            padding = 4 - (len(raw_b64) % 4)
            if padding != 4: raw_b64 += "=" * padding
            data = json.loads(base64.urlsafe_b64decode(raw_b64.encode("utf-8")).decode("utf-8"))
            return cls._from_meta(data)
        if target.startswith("http://") or target.startswith("https://"):
            if "dpaste.org" in target and not target.endswith(".txt"): target = f"{target}.txt"
            req = urllib.request.Request(target, headers={"User-Agent": "SHH-AI/1.0"})
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                text = resp.read().decode("utf-8")
                try: data = json.loads(text)
                except:
                    for line in text.splitlines():
                        if "shh://" in line: return cls.connect(line[line.find("shh://"):].strip())
                    raise ValueError("Parse failed")
                return cls._from_meta(data)
        return cls(base_url=target)

    @classmethod
    def _from_meta(cls, meta):
        token = meta.get("token")
        endpoints = meta.get("endpoints", {})
        ipv4 = endpoints.get("ipv4") or meta.get("public_ipv4")
        ipv6 = endpoints.get("ipv6") or meta.get("public_ipv6")
        lan_ip = endpoints.get("lan_ip") or meta.get("lan_ip", "127.0.0.1")
        port = endpoints.get("http_port") or meta.get("port", 18888)
        base_url = meta.get("http_base_url") or f"http://{ipv4 or (f'[{ipv6}]' if ipv6 else lan_ip)}:{port}"
        return cls(base_url=base_url, token=token)

    def _call(self, endpoint, payload=None, timeout=60.0):
        url = f"{self.base_url}{endpoint}"
        headers = {"User-Agent": "SHH-AI/1.0", "Content-Type": "application/json"}
        if self.token: headers["Authorization"] = f"Bearer {self.token}"
        is_post = endpoint.startswith("/api/tools") or endpoint.startswith("/api/exec") or payload is not None
        body = payload if payload is not None else ({} if is_post else None)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if is_post else "GET")
        with urllib.request.urlopen(req, timeout=timeout, context=self._ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def exec(self, cmd, cwd=None, shell="auto", timeout=60):
        res = self._call("/api/exec", {"command": cmd, "cwd": cwd, "shell": shell, "timeout": timeout}, timeout+5)
        return res.get("stdout") if res.get("success") else f"[Error]: {res.get('stderr')}"

    def read_file(self, path, start_line=None, max_lines=None):
        return self._call("/api/tools/file_read", {"path": path, "start_line": start_line, "max_lines": max_lines}).get("content", "")

    def write_file(self, path, content):
        return self._call("/api/tools/file_write", {"path": path, "content": content}).get("success", False)

    def edit_file(self, path, old_text, new_text):
        return self._call("/api/tools/file_edit", {"path": path, "old_text": old_text, "new_text": new_text}).get("success", False)

    def list_dir(self, path=None):
        return self._call("/api/tools/file_list", {"path": path}).get("items", [])

    def file_tree(self, path=None, max_depth=3):
        return self._call("/api/tools/file_tree", {"path": path, "max_depth": max_depth}).get("tree_view", "")

    def screenshot(self, save_path="screenshot.jpg", max_width=1280):
        res = self._call("/api/tools/capture_screen", {"max_width": max_width, "quality": 75, "return_base64": True})
        b64 = res["image_data_uri"].split(",", 1)[1]
        data = base64.b64decode(b64)
        if save_path:
            with open(save_path, "wb") as f: f.write(data)
        return data

    def list_ports(self):
        return self._call("/api/tools/list_open_ports").get("open_ports", [])

    def proxy_http(self, url, method="GET", headers=None, body=None):
        return self._call("/api/tools/proxy_http_request", {"url": url, "method": method, "headers": headers, "body": body})

    def get_system_info(self):
        return self._call("/api/tools/get_system_info")


# === 1. 初始化连接 (将下方的 URL 替换为你在本地控制台看到的 公共告示板 URL 或 票据) ===
win = RemoteWindows.connect("https://dpaste.org/xxxx.txt")  # 或 win = RemoteWindows.connect("shh://...")

# === 2. 验证连接并查看系统状态 ===
print(win.get_system_info())

# === 3. 执行 Windows 命令 ===
print(win.exec("dir"))
```
```

---

## 💡 常见开发交互场景示例代码

### 1. 查看本地项目目录树与读取文件
```python
# 获取目录树
print(win.file_tree("D:/my_project", max_depth=3))

# 读取指定文件内容
code = win.read_file("D:/my_project/src/index.js")
print(code)
```

### 2. 生成代码并写入本地文件
```python
new_code = """
import express from 'express';
const app = express();
app.get('/api/health', (req, res) => res.json({ status: 'ok' }));
app.listen(3000, () => console.log('Server running on 3000'));
"""
win.write_file("D:/my_project/src/server.js", new_code)
```

### 3. 在本地运行命令并测试接口
```python
# 运行安装依赖或测试
print(win.exec("npm test", cwd="D:/my_project"))

# 启动本地服务并通过 proxy_http 调试内部接口
print(win.exec("python -m http.server 8080", cwd="D:/my_project"))
resp = win.proxy_http("http://localhost:8080")
print("Response status:", resp.get("status_code"))
```

### 4. 截取屏幕让 AI 视觉模型分析报错与 UI
```python
# 截取屏幕并保存到云端沙箱本地，AI 即可直接查看分析
win.screenshot("desktop_error.jpg", max_width=1280)
```
