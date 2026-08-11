"""Deterministic security-analysis tools. Tools are neurons too: structured
output with confidence, no orchestration.

This module now builds the ToolRegistry on top of the unified tool harness
(`rgi.tools.harness`). Each local tool declares a schema, domain, and
permission set so governance and the LLM prompt can reason about it.
"""
import ast
import contextlib
import io
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rgi.tools.filesystem import find_files, list_dir, stat_file
from rgi.tools.grounded_repl import callers, grep, read_file
from rgi.tools.harness import LocalToolProvider, Tool, ToolRegistry as _ToolRegistry
from rgi.tools.security_scan import run_security_scan
from rgi.tools.verify import run_py_compile, run_pyflakes, run_pytest

_SECRET_RE = re.compile(
    r"""(?P<name>[A-Z_]*(?:SECRET|API_KEY|TOKEN|PASSWORD|DATABASE_URL)[A-Z_]*)\s*=\s*["'](?P<value>[^"']{6,})["']"""
)

# Sandboxed REPL builtins for explore_corpus (RLM-style corpus exploration).
# No open/__import__/eval/exec — the corpus is the only input, stdout/RESULT
# the only output. TODO: FortSignal boundary for production code-exec policy.
def _safe_builtins() -> dict:
    import builtins
    return {k: getattr(builtins, k) for k in (
        "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
        "int", "isinstance", "len", "list", "map", "max", "min", "print",
        "range", "repr", "round", "set", "sorted", "str", "sum", "tuple", "zip",
        "Exception", "ValueError", "KeyError", "IndexError", "TypeError",
    )}


def _read_source(path: str) -> str:
    """Tools accept a file OR a directory (all *.py files concatenated)."""
    p = Path(path)
    if p.is_dir():
        return "\n".join(f.read_text() for f in sorted(p.rglob("*.py")))
    return p.read_text()


def _py_files(path: str) -> list:
    p = Path(path)
    return sorted(p.rglob("*.py")) if p.is_dir() else [p]


