from rgi.reasoning.llm_client import MockLLMClient, default_mock_script


async def test_mock_matches_by_keyword_and_counts_calls():
    calls = []
    client = MockLLMClient(on_call=lambda: calls.append(1))
    result = await client.reason("Decompose objective into subgraphs: analyze auth", "")
    assert result["suggested_subgraphs"]
    assert len(calls) == 1


async def test_mock_script_sequence_pops_then_repeats_last():
    script = {"jwt": [
        {"finding": "first", "confidence": 0.6, "reasoning": "", "recommended_action": "", "suggested_subgraphs": []},
        {"finding": "second", "confidence": 0.88, "reasoning": "", "recommended_action": "", "suggested_subgraphs": []},
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
    challenge = await client.reason("challenge finding: jwt security analysis", "")
    assert challenge["finding_valid"] is False
    strict = await client.reason("strict re-analysis: jwt security analysis", "")
    assert strict["confidence"] >= 0.8
    session = await client.reason("analyze findings for session management analysis", "")
    assert session["confidence"] >= 0.7
