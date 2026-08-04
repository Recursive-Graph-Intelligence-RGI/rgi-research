"""Append-only audit trail. Every harness/engine decision is recorded here."""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events: list[dict] = []

    def record(self, event: str, graph_id: Optional[str] = None, **details) -> dict:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "graph_id": graph_id,
            **details,
        }
        self.events.append(entry)
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry
