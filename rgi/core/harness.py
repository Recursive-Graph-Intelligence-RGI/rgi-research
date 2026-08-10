"""The Harness: safety kernel. Permission-scheduler stance for v0.1
(inhibition-default basal-ganglia stance is v0.3). Holds every graph,
enforces hard limits, approves/rejects every spawn, logs every decision."""
import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from rgi.core.audit import AuditLog
from rgi.core.context_builder import ContextBuilder
from rgi.core.governance import LocalGate
from rgi.core.models import CognitiveGraph, CognitiveNode, GraphPolicy, GraphState, LoopType, NodeType
from rgi.loops import initialize_graph_nodes
from rgi.loops.learning import LearningEngine
from rgi.memory.activation import ActivationEngine
from rgi.reasoning.llm_client import LLMClient
from rgi.tools.registry import ToolRegistry


@dataclass
class HarnessConfig:
    target_path: str = "./sample_project"
    max_llm_calls: int = 20
    max_total_nodes: int = 50
    max_depth: int = 3
    max_seconds: int = 300
    llm_client: object = None
    activation_engine: object = None
    data_dir: str = "data"


class Harness:
    def __init__(self, config: HarnessConfig):
        self.config = config
        self.graphs: dict[str, CognitiveGraph] = {}
        self.total_llm_calls = 0
        self.max_llm_calls = config.max_llm_calls
        self.max_total_nodes = config.max_total_nodes
        self.max_depth = config.max_depth
        self.max_seconds = config.max_seconds
        self.started_at = time.monotonic()
        self.activation_engine = config.activation_engine or ActivationEngine()
        self.context_builder = ContextBuilder()
        self.llm_client = config.llm_client or LLMClient(on_call=self._count_llm_call)
        if config.llm_client is not None:
            self.llm_client.on_call = self._count_llm_call
        self.tool_registry = ToolRegistry()
        self.learning_engine = LearningEngine(f"{config.data_dir}/pathways.json")
        self.audit = AuditLog(f"{config.data_dir}/audit.jsonl")
        self.gate = LocalGate(config.target_path, config.max_llm_calls)
        self.lock = asyncio.Lock()

    def _count_llm_call(self):
        self.total_llm_calls += 1

    def get_graph(self, graph_id: str) -> Optional[CognitiveGraph]:
        return self.graphs.get(graph_id)

    def total_nodes(self) -> int:
        """Nodes counting against the spawn budget: cognitive work graphs only.
        KNOWLEDGE graphs are the inert parsed world model (one node per
        module/class/function), so counting them lets corpus size veto all
        spawning — the L5 collapse: 305 knowledge nodes ate the 200-node
        budget before any work graph was born."""
        return sum(len(g.nodes) for g in self.graphs.values()
                   if g.loop_type != LoopType.KNOWLEDGE)

    def depth_of(self, graph: CognitiveGraph) -> int:
        depth, current = 0, graph
        while current.parent_graph_id:
            depth += 1
            current = self.graphs.get(current.parent_graph_id)
            if current is None:
                break
        return depth

    def time_exceeded(self) -> bool:
        return (time.monotonic() - self.started_at) > self.max_seconds

    async def request_subgraph_spawn(self, parent_id: str, proposal: dict) -> Optional[str]:
        """Evaluate a spawn request. Returns new graph ID or None if rejected.
        The lock protects approval only — graph execution runs unlocked."""
        async with self.lock:
            parent = self.graphs.get(parent_id)
            if parent is None:
                self.audit.record("spawn_rejected", graph_id=parent_id, reason="unknown_parent")
                return None

            depth = self.depth_of(parent) + 1
            if depth >= self.max_depth:
                self.audit.record("spawn_rejected", graph_id=parent_id,
                                  reason="depth_limit", attempted_depth=depth)
                return None

            if self.total_nodes() >= self.max_total_nodes:
                self.audit.record("spawn_rejected", graph_id=parent_id,
                                  reason="node_limit", total_nodes=self.total_nodes())
                return None

            new_graph = CognitiveGraph(
                loop_type=proposal["loop_type"],
                state=GraphState(objective=proposal["objective"]),
                policy=GraphPolicy(
                    max_depth=self.max_depth - depth,
                    auto_spawn=(depth < self.max_depth - 1),
                ),
                parent_graph_id=parent_id,
                spawn_reason=proposal.get("reason", "decomposition"),
            )
            initialize_graph_nodes(new_graph, proposal)
            self.graphs[new_graph.id] = new_graph
            parent.subgraph_ids.append(new_graph.id)
            self.audit.record("spawn_approved", graph_id=new_graph.id,
                              parent=parent_id, loop_type=proposal["loop_type"].value,
                              depth=depth, reason=new_graph.spawn_reason)
            return new_graph.id

    def governance_check(self, graph: CognitiveGraph, node: CognitiveNode) -> bool:
        # TODO: Integrate FortSignal for identity, risk, and policy context
        if node.type == NodeType.REASONING:
            decision = self.gate.check("llm_call", {"calls_so_far": self.total_llm_calls})
        elif node.type == NodeType.TOOL:
            path = node.metadata.get("params", {}).get("path", self.config.target_path)
            decision = self.gate.check("tool_execute", {"path": path})
        else:
            return True
        if not decision.allowed:
            self.audit.record("governance_denied", graph_id=graph.id,
                              node_id=node.id, reason=decision.reason)
        return decision.allowed
