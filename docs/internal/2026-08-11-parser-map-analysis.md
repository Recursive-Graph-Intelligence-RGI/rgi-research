# Parser Map — AST vs tree-sitter vs regex vs TS compiler (both projects)

**Date:** 2026-08-11
**Status:** reference — feeds the canonical plan §8 (parser map & integration design)
**Source:** subagent deep-dive over 16 files across both repos.

---

## 1. The complete parser map

| # | Subsystem | Project | Technology | What it parses |
|---|---|---|---|---|
| 1 | Default perception | RGI `code_parser.py` | **Python stdlib `ast` ONLY** | Python only; `ast.parse`/`ast.walk`; syntax-error files silently skipped |
| 2 | Structure extraction (compat) | RGI `rlmlocal_compat/structure_extractor.py` | **tree-sitter + regex fallback** | py/js/go/rust walkers; `_regex_fallback` on error/unknown |
| 3 | Import graph | RGI `import_graph.py` | **NONE (string/path only)** | consumes `CodeStructure.imports`; stem + `./../` + `index.ext` resolution |
| 4 | Call graph | RGI `call_graph.py` | **NONE (string only)** | consumes `CodeStructure.calls`; conservative single-def resolution |
| 5 | Reference graph | RGI `reference_graph.py` | **REGEX over raw text** | `@app.route`/`@router.get` decorators + `fetch`/`axios`/`requests` clients |
| 6 | Data-flow graph | RGI `data_flow_graph.py` | **REGEX op/key matching** | `.op(key)` with colon-namespaced keys; var-key resolution |
| 7 | Security scanner | RGI `security_scan.py` | **MIX: ast (1) + regex/substring (8)** | plaintext-password via `ast`; secrets/JWT/SQLi/path/crypto/cmd via regex |
| 8 | Tool registry | RGI `registry.py` | **ast + regex + sandboxed exec** | `parse_python_file` ast; security tools regex; `explore_corpus` exec |
| 9 | Tree-sitter wrapper | rlmlocal `treeSitter.ts` | **web-tree-sitter WASM** | version pair 0.20.8/0.1.13; grammars from LANGUAGE_PACKS; LRU cache |
| 10 | Language packs | rlmlocal `languagePacks.ts` | **DATA — 6 tree-sitter + 12 regex/content-only** | TS/TSX/JS/Py/Go/Rust AST; Ruby/Java/C#/PHP/C/C++/Swift/Kotlin/Scala/Vue/Svelte/SQL content-only |
| 11 | Import graph | rlmlocal `importGraph.ts` | **string/path heuristics + regex** | family-aware: Go dir-suffix, Rust `crate/self/super`, `@/ ~/` aliases, output-ext stripping |
| 12 | Structure extractor | rlmlocal `StructureExtractor.ts` | **tree-sitter AST + regex fallback** | `extractByFamily` js/py/go/rust; regex L1 for py/ts/js/go/rs/rb |
| 13 | Data-flow graph | rlmlocal `dataFlowGraph.ts` | **REGEX op/key matching — CONFIRMED** | same op tables + `${\}` normalize as RGI |
| 14 | Reference graph | rlmlocal `referenceGraph.ts` | **REGEX route matching** | param collapse `:id`/`${x}`/`[id]`/`{id}`/`<int:id>` → `*`; Django/`@Get`/`#[get]` |
| 15 | Toolkit | rlmlocal `browserTools.ts` | **NONE (pure file IO)** | File System Access API; no parsing |
| 16 | TS compiler service | rlmlocal `scripts/resolveExtractTypes.cjs` | **TypeScript compiler API** | `createProgram`/LanguageService; `resolveTypes`/`computeRefactor`; speaks tree-sitter coords |

## 2. Language coverage matrix