def _parse_python_file(params: dict) -> dict:
    classes, functions, imports = [], [], []
    for py_file in _py_files(params["path"]):
        tree = ast.parse(py_file.read_text())
        classes.extend(n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
        functions.extend(n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
        imports.extend(
            a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
        )
    # Full labeled source, not a 4k fragment: Run 9 showed reasoning
    # nodes starved when files past the alphabetical cut vanished.
    max_chars = int(params.get("max_chars", 30000))
    sections = [
        f"===== {py_file.name} =====\n{py_file.read_text()}"
        for py_file in _py_files(params["path"])
    ]
    source_excerpt = "\n\n".join(sections)
    if len(source_excerpt) > max_chars:
        source_excerpt = source_excerpt[:max_chars] + "\n[...truncated]"
    return {
        "findings": [{"classes": classes, "functions": functions,
                      "imports": imports, "source_excerpt": source_excerpt}],
        "confidence": 1.0,
    }


def _grep_security_patterns(params: dict) -> dict:
    text = _read_source(params["path"])
    keywords = params.get("keywords", ["jwt", "session", "password", "secret", "token"])
    findings = [
        {"kind": "keyword_hit", "keyword": k, "line": i + 1}
        for i, line in enumerate(text.splitlines())
        for k in keywords
        if k in line.lower()
    ]
    return {"findings": findings, "confidence": 0.75}


def _check_jwt_usage(params: dict) -> dict:
    text = _read_source(params["path"])
    findings = []
    if "jwt.decode" in text:
        exp_checked = '"exp"' in text or "verify_exp" in text or "expired" in text.lower()
        if not exp_checked:
            findings.append({
                "kind": "jwt_decode_without_exp_check",
                "severity": "high",
                "detail": "jwt.decode called without any expiration verification",
            })
    if re.search(r"algorithms\s*=\s*\[\s*[\"']HS256[\"']\s*\]", text):
        findings.append({
            "kind": "jwt_hs256_only",
            "severity": "medium",
            "detail": "Only HS256 allowed; check for algorithm confusion exposure",
        })
    return {"findings": findings, "confidence": 0.8}


def _find_hardcoded_secrets(params: dict) -> dict:
    text = _read_source(params["path"])
    findings = [
        {"kind": "hardcoded_secret", "name": m.group("name"), "line": text[: m.start()].count("\n") + 1}
        for m in _SECRET_RE.finditer(text)
    ]
    return {"findings": findings, "confidence": 0.9}


def _explore_corpus(params: dict) -> dict:
    """RLM-style REPL: the model writes Python over FILES (a
    {filename: source} dict) and `re`, instead of us guessing which
    fixed tool fits. Sandboxed: safe builtins only, 10s timeout,
    12k output cap. Scales where a fixed source dump cannot."""
    code = str(params.get("code", ""))
    corpus = {f.name: f.read_text() for f in _py_files(params["path"])}
    namespace = {"FILES": corpus, "re": re, "__builtins__": _safe_builtins()}

    def _run():
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exec(code, namespace)  # noqa: S102 — sandboxed namespace by design
        return buf.getvalue(), namespace.get("RESULT")

    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            stdout, result = pool.submit(_run).result(timeout=10)
        except Exception as exc:
            return {"findings": [{"kind": "repl_error", "detail": str(exc)[:500]}],
                    "confidence": 0.3}
    output = stdout
    if result is not None:
        output += f"\nRESULT: {result}"
    return {"findings": [{"kind": "repl_output", "output": output[:12000]}],
            "confidence": 0.9}


def _security_scan(params: dict) -> dict:
    return {
        "findings": run_security_scan(params["path"]),
        "confidence": 0.95,
    }


# Tool descriptors for the local provider. Schemas are OpenAI/MCP-compatible.
_LOCAL_TOOLS = [
    Tool(
        name="parse_python_file",
        description="Parse Python file(s) and return classes, functions, imports, and source excerpt.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}, "max_chars": {"type": "integer"}}, "required": ["path"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read"},
        handler=_parse_python_file,
    ),
    Tool(
        name="grep_security_patterns",
        description="Search source for security-related keywords.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}, "keywords": {"type": "array", "items": {"type": "string"}}}, "required": ["path"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read"},
        handler=_grep_security_patterns,
    ),
    Tool(
        name="check_jwt_usage",
        description="Check for weak JWT decode patterns.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read"},
        handler=_check_jwt_usage,
    ),
    Tool(
        name="find_hardcoded_secrets",
        description="Find hardcoded secret literals in Python source.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read"},
        handler=_find_hardcoded_secrets,
    ),
    Tool(
        name="explore_corpus",
        description="Run sandboxed Python over the corpus. Provide code that uses FILES (dict filename->source) and re. Output via print() or set RESULT.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}, "code": {"type": "string"}}, "required": ["path", "code"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read", "exec"},
        handler=_explore_corpus,
    ),
    Tool(
        name="read_file",
        description="Read a file from the project. Optionally bound line_start/line_end.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}, "line_start": {"type": "integer"}, "line_end": {"type": "integer"}}, "required": ["path"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read"},
        handler=read_file,
    ),
    Tool(
        name="grep",
        description="Search files under root matching glob for a regex pattern.",
        input_schema={"type": "object", "properties": {"root": {"type": "string"}, "pattern": {"type": "string"}, "glob": {"type": "string"}}, "required": ["root", "pattern"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read"},
        handler=grep,
    ),
    Tool(
        name="callers",
        description="Find import-graph edges that mention a symbol.",
        input_schema={"type": "object", "properties": {"symbol": {"type": "string"}, "import_graph_edges": {"type": "array"}}, "required": ["symbol"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read"},
        handler=callers,
    ),
    Tool(
        name="run_py_compile",
        description="Compile Python source to check for syntax errors.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read", "exec"},
        handler=run_py_compile,
    ),
    Tool(
        name="run_pytest",
        description="Run pytest for the project or file.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read", "exec"},
        handler=run_pytest,
    ),
    Tool(
        name="run_pyflakes",
        description="Run pyflakes static analysis on Python source.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read", "exec"},
        handler=run_pyflakes,
    ),
    Tool(
        name="list_dir",
        description="List files and directories under a path.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read"},
        handler=list_dir,
    ),
    Tool(
        name="find_files",
        description="Recursively find files matching a glob pattern.",
        input_schema={"type": "object", "properties": {"root": {"type": "string"}, "pattern": {"type": "string"}}, "required": ["root"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read"},
        handler=find_files,
    ),
    Tool(
        name="stat",
        description="Return metadata for a file or directory.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read"},
        handler=stat_file,
    ),
    Tool(
        name="security_scan",
        description="Run deterministic security scanners over the target path.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read"},
        handler=_security_scan,
        verifier={
            "objective_template": "Verify security finding {kind} at {file}:{line}",
            "loop_type": "verification",
        },
    ),
]


class ToolRegistry:
    """Backward-compatible registry built on the unified tool harness."""

    def __init__(self):
        provider = LocalToolProvider(_LOCAL_TOOLS)
        self._registry = _ToolRegistry()
        self._registry.register_provider(provider)

    @property
    def tools(self) -> dict[str, Any]:
        """Backward-compatible mapping of tool name to descriptor/handler."""
        return self._registry.list_tools()

    async def execute(self, tool_name: str, params: dict) -> dict:
        return await self._registry.execute(tool_name, params)

    def list_tools(self) -> dict:
        """Return tool descriptors keyed by name."""
        return self._registry.list_tools()

    def list_tools_for_prompt(self) -> list[dict]:
        """Return OpenAI/MCP-style function signatures for the system prompt."""
        return self._registry.list_tools_for_prompt()

    def get_tool(self, tool_name: str):
        """Return the Tool descriptor for a named tool."""
        return self._registry.get_tool(tool_name)
