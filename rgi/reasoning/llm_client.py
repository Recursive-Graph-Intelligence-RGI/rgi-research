"""The LLM is a reasoning primitive inside nodes. It never orchestrates.
Two implementations behind one interface: deterministic mock (tests/demo
without keys) and an OpenAI-compatible real client (Kimi preset by default)."""
import copy
import json
import os
from typing import Callable, Optional

SYSTEM_PROMPT = (
    "You are a specialized reasoning node in a recursive graph intelligence "
    "system. Analyze the given context and return structured JSON: "
    '{"finding": str, "confidence": float (0.0-1.0), "reasoning": str, '
    '"recommended_action": str, "suggested_subgraphs": [str]}. '
    'When asked to challenge a finding, also include "finding_valid": bool. '
    'If you need to inspect the corpus programmatically before concluding, '
    'instead return {"repl_code": str} — Python over FILES (a {filename: '
    'source} dict) and re; print() or set RESULT. You will be re-invoked '
    'with the output. Keep repl_code under 20 lines.'
)


def _resp(finding, confidence, reasoning="", action="", subgraphs=None, **extra):
    return {
        "finding": finding,
        "confidence": confidence,
        "reasoning": reasoning,
        "recommended_action": action,
        "suggested_subgraphs": subgraphs or [],
        **extra,
    }


def default_mock_script() -> dict[str, list[dict]]:
    """Deterministic responses for the demo flow. Order matters: the first
    key found as a substring of the task (lowercased) wins."""
    return {
        "decompose": [_resp(
            "Codebase has 4 auth-related modules requiring analysis", 0.9,
            reasoning="Perception found JWT, session, login, config modules",
            action="spawn_execution_subgraphs",
            subgraphs=["JWT Security Analysis", "Session Management Analysis"],
        )],
        "strict re-analysis": [_resp(
            "Confirmed: JWT tokens never expire (critical) and secret is weak", 0.88,
            reasoning="Strict criteria: missing exp claim + HS256 + short secret",
            action="patch_auth_py",
            subgraphs=["JWT Deep Dive: weak secrets and algorithm confusion"],
        )],
        "challenge": [_resp(
            "Original finding is valid and was under-confident", 0.9,
            reasoning="Missing expiration is unconditionally a vulnerability here",
            action="trigger_correction",
            finding_valid=False,
        )],
        "deep dive": [_resp(
            "Weak secret, algorithm confusion exposure, no refresh rotation", 0.9,
            reasoning="HS256-only + hardcoded short secret + no rotation",
            action="report_findings",
        )],
        "session management analysis": [_resp(
            "Sessions have no timeout and no invalidation on logout", 0.85,
            reasoning="SessionStore never checks age",
            action="add_session_expiry",
        )],
        "jwt security analysis": [_resp(
            "JWT handling may be missing expiration verification", 0.6,
            reasoning="jwt.decode seen; exp handling unclear from surface scan",
            action="verify_finding",
        )],
    }


class MockLLMClient:
    def __init__(self, script: Optional[dict[str, list[dict]]] = None,
                 on_call: Optional[Callable] = None):
        self.script = copy.deepcopy(script) if script is not None else default_mock_script()
        self.on_call = on_call
        self.calls = 0

    async def reason(self, task: str, context: str) -> dict:
        self.calls += 1
        if self.on_call:
            self.on_call()
        lowered = task.lower()
        for key, responses in self.script.items():
            if key in lowered and responses:
                return self._validate(responses.pop(0) if len(responses) > 1 else responses[0])
        return _resp("no finding", 0.5, reasoning="mock fallback", action="none")

    @staticmethod
    def _validate(result: dict) -> dict:
        try:
            conf = float(result.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        result["confidence"] = min(1.0, max(0.0, conf))
        result.setdefault("suggested_subgraphs", [])
        return result


class LLMClient:
    """OpenAI-compatible chat completions with JSON mode. Configure by env:
    RGI_LLM_BASE_URL, RGI_LLM_API_KEY, RGI_LLM_MODEL. The 'kimi' preset is the
    default; any OpenAI-compatible endpoint works via env vars."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None,
                 model: Optional[str] = None, on_call: Optional[Callable] = None):
        self.base_url = (base_url or os.environ.get("RGI_LLM_BASE_URL")
                         or "https://api.moonshot.ai/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("RGI_LLM_API_KEY", "")
        self.model = model or os.environ.get("RGI_LLM_MODEL", "kimi-k2-0711-preview")
        self.on_call = on_call
        self.calls = 0
        self.tokens_prompt = 0
        self.tokens_completion = 0
        self.timeout = float(os.environ.get("RGI_LLM_TIMEOUT", "60"))

    async def reason(self, task: str, context: str) -> dict:
        import httpx

        self.calls += 1
        if self.on_call:
            self.on_call()
        payload = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"CONTEXT:\n{context}\n\nTASK:\n{task}"},
            ],
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            body = resp.json()
            usage = body.get("usage") or {}
            self.tokens_prompt += int(usage.get("prompt_tokens", 0))
            self.tokens_completion += int(usage.get("completion_tokens", 0))
            content = body["choices"][0]["message"]["content"]
        return self._validate(self._parse_json(content))

    @staticmethod
    def _parse_json(content: str) -> dict:
        """Tolerance layer for weak models: strip markdown fences and prose
        around the JSON object before strict parsing (json_repair-lite,
        zero dependencies). Raises JSONDecodeError if truly unparseable."""
        text = content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]
        return json.loads(text)

    @staticmethod
    def _validate(result: dict) -> dict:
        try:
            conf = float(result.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        result["confidence"] = min(1.0, max(0.0, conf))
        result.setdefault("suggested_subgraphs", [])
        return result
