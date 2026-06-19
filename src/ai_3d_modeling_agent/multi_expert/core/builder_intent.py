"""Parser for one-step Builder Markdown operation intent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


SUPPORTED_INTENTS = {"create", "place", "material"}
CREATE_WORDS = ("create", "build", "generate", "procedural", "primitive", "mesh", "geometry")
PLACE_WORDS = ("place", "move", "position", "locate", "translate", "assemble")


@dataclass
class BuilderIntent:
    intent: str
    target: str
    parameters: dict[str, Any] = field(default_factory=dict)
    validation: str = ""
    raw_markdown: str = ""


def parse_builder_intent(markdown: str, *, expected_intent: str = "") -> BuilderIntent:
    sections = _sections(markdown)
    raw_intent = (
        _first_value(sections, "operation")
        or _first_value(sections, "intent")
        or _first_value(sections, "action")
        or _first_value(sections, "tool plan")
    )
    intent = _normalize_intent(raw_intent, expected_intent=expected_intent)
    target = _first_value(sections, "target")
    params = _parse_parameters(sections.get("parameters", ""))
    validation = sections.get("validation", "").strip()
    if not intent and not target and not params:
        salvaged = _parse_task_call_prompt(markdown)
        if salvaged is not None:
            return salvaged
    if intent not in SUPPORTED_INTENTS:
        raise ValueError(f"Unsupported builder intent: {raw_intent or intent or '(missing)'}")
    if not target:
        raise ValueError("Builder intent requires a Target section")
    return BuilderIntent(intent=intent, target=target, parameters=params, validation=validation, raw_markdown=markdown)


def _normalize_intent(raw_intent: str, *, expected_intent: str = "") -> str:
    expected = str(expected_intent or "").strip().lower()
    text = _decode_escaped_text(str(raw_intent or "")).strip().lower()
    if text in SUPPORTED_INTENTS:
        return text
    if expected in SUPPORTED_INTENTS and text:
        if expected == "create" and any(word in text for word in CREATE_WORDS):
            return "create"
        if expected == "place" and any(word in text for word in PLACE_WORDS):
            return "place"
        if expected == "material" and "material" in text:
            return "material"
    if any(word in text for word in CREATE_WORDS):
        return "create"
    if any(word in text for word in PLACE_WORDS):
        return "place"
    if "material" in text:
        return "material"
    return text


def _parse_task_call_prompt(markdown: str) -> BuilderIntent | None:
    """Salvage AO responses that echoed a Task call instead of the Builder result.

    This intentionally accepts only explicit, executable fields from the echoed
    prompt. It does not infer missing Blender actions.
    """
    text = _decode_escaped_text(str(markdown or ""))
    if "task(" not in text or "subagent_type=\"builder\"" not in text:
        return None
    action = _field_value(text, "Action").lower()
    if action.startswith("create"):
        intent = "create"
    elif action.startswith("place"):
        intent = "place"
    else:
        return None
    target = _field_value(text, "Target Name") or _field_value(text, "Target")
    if not target:
        return None
    params: dict[str, Any] = {}
    primitive = _field_value(text, "Primitive Type")
    if primitive:
        params["primitive_type"] = primitive.lower()
    instance_count = _field_value(text, "Instance Count")
    if instance_count:
        params["instance_count"] = _parse_scalar(instance_count)
    scale = _field_value(text, "Scale")
    if scale:
        params["scale"] = _parse_scalar(scale)
    location = _field_value(text, "Location")
    if location:
        params["location"] = _parse_scalar(location)
    rotation = _field_value(text, "Rotation")
    if rotation:
        params["rotation_degrees"] = _parse_scalar(rotation)
    if intent == "create" and ("primitive_type" not in params or "scale" not in params):
        return None
    return BuilderIntent(
        intent=intent,
        target=target.strip().lower(),
        parameters=params,
        validation="Parsed from echoed AO Task call prompt.",
        raw_markdown=markdown,
    )


def _decode_escaped_text(text: str) -> str:
    decoded = text.replace("\\n", "\n").replace('\\"', '"')
    decoded = decoded.replace("\\t", "\t")
    return decoded


def _field_value(text: str, label: str) -> str:
    pattern = re.compile(rf"\*\*\s*{re.escape(label)}\s*:\s*\*\*\s*([^\n\r]+)", re.IGNORECASE)
    match = pattern.search(text or "")
    if not match:
        return ""
    value = match.group(1).strip()
    value = re.split(r"\s+\(", value, maxsplit=1)[0].strip()
    return value


def _sections(markdown: str) -> dict[str, str]:
    result: dict[str, list[str]] = {}
    current = ""
    for raw in str(markdown or "").splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            heading = line[3:].strip()
            inline_value = ""
            if ":" in heading:
                heading, inline_value = heading.split(":", 1)
            current = heading.strip().lower()
            result.setdefault(current, [])
            if inline_value.strip():
                result[current].append(inline_value.strip())
            continue
        if current:
            result.setdefault(current, []).append(line)
    return {key: "\n".join(value).strip() for key, value in result.items()}


def _first_value(sections: dict[str, str], key: str) -> str:
    text = sections.get(key, "")
    for line in text.splitlines():
        cleaned = line.strip().lstrip("-").strip()
        if cleaned:
            return cleaned
    return text.strip()


def _parse_parameters(text: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for line in text.splitlines():
        cleaned = line.strip().lstrip("-*").strip()
        if not cleaned or ":" not in cleaned:
            continue
        key, value = cleaned.split(":", 1)
        params[_clean_key(key)] = _parse_scalar(value.strip())
    return params


def _clean_key(value: str) -> str:
    return value.strip().replace("\\_", "_")


def _parse_scalar(value: str) -> Any:
    stripped = _strip_inline_note(value.strip())
    if (stripped.startswith("[") and stripped.endswith("]")) or (stripped.startswith("{") and stripped.endswith("}")):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    if "," in value:
        return [_parse_scalar(part.strip()) for part in value.split(",")]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return stripped.replace("\\_", "_")


def _strip_inline_note(value: str) -> str:
    stripped = value.strip()
    bracket_match = re.match(r"^(\[[^\]]+\]|\{[^}]+\})", stripped)
    if bracket_match:
        return bracket_match.group(1)
    return re.split(r"\s+\(", stripped, maxsplit=1)[0].strip()
