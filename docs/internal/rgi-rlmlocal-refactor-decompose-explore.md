Here is the structured read-only report.

---

# RLMLocal decomposition, refactoring, and execution flow

## 1. Decomposition / refactoring skills and how they are triggered

### Skill catalog
Skills live in `src/features/skills/`:

- `SkillRegistry.ts:10-33` — simple `Map` of `SkillDef`s, filtered by selection node kind.
- `skill.types.ts:39-58` — `SkillDef` shape: `id`, `trigger: GraphNodeKind[]`, `executionDomain: 'browser' | 'executor'`, optional `buildPrompt()`, optional custom `run()`.
- `skillTemplates.ts:34-304` — declarative prompt-template skills divided into:
  - **T0 explain/analysis**: `analyze`, `find-callers`, `find-callees`, `dependencies`, `metrics`, `cluster-map`, `cluster-fields`.
  - **T0 reason/planning**: `plan`, `decompose`, `design`, `reason`.
  - **T1 verified changes** (`executionDomain: 'executor'`): `move`, `move-cluster`, `batch-move`, `extract`, `carve`, `decouple`, `extract-collaborator`, `method-object`, `rename`, `refactor`, `edit`, `converge`.
  - **Test**: `run-tests`, `debug-tests`.
- `registerSkills.ts:49-83` — bootstraps all skills into the registry plus placeholder skills.
- `explainSkill.ts:8-39` — the only custom `run()` skill shown; it builds a prompt and calls `runtime.chat()`.

### Trigger path
`SkillRuntime.ts:29-87` listens for `skill.invoked` app events:

1. Resolve skill from registry (`SkillRuntime.ts:30`).
2. If the skill is declarative (`buildPrompt` but no `run`):
   - Fail fast if `executionDomain === 'executor'` and no desktop executor is available (`SkillRuntime.ts:59-62`).
   - Build the prompt (`SkillRuntime.ts:63`).
   - Derive a structured `TurnScope` from the selection (`SkillRuntime.ts:117-126`).
   - Send it through `agent.chat()` (`SkillRuntime.ts:67`, `runEngineChat()` at `SkillRuntime.ts:128-142`).
3. If custom `run()` exists, call it directly.

So a toolbar click on e.g. **Decompose** turns into the chat prompt `decompose <symbol>` and is routed through the same gate cascade as a typed message.

### Structural vs generative refactor lanes
`src/features/execution/codeTaskRouter.ts:26-42` explicitly partitions code work:

- **T0 lane**: deterministic structural transforms (`move`, `extract`, `carve`, `decouple`, `converge`, `cluster`, `method-object`, `rename`).
- **T1 lane**: bounded single-file surgical patch.
- **Graph-coder/OpenCode lane**: multi-file, new-file, feature-scale, or tool-needed work.

All three lanes eventually feed the same shadow-verify → approve → apply patch pipe.

---

## 2. Verify → approve → land execution flow

### Execution seam
`src/features/execution/platform.ts` defines the contract:

- `ExecPort` interface (`platform.ts:120-136`): `runTests`, `verifyPatch`, `applyPatch`, `resolveTypes`, `computeRefactor`, `gitCochange`.
- `verifyPatch()` (`platform.ts:191-203`): runs baseline → apply edits → after-tests → always revert. Returns `PatchVerify` with `broke` (new failures), `baseline_failed`, `after_failed`, `lint_new`, `type_new`.
- `applyPatch()` (`platform.ts:208-221`): the one real write, called only after cockpit approval; commits as one git commit using the proposal spec as message.

### Worker → main relay
The engine runs in a Web Worker and cannot call Tauri directly:

- `src/features/agent/engine.worker.ts:55-61` — `requestExec()` emits `execRequest{opId}` and awaits `execResult{opId}`.
- `src/features/agent/engine.worker.ts:152-164` — attaches the execution port to the agent via `setExecPort()`.
- `src/features/agent/EngineClient.ts:310-348` — main-thread relay: receives `execRequest`, invokes the matching `platform.ts` function, posts `execResult` back.

