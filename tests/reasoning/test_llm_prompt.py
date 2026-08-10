from rgi.reasoning.llm_client import SYSTEM_PROMPT


def test_prompt_requires_grounding():
    assert "file" in SYSTEM_PROMPT.lower() or "line" in SYSTEM_PROMPT.lower()
    assert "repl_code" in SYSTEM_PROMPT


def test_prompt_example_is_structured():
    """The prompt example must show a structured finding dict, not a plain str."""
    assert '"kind"' in SYSTEM_PROMPT
    assert '"file"' in SYSTEM_PROMPT
    assert '"line"' in SYSTEM_PROMPT
