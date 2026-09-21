"""
SHH 1.0 - Interactive Local Dashboard Web UI
"""

def get_dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SHH 1.0 - Smart Host Hub | AI 本地电脑控制桥梁</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;600&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0d1117;
      --card-bg: #161b22;
      --border: #30363d;
      --text: #c9d1d9;
      --heading: #f0f6fc;
      --accent: #58a6ff;
      --success: #238636;
      --success-text: #3fb950;
      --warning: #d29922;
      --danger: #f85149;
      --code-bg: #090d13;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      line-height: 1.6;
      padding: 24px;
    }
    .container { max-width: 1200px; margin: 0 auto; }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 24px;
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand h1 { font-size: 1.6rem; color: var(--heading); font-weight: 700; }
    .brand span { font-size: 0.85rem; background: #1f6feb33; color: var(--accent); padding: 3px 8px; border-radius: 6px; border: 1px solid #1f6feb66; }
    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 0.85rem;
      font-weight: 600;
      background: rgba(35, 134, 54, 0.2);
      color: var(--success-text);
      border: 1px solid var(--success);
    }
    .pulse-dot {
      width: 8px; height: 8px; border-radius: 50%; background: var(--success-text);
      animation: pulse 2s infinite;
    }
    @keyframes pulse { 0% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(1.3); } 100% { opacity: 1; transform: scale(1); } }

    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; margin-bottom: 24px; }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
    }
    .card h2 { font-size: 1.1rem; color: var(--heading); margin-bottom: 14px; display: flex; align-items: center; gap: 8px; }
    
    .info-row { display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.9rem; }
    .info-label { color: #8b949e; }
    .info-val { font-family: 'Fira Code', monospace; color: var(--heading); font-weight: 600; }
    
    .ticket-box {
      background: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      font-family: 'Fira Code', monospace;
      font-size: 0.85rem;
      word-break: break-all;
      color: var(--accent);
      margin-bottom: 12px;
      max-height: 90px;
      overflow-y: auto;
    }

    button, .btn {
      background: #238636;
      color: #fff;
      border: none;
      padding: 8px 16px;
      border-radius: 6px;
      font-weight: 600;
      cursor: pointer;
      font-size: 0.9rem;
      transition: all 0.2s;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      text-decoration: none;
    }
    button:hover, .btn:hover { background: #2ea043; }
    button.secondary, .btn.secondary { background: #21262d; border: 1px solid var(--border); color: var(--text); }
    button.secondary:hover, .btn.secondary:hover { background: #30363d; color: #fff; }

    .tabs { display: flex; gap: 8px; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
    .tab {
      padding: 10px 18px;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      color: #8b949e;
      font-weight: 600;
    }
    .tab.active { color: var(--accent); border-bottom-color: var(--accent); }

    .tab-content { display: none; }
    .tab-content.active { display: block; }

    .terminal-box {
      background: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
      font-family: 'Fira Code', monospace;
      font-size: 0.85rem;
      min-height: 240px;
      max-height: 400px;
      overflow-y: auto;
      white-space: pre-wrap;
      color: #7ee787;
      margin-bottom: 12px;
    }
    .input-group { display: flex; gap: 8px; }
    .input-group input {
      flex: 1;
      background: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 14px;
      color: var(--heading);
      font-family: 'Fira Code', monospace;
    }
    .input-group input:focus { outline: none; border-color: var(--accent); }

    .screen-preview {
      width: 100%;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: #000;
      margin-top: 12px;
      display: block;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <h1>SHH 1.0</h1>
        <span>AI Bridge & Tunnel</span>
      </div>
      <div class="status-badge">
        <div class="pulse-dot"></div>
        <span id="server-status">服务运行中 (Online)</span>
      </div>
    </header>

    <div class="grid">
      <!-- Connection Card -->
      <div class="card">
        <h2>🌐 穿透与连接状态 (Rendezvous)</h2>
        <div class="info-row">
          <span class="info-label">会话 ID:</span>
          <span class="info-val" id="session-id">加载中...</span>
        </div>
        <div class="info-row">
          <span class="info-label">动态 IPv4 / STUN:</span>
          <span class="info-val" id="pub-ipv4">检测中...</span>
        </div>
        <div class="info-row">
          <span class="info-label">动态 IPv6:</span>
          <span class="info-val" id="pub-ipv6">-</span>
        </div>
        <div class="info-row">
          <span class="info-label">HTTP / MCP 端口:</span>
          <span class="info-val" id="http-port">18888</span>
        </div>
        <div class="info-row">
          <span class="info-label">SSH 端口 / 用户:</span>
          <span class="info-val" id="ssh-info">2222 / ai-agent</span>
        </div>
        <div class="info-row">
          <span class="info-label">公共告示板 (Board):</span>
          <span class="info-val" id="board-status">就绪</span>
        </div>
      </div>

      <!-- Quick AI Ticket Card -->
      <div class="card">
        <h2>🎫 一键 AI 接入票据 (AI Prompt Ticket)</h2>
        <p style="font-size:0.85rem; color:#8b949e; margin-bottom:8px;">
          复制以下票据或 System Prompt，直接粘贴发送给云端 AI (ChatGPT / Claude / DeepSeek)，AI 即可立刻识别并接入本地：
        </p>
        <div class="ticket-box" id="ticket-text">加载中...</div>
        <div style="display:flex; gap:8px;">
          <button onclick="copyPrompt()">📋 复制 AI 系统提示词</button>
          <button class="secondary" onclick="copyTicket()">🔗 仅复制票据</button>
          <a href="/api/manifest" target="_blank" class="btn secondary">📖 查看工具大纲</a>
        </div>
      </div>
    </div>

    <!-- Interactive Workspace Tabs -->
    <div class="tabs">
      <div class="tab active" onclick="switchTab('terminal')">⚡ 终端命令测试 (Shell)</div>
      <div class="tab" onclick="switchTab('vision')">👁️ 屏幕视觉识别 (Vision)</div>
      <div class="tab" onclick="switchTab('tools')">🛠️ 已挂载工具清单 (Tools)</div>
      <div class="tab" onclick="switchTab('system')">💻 系统与网络状态 (System)</div>
    </div>

    <!-- Terminal Tab -->
    <div id="tab-terminal" class="tab-content active">
      <div class="card">
        <h2>💻 本地 Shell 交互测试</h2>
        <div class="terminal-box" id="term-output">SHH 1.0 Terminal Ready. Type a command below to execute locally on Windows.\n</div>
        <div class="input-group">
          <input type="text" id="cmd-input" placeholder="输入命令 (如 dir, git status, python --version)..." onkeydown="if(event.key==='Enter') runCommand()" />
          <button onclick="runCommand()">▶ 执行</button>
        </div>
      </div>
    </div>

    <!-- Vision Tab -->
    <div id="tab-vision" class="tab-content">
      <div class="card">
        <h2>📸 实时屏幕快照与视觉识别 (Multimodal Vision)</h2>
        <p style="font-size:0.85rem; color:#8b949e;">AI 可调用 capture_screen 获取当前桌面图像进行视觉分析与 UI 识别：</p>
        <div style="margin: 12px 0;">
          <button onclick="refreshScreenshot()">🔄 立即截屏刷新</button>
          <span id="screen-meta" style="font-size:0.85rem; color:#8b949e; margin-left:12px;"></span>
        </div>
        <img id="screen-img" class="screen-preview" src="" alt="Screen Preview" />
      </div>
    </div>

    <!-- Tools Tab -->
    <div id="tab-tools" class="tab-content">
      <div class="card">
        <h2>🛠️ 挂载的 AI 本地工具集 (Tool Catalog)</h2>
        <div id="tools-list" style="margin-top:12px;">正在加载工具列表...</div>
      </div>
    </div>

    <!-- System Tab -->
    <div id="tab-system" class="tab-content">
      <div class="card">
        <h2>📊 本机系统与硬件概况</h2>
        <div id="sys-info-box" class="terminal-box" style="color:var(--text);">正在获取硬件信息...</div>
      </div>
    </div>
  </div>

  <script>
    let currentToken = '';
    let promptContent = '';
    let currentTicket = '';

    async function loadInfo() {
      try {
        const res = await fetch('/api/info');
        const data = await res.json();
        currentToken = data.token || '';
        currentTicket = data.ticket || '';
        document.getElementById('session-id').innerText = data.session_id || '-';
        document.getElementById('pub-ipv4').innerText = data.public_ipv4 || data.lan_ip || '127.0.0.1';
        document.getElementById('pub-ipv6').innerText = data.public_ipv6 || '无 (IPv4 STUN 中继)';
        document.getElementById('http-port').innerText = data.port || 18888;
        document.getElementById('ssh-info').innerText = `${data.ssh_port || 2222} / ${data.ssh_username || 'ai-agent'}`;
        document.getElementById('ticket-text').innerText = data.ticket || 'Ticket ready';

        if (data.board_url) {
          document.getElementById('board-status').innerHTML = `<a href="${data.board_url}" target="_blank" style="color:var(--accent); text-decoration:none;">${data.board_url}</a>`;
        }
      } catch (e) {
        console.error(e);
      }
    }

    async function loadTools() {
      try {
        const res = await fetch('/api/tools');
        const data = await res.json();
        let html = '<table style="width:100%; border-collapse:collapse; font-size:0.9rem;">';
        html += '<tr style="border-bottom:1px solid var(--border); text-align:left; color:#8b949e;"><th style="padding:8px;">分类</th><th>工具名称</th><th>描述</th></tr>';
        (data.tools || []).forEach(t => {
          html += `<tr style="border-bottom:1px solid var(--border);">
            <td style="padding:8px;"><span style="background:#21262d; padding:2px 6px; border-radius:4px; font-size:0.8rem;">${t.category}</span></td>
            <td style="font-family:'Fira Code'; font-weight:600; color:var(--accent);">${t.name}</td>
            <td style="color:#c9d1d9;">${t.description}</td>
          </tr>`;
        });
        html += '</table>';
        document.getElementById('tools-list').innerHTML = html;
      } catch (e) {
        document.getElementById('tools-list').innerText = '加载工具失败';
      }
    }

    async function loadSystem() {
      try {
        const res = await fetch('/api/tools/get_system_info', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        });
        const data = await res.json();
        document.getElementById('sys-info-box').innerText = JSON.stringify(data, null, 2);
      } catch (e) {
        document.getElementById('sys-info-box').innerText = '加载系统信息失败';
      }
    }

    async function runCommand() {
      const input = document.getElementById('cmd-input');
      const cmd = input.value.trim();
      if (!cmd) return;
      
      const term = document.getElementById('term-output');
      term.innerText += `\n> ${cmd}\n`;
      input.value = '';

      try {
        const res = await fetch('/api/exec', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ command: cmd })
        });
        const data = await res.json();
        if (data.stdout) term.innerText += data.stdout;
        if (data.stderr) term.innerText += `[STDERR] ${data.stderr}\n`;
        term.innerText += `[Exit Code: ${data.exit_code}, Duration: ${data.duration_ms}ms]\n`;
        term.scrollTop = term.scrollHeight;
      } catch (err) {
        term.innerText += `[Error] ${err.message}\n`;
      }
    }

    async function refreshScreenshot() {
      const meta = document.getElementById('screen-meta');
      meta.innerText = '正在截屏并编码...';
      try {
        const res = await fetch('/api/tools/capture_screen', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ max_width: 1280, quality: 75 })
        });
        const data = await res.json();
        if (data.image_data_uri) {
          document.getElementById('screen-img').src = data.image_data_uri;
          meta.innerText = `分辨率: ${data.width}x${data.height} | 大小: ${data.file_size_kb} KB`;
        }
      } catch (e) {
        meta.innerText = '截屏失败';
      }
    }

    function switchTab(name) {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById('tab-' + name).classList.add('active');
      if (name === 'vision') refreshScreenshot();
      if (name === 'system') loadSystem();
    }

    async function copyPrompt() {
      try {
        const res = await fetch('/api/manifest?type=prompt');
        const text = await res.text();
        await navigator.clipboard.writeText(text);
        alert('✔ AI 系统提示词已复制到剪贴板！直接粘贴发送给云端 AI 即可。');
      } catch (e) {
        alert('复制失败，请直接在页面查看。');
      }
    }

    async function copyTicket() {
      try {
        await navigator.clipboard.writeText(currentTicket);
        alert('✔ 连接票据已复制到剪贴板！');
      } catch (e) {
        alert('复制失败。');
      }
    }

    loadInfo();
    loadTools();
  </script>
</body>
</html>
"""