### Surfacing proposals and plans
- `engine.worker.ts:167` — `setProposalHandler` forwards verified proposals as `execProposal` events.
- `engine.worker.ts:171` — `setPlanHandler` forwards refactor plans as `execPlan` events.
- `SimpleRLMAgent.ts:649-667` — defines these handlers; proposals are traced through the turn recorder.

### Cockpit gate: To Verify
`src/features/execution/execConsole.ts:548-789` implements the human approval gate:

- `addProposal()` (`execConsole.ts:576`) renders the diff, trust-tier badge, test/lint/type verdict, fence proof, and review warnings.
- Approve button (`execConsole.ts:668-746`):
  - Optionally renames a helper at the gate (`execConsole.ts:676-682`).
  - Calls `applyPatch()` through the single atomic path (`execConsole.ts:696`).
  - Cleans up OpenCode task shadow (`execConsole.ts:697`).
  - Greys the matching plan step via `markStepStale()` (`execConsole.ts:707`).
  - Records ledger/trust/learning events.
- Reject button (`execConsole.ts:748-754`) discards the proposal and cleans up.
- One-at-a-time guard: while any proposal is pending, plan step Run buttons are disabled (`execConsole.ts:459`, `runBusy()`).

### Code-muscle iteration loop
`src/features/execution/RunCodeTaskIterate.ts` is the OpenCode / direct-LLM implementation path:

- `verifyCodeWrite()` (`RunCodeTaskIterate.ts:277-313`) wraps `verifyPatch()` for a single proposed write.
- `runScopedT1Task()` (`RunCodeTaskIterate.ts:351-489`) does up to 3 SEARCH/REPLACE patch attempts with host-built anchors.
- The main `runCodeTaskIterate()` loop (`RunCodeTaskIterate.ts:491-1685`) iterates up to `attemptCeiling`, proposing, verifying, and repairing on RED/incomplete.
- On GREEN, it returns `VerifiedWrite[]` which surfaces as an `ExecProposal`.

---

## 3. How the agent decides to decompose vs. do it in one shot

### High-level routing
`src/features/agent/planner.ts` is the pure routing spine:

- `computeFastPath()` (`planner.ts:40-52`) decides one-pass from-context answers.
- `computeRoute()` (`planner.ts:140-177`) returns `'fast' | 'web' | 'tool' | 'recursive' | 'toolLoop'`.
- `shouldRecurse()` (`planner.ts:125-134`) sends analytical/decompose-worthy questions to recursive decomposition unless `reasoningMode === 'fast'`.

`RecursiveScheduler.ts` provides the deterministic decomposition heuristics:

- `shouldDecompose()` (`RecursiveScheduler.ts:228-232`): enabled per backend profile, question length ≥ 20, and matches `COMPLEX_PATTERNS` (`RecursiveScheduler.ts:118-193`).
- Backend profiles (`RecursiveScheduler.ts:75-100`):
  - `webllm-tiny`: `decompose: false`, `maxDepth: 1`.
  - `webllm-small`: `decompose: true`, `maxDepth: 2`.
  - `ollama`: `decompose: true`, `maxDepth: 2`, `maxIterations: 20`.
- `isSimple()` (`RecursiveScheduler.ts:216-226`) and `isContextSufficient()` (`RecursiveScheduler.ts:882-909`) suppress decomposition when context already covers the question.
- `validateSubQuestions()` (`RecursiveScheduler.ts:840-876`) drops duplicates/rephrases and warns on unknown file refs.
- `hasConverged()` (`RecursiveScheduler.ts:915-919`) uses Jaccard similarity against a threshold to stop refinement.

### Refactor-specific decomposition triggers
A separate set of intent gates in `RecursiveScheduler.ts` decides the *kind* of decomposition:

