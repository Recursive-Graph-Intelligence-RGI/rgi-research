"""Governance gate: deterministic enforcement, outside the reasoning layer.

FortSignal (https://fortsignal.com) is the Phase 2 external enforcement
boundary: cryptographic intent binding + delegation caps + signed receipts.
v0.1 ships the interface and a local deterministic gate only.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class GateDecision:
    allowed: bool
    reason: str = "ok"


class GovernanceGate(Protocol):
    def check(self, action: str, params: dict) -> GateDecision: ...


class LocalGate:
    """Deterministic offline gate. Tool paths must stay under allowed_root;
    LLM calls are capped by budget."""

    def __init__(self, allowed_root: str, max_llm_calls: int = 20):
        self.allowed_root = Path(allowed_root).resolve()
        self.max_llm_calls = max_llm_calls

    def check(self, action: str, params: dict) -> GateDecision:
        if action == "llm_call":
            if params.get("calls_so_far", 0) >= self.max_llm_calls:
                return GateDecision(False, "llm_budget_exhausted")
            return GateDecision(True)
        if action == "tool_execute":
            path = Path(params.get("path", "")).resolve()
            try:
                path.relative_to(self.allowed_root)
            except ValueError:
                return GateDecision(False, "path_outside_scope")
            return GateDecision(True)
        return GateDecision(True)


class FortSignalGate:
    """Phase 2 adapter stub. Will map spawn/tool/llm actions to FortSignal
    challenge/verify and write receipts (signalId, policyId, deny reasons)
    into the audit log. Requires FORTSIGNAL_API_KEY + agent credentials."""

    def __init__(self, api_key: str | None = None, agent_id: str | None = None):
        self.api_key = api_key
        self.agent_id = agent_id

    def check(self, action: str, params: dict) -> GateDecision:
        raise NotImplementedError("FortSignal integration is Phase 2")
