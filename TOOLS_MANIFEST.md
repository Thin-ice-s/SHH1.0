# 🛠️ SHH 1.0 - 本地电脑 AI 控制工具大纲 (Tool Manifest)

> 本文档定义了云端 AI 可调用的本地 Windows 电脑全套开发与控制工具。AI 可通过 REST API、MCP 协议或 WebSocket 直接调用以下工具。

## 📑 工具分类概览

| 分类 | 工具名称 | 功能说明 |
| :--- | :--- | :--- |
| `shell` | **`shell_exec`** | Execute a command in PowerShell, CMD, Bash, or WSL on the local Windows computer and return stdout, stderr, exit code. |
| `file` | **`file_read`** | Read file content from local disk. Supports text with line numbers/ranges or base64 binary encoding. |
| `file` | **`file_write`** | Create or overwrite a file with given text or base64 binary content. Creates parent folders automatically. |
| `file` | **`file_edit`** | Search and replace a specific text block within a file (exact or whitespace-tolerant match). |
| `file` | **`file_list`** | List files and directories inside a path with size, modified timestamp, and type. |
| `file` | **`file_tree`** | Generate a formatted visual tree structure of a directory with depth limit and ignored patterns. |
| `file` | **`file_search`** | Search for files by filename pattern (glob) or search file contents with regex grep. |
| `process` | **`list_processes`** | List active system processes with PID, name, CPU %, memory usage, and command line. |
| `process` | **`kill_process`** | Terminate a running process by PID or process name. |
| `process` | **`start_process`** | Start a persistent background process (e.g. dev server, npm run dev, python app.py) and return a job_id to monitor. |
| `process` | **`get_process_logs`** | Get status or active background jobs list. |
| `network` | **`list_open_ports`** | List all active TCP listening ports and the processes bound to them on the local computer. |
| `network` | **`proxy_http_request`** | Make an HTTP request from inside the local machine to a local dev server (e.g. http://localhost:3000/api) and return the response. |
| `vision` | **`capture_screen`** | Capture the desktop screen, compress/downscale to save tokens, and return as base64 image for multimodal AI vision models (GPT-4o, Claude 3.5 Sonnet, Gemini). |
| `vision` | **`get_screen_info`** | Get information about display resolution, open application windows, and UI element positions. |
| `system` | **`show_popup`** | Display a native Windows popup dialog / message box on the user's screen. |
| `system` | **`get_system_info`** | Retrieve comprehensive system hardware, OS version, CPU, RAM, disk space, and network info. |
| `system` | **`get_env_vars`** | Get system environment variables or query a specific environment variable. |
| `admin` | **`get_privilege_info`** | Check whether the local SHH agent currently runs with Windows Administrator (UAC elevated) rights, and which operations are available without a UAC prompt. |
| `admin` | **`run_admin_command`** | Execute a shell command with Windows Administrator rights (e.g. netsh, sc, reg, mklink, driver/service management, writing to C:\Program Files, killing system processes). If SHH was started with start_shh_admin.bat it runs silently; otherwise ONE UAC prompt appears on the user's screen and must be approved. |
| `admin` | **`manage_firewall`** | Add / delete / list Windows Firewall inbound rules with administrator rights (allow a local port so other machines or tunnels can reach it). |
| `admin` | **`manage_port_forward`** | Create / delete / list OS-level TCP port forwarding rules (netsh interface portproxy) so traffic arriving on a local port is forwarded to another local or LAN host:port. Requires Administrator. |

---

## 🔧 详细工具规范与参数说明

### `shell_exec`
**功能描述**: Execute a command in PowerShell, CMD, Bash, or WSL on the local Windows computer and return stdout, stderr, exit code.  
**所属分类**: `shell`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "command": {
      "type": "string",
      "description": "The command string to execute (e.g. 'dir', 'npm test', 'git status', 'python main.py')."
    },
    "cwd": {
      "type": "string",
      "description": "Working directory to execute command in. Defaults to current workspace."
    },
    "shell": {
      "type": "string",
      "enum": [
        "powershell",
        "cmd",
        "bash",
        "wsl",
        "auto"
      ],
      "default": "auto",
      "description": "Shell type to execute in. 'powershell' (PowerShell), 'cmd' (Windows CMD), 'bash' (Git Bash / Linux bash), 'wsl' (WSL2), or 'auto'."
    },
    "timeout": {
      "type": "integer",
      "default": 60,
      "description": "Maximum execution time in seconds before terminating the process (default 60s)."
    }
  },
  "required": [
    "command"
  ]
}
```

**调用示例 (HTTP POST /api/tools/shell_exec)**:
```json
{
  "command": "git status",
  "cwd": "example_value",
  "shell": "auto",
  "timeout": 60
}
```

---

### `file_read`
**功能描述**: Read file content from local disk. Supports text with line numbers/ranges or base64 binary encoding.  
**所属分类**: `file`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "Path to file (absolute or relative to workspace)."
    },
    "start_line": {
      "type": "integer",
      "description": "1-based starting line number (optional, for pagination)."
    },
    "max_lines": {
      "type": "integer",
      "description": "Maximum number of lines to return (optional)."
    },
    "encoding": {
      "type": "string",
      "default": "utf-8",
      "description": "File encoding ('utf-8', 'gbk', 'binary'). If 'binary', returns base64 string."
    }
  },
  "required": [
    "path"
  ]
}
```

