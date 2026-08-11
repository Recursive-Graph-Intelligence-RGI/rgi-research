"""Optional frontier-model integration layer for RGI.

Local recursive graphs do the work. The frontier is invoked only at
high-leverage inflection points: initial planning, deadlock arbitration,
and final synthesis. All calls are optional and fall back to local logic
on failure or when disabled.
"""
import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from rgi.reasoning.llm_client import LLMClient


class PlanResult(BaseModel):
    strategy: str
    initial_subgraph_objectives: list[str]
    focus_areas: list[str]
    expected_findings: list[str] = []


class ArbitrationResult(BaseModel):
    decision: str = Field(..., pattern="^(respawn|merge|drop|escalate|noop)$")
    reasoning: str
    spawn_objectives: list[str] = []
    findings_to_drop: list[str] = []
    escalate_to_user: bool = False


class SynthesisResult(BaseModel):
    summary: str
    findings: list[dict]
    confidence: float = Field(..., ge=0.0, le=1.0)
    recommendations: list[str] = []


@dataclass
class FrontierConfig:
    enabled: bool = False
    provider: str = "kimi"
    model: str | None = None
    plan_at_start: bool = True
    arbitrate_on_deadlock: bool = True
    synthesize_at_end: bool = True
    max_arbitration_calls: int = 2


class FrontierIntegration:
    def __init__(self, config: FrontierConfig, llm_client: Any = None):
        self.config = config
        self.llm_client = llm_client or LLMClient(model=config.model)

    async def plan_root(self, objective: str, world_model: dict[str, Any]) -> PlanResult | None:
        if not self.config.enabled or not self.config.plan_at_start:
            return None
        prompt = (
            "You are the strategic planner for a recursive code-intelligence engine. "
            "Given the objective and a condensed world model, produce a concise plan. "
            "Return strictly JSON matching this schema:\n"
            '{"strategy": str, "initial_subgraph_objectives": [str], '
            '"focus_areas": [str], "expected_findings": [str]}\n\n'
            f"Objective: {objective}\n\n"
            f"World model keys: {list(world_model.keys())}\n"
            f"World model summary: {json.dumps(world_model, default=str)[:4000]}"
        )
        try:
            raw = await self.llm_client.reason("Plan root investigation strategy", prompt)
            return PlanResult.model_validate(raw)
        except Exception as exc:
            return PlanResult(
                strategy=f"frontier plan failed: {exc}",
                initial_subgraph_objectives=[],
                focus_areas=[],
            )

    async def arbitrate(self, state: dict[str, Any]) -> ArbitrationResult | None:
        if not self.config.enabled or not self.config.arbitrate_on_deadlock:
            return None
        return ArbitrationResult(decision="noop", reasoning="frontier not yet implemented")

    async def synthesize(self, graph_state: dict[str, Any], findings: list[dict]) -> SynthesisResult | None:
        if not self.config.enabled or not self.config.synthesize_at_end:
            return None
        return SynthesisResult(
            summary="local synthesis fallback",
            findings=findings,
            confidence=0.5,
        )
