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

from aiohttp import web

from rgi.api.project_store import STORE, ProjectStore
from rgi.api.snapshot import import_snapshot
from rgi.cli import run_analysis

logger = logging.getLogger(__name__)

JobStatus = dict[str, Any]


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
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    def _make_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/health", self.health)
        app.router.add_post("/analyze", self.analyze)
        app.router.add_get("/jobs/{job_id}/status", self.status)
        app.router.add_get("/jobs/{job_id}/result", self.result)
        app.router.add_post("/shutdown", self.shutdown)
        app.router.add_get("/v1/projects/{project_id}/status", self.project_status)
        app.router.add_post("/v1/projects/{project_id}/snapshot", self.snapshot)
        app.router.add_post("/v1/projects/{project_id}/chat", self.chat)
        app.router.add_post("/v1/projects/{project_id}/security-scan", self.security_scan)
        app.router.add_post("/v1/projects/{project_id}/exec-result", self.exec_result)
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

    async def security_scan(self, request: web.Request) -> web.StreamResponse:
        # Placeholder until Task 1.4 imports the real implementation.
        from rgi.api.sse import event_stream

        async def _fallback():
            yield {"kind": "error", "message": "security_scan not yet implemented"}

        return await event_stream(request, _fallback())

    async def chat(self, request: web.Request) -> web.StreamResponse:
        # Placeholder until Task 1.3 imports the real implementation.
        from rgi.api.sse import event_stream

        async def _fallback():
            yield {"kind": "error", "message": "chat not yet implemented"}

        return await event_stream(request, _fallback())

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