**调用示例 (HTTP POST /api/tools/file_read)**:
```json
{
  "path": "C:\\projects\\demo\\app.py",
  "start_line": 10,
  "max_lines": 10,
  "encoding": "utf-8"
}
```

---

### `file_write`
**功能描述**: Create or overwrite a file with given text or base64 binary content. Creates parent folders automatically.  
**所属分类**: `file`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "Path to file (absolute or relative to workspace)."
    },
    "content": {
      "type": "string",
      "description": "Text content to write to the file."
    },
    "content_base64": {
      "type": "string",
      "description": "Optional base64 binary data if writing binary file."
    },
    "encoding": {
      "type": "string",
      "default": "utf-8",
      "description": "Text encoding to write (default: utf-8)."
    }
  },
  "required": [
    "path"
  ]
}
```

**调用示例 (HTTP POST /api/tools/file_write)**:
```json
{
  "path": "C:\\projects\\demo\\app.py",
  "content": "example_value",
  "content_base64": "example_value",
  "encoding": "utf-8"
}
```

---

### `file_edit`
**功能描述**: Search and replace a specific text block within a file (exact or whitespace-tolerant match).  
**所属分类**: `file`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "Target file path."
    },
    "old_text": {
      "type": "string",
      "description": "Text snippet to find and replace."
    },
    "new_text": {
      "type": "string",
      "description": "Replacement text snippet."
    }
  },
  "required": [
    "path",
    "old_text",
    "new_text"
  ]
}
```

**调用示例 (HTTP POST /api/tools/file_edit)**:
```json
{
  "path": "C:\\projects\\demo\\app.py",
  "old_text": "example_value",
  "new_text": "example_value"
}
```

---

### `file_list`
**功能描述**: List files and directories inside a path with size, modified timestamp, and type.  
**所属分类**: `file`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "Directory path (defaults to current workspace)."
    },
    "show_hidden": {
      "type": "boolean",
      "default": false,
      "description": "Whether to include hidden files (starting with .)."
    }
  }
}
```

**调用示例 (HTTP POST /api/tools/file_list)**:
```json
{
  "path": "C:\\projects\\demo\\app.py",
  "show_hidden": false
}
```

---

### `file_tree`
**功能描述**: Generate a formatted visual tree structure of a directory with depth limit and ignored patterns.  
**所属分类**: `file`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "Root directory path."
    },
    "max_depth": {
      "type": "integer",
      "default": 3,
      "description": "Maximum directory traversal depth (default: 3)."
    }
  }
}
```

**调用示例 (HTTP POST /api/tools/file_tree)**:
```json
{
  "path": "C:\\projects\\demo\\app.py",
  "max_depth": 3
}
```

---

### `file_search`
**功能描述**: Search for files by filename pattern (glob) or search file contents with regex grep.  
**所属分类**: `file`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "Directory to search within."
    },
    "filename_pattern": {
      "type": "string",
      "description": "Glob pattern for filename (e.g. '*.py', '*.json', 'config.*')."
    },
    "content_regex": {
      "type": "string",
      "description": "Regex pattern to grep file contents for."
    },
    "max_results": {
      "type": "integer",
      "default": 50,
      "description": "Maximum number of search results to return."
    }
  }
}
```

**调用示例 (HTTP POST /api/tools/file_search)**:
```json
{
  "path": "C:\\projects\\demo\\app.py",
  "filename_pattern": "example_value",
  "content_regex": "example_value",
  "max_results": 50
}
```

---

### `list_processes`
**功能描述**: List active system processes with PID, name, CPU %, memory usage, and command line.  
**所属分类**: `process`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "name_filter": {
      "type": "string",
      "description": "Optional filter string to match against process name or cmdline (e.g. 'node', 'python', 'chrome')."
    },
    "limit": {
      "type": "integer",
      "default": 30,
      "description": "Maximum number of processes to return (sorted by memory usage)."
    }
  }
}
```

