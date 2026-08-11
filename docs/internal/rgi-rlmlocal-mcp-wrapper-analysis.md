# rlmlocal-site MCP Wrapper Analysis

**Date:** 2026-08-12  
**Goal:** Understand the lightweight MCP wrapper in `rlmlocal-site`, how it connects to the agent, and how it can plug into RGI.

> **Canonical integration roadmap:** `docs/superpowers/plans/2026-08-12-rgi-rlmlocal-master-integration-roadmap.md`

---

## 1. What the wrapper is

The MCP client in `rlmlocal-site` is intentionally thin. It has two layers:

| Layer | File | Responsibility |
|---|---|---|
| Main-thread facade | `src/lib/mcp/McpClient.ts` | `connect()`, `listTools()`, `callTool()`, `getCachedTools()`, `abortMcpRequest()`. |
| Web Worker engine | `src/lib/workers/mcp.worker.ts` | Real JSON-RPC 2.0 over HTTP POST, SSE streaming support, abort handling. |
| UI / persistence | `src/features/mcp/mcpListUI.ts` | Built-in + user server list, reconnect on load, disconnect buttons. |

### 1.1 Protocol details

- Transport: HTTP POST with JSON-RPC 2.0 body.
- Headers: `Content-Type: application/json`, `Accept: application/json, text/event-stream`.
- Session tracking via `Mcp-Session-Id` response header.
- Supports SSE responses for streaming tools (partial results posted back to main thread).
- Abort: main thread sends `abort` message; worker cancels the in-flight `fetch`.

### 1.2 Built-in cloud server

`rlmlocal-site` always tries to connect to:

```
https://rlmlocal-mcp.fortsignal.workers.dev
```

This is the "hybrid cloud" part. It provides web tools (search, fetch, weather, stocks, news) without exposing the user's local files to the cloud.

### 1.3 Tools exposed *by* rlmlocal-site

`McpClient.ts` defines `MCP_EXPOSED_TOOLS` — schemas for what rlmlocal can advertise when it acts as an MCP server:

- `list_local_resources`
- `read_local_file`
- `grep_local_resources`
- `find_local_files`
- `search_memory`
- `get_relations`
- `rlm_decompose`
- `rlm_analyze_item`
- `rlm_recursive_answer`

These map directly to the browser toolkit, `VectorStore`, and the recursive RLM engine. Today they are only schemas; there is no actual MCP server endpoint in the browser bundle serving them.

### 1.4 How tools reach the agent

`main.ts` calls `reconnectSavedMcpServers(...)`, which builds `McpClient` instances and attaches them to the current agent via `agent.addMcpClient()`. Inside `engine.worker.ts`, the agent rebuilds its own `McpClient`s from the URLs and merges their tool signatures into the tool loop.

---

## 2. Integration options with RGI

RGI's `ToolRegistry` (`rgi/tools/harness.py`) already has a `domain` field that includes `mcp`, but there is no `McpToolProvider` yet. There is also no RGI MCP server endpoint.

### Option A — RGI exposes an MCP server; rlmlocal-site consumes it

RGI runs an MCP server at `/mcp` (or a separate port). It advertises RGI tools:

- `security_scan`
- `read_file`
- `grep`
- `explore_corpus`
- `run_pytest`
- `parse_python_file`
- etc.

rlmlocal-site adds `http://127.0.0.1:8787/mcp` as an MCP server. The existing `McpClient` connects, lists tools, and the agent can call them.

**Pros:**
- Uses rlmlocal's existing MCP plumbing — no new adapter code on that side.
- RGI tools become available inside rlmlocal's chat/tool loop immediately.
- Standard protocol; other MCP clients could also connect.

**Cons:**
- Does not handle chat streaming, graph events, or execution telemetry. Those still need a separate channel (HTTP/SSE or WebSocket).
- RGI would need to implement the MCP server protocol (initialize, tools/list, tools/call, session mgmt).

### Option B — rlmlocal-site exposes an MCP server; RGI consumes it

rlmlocal-site serves its `MCP_EXPOSED_TOOLS` from a local endpoint (e.g., a Service Worker, a Tauri command, or a small local HTTP server). RGI adds an `McpToolProvider` that connects to it.

