"""The control condition: a monolithic single agent. One LLM call, the whole
codebase in context, no graphs, no memory, no self-correction. This is the
'single smart neuron' the RGI thesis argues against — the comparison exists
so the claim stays empirical instead of rhetorical."""
from pathlib import Path

MOCK_CAVEAT = (
    "Mock mode is scripted on both sides: this comparison demonstrates the "
    "mechanism (scaffolding vs none), not real reasoning quality. It is "
    "not evidence for the RGI hypothesis — run with a live LLM for that."
)


async def run_baseline(path: str, objective: str, llm) -> dict:
    source = "\n\n".join(
        f"# FILE: {f.name}\n{f.read_text()}"
        for f in sorted(Path(path).glob("*.py"))
    )
    task = f"{objective}\nAnalyze this entire codebase:\n\n{source}"
    result = await llm.reason(task, "")
    return {
        "objective": objective,
        "mode": "single_agent",
        "status": "completed",
        "confidence": float(result.get("confidence", 0.5)),
        "llm_calls": llm.calls,
        "findings": [result],
    }