**调用示例 (HTTP POST /api/tools/list_processes)**:
```json
{
  "name_filter": "example_value",
  "limit": 30
}
```

---

### `kill_process`
**功能描述**: Terminate a running process by PID or process name.  
**所属分类**: `process`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "pid": {
      "type": "integer",
      "description": "Process ID to terminate."
    },
    "name": {
      "type": "string",
      "description": "Process name to terminate all matching instances (e.g. 'node.exe')."
    },
    "force": {
      "type": "boolean",
      "default": true,
      "description": "Whether to forcefully kill the process (SIGKILL / taskkill /F)."
    }
  }
}
```

**调用示例 (HTTP POST /api/tools/kill_process)**:
```json
{
  "pid": 10,
  "name": "example_value",
  "force": true
}
```

---

### `start_process`
**功能描述**: Start a persistent background process (e.g. dev server, npm run dev, python app.py) and return a job_id to monitor.  
**所属分类**: `process`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "command": {
      "type": "string",
      "description": "Command to run in background."
    },
    "cwd": {
      "type": "string",
      "description": "Working directory for the process."
    }
  },
  "required": [
    "command"
  ]
}
```

**调用示例 (HTTP POST /api/tools/start_process)**:
```json
{
  "command": "git status",
  "cwd": "example_value"
}
```

---

### `get_process_logs`
**功能描述**: Get status or active background jobs list.  
**所属分类**: `process`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "job_id": {
      "type": "string",
      "description": "Job ID (e.g. 'job-001'). Omit to list all background jobs."
    }
  }
}
```

**调用示例 (HTTP POST /api/tools/get_process_logs)**:
```json
{
  "job_id": "example_value"
}
```

---

### `list_open_ports`
**功能描述**: List all active TCP listening ports and the processes bound to them on the local computer.  
**所属分类**: `network`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {}
}
```

**调用示例 (HTTP POST /api/tools/list_open_ports)**:
```json
{}
```

---

### `proxy_http_request`
**功能描述**: Make an HTTP request from inside the local machine to a local dev server (e.g. http://localhost:3000/api) and return the response.  
**所属分类**: `network`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "url": {
      "type": "string",
      "description": "Target URL (e.g. 'http://localhost:3000/api/users', 'http://127.0.0.1:8000/docs')."
    },
    "method": {
      "type": "string",
      "enum": [
        "GET",
        "POST",
        "PUT",
        "DELETE",
        "PATCH",
        "HEAD"
      ],
      "default": "GET",
      "description": "HTTP Method."
    },
    "headers": {
      "type": "object",
      "description": "Optional HTTP request headers dictionary."
    },
    "body": {
      "type": "string",
      "description": "Optional request body string (JSON/text)."
    },
    "timeout": {
      "type": "integer",
      "default": 10,
      "description": "Request timeout in seconds."
    }
  },
  "required": [
    "url"
  ]
}
```

**调用示例 (HTTP POST /api/tools/proxy_http_request)**:
```json
{
  "url": "http://localhost:3000",
  "method": "GET",
  "body": "example_value",
  "timeout": 10
}
```

---

### `capture_screen`
**功能描述**: Capture the desktop screen, compress/downscale to save tokens, and return as base64 image for multimodal AI vision models (GPT-4o, Claude 3.5 Sonnet, Gemini).  
**所属分类**: `vision`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "max_width": {
      "type": "integer",
      "default": 1280,
      "description": "Maximum width in pixels for downscaling (preserves aspect ratio, reduces AI token consumption). Set 0 for native resolution."
    },
    "quality": {
      "type": "integer",
      "default": 75,
      "description": "JPEG compression quality (1-100, default: 75)."
    },
    "save_path": {
      "type": "string",
      "description": "Optional file path to save the screenshot on disk (e.g. 'screenshot.jpg')."
    },
    "return_base64": {
      "type": "boolean",
      "default": true,
      "description": "Whether to return the base64 data URL in the response (default: True)."
    }
  }
}
```

**调用示例 (HTTP POST /api/tools/capture_screen)**:
```json
{
  "max_width": 1280,
  "quality": 75,
  "save_path": "C:\\projects\\demo\\app.py",
  "return_base64": true
}
```

---

### `get_screen_info`
**功能描述**: Get information about display resolution, open application windows, and UI element positions.  
**所属分类**: `vision`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {}
}
```

**调用示例 (HTTP POST /api/tools/get_screen_info)**:
```json
{}
```

---

### `show_popup`
**功能描述**: Display a native Windows popup dialog / message box on the user's screen.  
**所属分类**: `system`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "title": {
      "type": "string",
      "default": "AI Notification",
      "description": "Title of the popup window."
    },
    "message": {
      "type": "string",
      "description": "Message text to display in the popup."
    }
  },
  "required": [
    "message"
  ]
}
```

