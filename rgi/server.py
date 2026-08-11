"""HTTP service mode for RGI.

Exposes the recursive-graph engine over a local HTTP API so that a Tauri
sidecar or any other client can spawn RGI and run analyses.
"""
import asyncio
import json
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from aiohttp import web

from rgi.api.chat_stream import chat_stream
from rgi.api.project_store import STORE, ProjectStore
from rgi.api.security_stream import security_scan_stream
from rgi.api.snapshot import import_snapshot
from rgi.cli import run_analysis
from rgi.mcp.server import MCPServer

logger = logging.getLogger(__name__)

JobStatus = dict[str, Any]

_LOCALHOST_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _origin_allowed(origin: str) -> bool:
    """Only localhost origins may call this server (DNS-rebinding defense)."""
    try:
        parts = urlsplit(origin)
        return parts.scheme in ("http", "https") and parts.hostname in _LOCALHOST_HOSTS
    except ValueError:
        return False


@web.middleware
async def localhost_guard(request: web.Request, handler):
    """Reject cross-origin / non-localhost requests before they reach a route.

    Host check blocks DNS rebinding (a malicious page resolving to 127.0.0.1
    would send a foreign Host). Origin check is defense in depth for browsers.
    CORS headers are added so localhost pages (PWA dev server, Tauri webview)
    may call the API. SSE responses add their own headers in event_stream.
    """
    host = (request.headers.get("Host", "") or "").split(":")[0].lower()
    if host not in _LOCALHOST_HOSTS:
        return web.json_response({"error": "forbidden_host"}, status=403)
    origin = request.headers.get("Origin")
    if origin and not _origin_allowed(origin):
        return web.json_response({"error": "forbidden_origin"}, status=403)
    resp = await handler(request)
    resp.headers.setdefault("Access-Control-Allow-Origin", "*")
    resp.headers.setdefault("Access-Control-Allow-Headers", "Content-Type, Accept")
    resp.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    return resp


