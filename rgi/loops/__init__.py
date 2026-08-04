"""Cognitive loops package. Each loop type gets starter nodes from its own
module; the dispatcher is the single entry point used by the Harness."""
from rgi.core.models import CognitiveGraph, LoopType
from rgi.loops import execution, planning, verification

_INITIALIZERS = {
    LoopType.PLANNING: planning.initialize,
    LoopType.EXECUTION: execution.initialize,
    LoopType.VERIFICATION: verification.initialize,
}


def initialize_graph_nodes(graph: CognitiveGraph, proposal: dict) -> None:
    initializer = _INITIALIZERS.get(graph.loop_type, execution.initialize)
    initializer(graph, proposal)
