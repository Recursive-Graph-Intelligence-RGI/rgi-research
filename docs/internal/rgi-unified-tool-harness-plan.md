# RGI Unified Tool Harness Plan

**Date:** 2026-08-10  
**Goal:** Design a scalable tool harness that lets RGI consume local tools, remote rlmlocal-site tools, Tauri execution commands, and MCP servers under one governed registry — and explain how this fits the recursive subgraph architecture.

---

## 1. How RGI's Current Tool Infrastructure Works

From `rgi/core/harness.py` and `rgi/core/engine.py`:

1. **`Harness` owns a `ToolRegistry`** (`rgi/tools/registry.py`).
2. **`ToolRegistry` is a flat dict**: `{"tool_name": callable(params) -> dict}`.
3. **TOOL nodes carry metadata:** `{"tool": "security_scan", "params": {"path": "..."}}`.
4. **Engine execution:** `await harness.tool_registry.execute(tool_name, params)`.
5. **Governance:** `Harness.governance_check()` calls `LocalGate.check("tool_execute", {tool, path, ...})` before the node runs.
6. **Subgraph spawning is separate:** tools return data; REASONING nodes then suggest subgraphs; `Harness.request_subgraph_spawn()` approves/rejects them under depth/node/budget limits.

**What is missing for a rich tool ecosystem:**
- No tool schemas → the LLM and governance reason from hard-coded descriptions.
- No remote/MCP tool support → everything must be a Python function in `rgi/tools/`.
- No capability advertisement → the system prompt does not dynamically list tools.
- No lifecycle management → remote tools can't be added/removed at runtime.
- No permission classes → governance can't distinguish read-only vs write vs network vs exec.
- No tool-driven verification hooks → a tool can't request a verifier subgraph.

---

## 2. Proposed Unified Tool Harness

The harness stays the single authority, but `ToolRegistry` becomes a **multi-provider tool bus**. Every tool — local Python, rlmlocal engine query, Tauri command, MCP server — plugs into the same interface.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Harness                                                            │
│  - owns ToolRegistry                                                │
│  - governance check before every tool call                          │
│  - audit log                                                        │
└───────────────────────┬─────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┬────────────────┐
        │               │               │                │
┌───────▼──────┐ ┌──────▼──────┐ ┌─────▼──────┐ ┌───────▼────────┐
│ LocalProvider│ │HttpProvider │ │McpProvider │ │TauriProvider   │
│              │ │             │ │            │ │                │
│ Python funcs │ │rlmlocal     │ │external    │ │Tauri bridge    │
│ in rgi/tools/│ │engine RPCs  │ │MCP servers │ │127.0.0.1:1421  │
└──────────────┘ └─────────────┘ └────────────┘ └────────────────┘
```

### 2.1 Tool descriptor

Every tool exposes the same contract:

```python
@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict   # JSON Schema
    output_schema: dict  # JSON Schema
    domain: str          # "local", "http", "mcp", "tauri"
    permissions: set[str] # {"read", "write", "network", "exec", "git"}
    provider: ToolProvider
```

The descriptor is what gets advertised to the LLM and checked by governance.

### 2.2 Tool providers

**`LocalToolProvider`**
- Loads Python callables from `rgi/tools/` modules.
- Each module exposes a `TOOLS: list[Tool]` or registers via decorator.
- Sandboxed `exec` for REPL-style tools stays here.

**`HttpToolProvider`**
- Configured with base URL + optional auth.
- Calls rlmlocal-site engine queries: `getDependencies`, `resolveCallers`, `fileNeighborhood`, etc.
- Maps JSON responses to RGI's `{findings: [...], confidence: float}` shape.

**`McpToolProvider`**
- Connects to MCP servers (stdio, SSE, or HTTP).
- Dynamically lists tools via `tools/list`.
- Forwards calls via `tools/call`.
- Used for: `web_search`, `fetch_page`, memory tools, future third-party MCP servers.

**`TauriToolProvider`**
- Proxies to the same Tauri dev bridge rlmlocal-site uses (`127.0.0.1:1421`).
- Tools: `run_tests`, `verify_patch`, `apply_patch`, `resolve_types`, `compute_refactor`, `git_cochange`.
- Requires pairing token from `localStorage`/`rlm-exec-token`.

### 2.3 ToolRegistry 2.0

```python
class ToolRegistry:
    def __init__(self):
        self.providers: list[ToolProvider] = []
        self._tools: dict[str, Tool] = {}

    def register_provider(self, provider: ToolProvider):
        self.providers.append(provider)
        self._tools.update(provider.list_tools())

    async def execute(self, name: str, params: dict) -> dict:
        tool = self._tools[name]
        # schema validation
        validate(params, tool.input_schema)
        # execute via provider
        result = await tool.provider.call(name, params)
        # schema validation
        validate(result, tool.output_schema)
        return result

    def list_tools_for_prompt(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "parameters": t.input_schema}
            for t in self._tools.values()
        ]
