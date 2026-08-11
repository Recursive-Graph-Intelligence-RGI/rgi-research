"""In-memory project registry keyed by project_id.

Projects hold a CognitiveGraph built from a snapshot or filesystem path and are
used by the adapter endpoints (chat, security-scan, exec-result).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

from rgi.core.models import CognitiveGraph


@dataclass
class Project:
    project_id: str
    graph: CognitiveGraph
    path: Optional[str] = None
    last_activity: float = field(default_factory=time.time)


class ProjectStore:
    """Thread-safe enough for asyncio: all access happens on the event loop."""

    def __init__(self) -> None:
        self._projects: Dict[str, Project] = {}

    def create(
        self, project_id: str, graph: CognitiveGraph, path: Optional[str] = None
    ) -> Project:
        project = Project(project_id=project_id, graph=graph, path=path)
        self._projects[project_id] = project
        return project

    def get(self, project_id: str) -> Optional[Project]:
        project = self._projects.get(project_id)
        if project is not None:
            project.last_activity = time.time()
        return project

    def delete(self, project_id: str) -> bool:
        return self._projects.pop(project_id, None) is not None

    def list_ids(self) -> list[str]:
        return list(self._projects.keys())


# Global store used by the HTTP server. Tests may replace this singleton.
STORE = ProjectStore()
