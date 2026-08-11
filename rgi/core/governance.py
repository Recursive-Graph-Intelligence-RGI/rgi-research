"""Governance gate: deterministic enforcement, outside the reasoning layer.

FortSignal (https://fortsignal.com) is the Phase 2 external enforcement
boundary: cryptographic intent binding + delegation caps + signed receipts.
v0.1 ships the interface and a local deterministic gate only.
"""
import json
import os
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
    """Deterministic offline gate.

    Loads policy from an optional JSON file (``RGI_POLICY_FILE``) and enforces:

    - ``llm_call``: capped by ``max_llm_calls``.
    - ``tool_execute``: path must stay under ``allowed_root`` and the tool must
      be in ``allowed_tools`` and not in ``denied_tools``.
    - ``spawn``: allowed only if ``allow_spawn`` is true and depth <= ``max_depth``.

    Unknown actions are allowed by default so the engine keeps working while
    policy coverage is partial.
    """

    def __init__(self, allowed_root: str, max_llm_calls: int = 20,
                 policy_path: str | None = None, policy: dict | None = None):
        self.allowed_root = Path(allowed_root).resolve()
        self.max_llm_calls = max_llm_calls
        self.policy = policy if policy is not None else self._load_policy(policy_path)

    def _load_policy(self, policy_path: str | None) -> dict:
        path = policy_path or os.environ.get("RGI_POLICY_FILE")
        if not path:
            return {}
        try:
            return json.loads(Path(path).read_text())
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid policy file {path}: {exc}") from exc

    def _tool_path(self, params: dict) -> Path:
        """Return the filesystem path a tool targets, if any."""
        raw = params.get("path") or params.get("root") or ""
        return Path(raw).resolve() if raw else self.allowed_root

    def _path_allowed(self, path: Path) -> bool:
        try:
            path.relative_to(self.allowed_root)
            return True
        except ValueError:
            return False

    def _tool_allowed(self, tool_name: str) -> bool:
        allowed = self.policy.get("allowed_tools")
        if isinstance(allowed, list) and tool_name not in allowed:
            return False
        denied = self.policy.get("denied_tools", [])
        if isinstance(denied, list) and tool_name in denied:
            return False
        return True

    def _permissions_allowed(self, permissions: set[str]) -> bool:
        """Check tool permission class against policy.

        By default all permissions are allowed. Policy can set
        ``allowed_permissions`` (whitelist) or ``denied_permissions`` (blacklist).
        """
        allowed = self.policy.get("allowed_permissions")
        if isinstance(allowed, list) and not permissions.issubset(set(allowed)):
            return False
        denied = self.policy.get("denied_permissions", [])
        if isinstance(denied, list) and permissions.intersection(denied):
            return False
        return True

    def check(self, action: str, params: dict) -> GateDecision:
        if action == "llm_call":
            budget = self.policy.get("max_llm_calls", self.max_llm_calls)
            if params.get("calls_so_far", 0) >= budget:
                return GateDecision(False, "llm_budget_exhausted")
            return GateDecision(True)

        if action == "tool_execute":
            tool_name = params.get("tool", "")
            if not self._tool_allowed(tool_name):
                return GateDecision(False, f"tool_denied:{tool_name}")

            permissions = set(params.get("permissions", []))
            if not self._permissions_allowed(permissions):
                denied = permissions - set(self.policy.get("allowed_permissions", []))
                return GateDecision(False, f"permission_denied:{','.join(sorted(denied)) or 'policy'}")

            target = self._tool_path(params)
            if not self._path_allowed(target):
                return GateDecision(False, "path_outside_scope")
            return GateDecision(True)

        if action == "spawn":
            if not self.policy.get("allow_spawn", True):
                return GateDecision(False, "spawn_disabled")
            depth = params.get("depth", 0)
            max_depth = self.policy.get("max_depth")
            if isinstance(max_depth, int) and depth > max_depth:
                return GateDecision(False, "depth_limit")
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
