"""Load prompt templates from Markdown files.

Prompt bodies are stored as Markdown so they can be edited outside code
while still being sent to the LLM as plain strings.
"""

from __future__ import annotations

from functools import lru_cache
import re
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parent
_VAR_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")
_USER_HEADER = re.compile(r"^##\s*User\s*$", re.IGNORECASE | re.MULTILINE)
_ASSISTANT_HEADER = re.compile(r"^##\s*Assistant\s*$", re.IGNORECASE | re.MULTILINE)
_CODE_FENCE_PATTERN = re.compile(r"^```[a-zA-Z0-9_-]*\s*[\r\n]+(?P<body>.*?)[\r\n]+```\s*$", re.DOTALL)


def prompt_template_path(relative_path: str) -> Path:
    return _ROOT / relative_path


@lru_cache(maxsize=None)
def read_markdown_prompt(relative_path: str) -> str:
    path = prompt_template_path(relative_path)
    return path.read_text(encoding="utf-8").strip()


def load_markdown_prompt(relative_path: str, **variables: Any) -> str:
    template = read_markdown_prompt(relative_path)
    if not variables:
        return template
    return _VAR_PATTERN.sub(lambda match: _resolve_variable(match.group(1), variables), template)


def load_chat_examples(relative_path: str) -> list[dict[str, str]]:
    raw = read_markdown_prompt(relative_path)
    blocks = [block.strip() for block in re.split(r"^\s*---+\s*$", raw, flags=re.MULTILINE) if block.strip()]
    examples: list[dict[str, str]] = []
    for block in blocks:
        user_match = _USER_HEADER.search(block)
        assistant_match = _ASSISTANT_HEADER.search(block)
        if not user_match or not assistant_match or assistant_match.start() <= user_match.end():
            raise ValueError(f"Invalid chat example block in {relative_path!r}")
        user_content = block[user_match.end():assistant_match.start()].strip()
        assistant_content = block[assistant_match.end():].strip()
        assistant_content = _strip_optional_code_fence(assistant_content)
        examples.append({"role": "user", "content": user_content})
        examples.append({"role": "assistant", "content": assistant_content})
    return examples


def _resolve_variable(name: str, variables: dict[str, Any]) -> str:
    if name not in variables:
        raise KeyError(f"Missing prompt template variable: {name}")
    value = variables[name]
    if value is None:
        return ""
    return str(value)


def _strip_optional_code_fence(value: str) -> str:
    match = _CODE_FENCE_PATTERN.match(value.strip())
    if not match:
        return value.strip()
    return match.group("body").strip()