**调用示例 (HTTP POST /api/tools/show_popup)**:
```json
{
  "title": "AI Notification",
  "message": "example_value"
}
```

---

### `get_system_info`
**功能描述**: Retrieve comprehensive system hardware, OS version, CPU, RAM, disk space, and network info.  
**所属分类**: `system`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {}
}
```

**调用示例 (HTTP POST /api/tools/get_system_info)**:
```json
{}
```

---

### `get_env_vars`
**功能描述**: Get system environment variables or query a specific environment variable.  
**所属分类**: `system`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "key": {
      "type": "string",
      "description": "Specific environment variable name to query (e.g. 'PATH', 'PYTHONPATH', 'USER'). Omit for all safe variables."
    }
  }
}
```

**调用示例 (HTTP POST /api/tools/get_env_vars)**:
```json
{
  "key": "example_value"
}
```

---

### `get_privilege_info`
**功能描述**: Check whether the local SHH agent currently runs with Windows Administrator (UAC elevated) rights, and which operations are available without a UAC prompt.  
**所属分类**: `admin`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {}
}
```

**调用示例 (HTTP POST /api/tools/get_privilege_info)**:
```json
{}
```

---

### `run_admin_command`
**功能描述**: Execute a shell command with Windows Administrator rights (e.g. netsh, sc, reg, mklink, driver/service management, writing to C:\Program Files, killing system processes). If SHH was started with start_shh_admin.bat it runs silently; otherwise ONE UAC prompt appears on the user's screen and must be approved.  
**所属分类**: `admin`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "command": {
      "type": "string",
      "description": "Command line to execute with administrator privileges."
    },
    "shell": {
      "type": "string",
      "enum": [
        "cmd",
        "powershell"
      ],
      "default": "cmd",
      "description": "Which elevated shell to use."
    },
    "timeout": {
      "type": "integer",
      "default": 120,
      "description": "Maximum seconds to wait for the command to finish."
    },
    "cwd": {
      "type": "string",
      "description": "Optional working directory for the elevated command."
    }
  },
  "required": [
    "command"
  ]
}
```

**调用示例 (HTTP POST /api/tools/run_admin_command)**:
```json
{
  "command": "git status",
  "shell": "cmd",
  "timeout": 120,
  "cwd": "example_value"
}
```

---

### `manage_firewall`
**功能描述**: Add / delete / list Windows Firewall inbound rules with administrator rights (allow a local port so other machines or tunnels can reach it).  
**所属分类**: `admin`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "enum": [
        "add",
        "delete",
        "list"
      ],
      "default": "list",
      "description": "Firewall operation to perform."
    },
    "name": {
      "type": "string",
      "description": "Rule name (used for add/delete, and as the list filter keyword)."
    },
    "port": {
      "type": "integer",
      "description": "Local TCP port to allow (required for action=add)."
    },
    "protocol": {
      "type": "string",
      "enum": [
        "TCP",
        "UDP"
      ],
      "default": "TCP"
    }
  },
  "required": [
    "action"
  ]
}
```

**调用示例 (HTTP POST /api/tools/manage_firewall)**:
```json
{
  "action": "list",
  "name": "example_value",
  "port": 10,
  "protocol": "TCP"
}
```

---

### `manage_port_forward`
**功能描述**: Create / delete / list OS-level TCP port forwarding rules (netsh interface portproxy) so traffic arriving on a local port is forwarded to another local or LAN host:port. Requires Administrator.  
**所属分类**: `admin`  

**参数定义 (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "enum": [
        "add",
        "delete",
        "list"
      ],
      "default": "list"
    },
    "listen_port": {
      "type": "integer",
      "description": "Local port to listen on."
    },
    "connect_host": {
      "type": "string",
      "default": "127.0.0.1",
      "description": "Target host to forward traffic to (IP or hostname)."
    },
    "connect_port": {
      "type": "integer",
      "description": "Target port (defaults to listen_port)."
    },
    "listen_address": {
      "type": "string",
      "default": "0.0.0.0",
      "description": "Local address to bind the listener to."
    }
  },
  "required": [
    "action"
  ]
}
```

**调用示例 (HTTP POST /api/tools/manage_port_forward)**:
```json
{
  "action": "list",
  "listen_port": 10,
  "connect_host": "127.0.0.1",
  "connect_port": 10,
  "listen_address": "0.0.0.0"
}
```

---
