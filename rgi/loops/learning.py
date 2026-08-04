"""Learning engine v0.1: records which topologies led to which outcomes.
v0.3 will use these pathways for Hebbian edge-weight updates — the data
collected here is the training set for that future plasticity."""
import json
from datetime import datetime
from pathlib import Path

from rgi.core.models import CognitiveGraph, NodeState


class LearningEngine:
    def __init__(self, path: str | Path = "data/pathways.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record_pathway(self, graph: CognitiveGraph) -> dict:
        completed = [n for n in graph.nodes.values() if n.state == NodeState.COMPLETED]
        avg = sum(n.confidence for n in completed) / len(completed) if completed else 0.0
        entry = {
            "timestamp": datetime.now().isoformat(),
            "objective": graph.state.objective,
            "loop_type": graph.loop_type.value,
            "topology": {
                "node_types": [n.type.value for n in graph.nodes.values()],
                "edges": [
                    {"source": e.source, "target": e.target, "type": e.edge_type}
                    for e in graph.edges
                ],
            },
            "outcome": graph.state.status,
            "avg_confidence": avg,
        }
        existing = json.loads(self.path.read_text()) if self.path.exists() else []
        existing.append(entry)
        self.path.write_text(json.dumps(existing, indent=2))
        return entry