| Language | Exts | RGI | rlmlocal |
|---|---|---|---|
| Python | `.py` | **ast** (default) / **tree-sitter** (compat) / regex fallback | **tree-sitter** + regex L1 |
| TypeScript | `.ts .mts .cts` | tree-sitter (family js) | tree-sitter + **TS compiler** |
| TSX/JSX | `.tsx .jsx` | tree-sitter | tree-sitter tsx |
| JavaScript | `.js .jsx .mjs .cjs` | tree-sitter | tree-sitter |
| Go | `.go` | tree-sitter (no types) | tree-sitter (has types) |
| Rust | `.rs` | tree-sitter (no structs/enums) | tree-sitter (has structs/enums) |
| Ruby | `.rb` | **NOT INDEXED** | regex-only |
| Java/C#/PHP/C/C++/Swift/Kotlin/Scala/Vue/Svelte/SQL | various | **NOT INDEXED** | content-only (no functions/classes/imports) |

**Net:** rlmlocal indexes 18 extensions (6 AST + 1 regex (ruby) + 11 content-only).
RGI's compat layer indexes **6, all AST-level**, ignoring everything else.

## 3. Where the projects DIVERGE

1. **RGI has TWO perception paths** (`ast` default vs tree-sitter compat) producing
   different graphs — must be unified before integration.
2. **CodeStructure wire shape differs**: RGI keeps `line`/`span`/`class` metadata +
   full callee text (`structure_extractor.py:112-113`); rlmlocal keeps name arrays +
   rightmost callee identifier (`StructureExtractor.ts:59-64`) + `callSites`
   (function-level calls, RGI lacks).
3. **Import-resolution fidelity**: rlmlocal is family-aware (Go dirs, Rust
   `crate/self/super`, `@/~/` aliases, output-ext stripping); RGI only stem +
   `./../` + `index.ext`.
4. **Reference-graph semantics (the biggest real divergence)**: rlmlocal collapses
   `:id`/`${x}`/`[id]`/`{id}`/`<int:id>` → `*` (`referenceGraph.ts:30`) + has
   three confirmation strategies (registered incl. Django/`@Get`/`#[get]`,
   file-routed Next/Pages, client-discovery); RGI only splits at `<` and has one
   decorator-based strategy. A `fetch('/users/${id}')` + `@app.get('/users/<int:id>')`
   pair connects in rlmlocal's scheme, not RGI's.
5. **Structure-extraction fidelity**: RGI walkers only look at top-level nodes
   (`node.parent == root`) — nested classes, `if __name__`-wrapped defs missed;
   RGI JS misses `const foo = () => {}`; RGI Go/Rust extract no types/classes.
6. **The `${...}` interpolation is NOT a divergence** — data-flow modules are
   byte-for-byte semantic twins (identical op tables, regexes, fan-out cap 12).
7. **TS semantic depth exists only on the rlmlocal side** — `resolveExtractTypes.cjs`
   is the ONLY full-semantic parser, and it speaks tree-sitter coordinates.

## 4. Where they must align for integration

1. **Language-pack tables** — single source of truth; RGI's 6 rows vs rlmlocal's 18
   must be generated from one source, and the code-file universe decided.
2. **CodeStructure ↔ FileStructure wire shape** — pick one schema; decide callee
   semantics (full dotted vs rightmost identifier) — changes every call edge.
3. **Data-flow tables stay in sync** — one shared artifact (generated), not two
   hand-maintained lists.
4. **Reference-graph route normalization** — adopt rlmlocal's `*` collapse + the
   three confirmation strategies.
5. **Canonical perception path** — retire `ast` default or define as Python fallback.
6. **TS type/refactor access** — RGI shells out to `resolveExtractTypes.cjs`.

## 5. Honest gaps

- **Regex where AST would be better**: data-flow + reference graphs match inside
  comments/strings → phantom edges possible. Both projects chose regex for cost.
- **RGI reference graph double-IO**: re-reads files from disk instead of reusing
  parsed structs.
- **RGI `_regex_fallback`** is cruder than rlmlocal's L1 (no per-language branches).
- **Security scanner (RGI-only)**: 8/9 checks are line-regex/substring; SQLi
  detection is "f-string on a line with SQL keywords" — false positives + misses.
- **Missing language support**: no AST-level ruby/java/csharp/php/c/cpp/swift/
  kotlin/scala/vue/svelte/sql in either project.
- **RGI structure-extractor gaps vs rlmlocal**: no `const`-arrow JS, no Go types,
  no Rust struct/enum, top-level-only Python/JS, no `callSites`.
- **`code_parser.py` drops SyntaxError files entirely** — no partial recovery.
