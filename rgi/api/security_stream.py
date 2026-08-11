"""Streaming deterministic security scan endpoint."""
from typing import AsyncGenerator

from rgi.api.project_store import STORE
from rgi.tools.security_scan import run_security_scan


async def security_scan_stream(
    project_id: str, override_path: str | None = None
) -> AsyncGenerator[dict, None]:
    """Yield SSE events for the deterministic security scanner.

    Emits ``thinking`` at start, ``securityFindings`` if any issues are found,
    and a ``result`` event with the issue count.
    """
    project = STORE.get(project_id)
    if project is None:
        yield {"kind": "error", "message": "project not found"}
        return

    path = override_path or project.path
    if path is None:
        yield {"kind": "error", "message": "project has no filesystem path"}
        return

    yield {"kind": "thinking", "step": "security_scan_started"}
    findings = run_security_scan(path)
    if findings:
        yield {"kind": "securityFindings", "findings": findings}
    yield {"kind": "result", "content": f"Found {len(findings)} issue(s)."}
