"""Control B: a fixed, hardcoded pipeline with the SAME tools and SAME model
as RGI — parse, run all security tools, one LLM call per module, merge.
No graphs, no spawning, no verification, no correction. Beating THIS (not
the single-shot baseline) is what isolates adaptive topology as the active
ingredient."""
import json
from pathlib import Path

from rgi.tools.registry import ToolRegistry

TOOLS = ("parse_python_file", "check_jwt_usage", "find_hardcoded_secrets", "grep_security_patterns")


async def run_fixed_workflow(path: str, objective: str, llm) -> dict:
    registry = ToolRegistry()
    findings = []
    for py_file in sorted(Path(path).rglob("*.py")):
        tool_results = {}
        for tool in TOOLS:
            tool_results[tool] = await registry.execute(tool, {"path": str(py_file)})
        context = json.dumps(tool_results)[:8000]
        result = await llm.reason(
            f"{objective}\nAnalyze module {py_file.name} using the tool results in context.",
            context,
        )
        findings.append({
            "module": py_file.name,
            "finding": result.get("finding", ""),
            "confidence": float(result.get("confidence", 0.5)),
        })
    avg = sum(f["confidence"] for f in findings) / len(findings) if findings else 0.0
    return {
        "objective": objective,
        "mode": "fixed_workflow",
        "status": "completed",
        "confidence": avg,
        "llm_calls": llm.calls,
        "findings": findings,
    }
