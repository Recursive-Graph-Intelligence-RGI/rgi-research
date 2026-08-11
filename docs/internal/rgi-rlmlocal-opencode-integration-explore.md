# OpenCode integration report — `rlmlocal-site`

## 1. How the OpenCode CLI is spawned and managed

**Binary discovery**
- `src-tauri/src/opencode_host.rs:125-147` — resolves `opencode` from `OPENCODE_BIN` env, then `PATH` (`opencode.exe` on Windows).

**Serve mode (legacy/sidecar)**
- `src-tauri/src/opencode_host.rs:26` — binds to **port 4097** (avoids Kilo on 4096).
- `src-tauri/src/opencode_host.rs:258-374` (`start_inner`) spawns:

```text
opencode serve --hostname 127.0.0.1 --port 4097 \
  --cors http://localhost:5173 --cors http://127.0.0.1:5173 \
  --cors https://rlmlocal.com --cors https://www.rlmlocal.com
```

- It explicitly removes `OPENCODE_SERVER_PASSWORD` (line 312), waits up to 8 s for health (`probe_healthy` at `188-199`), and stores the child in a static `HOST` mutex (`48-53`).
- `stop_inner` (`235-256`) kills the child, clears the host lock, cancels any active task, and removes its shadow.
- `applyRlmModelToOpenCode.ts:13-76` patches provider/model config onto the running serve instance per-directory.

**One-shot mode**
- `src-tauri/src/opencode_host.rs:388-515` (`run_inner`) runs `opencode run --auto -m <model> --dir <project> --format default` with an inline config in `OPENCODE_CONFIG_CONTENT`.

**Frontend port**
- `src/features/execution/platform.ts:452-463` exposes `opencodeStatus`, `opencodeStart`, `opencodeStop`, `opencodeEnsure`.
- `platform.ts:542-580` exposes `opencodeRun`.

## 2. Task turn / collect / cleanup flow

The persistent “graph coder” task uses a **disposable git worktree** owned by Tauri.

| Step | Frontend | Rust backend | What it does |
|---|---|---|---|
| **Start** | `platform.ts:501-513` → `opencode_task_start` | `opencode_host.rs:1244-1285` (`task_start_inner`) | Creates shadow via `lib.rs:503-595` (`make_shadow`), snapshots baseline with `project_files` (`opencode_host.rs:1217-1242`), pins model/provider, stores in `AGENT_TASK` (`opencode_host.rs:58-68`, `1275`). |
| **Turn** | `platform.ts:520-535` → `opencode_task_turn` | `opencode_host.rs:1327-1354` (`task_turn_inner`) | Spawns `opencode run --auto --agent rlm-shadow -m <model> --dir <shadow> --format default`, adds `--continue` after the first turn (`1340`), injects `OPENCODE_CONFIG_CONTENT` from `build_task_opencode_config` (`1181`), rewrites absolute paths to relative (`task_message_in_shadow`, `1308`), merges stdout/stderr (`1291`). |
| **Collect** | `platform.ts:516-518` → `opencode_task_collect` | `opencode_host.rs:1356-1371` (`task_collect_inner`) | Diff of `baseline` vs current shadow files; returns `{relative, path, previous, content}` JSON. |
| **Cleanup** | `platform.ts:537-539` → `opencode_task_cleanup` | `opencode_host.rs:1373-1382` (`task_cleanup_inner`) | Removes shadow (`lib.rs:598-606` `remove_shadow`) and releases `AGENT_TASK`. |

In the loop:

- `RunCodeTaskIterate.ts:902-934` starts the persistent task.
- `RunCodeTaskIterate.ts:1129` sends the turn.
- `RunCodeTaskIterate.ts:1137` collects changed files.
- Cleanup happens on land/reject/junk/stop (`execConsole.ts:2022`, `2245`, `1984`, `1993`).

## 3. How write proposals are blocked until human approval

**One-shot mode (`opencode_run`)**
- `opencode_host.rs:1120-1177` (`build_rlm_opencode_config`) sets:

```json
"permission": { "*": "deny", "edit": "deny", "bash": "deny",
  "external_directory": "deny", "read": "allow", "grep": "allow", "glob": "allow" }
```

- The prompt explicitly tells OpenCode disk writes are blocked and to emit write-proposal JSON (`run_inner:416-432`).
- `parse_emitted_write_tools` (`opencode_host.rs:1430-1563`) extracts proposals from stdout; nothing is written to the real tree.

