# RGI ↔ rlmlocal Integration Strategy

*Discussion notes from 2026-08-10 session. RGI is the recursive-graph research engine; rlmlocal is the local-first code assistant with a rich code-grounded graph.*

## Core insight

RGI and rlmlocal are two sides of the same idea:

- **RGI** has recursive orchestration (planning → execution → verification → correction → learning) and a safety harness, but its **perception/activation substrate is shallow**.
- **rlmlocal** has a **rich code-grounded graph** (AST parse, import/call/data-flow/reference edges, embeddings, semantic concepts, freshness/re-healing) but its orchestration is currently gate/chat-driven rather than recursive-graph-native.

The integration opportunity: **let RGI's orchestration run on top of rlmlocal's graph substrate.**

## What rlmlocal has that RGI needs

| rlmlocal primitive | RGI gap | Integration point |
|---|---|---|
| `StructureExtractor.ts` | Perception only stores module/function names | Replace/augment `rgi/perception/code_parser.py` |
| `importGraph.ts` / `dataFlowGraph.ts` / `referenceGraph.ts` | No call/data-flow/reference edges | Feed into RGI's world model |
| `VectorStore.ts` | Nodes have no content or embeddings | Power `EmbeddingActivationEngine` |
| `semanticEngine.ts` / `ConceptStore` | No concept layer | Guide subgraph spawning |
| Gate cascade + tool-backed leaves | Generic subgraph objectives | Make spawning targeted and code-anchored |
| `read_file`, `grep`, `callers`, etc. (existing gates) | REPL only runs generic tools | Add grounded exploration primitives |
| Shadow verify → approve → land | RGI has no execution pipeline | Apply same discipline to findings |

## Two integration models

### Model A: Port concepts into RGI (keep RGI Python)

Lift the *algorithms and data models* from rlmlocal into RGI's Python stack.

**Pros:**
- Keeps RGI as a standalone research/engine project.
- Python ecosystem for agent/graph research (LangGraph, etc.).
- Easier to iterate on orchestration independently of UI.

**Cons:**
- Rewriting parser/embedding/semantic engine in Python.
- Two codebases to maintain.

**Best for:** RGI as an open/research engine; rlmlocal as one consumer.

### Model B: RGI orchestration layer inside rlmlocal

Keep rlmlocal's TypeScript graph substrate and add RGI-style recursive spawning, verification, and correction on top.

**Pros:**
- Built on proven, working code graph.
- Single product stack.
- Faster path to user-facing value.

**Cons:**
- RGI becomes a component, not a standalone engine.
- TypeScript is less ideal for rapid research iteration.

**Best for:** Product-first path; rlmlocal becomes the recursive-graph code assistant.

### Model C: Hybrid — shared graph spec, separate runtimes

Define a common graph interchange format (JSON/LSP-ish). RGI Python experiments export/import from rlmlocal's graph. Over time, proven RGI primitives move into rlmlocal.

**Pros:**
- Research and product can move in parallel.
- Common language between codebases.

**Cons:**
- More integration work upfront.
- Risk of spec drift.

**Best for:** Long-term; lets RGI stay research while rlmlocal productizes wins.

## Does the recent C2 improvement change this?

**No.** The topology + time-limit fixes let RGI complete larger targets and find real vulnerabilities (4b R3 aiohttp rgi: 0.667 recall). That validates the **orchestration mechanism**.

But the underlying substrate problems remain:
- Precision is still poor (4b R4 rgi: 0.846 recall, 0.021 precision).
- 1.5b still gets JSON parse failures in fixed workflow on large files.
- The knowledge graph still carries almost no code content.
- RGI cannot yet target specific functions/symbols the way rlmlocal can.

So the C2 fixes are **short-term enablers**, not a replacement for substrate work.

## Recommended path forward

1. **Finish C2** and write the final verdict.
2. **Use C2 as the bridge:** the verdict should explicitly state that v0.2 proves recursive topology helps, but v0.3 requires a code-grounded substrate.
3. **Choose Model A or C** for v0.3:
   - If RGI must remain a standalone engine: Model A (port rlmlocal concepts to Python).
   - If product velocity matters more: Model C (shared graph spec, RGI experiments feed rlmlocal).
4. **Do not choose Model B unless** the explicit goal is to sunset RGI as a separate project.
5. **First v0.3 milestone:** RGI can ingest a codebase and build a rlmlocal-style graph (source bodies + edges + embeddings) before any spawning happens.

## Risks

- rlmlocal's parser/semantics are not perfect (acknowledged by builder).
- Port only the mature, well-tested parts first.
- Avoid importing UI, Tauri, or OpenCode path into RGI.

## Open questions

- Which rlmlocal files are most stable for porting?
- Should RGI's perception be tree-sitter based (like rlmlocal) or stay Python-AST based?
- How should findings be verified against source code?
- What is the minimal graph interchange spec for Model C?
