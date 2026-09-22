"""
SHH 1.0 - Cloud AI Agent Integration Demo
Demonstrates how a remote AI agent can connect to the local Windows machine using a Public Board URL or Ticket.
"""

import time
from shh.client.cloud_client import SHHClient


def main():
    print("=== SHH 1.0 Cloud AI Agent Demo ===")

    # In actual usage, the Cloud AI reads the ticket or dpaste URL from the user's prompt
    # Example: client = SHHClient.from_ticket("shh://...") or SHHClient.from_board("https://dpaste.org/xyz.txt")
    # For local test:
    client = SHHClient(base_url="http://127.0.0.1:18888")

    print("\n1. 检查本地机器连接与工具清单...")
    tools_data = client.get_tools_schema()
    print(f"✔ 成功连接！本地挂载工具数: {tools_data.get('count')}")

    print("\n2. 获取本地系统硬件概况...")
    sys_info = client.get_system_info()
    os_info = sys_info.get("os", {})
    cpu_info = sys_info.get("cpu", {})
    mem_info = sys_info.get("memory", {})
    print(f"✔ OS: {os_info.get('system')} {os_info.get('release')}")
    print(f"✔ CPU: {cpu_info.get('logical_cores')} 逻辑核心 | 内存使用: {mem_info.get('used_percent')}%")

    print("\n3. 执行本地 Shell 命令 (PowerShell / CMD)...")
    shell_res = client.exec_shell("echo 'AI Bridge Connected Successfully!'")
    print(f"✔ 输出: {shell_res.get('stdout', '').strip()} (耗时: {shell_res.get('duration_ms')}ms)")

    print("\n4. 截取本地屏幕快照 (Multimodal Vision)...")
    screen_res = client.capture_screen(max_width=800, quality=70)
    print(f"✔ 截屏分辨率: {screen_res.get('width')}x{screen_res.get('height')}")
    print(f"✔ 图像大小: {screen_res.get('file_size_kb')} KB (已编码为 Base64 Data URI)")
    print(f"✔ Base64 数据片段: {screen_res.get('image_data_uri')[:40]}...")

    print("\n5. 本地文件操作 (创建、修改、查找)...")
    client.write_file("test_ai_agent.txt", content="Hello from Cloud AI Agent!\nTimestamp: " + str(time.time()))
    read_res = client.read_file("test_ai_agent.txt")
    print(f"✔ 读取写入的文件内容:\n{read_res.get('content')}")

    print("\n6. 扫描本地开放端口...")
    ports_res = client.list_open_ports()
    print(f"✔ 当前监听端口数: {ports_res.get('total_open_ports')}")
    for p in ports_res.get("open_ports", [])[:5]:
        print(f"   - {p['ip']}:{p['port']} ({p.get('process_name') or 'unknown'})")

    print("\n✨ Cloud AI 演示完成！所有本地环境与工具均可直接调用。")


if __name__ == "__main__":
    main()
