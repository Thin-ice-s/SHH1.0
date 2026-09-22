"""
SHH 1.0 - AI Tool Schema & Manifest Exporter
Generates OpenAPI, OpenAI function schemas, Anthropic Claude schemas, MCP schemas, and Markdown outlines.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from shh.tools import registry


def generate_tools_markdown() -> str:
    """Generate a comprehensive Markdown Tool Outline (工具大纲) for AI models."""
    tools = registry.list_tools()
    
    md = [
        "# 🛠️ SHH 1.0 - 本地电脑 AI 控制工具大纲 (Tool Manifest)",
        "",
        "> 本文档定义了云端 AI 可调用的本地 Windows 电脑全套开发与控制工具。AI 可通过 REST API、MCP 协议或 WebSocket 直接调用以下工具。",
        "",
        "## 📑 工具分类概览",
        "",
        "| 分类 | 工具名称 | 功能说明 |",
        "| :--- | :--- | :--- |",
    ]

    for tool in tools:
        md.append(f"| `{tool.category}` | **`{tool.name}`** | {tool.description} |")

    md.append("")
    md.append("---")
    md.append("")
    md.append("## 🔧 详细工具规范与参数说明")
    md.append("")

    for tool in tools:
        md.append(f"### `{tool.name}`")
        md.append(f"**功能描述**: {tool.description}  ")
        md.append(f"**所属分类**: `{tool.category}`  ")
        md.append("")
        md.append("**参数定义 (JSON Schema)**:")
        md.append("```json")
        md.append(json.dumps(tool.parameters, indent=2, ensure_ascii=False))
        md.append("```")
        md.append("")

        # Example usage
        md.append("**调用示例 (HTTP POST /api/tools/" + tool.name + ")**:")
        example_payload = {}
        props = tool.parameters.get("properties", {})
        for prop_name, prop_spec in props.items():
            if "default" in prop_spec:
                example_payload[prop_name] = prop_spec["default"]
            elif prop_spec.get("type") == "string":
                if "path" in prop_name:
                    example_payload[prop_name] = "C:\\projects\\demo\\app.py"
                elif "command" in prop_name:
                    example_payload[prop_name] = "git status"
                elif "url" in prop_name:
                    example_payload[prop_name] = "http://localhost:3000"
                else:
                    example_payload[prop_name] = "example_value"
            elif prop_spec.get("type") == "integer":
                example_payload[prop_name] = 10
            elif prop_spec.get("type") == "boolean":
                example_payload[prop_name] = True

        md.append("```json")
        md.append(json.dumps(example_payload, indent=2, ensure_ascii=False))
        md.append("```")
        md.append("")
        md.append("---")
        md.append("")

    return "\n".join(md)


def export_all_manifests(output_dir: str = ".") -> Dict[str, Path]:
    """Export all tool manifests and schemas to disk."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    tools = registry.list_tools()

    # 1. TOOLS_MANIFEST.md
    manifest_md = generate_tools_markdown()
    p_manifest = out / "TOOLS_MANIFEST.md"
    p_manifest.write_text(manifest_md, encoding="utf-8")

    # 2. openai_tools.json
    openai_schemas = [t.to_openai_schema() for t in tools]
    p_openai = out / "openai_tools.json"
    p_openai.write_text(json.dumps(openai_schemas, indent=2, ensure_ascii=False), encoding="utf-8")

    # 3. anthropic_tools.json
    anthropic_schemas = [t.to_anthropic_schema() for t in tools]
    p_anthropic = out / "anthropic_tools.json"
    p_anthropic.write_text(json.dumps(anthropic_schemas, indent=2, ensure_ascii=False), encoding="utf-8")

    # 4. mcp_tools.json
    mcp_schemas = [t.to_mcp_schema() for t in tools]
    p_mcp = out / "mcp_tools.json"
    p_mcp.write_text(json.dumps(mcp_schemas, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "manifest_md": p_manifest,
        "openai": p_openai,
        "anthropic": p_anthropic,
        "mcp": p_mcp
    }
