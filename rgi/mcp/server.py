"""Minimal MCP server exposing RGI's ToolRegistry over JSON-RPC 2.0 (HTTP POST).

Implements the subset of the MCP protocol that rlmlocal-site's McpClient uses:

- ``initialize`` / ``notifications/initialized``
- ``tools/list``
- ``tools/call``

This is a stateless, localhost-only bridge: the RGI server's ``localhost_guard``
middleware enforces Host/Origin checks and every tool call is just a registry
execute. Security-relevant tools (read_file, list_dir, security_scan, ...) carry
``read`` permissions and are confined by governance when run inside the engine;
external callers reach the same code paths.
"""
import json
import uuid
from typing import Any

from aiohttp import web

from rgi.tools.registry import ToolRegistry

PROTOCOL_VERSION = "2024-11-05"


def _rpc(msg_id: Any, result: Any = None, error: dict | None = None) -> dict:
    msg: dict = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    return msg


class MCPServer:
    """One MCP endpoint; tools come from the shared RGI ToolRegistry."""

    def __init__(self, registry: ToolRegistry | None = None):
        self.registry = registry or ToolRegistry()
        self._session_id = uuid.uuid4().hex

    async def handle(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            return web.json_response(
                _rpc(None, error={"code": -32700, "message": "parse error"}),
                status=400,
            )

        method = body.get("method")
        msg_id = body.get("id")
        params = body.get("params") or {}

        if method == "initialize":
            return self._respond(_rpc(msg_id, result={
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "rgi", "version": "0.3"},
            }))
        if method == "notifications/initialized":
            # Notifications have no response; an empty body keeps naive clients happy.
            return web.json_response({})
        if method == "tools/list":
            tools = []
            for name, tool in self.registry.list_tools().items():
                tools.append({
                    "name": name,
                    "description": tool.description,
                    "inputSchema": tool.input_schema
                    or {"type": "object", "properties": {}},
                })
            return self._respond(_rpc(msg_id, result={"tools": tools}))
        if method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments") or {}
            if self.registry.get_tool(name) is None:
                return self._respond(_rpc(
                    msg_id, error={"code": -32602, "message": f"unknown tool: {name}"},
                ))
            try:
                result = await self.registry.execute(name, arguments)
            except Exception as exc:  # containment: a tool error is a JSON-RPC error, not a crash
                return self._respond(_rpc(
                    msg_id, error={"code": -32000, "message": f"{type(exc).__name__}: {exc}"},
                ))
            return self._respond(_rpc(msg_id, result={
                "content": [{"type": "text", "text": json.dumps(result, default=str)}],
                "isError": False,
            }))

        return self._respond(_rpc(
            msg_id, error={"code": -32601, "message": f"method not found: {method}"},
        ))

    def _respond(self, payload: dict) -> web.Response:
        resp = web.json_response(payload)
        resp.headers["Mcp-Session-Id"] = self._session_id
        return resp
