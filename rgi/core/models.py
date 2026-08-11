"""RGI data models. The fundamental unit is the Cognitive Graph G = (V, E, S, P)."""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    REASONING = "reasoning"        # LLM-based cognitive work
    MEMORY = "memory"              # Knowledge storage node
    TOOL = "tool"                  # External execution (parser, grep, etc.)
    VERIFICATION = "verification"  # Self-correction, challenge, validate
    GOVERNANCE = "governance"      # Policy check, safety gate
    SIMULATION = "simulation"      # Hypothetical test


class LoopType(str, Enum):
    PLANNING = "planning"
    KNOWLEDGE = "knowledge"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    GOVERNANCE = "governance"
    LEARNING = "learning"


class NodeState(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CORRECTING = "correcting"


class CognitiveNode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: NodeType
    content: str                    # Prompt, code, or data payload
    state: NodeState = NodeState.PENDING
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    activation: float = Field(0.0, ge=0.0, le=1.0)
    history: List[Dict] = []
    policy: Dict = {}
    parent_graph_id: str
    result: Optional[Any] = None
    metadata: Dict = {}


class CognitiveEdge(BaseModel):
    source: str                     # Node ID
    target: str                     # Node ID
    edge_type: Literal["dependency", "flow", "feedback", "triggers", "verifies", "activates", "contains", "imports"]
    weight: float = 1.0
    metadata: Dict = {}


class GraphState(BaseModel):
    objective: str
    status: Literal["running", "completed", "failed", "paused", "evolving"] = "running"
    iteration: int = 0
    max_iterations: int = 10
    confidence_threshold: float = 0.7
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    correction_count: int = 0


class GraphPolicy(BaseModel):
    max_nodes: int = 10
    max_depth: int = 2
    allowed_node_types: List[NodeType] = Field(default_factory=lambda: list(NodeType))
    require_verification: bool = True
    auto_spawn: bool = True
    llm_budget: int = 5


class CognitiveGraph(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    loop_type: LoopType
    nodes: Dict[str, CognitiveNode] = {}
    edges: List[CognitiveEdge] = []
    state: GraphState
    policy: GraphPolicy
    parent_graph_id: Optional[str] = None
    subgraph_ids: List[str] = []
    memory_snapshot: Dict = {}
    spawn_reason: Optional[str] = None
