"""Shared LLM response parsing utilities.

Eliminates duplication of ``_json_from_llm`` (was in both
the multi-expert extraction prompts) and attachment-matching logic.
"""

import json
import re
from typing import Any, Dict, List, Optional

from ai_3d_modeling_agent.schemas.part import AttachmentPoint


# ── JSON extraction ───────────────────────────────────────────────────


def extract_json_from_llm(
    raw_response: str,
    context_label: str = "LLM",
) -> Dict[str, Any]:
    """Extract a JSON object from an LLM response.

    Handles:
    - Markdown fence markers (`` ```json``, `` ``` ``, etc.)
    - Leading/trailing human commentary
    - Extra text after the closing brace

    Parameters
    ----------
    raw_response:
        Raw LLM output text.
    context_label:
        Label used in error messages to identify which LLM call failed
        (e.g. ``"Decompose"``, ``"Specify"``).

    Returns
    -------
    Parsed JSON dict.

    Raises
    ------
    ValueError
        If the response cannot be parsed as JSON.
    """
    cleaned = _extract_fenced_json_candidate(raw_response.strip())

    # ── locate the outermost JSON braces ──────────────────────────
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        cleaned = cleaned[first_brace:last_brace + 1]

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        context = raw_response[:500]
        raise ValueError(
            f"{context_label} response is not valid JSON: {context}"
        ) from exc


def _extract_fenced_json_candidate(text: str) -> str:
    """Return the most likely JSON payload from a possibly fenced response."""
    json_fence_pattern = re.compile(r"```[ \t]*(?:json|JSON)[ \t]*\r?\n(.*?)```", re.DOTALL)
    for match in json_fence_pattern.finditer(text):
        candidate = match.group(1).strip()
        if candidate.startswith("{") or "{" in candidate:
            return candidate

    bare_fence_pattern = re.compile(r"```[ \t]*\r?\n(.*?)```", re.DOTALL)
    matches = [match.group(1).strip() for match in bare_fence_pattern.finditer(text)]
    for candidate in matches:
        if candidate.startswith("{") or "{" in candidate:
            return candidate
    if matches:
        return matches[0]
    return text


# ── attachment point matching ─────────────────────────────────────────


def match_parent_attachment(
    child_ap_name: str,
    parent_aps: List[AttachmentPoint],
) -> Optional[AttachmentPoint]:
    """Find the parent attachment point that pairs with a child attachment point.

    Uses name-based heuristics to find the OPPOSING-FACE match:

    - child ``bottom*`` → parent ``top*``
    - child ``top*``    → parent ``bottom*``
    - child ``back*``   → parent ``front*`` (``back*`` as fallback)
    - child ``front*``  → parent ``back*``
    - child ``left*``   → parent ``right*``
    - child ``right*``  → parent ``left*``

    Returns ``None`` if no match is found.
    """
    name_lower = child_ap_name.lower()
    if name_lower.startswith("bottom"):
        targets = ["top"]
    elif name_lower.startswith("top"):
        targets = ["bottom"]
    elif name_lower.startswith("back"):
        targets = ["front", "back"]
    elif name_lower.startswith("front"):
        targets = ["back"]
    elif name_lower.startswith("left"):
        targets = ["right"]
    elif name_lower.startswith("right"):
        targets = ["left"]
    else:
        return None

    for pap in parent_aps:
        pname = pap.name.lower()
        for t in targets:
            if pname.startswith(t):
                return pap
    return None


# ── error hinting for LLM retry ────────────────────────────────────────


def hint_for_error(error: str) -> str:
    """Generate a targeted hint for a validation error to guide LLM retry.

    Handles these error patterns:

    - Dimension exceeds parent (``"exceeds parent"`` / ``"max dimension"``):
      extracts dimension and computes max allowed value.
    - ``LEFT_RIGHT_X`` symmetry: suggests left_face/right_face attachment.
    - ``QUADRANT_Z`` symmetry: suggests corner attachment with XY offset.
    - Attachment pairing (opposing faces): suggests flipping child's face.
    - All others: returns empty string (no hint).

    Parameters
    ----------
    error:
        The validation error message.

    Returns
    -------
    A hint string, or ``""`` if no applicable hint.
    """
    # Pattern 1: child dimension exceeds parent
    #   "'leg'.width=0.600 exceeds parent 'seat'.width=0.500"
    if "exceeds parent" in error:
        m = re.search(
            r"'(\w+)'\.(\w+)=([\d.]+) exceeds parent '\w+'\.\w+=([\d.]+)",
            error,
        )
        if m:
            dim = m.group(2)
            parent_val = float(m.group(4))
            max_allowed = parent_val * 1.05
            return f"Reduce {dim} to \u2264{max_allowed:.3f}"

    # Pattern 2: "max dimension" format (fallback for older error phrasing)
    #   "max dimension (0.600) must be smaller than parent (0.500)"
    if "max dimension" in error:
        m = re.search(r"max dimension \(([\d.]+)\).*parent \(([\d.]+)\)", error)
        if m:
            parent_val = float(m.group(2))
            max_allowed = parent_val * 1.05
            return f"Reduce dimension to \u2264{max_allowed:.3f}"

    # Pattern 3: LEFT_RIGHT_X symmetry error
    if "LEFT_RIGHT_X" in error:
        return "Use left_face/right_face instead of centered attachment"

    # Pattern 4: QUADRANT_Z symmetry error
    if "QUADRANT_Z" in error:
        return "Use corner attachment with XY offset"

    # Pattern 5: attachment pairing (opposing faces)
    if "Attachment pairing" in error and "do not face each other" in error:
        m = re.search(r"'(\w+)'\.(\w+)", error)
        if m:
            child_ap = m.group(2)
            opposite = {
                "top": "bottom", "bottom": "top",
                "front": "back", "back": "front",
                "left": "right", "right": "left",
            }
            for key, val in opposite.items():
                if child_ap.startswith(key):
                    return (
                        f"Child '{child_ap}' and parent attachment are on the SAME face. "
                        f"Change child to '{val}_center' so they OPPOSE each other "
                        f"(e.g. child {val}_center \u2194 parent {child_ap})."
                    )
        return (
            "Child and parent attachment surfaces face the SAME direction. "
            "Change so they OPPOSE each other. "
            "E.g. child front_center \u2194 parent back_center, "
            "child bottom_center \u2194 parent top_center."
        )

    return ""
