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
    decision: str = Field(..., pattern="^(respawn|drop|noop)$")
    reasoning: str
    spawn_objectives: list[str] = []
    findings_to_drop: list[str] = []


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
        raw = await self.llm_client.reason("Plan root investigation strategy", prompt)
        return PlanResult.model_validate(raw)

    async def arbitrate(self, state: dict[str, Any]) -> ArbitrationResult | None:
        if not self.config.enabled or not self.config.arbitrate_on_deadlock:
            return None
        prompt = (
            "You are an arbitration judge in a recursive code-intelligence engine. "
            "Local subgraphs have produced the following state. Decide how to proceed. "
            "Return strictly JSON matching this schema:\n"
            '{"decision": "respawn|merge|drop|escalate|noop", "reasoning": str, '
            '"spawn_objectives": [str], "findings_to_drop": [str], "escalate_to_user": bool}\n\n'
            f"State: {json.dumps(state, default=str)[:6000]}"
        )
        raw = await self.llm_client.reason("Arbitrate local deadlock", prompt)
        return ArbitrationResult.model_validate(raw)

    async def synthesize(self, graph_state: dict[str, Any], findings: list[dict]) -> SynthesisResult | None:
        if not self.config.enabled or not self.config.synthesize_at_end:
            return None
        prompt = (
            "You are the final report synthesizer for a recursive code-intelligence engine. "
            "Given the converged graph state and a list of grounded findings, produce the final report. "
            "Return strictly JSON matching this schema:\n"
            '{"summary": str, "findings": [{"kind": str, "severity": str, "detail": str, '
            '"file": str, "line": int, "symbol": str, "confidence": float}], '
            '"confidence": float (0.0-1.0), "recommendations": [str]}\n\n'
            f"Graph state: {json.dumps(graph_state, default=str)[:2000]}\n\n"
            f"Findings: {json.dumps(findings, default=str)[:6000]}"
        )
        raw = await self.llm_client.reason("Synthesize final report", prompt)
        return SynthesisResult.model_validate(raw)