**Pros:**
- RGI gets deep local access (`read_local_file`, `search_memory`, `get_relations`) without porting all of rlmlocal's graph code first.
- The integration direction matches RGI's design goal: RGI orchestrates, rlmlocal provides the substrate.

**Cons:**
- Requires rlmlocal-site to become an MCP server, which it is not today.
- PWA mode has no long-running server; Tauri or a Service Worker would be needed.
- Adds a runtime dependency: RGI cannot work without rlmlocal-site running.

### Option C — Dual channel (recommended)

Use the **HTTP/SSE adapter** from `docs/superpowers/specs/2026-08-12-rgi-rlmlocal-adapter-design.md` for chat, graph snapshots, and execution events, and add **MCP** as a secondary tool bridge:

1. **RGI exposes `/mcp`.** rlmlocal-site can add it as an MCP server to get RGI tools in its existing tool loop.
2. **RGI can consume external MCP servers** (including rlmlocal's cloud `fortsignal.workers.dev` server and any user-added servers) via a new `McpToolProvider`.
3. **Tool names are namespaced** to avoid collisions: `rgi_security_scan`, `rgi_read_file`, `rlm_web_search`, etc.

This gives the best of both worlds: streaming chat over SSE, tool interoperability over MCP, and no requirement that either project become a server unless the user opts in.

---

## 3. Concrete next steps

### 3.1 Add an MCP server surface to RGI

Create `rgi/mcp/server.py` mounted at `/mcp` on the existing aiohttp app. Minimum JSON-RPC handlers:

- `initialize`
- `notifications/initialized`
- `tools/list` — returns `ToolRegistry.list_tools_for_prompt()`
- `tools/call` — routes to `ToolRegistry.execute()`

Example shape:

```python
# rgi/mcp/server.py (conceptual)
async def mcp_handler(request: web.Request) -> web.Response:
    body = await request.json()
    method = body.get("method")
    params = body.get("params", {})
    if method == "tools/list":
        return web.json_response({"result": {"tools": registry.list_tools_for_prompt()}})
    if method == "tools/call":
        result = await registry.execute(params["name"], params.get("arguments", {}))
        return web.json_response({"result": {"content": [{"type": "text", "text": json.dumps(result)}]}})
    return web.json_response({"error": {"code": -32601, "message": "method not found"}})
```

### 3.2 Add an MCP client provider to RGI

Create `rgi/tools/mcp_provider.py` implementing `ToolProvider`. It connects to a list of MCP URLs (`RGI_MCP_URLS`), calls `tools/list`, and forwards `tools/call` via JSON-RPC.

Example env:

```bash
RGI_MCP_URLS="https://rlmlocal-mcp.fortsignal.workers.dev"
```

### 3.3 Smoke test the dual channel

1. Start RGI server with `/mcp` enabled.
2. In rlmlocal-site dev console, add `http://127.0.0.1:8787/mcp` to `rlm-mcp-servers` and reload.
3. Ask rlmlocal's chat: "Run an RGI security scan on auth.py."
4. Verify the agent calls the `rgi_security_scan` MCP tool and surfaces the result.

---

## 4. Risks

| Risk | Mitigation |
|---|---|
| Tool name collisions between RGI and rlmlocal | Prefix all cross-runtime tools: `rgi_*`, `rlm_*`. |
| SSE partials not yet used by the worker | Start with synchronous tool results; streaming partials are a later enhancement. |
| Session / state management in MCP | Keep RGI MCP server stateless; session ID is only echoed for compatibility. |
| Auth on MCP endpoints | Local-only by default; cloud server already has its own auth. |
| PWA cannot run a server | RGI-as-server solves this; rlmlocal-as-server only works in Tauri or with a Service Worker. |

---

## 5. Recommendation

Implement **Option C** but start with only **RGI-as-MCP-server** (Option A). It is the smallest increment: one new Python module (`rgi/mcp/server.py`) and a route addition, then rlmlocal-site can consume RGI tools through its existing `McpClient`. After that works, add `McpToolProvider` so RGI can call the cloud `fortsignal.workers.dev` tools directly, reducing the need to reimplement `web_search`/`fetch_page` in Python.