**Persistent task mode**
- OpenCode *can* edit, but only inside the disposable shadow (`build_task_opencode_config:1181-1215` sets `edit: "allow"` and a limited bash allowlist for `git status/diff`, `npm test/lint`, `npx tsc`).
- Real project writes only happen after the shared human gate:
  - `RunCodeTaskIterate.ts:1458-1468` runs `verifyPatch` on the **shadow** first.
  - On success, `execConsole.ts:2059-2093` (`enqueueVerifiedCodeBatch`) creates an `ExecProposal`, fires `rlm-exec-proposal`.
  - `execConsole.ts:761-790` listens and queues the card in **TO VERIFY**.
  - `showCodeChatGate` (`2187-2253`) renders **Approve & Land / Reject**.
  - **Approve** calls `applyPatch` (`2222`), which invokes Rust `apply_patch` (`lib.rs:980-989` → `apply_patch_inner:945-977`), writes the real tree, and commits (`lib.rs:965-975`). Then `opencodeTaskCleanup` releases the shadow (`2223`).
  - **Reject** calls `opencodeTaskCleanup` (`2245`).

## 4. How this could be reused or replaced by RGI-driven coding tasks

**Reusable infrastructure**
- Shadow worktree: `lib.rs:503-606` (`make_shadow` / `remove_shadow`).
- Verify/apply gate: `lib.rs:819-924` (`verify_patch_inner`) and `lib.rs:945-977` (`apply_patch_inner`).
- Proposal bus: `rlm-exec-proposal` DOM event (`execConsole.ts:761`, `2091`, `2183`) and the TO VERIFY UI (`addProposal` / `showCodeChatGate`).
- Trust ledger, trace DB, GEPA prompts: `platform.ts:120` `ExecPort`, `logTrace`, `savePrompt`, `queryTraces`.
- Provider adapter: `EdgeProxy` (`opencode_host.rs:95-114`, `start_edge_proxy:1045-1093`) translates Workers AI to an OpenAI-compatible local endpoint.

**Replacement seam**
- The execution seam is `platform.ts:120` (`ExecPort`) plus the `opencode*` functions.
- `RunCodeTaskIterate.ts` is largely transport-agnostic: it consumes `OpencodeProposedWrite[]`, runs `verifyCodeWrite`, and surfaces the result. It already falls back to direct-LLM transport (`CallHandler.ts:149-228`, `runCodeTaskDirectLlm`).
- An RGI coding agent could replace the OpenCode subprocess by implementing the same `opencodeTaskStart/Turn/Collect/Cleanup` contract (or a new port) and returning the same proposal shape. OpenCode-specific pieces to swap: `OPENCODE_CONFIG_CONTENT`, `parse_emitted_write_tools`, `--continue` semantics, and artifact-literal shields.

## 5. Risks and constraints

- **One task at a time**: `AGENT_TASK` mutex (`opencode_host.rs:58-68`, `1253-1274`). A second start fails until the first is approved/rejected/cleaned up.
- **Model pinned at start**: `task_turn_inner:1331-1334` rejects mid-task model switches.
- **Git required**: `make_shadow` uses `git worktree add --detach HEAD` (`lib.rs:511-519`); non-git projects cannot shadow-verify.
- **Timeouts**: `run_inner` waits max 180 s (`459`); serve health probe waits 8 s (`325`).
- **Edge context budget**: `edge_completion_budget` (`553-571`) caps `max_tokens` against the shared Workers AI input+output window; artifact literal shields (`592-615`) protect source text from template markup.
- **No real writes in shadow mode until approval**: safe by design, but a user can still click **Approve anyway & Land** on RED proposals.
- **Large-file raw dumps blocked**: policy refuses isolated full-file raw writes for large deliverables (`RunCodeTaskIterate.ts:541-555`, `1348-1354`).
- **Small-model fragility**: write JSON may be malformed; parser has forgiving fallback (`parse_one_write:1492-1563`, `parseWriteProposals.ts:71-147`) but can still miss proposals.
- **Port/hostname assumptions**: serve binds `127.0.0.1:4097`; CORS allowlist is hard-coded (`opencode_host.rs:303-310`); public web builds fall back to the `:1421` bridge.
- **Stale proposals**: if the project changes after shadow verify, queued cards are flagged stale (`execConsole.ts:796-810`).