class AnalysisJobStore:
    """In-memory store for active and completed analysis jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobStatus] = {}

    def create(self, payload: dict) -> str:
        job_id = str(uuid.uuid4())[:8]
        self._jobs[job_id] = {
            "id": job_id,
            "status": "pending",
            "payload": payload,
            "progress": [],
            "result": None,
            "error": None,
        }
        return job_id

    def get(self, job_id: str) -> JobStatus | None:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs) -> None:
        job = self._jobs.get(job_id)
        if job is not None:
            job.update(kwargs)

    def append_progress(self, job_id: str, message: str) -> None:
        job = self._jobs.get(job_id)
        if job is not None:
            job["progress"].append(message)


class RGIServer:
    """Local HTTP server wrapping the RGI recursive-graph engine."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8787) -> None:
        self.host = host
        self.port = port
        self.store = AnalysisJobStore()
        self._mcp = MCPServer()
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    def _make_app(self) -> web.Application:
        app = web.Application()
        app.middlewares.append(localhost_guard)
        app.router.add_get("/health", self.health)
        app.router.add_post("/analyze", self.analyze)
        app.router.add_get("/jobs/{job_id}/status", self.status)
        app.router.add_get("/jobs/{job_id}/result", self.result)
        app.router.add_post("/shutdown", self.shutdown)
        app.router.add_post("/mcp", self.mcp)
        app.router.add_get("/v1/projects/{project_id}/status", self.project_status)
        app.router.add_post("/v1/projects/{project_id}/snapshot", self.snapshot)
        app.router.add_post("/v1/projects/{project_id}/chat", self.chat)
        app.router.add_post("/v1/projects/{project_id}/security-scan", self.security_scan)
        app.router.add_post("/v1/projects/{project_id}/exec-result", self.exec_result)
        app.router.add_route("OPTIONS", "/{tail:.*}", self._options)
        return app

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def analyze(self, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid_json"}, status=400)

        path = payload.get("path")
        objective = payload.get("objective")
        if not path or not objective:
            return web.json_response(
                {"error": "missing_path_or_objective"}, status=400
            )

        job_id = self.store.create(payload)
        asyncio.create_task(self._run_job(job_id, payload))
        return web.json_response({"job_id": job_id, "status": "pending"})

    async def _run_job(self, job_id: str, payload: dict) -> None:
        self.store.update(job_id, status="running")
        self.store.append_progress(job_id, "job_started")

        path = payload["path"]
        objective = payload["objective"]
        output_path = Path(tempfile.gettempdir()) / f"rgi_report_{job_id}.json"

        try:
            report = await run_analysis(
                path=path,
                objective=objective,
                output=str(output_path),
                mock=bool(payload.get("mock", False)),
                provider=payload.get("provider", "kimi"),
                model=payload.get("model"),
                max_llm_calls=int(payload.get("max_llm_calls", 20)),
                max_total_nodes=int(payload.get("max_total_nodes", 50)),
                embed=bool(payload.get("embed", False)),
            )
            self.store.update(job_id, status="completed", result=report)
            self.store.append_progress(job_id, "job_completed")
        except Exception as exc:
            logger.exception("analysis failed")
            self.store.update(job_id, status="failed", error=str(exc))
            self.store.append_progress(job_id, f"job_failed: {exc}")

    async def status(self, request: web.Request) -> web.Response:
        job_id = request.match_info["job_id"]
        job = self.store.get(job_id)
        if job is None:
            return web.json_response({"error": "job_not_found"}, status=404)
        return web.json_response({
            "id": job["id"],
            "status": job["status"],
            "progress": job["progress"],
            "error": job["error"],
        })

    async def result(self, request: web.Request) -> web.Response:
        job_id = request.match_info["job_id"]
        job = self.store.get(job_id)
        if job is None:
            return web.json_response({"error": "job_not_found"}, status=404)
        if job["status"] not in ("completed", "failed"):
            return web.json_response(
                {"error": "job_not_finished", "status": job["status"]},
                status=409,
            )
        return web.json_response({
            "id": job["id"],
            "status": job["status"],
            "result": job["result"],
            "error": job["error"],
        })

    async def shutdown(self, request: web.Request) -> web.Response:
        asyncio.create_task(self._stop())
        return web.json_response({"status": "shutting_down"})

    async def snapshot(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid_json"}, status=400)
        project_id = request.match_info["project_id"]
        try:
            project = import_snapshot(data, project_id)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({
            "project_id": project_id,
            "status": "imported",
            "nodes": len(project.graph.nodes),
            "edges": len(project.graph.edges),
        })

    async def project_status(self, request: web.Request) -> web.Response:
        project = STORE.get(request.match_info["project_id"])
        if project is None:
            return web.json_response({"error": "project_not_found"}, status=404)
        return web.json_response({
            "project_id": project.project_id,
            "status": "ready",
            "nodes": len(project.graph.nodes),
            "edges": len(project.graph.edges),
            "last_activity": project.last_activity,
        })

    async def exec_result(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid_json"}, status=400)
        project_id = request.match_info["project_id"]
        project = STORE.get(project_id)
        if project is None:
            return web.json_response({"error": "project_not_found"}, status=404)
        pending = project.graph.memory_snapshot.setdefault("pending_exec_results", {})
        pending[body.get("opId")] = body
        return web.json_response({"status": "received"})

    async def _options(self, request: web.Request) -> web.Response:
        """CORS preflight. The middleware adds the allow headers."""
        return web.Response(status=204)

    async def mcp(self, request: web.Request) -> web.Response:
        return await self._mcp.handle(request)

    def _confine_path(self, project: Any, requested: str | None) -> str | None:
        """Resolve a tool path under the project root; None means the project root.

        Raises ValueError when the project has no filesystem path or the
        requested path escapes the project root.
        """
        project_root = Path(project.path).resolve() if project.path else None
        if requested is None:
            return project.path
        if project_root is None:
            raise ValueError("project has no filesystem path")
        p = Path(requested).resolve()
        try:
            p.relative_to(project_root)
        except ValueError:
            raise ValueError(f"path outside project root: {requested}")
        return str(p)

    async def security_scan(self, request: web.Request) -> web.StreamResponse:
        from rgi.api.sse import event_stream

        try:
            body = await request.json()
        except json.JSONDecodeError:
            body = {}
        project_id = request.match_info["project_id"]
        project = STORE.get(project_id)
        if project is None:
            return web.json_response({"error": "project_not_found"}, status=404)
        try:
            safe_path = self._confine_path(project, body.get("path"))
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return await event_stream(
            request, security_scan_stream(project_id, safe_path)
        )

    async def chat(self, request: web.Request) -> web.StreamResponse:
        from rgi.api.sse import event_stream

        try:
            body = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid_json"}, status=400)
        project_id = request.match_info["project_id"]
        return await event_stream(
            request,
            chat_stream(project_id, body.get("message", ""), body.get("options")),
        )

    async def _stop(self) -> None:
        await asyncio.sleep(0.5)
        if self._runner is not None:
            await self._runner.cleanup()

    async def start(self) -> None:
        app = self._make_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        logger.info("RGI server listening on http://%s:%d", self.host, self.port)

    async def run_forever(self) -> None:
        await self.start()
        while self._site is not None:
            await asyncio.sleep(3600)


async def main(host: str = "127.0.0.1", port: int = 8787) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    server = RGIServer(host=host, port=port)
    await server.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
