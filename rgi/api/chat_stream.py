"""Chat-turn streaming wrapper around the RGI engine."""
import tempfile
from pathlib import Path
from typing import AsyncGenerator

from rgi.api.project_store import STORE
from rgi.cli import run_analysis


async def chat_stream(
    project_id: str, message: str, options: dict | None = None
) -> AsyncGenerator[dict, None]:
    """Run a chat turn against a project and yield SSE events.

    Events emitted:
    - ``thinking``: analysis has started.
    - ``filesRead``: files touched by perception (best-effort, currently inferred
      from grounded findings).
    - ``securityFindings``: each grounded finding from the report.
    - ``result``: final summary text.
    - ``error``: if the project is missing or analysis fails.
    """
    project = STORE.get(project_id)
    if project is None:
        yield {"kind": "error", "message": "project not found"}
        return

    path = project.path
    if path is None:
        yield {"kind": "error", "message": "project has no filesystem path"}
        return

    yield {"kind": "thinking", "step": "planning"}
    try:
        output_path = Path(tempfile.gettempdir()) / f"rgi_chat_{project_id}.json"
        report = await run_analysis(
            path=path,
            objective=message,
            output=str(output_path),
            mock=False,
            provider="ollama",
            model=None,
            max_llm_calls=int((options or {}).get("max_llm_calls", 20)),
            max_total_nodes=int((options or {}).get("max_total_nodes", 50)),
        )
    except Exception as exc:
        yield {"kind": "error", "message": str(exc)}
        return

    files_read = set()
    for finding in report.get("findings", []):
        if isinstance(finding, dict) and finding.get("file"):
            files_read.add(finding["file"])
            yield {"kind": "securityFindings", "findings": [finding]}

    if files_read:
        yield {"kind": "filesRead", "paths": sorted(files_read)}

    summary = report.get("summary")
    if not summary:
        summary = f"Completed analysis. Findings: {len(report.get('findings', []))}."
    yield {"kind": "result", "content": summary}