- `isDecomposeRequest()` (`RecursiveScheduler.ts:496-523`) — "break X into steps".
- `isFilePlanRequest()` (`RecursiveScheduler.ts:735-756`) — "plan / decompose / refactor `<file>`" emits a full tier-tagged `ExecPlan`.
- `isConvergeRequest()` (`RecursiveScheduler.ts:694-699`) — "converge `<file>`" auto-walks to a fixed point.
- `isVerifyChangeRequest()` (`RecursiveScheduler.ts:460-476`) — bare imperative ("fix X", "refactor X") becomes a single verified change, not a plan.

So the decision is:
- **One-shot** when fast-path flags are satisfied (`planner.ts:40-52`), the question is short/simple, or context is sufficient.
- **Decompose** when backend supports it, complexity patterns match, explicit parts exist, or the user explicitly asks for steps/plan/converge.

---

## 4. How RGI's recursive spawn/verify/correct model maps onto this flow

RGI's mental model — recursively spawn sub-tasks, verify each, correct on failure — already has partial, but not complete, analogs in the codebase.

| RGI concept | Existing RLMLocal analog | Location |
|---|---|---|
| **Spawn a sub-task** | `requestExec()` over Boundary A; `runRecursiveRefactor()`; `runGepaRefactor()`; `SkillRuntime.chat()` with a plan/decompose skill | `engine.worker.ts:55`, `refactorer.ts:88-117`, `SkillRuntime.ts:67 |
| **Verify** | `verifyPatch()` / `verifyCodeWrite()`; `decideAfterVerify()` | `platform.ts:191`, `RunCodeTaskIterate.ts:277`, `RunCodeTaskIterate.ts:1488 |
| **Correct / iterate** | RED repair loop; `runScopedT1Task()` up to 3 attempts; `focusMissingBrief()`; `withCoderFeedback()` | `RunCodeTaskIterate.ts:1572-1672`, `RunCodeTaskIterate.ts:351-489 |
| **Convergence / stop** | `hasConverged()`; `isOverBudget()`; max attempt ceiling | `RecursiveScheduler.ts:915`, `RecursiveScheduler.ts:921`, `RunCodeTaskIterate.ts:315-316, 832 |
| **Surface results** | `execProposal` (single verified change) and `execPlan` (DAG of steps) events | `engine.worker.ts:167-171`, `SimpleRLMAgent.ts:649-667 |
| **Human approval gate** | "To Verify" queue in exec console | `execConsole.ts:548-789 |
| **Trust tiering** | T0 deterministic / T1 generative / T2 scheduling | `platform.ts:59-64`, `execConsole.ts:166-173 |

### Closest existing recursive decomposition
`Refactorer.runRecursiveRefactor()` (`refactorer.ts:88-117`) is essentially an RGI-style recursive driver:

1. Reads disk truth for the function.
2. Generates a candidate change.
3. `verifyPatch()` the edit.
4. On failure, `extractCandidates()` breaks the function into cohesive spans and recurses.

`runGepaRefactor()` (`refactorer.ts:24-86`) is an evolutionary loop over a trainset of candidate tasks with scoring and prompt learning.

### Mapping a generic RGI recursive agent
A generic RGI "spawn verifier and corrector agents" could reuse:

1. **Spawn**: create a new `runCodeTaskIterate()` invocation or a new OpenCode task shadow (`opencodeTaskStart` in `platform.ts:501-513`) per sub-task.
2. **Verify**: call `verifyPatch()` / `verifyCodeWrite()` and `decideAfterVerify()` on the result.
3. **Correct**: feed RED output back into the task as a repair turn, exactly like `RunCodeTaskIterate.ts:1648-1661`.
4. **Surface**: wrap successful sub-task results into `ExecProposal` events and feed failed ones upward as `review`/`evidence`.
5. **Plan**: for multi-step refactors, emit an `ExecPlan` and let the existing cursor/auto-advance mechanism (`execConsole.ts:856-910`) drive step-by-step execution.

---

## 5. Gaps and risks for integration

### Gaps

1. **No generic "spawn child agent" primitive.**  
   `RecursiveScheduler` decomposition is deterministic regex-based (`RecursiveScheduler.ts:228-232`), not LLM sub-agent spawning. The only LLM-driven recursive decomposition is the narrow `runRecursive`/`runGepaRefactor` paths. A general RGI "spawn a verifier agent" would need a new worker-side orchestrator.

2. **Verification is desktop-only.**  
   `executionDomain: 'executor'` skills fail fast if no Tauri/bridge is present (`SkillRuntime.ts:59-62`). Any RGI verify/correct loop would be limited to desktop users; browser-only builds get honest "desktop-only" failures.

3. **Approval is always human-gated for writes.**  
   Even "auto-advance" plan steps (`execConsole.ts:856-910`) require a human Approve click per proposal. RGI's fully autonomous recursive land would conflict with the current trust model unless restricted to T0 deterministic transforms.

4. **No independent verifier model.**  
   `verifyCodeWrite` relies on tests/lint/types, not a separate LLM reviewer. RGI's "verifier agent" semantic review would be a new lane.

5. **Convergence is textual, not semantic.**  
   `hasConverged()` uses Jaccard word overlap (`RecursiveScheduler.ts:959-968`). For code tasks, structural/semantic equivalence is not measured.

6. **Plans are read-only and human-driven.**  
   `ExecPlan` surfaced by `setPlanHandler` renders steps but does not auto-execute them. RGI autonomous execution would need to bridge plan cards → automatic dispatch.

7. **Single persistent OpenCode context per task.**  
   `RunCodeTaskIterate.ts:902` holds one `{taskId, shadowPath}`. Parallel RGI sub-spawns would need multiple isolated task contexts or a new multi-agent host.

### Risks

1. **State contamination across recursive turns.**  
   The current code-muscle loop mutates `task`, `stash`, `lastVerified`, and `persistent` across iterations. Adding RGI parent/child spawning without isolation could let a failed child corrupt the parent's stash.

2. **Blast-radius underestimation.**  
   `ExecPlan.changeSet` is the transitive dependents closure (`platform.ts:85-92`), but RGI arbitrary sub-tasks may not compute cross-file ripples, leading to partial lands that break importers.

3. **Stale proposals after graph heal.**  
   `execConsole.ts:793-810` flags queued proposals when a file heals, because `verify_patch` baselines become stale. A fast RGI loop could land stale diffs if it bypasses this guard.

4. **Trust-tier escalation.**  
   Generative sub-agent outputs default to T1 (`platform.ts:61-64`). If RGI recursively composes T1 edits, the compound trust tier should arguably rise or require stronger review; the current ledger only records per-proposal `(kind, model)`.

5. **Tool / transport failures are not always recoverable.**  
   `RunCodeTaskIterate.ts:1173-1243` stops on OpenCode task failure and returns `junk: true`. RGI's "keep spawning until success" model would need to distinguish transient vs permanent failures.

6. **Phantom create risk.**  
   `RunCodeTaskIterate.ts:797-800` flags required deliverables not in the project index. An RGI agent spawning sub-tasks could invent new files that GREEN vacuously; the existing guard is best-effort and only inside the graph-coder lane.

---

### Bottom line

RLMLocal already has strong pieces of an RGI-style recursive execution model — `RecursiveScheduler`, `runRecursiveRefactor`, `RunCodeTaskIterate`, the `verifyPatch`/`applyPatch` seam, and the `execProposal`/`execPlan` approval surface. The cleanest integration path is to treat RGI's recursive spawn/verify/correct as an **orchestrator layer above `runCodeTaskIterate` and `Refactorer`**, emitting `ExecPlan`/`ExecProposal` events and respecting the existing human-approval gate. The biggest design decision is whether to allow autonomous landing (violating the current T1 human-gate invariant) or keep RGI recursive loops in the **prepare/verify** phase, with the final land still human-approved.