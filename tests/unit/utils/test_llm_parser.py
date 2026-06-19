import pytest

from ai_3d_modeling_agent.utils.llm_parser import extract_json_from_llm


def test_extract_json_from_plain_object() -> None:
    assert extract_json_from_llm('{"status":"ready"}') == {"status": "ready"}


def test_extract_json_from_markdown_json_fence() -> None:
    raw = """```json
{"status":"ready","parts":[]}
```"""
    assert extract_json_from_llm(raw) == {"status": "ready", "parts": []}


def test_extract_json_from_fence_with_surrounding_prose() -> None:
    raw = """Here is the artifact:

```json
{"parts":[{"name":"E2E_Cube"}],"summary":"ok"}
```

Done."""
    assert extract_json_from_llm(raw)["parts"][0]["name"] == "E2E_Cube"


def test_extract_json_prefers_json_fence_over_other_code_fence() -> None:
    raw = """The meeting note:

```text
not json {this would fail}
```

```json
{"summary":"ok"}
```"""
    assert extract_json_from_llm(raw) == {"summary": "ok"}


def test_extract_json_falls_back_to_outer_braces() -> None:
    raw = 'extra text before {"status":"blocked","reason":"missing"} extra after'
    assert extract_json_from_llm(raw) == {"status": "blocked", "reason": "missing"}


def test_extract_json_raises_with_context_label() -> None:
    with pytest.raises(ValueError, match="Builder response is not valid JSON"):
        extract_json_from_llm("not json", context_label="Builder")