```

### 2.4 Governance integration

`Harness.governance_check()` for TOOL nodes becomes:

```python
tool = self.tool_registry.get_tool(tool_name)
decision = self.gate.check(
    "tool_execute",
    {
        "tool": tool_name,
        "permissions": list(tool.permissions),
        "domain": tool.domain,
        "params": params,
    },
)
```

`LocalGate` policy can then deny all `write` tools, all `network` tools, all `tauri` tools, etc., based on runtime configuration or user approval.

### 2.5 Capability advertisement

The system prompt includes a dynamic tools section:

```
You may invoke tools by returning {"tool_call": {"name": str, "arguments": dict}}.
Available tools:
- read_file(path): Read a project file.
- resolve_callers(symbol, file): Find callers of a symbol.
- security_scan(path): Deterministic vulnerability scan.
- web_search(query): Search the web.
- verify_patch(file, edits): Verify edits in a shadow worktree.
```

This lets the model choose the right tool instead of guessing the JSON schema.

---

## 3. How Tools Fit the Subgraph Architecture

**Tools do not spawn subgraphs.** Tools produce structured observations. Subgraphs are spawned by REASONING nodes based on those observations and the objective.

The flow is:

```
REASONING node (root)
  └─ suggests tool call → TOOL node
       └─ returns findings
  REASONING node re-fires with tool output
  └─ suggests subgraph objectives → SPAWN proposals
       └─ Harness approves/rejects
            └─ child EXECUTION/VERIFICATION graphs run
```

**Tool-driven verification:**
A tool can request post-processing by declaring a `verifier`:

```python
Tool(
    name="security_scan",
    ...,
    verifier={
        "objective_template": "Verify {kind} finding at {file}:{line}",
        "loop_type": LoopType.VERIFICATION,
    }
)
```

After `security_scan` runs, the engine auto-spawns a verification subgraph for each high-severity finding. The verifier's job is to read the file/line and return `finding_valid: bool`.

This is the mechanism that will eliminate the duplicate/noise findings we saw from 7B models.

---

## 4. Build Order

### Phase 1: Refactor ToolRegistry without breaking existing tools (1–2 days)

- Introduce `Tool`, `ToolProvider`, and `ToolRegistry2` alongside the old registry.
- Port existing `rgi/tools/registry.py` tools to the new descriptor format.
- Keep `ToolRegistry.execute()` API stable so engine/harness don't change.
- Add schema validation and permission metadata.

**Files:**
- New `rgi/tools/harness.py`
- Refactor `rgi/tools/registry.py`

### Phase 2: Add capability advertisement to LLM prompts (1 day)

- Build `list_tools_for_prompt()`.
- Update `SYSTEM_PROMPT` to include available tools dynamically.
- Update `LLMClient._validate()` to handle `tool_call` responses.

**Files:**
- `rgi/reasoning/llm_client.py`
- `rgi/core/context_builder.py`

### Phase 3: Add HTTP and Tauri providers (2–3 days)

- `HttpToolProvider` for rlmlocal engine queries.
- `TauriToolProvider` for verify/apply/run_tests.
- Wire them in CLI/server config via env vars (`RGI_RLMLocal_ENGINE_URL`, `RGI_TAURI_BRIDGE_URL`).

**Files:**
- New `rgi/tools/providers/http_provider.py`
- New `rgi/tools/providers/tauri_provider.py`
- Update `rgi/cli.py`, `rgi/server.py`

### Phase 4: Add MCP provider (2–3 days)

- `McpToolProvider` wrapping an MCP client.
- Register built-in MCP server URLs from env/config.
- Use for `web_search`, `fetch_page`, memory tools.

**Files:**
- New `rgi/tools/providers/mcp_provider.py`
- Add MCP dependency

### Phase 5: Tool-driven verification (2–3 days)

- Add `verifier` field to `Tool`.
- Engine auto-spawns verifier subgraphs after tools that declare them.
- Re-run benchmarks to measure noise reduction.

**Files:**
- `rgi/core/engine.py`
- `rgi/tools/harness.py`

---

## 5. What This Unlocks

1. **RGI can use rlmlocal's graph without merging codebases.** HTTP provider queries the engine worker.
2. **RGI can propose verified edits.** Tauri provider calls `verify_patch`/`apply_patch` through the same relay rlmlocal uses.
3. **RGI can use web tools.** MCP provider connects to rlmlocal's worker or any MCP server.
4. **The LLM sees a unified tool surface.** No special knowledge of which runtime owns which tool.
5. **Governance is centralized.** Every tool call passes through `Harness.governance_check()` with permission classes.
6. **Tool-driven verification eliminates noise.** High-stakes tools auto-spawn verifier subgraphs.

---

## 6. Bottom Line

Yes, RGI needs a harness that all tools plug into. The current `ToolRegistry` is too simple for the integration we want. The right design is a **multi-provider tool bus** where local Python functions, rlmlocal HTTP endpoints, Tauri commands, and MCP servers all expose the same `Tool` descriptor. The Harness keeps governing every call, and the engine keeps spawning subgraphs based on tool outputs — but now tools can also declare verifier subgraphs, which is the key to cleaning up local-model noise.

This plan is concrete enough to start building. Phase 1 is safe and doesn't break anything.
