"""
SHH 1.0 - Base Tool & Registry System
Defines standardized tool interfaces compatible with OpenAI Function Calling, Anthropic Claude Tools, and MCP.
"""

import inspect
import json
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    category: str = "general"
    parameters: Dict[str, Any] = {}

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool with given arguments and return a dictionary result."""
        pass

    def to_openai_schema(self) -> Dict[str, Any]:
        """Export as OpenAI / DeepSeek function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }

    def to_anthropic_schema(self) -> Dict[str, Any]:
        """Export as Anthropic Claude tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters
        }

    def to_mcp_schema(self) -> Dict[str, Any]:
        """Export as Model Context Protocol (MCP) tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.parameters
        }


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> BaseTool:
        """Register a tool instance."""
        if not tool.name:
            raise ValueError(f"Tool {tool} has no name defined.")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Get tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_names(self) -> List[str]:
        return list(self._tools.keys())

    def get_by_category(self, category: str) -> List[BaseTool]:
        return [t for t in self._tools.values() if t.category == category]

    async def execute(self, name: str, **kwargs) -> Dict[str, Any]:
        """Execute a tool by name."""
        tool = self.get(name)
        if not tool:
            return {
                "success": False,
                "error": f"Tool '{name}' not found. Available tools: {', '.join(self.list_names())}"
            }
        try:
            res = await tool.execute(**kwargs)
            if not isinstance(res, dict):
                return {"success": True, "result": res}
            if "success" not in res:
                res["success"] = True
            return res
        except Exception as e:
            return {
                "success": False,
                "error": f"Execution error in '{name}': {str(e)}"
            }

    def export_all_schemas(self) -> Dict[str, Any]:
        """Export schemas in all standard AI formats."""
        return {
            "openai": [t.to_openai_schema() for t in self.list_tools()],
            "anthropic": [t.to_anthropic_schema() for t in self.list_tools()],
            "mcp": [t.to_mcp_schema() for t in self.list_tools()]
        }


# Global Default Registry
registry = ToolRegistry()
