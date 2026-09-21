"""
Integration Tests for SHH 1.0 Servers and Client SDK
"""

import asyncio
from fastapi.testclient import TestClient

from shh.client.cloud_client import SHHClient
from shh.config import SHHConfig
from shh.servers.http_server import create_app


def test_api_endpoints():
    config = SHHConfig(token="test-token-xyz")
    app = create_app(config, runtime_state={"lan_ip": "127.0.0.1", "ticket": "shh://test"})
    client = TestClient(app)

    # 1. Info endpoint
    resp = client.get("/api/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["token"] == "test-token-xyz"

    # 2. Tools list endpoint
    resp = client.get("/api/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] > 10

    # 3. Tool execution endpoint (shell_exec)
    resp = client.post("/api/tools/shell_exec", json={"command": "echo 'Testing API'"})
    assert resp.status_code == 200
    res = resp.json()
    assert res["success"] is True
    assert "Testing API" in res["stdout"]

    # 4. Fast exec endpoint
    resp = client.post("/api/exec", json={"command": "echo 'Fast Exec OK'"})
    assert resp.status_code == 200
    assert "Fast Exec OK" in resp.json()["stdout"]

    # 5. MCP JSON-RPC initialize
    mcp_init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {}
    }
    resp = client.post("/mcp", json=mcp_init)
    assert resp.status_code == 200
    assert resp.json()["result"]["serverInfo"]["name"] == "SHH-AI-Bridge"

    # 6. MCP JSON-RPC tools/list
    mcp_list = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list"
    }
    resp = client.post("/mcp", json=mcp_list)
    assert resp.status_code == 200
    tools = resp.json()["result"]["tools"]
    assert len(tools) > 10

    # 7. MCP JSON-RPC tools/call
    mcp_call = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "shell_exec",
            "arguments": {"command": "echo 'MCP Tool Call OK'"}
        }
    }
    resp = client.post("/mcp", json=mcp_call)
    assert resp.status_code == 200
    content = resp.json()["result"]["content"][0]["text"]
    assert "MCP Tool Call OK" in content


if __name__ == "__main__":
    test_api_endpoints()
    print("All server tests passed!")
