from rgi.reasoning.llm_client import MockLLMClient, default_mock_script


async def test_mock_matches_by_keyword_and_counts_calls():
    calls = []
    client = MockLLMClient(on_call=lambda: calls.append(1))
    result = await client.reason("Decompose objective into subgraphs: analyze auth", "")
    assert result["suggested_subgraphs"]
    assert len(calls) == 1


async def test_mock_script_sequence_pops_then_repeats_last():
    script = {"jwt": [
        {"finding": {"kind": "vulnerability", "severity": "medium", "detail": "first",
                     "file": "auth.py", "line": 1, "symbol": "verify"},
         "confidence": 0.6, "reasoning": "", "recommended_action": "", "suggested_subgraphs": []},
        {"finding": {"kind": "vulnerability", "severity": "high", "detail": "second",
                     "file": "auth.py", "line": 2, "symbol": "verify"},
         "confidence": 0.88, "reasoning": "", "recommended_action": "", "suggested_subgraphs": []},
    ]}
    client = MockLLMClient(script=script)
    r1 = await client.reason("jwt task", "")
    r2 = await client.reason("jwt task", "")
    r3 = await client.reason("jwt task", "")
    assert (r1["confidence"], r2["confidence"], r3["confidence"]) == (0.6, 0.88, 0.88)


async def test_mock_default_fallback():
    client = MockLLMClient(script={})
    result = await client.reason("no key matches", "")
    assert result["confidence"] == 0.5
    assert result["suggested_subgraphs"] == []


async def test_default_script_covers_demo_flow():
    client = MockLLMClient()
    plan = await client.reason("decompose objective: analyze authentication security", "")
    assert len(plan["suggested_subgraphs"]) >= 2
    jwt = await client.reason("analyze findings for jwt security analysis", "")
    assert jwt["confidence"] < 0.7                     # triggers correction
    assert isinstance(jwt["finding"], dict)
    assert jwt["finding"].get("file")
    assert jwt["finding"].get("line")
    challenge = await client.reason("challenge finding: jwt security analysis", "")
    assert challenge["finding_valid"] is False
    strict = await client.reason("strict re-analysis: jwt security analysis", "")
    assert strict["confidence"] >= 0.8
    assert isinstance(strict["finding"], dict)
    session = await client.reason("analyze findings for session management analysis", "")
    assert session["confidence"] >= 0.7
    assert isinstance(session["finding"], dict)


def test_llm_client_timeout_configurable_via_env(monkeypatch):
    """Local small models can exceed 60s per call (live smoke Run 5 cap:
    ReadTimeout in run_fixed_workflow on nemotron-3-nano:4b). The timeout
    must be configurable so slow local endpoints don't kill eval runs."""
    from rgi.reasoning.llm_client import LLMClient
    monkeypatch.delenv("RGI_LLM_TIMEOUT", raising=False)
    assert LLMClient().timeout == 60.0
    monkeypatch.setenv("RGI_LLM_TIMEOUT", "300")
    assert LLMClient().timeout == 300.0
