"""Unified tool harness for RGI.

Tools are no longer a flat dict of callables. Each tool declares a schema,
domain, and permission set so the harness can validate inputs, enforce
governance, and advertise capabilities to the LLM. Tools can be provided by
local Python functions, HTTP endpoints, MCP servers, or the Tauri bridge.
"""
from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


ToolHandler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]


@dataclass
class Tool:
    """Descriptor for one tool callable by RGI nodes.

    The descriptor is the contract between the tool implementer, the governance
    layer, and the LLM prompt. ``handler`` may be omitted for remote tools where
    execution is delegated to the provider.
    """
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    domain: str = "local"  # local | http | mcp | tauri
    permissions: set[str] = field(default_factory=set)
    handler: ToolHandler | None = None
    verifier: dict[str, Any] | None = None

    def prompt_signature(self) -> dict[str, Any]:
        """OpenAI/MCP-style function signature for the system prompt."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class ToolProvider:
    """Source of one or more tools. Subclass for local, HTTP, MCP, Tauri."""

    def list_tools(self) -> dict[str, Tool]:
        """Return a mapping from tool name to Tool descriptor."""
        raise NotImplementedError

    async def execute(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute the named tool with the given parameters."""
        raise NotImplementedError


class LocalToolProvider(ToolProvider):
    """Provider backed by Python callables in this process."""

    def __init__(self, tools: list[Tool] | None = None):
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.add(tool)

    def add(self, tool: Tool) -> None:
        if tool.handler is None:
            raise ValueError(f"Local tool {tool.name!r} requires a handler")
        self._tools[tool.name] = tool

    def list_tools(self) -> dict[str, Tool]:
        return dict(self._tools)

    async def execute(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools[name]
        result = tool.handler(params)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, dict):
            raise TypeError(f"Tool {name!r} returned {type(result).__name__}, expected dict")
        return result


class ToolRegistry:
    """Aggregates tools from multiple providers and executes them under governance.

    The registry is intentionally synchronous in construction (providers list their
    tools at startup) and asynchronous in execution (remote providers may await).
    """

    def __init__(self):
        self.providers: list[ToolProvider] = []
        self._tools: dict[str, Tool] = {}

    def register_provider(self, provider: ToolProvider) -> None:
        self.providers.append(provider)
        for name, tool in provider.list_tools().items():
            if name in self._tools:
                raise ValueError(f"Tool name collision: {name!r}")
            self._tools[name] = tool

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> dict[str, Tool]:
        return dict(self._tools)

    def list_tools_for_prompt(self) -> list[dict[str, Any]]:
        return [t.prompt_signature() for t in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name, routing to its provider."""
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"unknown_tool: {name}")
        # Route to the provider that owns this tool.
        for provider in self.providers:
            if name in provider.list_tools():
                return await provider.execute(name, params)
        raise RuntimeError(f"Tool {name!r} listed but no provider owns it")
