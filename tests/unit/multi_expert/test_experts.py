"""Layer 1 unit tests for the 6 expert subclasses.

Tests verify the contract defined by the Expert ABC:
- Class attributes (role_name, description, capabilities)
- speak() returns a valid Message with correct structure
- ABC cannot be instantiated directly
- MockLLM tracks invocation count and arguments
- Conversation messages are forwarded to the LLM
"""

import pytest

from ai_3d_modeling_agent.multi_expert.core.conversation import Message, Conversation
from ai_3d_modeling_agent.multi_expert.core.expert import Expert
from ai_3d_modeling_agent.multi_expert.experts import (
    Designer,
    Specifier,
    Reviewer,
    Builder,
    Inspector,
)


# ---------------------------------------------------------------------------
# A — Expert class attributes (parametrized across all 6 experts)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls,expected_role,expected_capabilities", [
    (Designer,   "designer",   ["task decomposition", "part family identification"]),
    (Specifier,  "specifier",  ["geometry specification", "bounding box assignment"]),
    (Reviewer,   "reviewer",   ["consistency checking", "constraint validation"]),
    (Builder,    "builder",    ["primitive creation", "blender object construction", "spatial placement"]),
    (Inspector,  "inspector",  ["dimensional verification", "instance count checking"]),
])
def test_expert_attributes(cls, expected_role, expected_capabilities):
    """Verify each expert has expected role_name, description,
    and capabilities including at least the listed ones."""
    expert = cls()
    assert expert.role_name == expected_role
    assert expert.description, f"{expected_role}.description should be non-empty"
    assert len(expert.capabilities) >= 1, (
        f"{expected_role} should have at least 1 capability"
    )
    for cap in expected_capabilities:
        assert cap in expert.capabilities, (
            f"{expected_role} should have capability {cap!r}"
        )
    assert expert.system_prompt == ""


# ---------------------------------------------------------------------------
# B — speak() returns correct Message structure (parametrized)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls,expected_role_name", [
    (Designer,   "designer"),
    (Specifier,  "specifier"),
    (Reviewer,   "reviewer"),
    (Builder,    "builder"),
    (Inspector,  "inspector"),
])
def test_expert_speak_returns_message(cls, expected_role_name, mock_llm, basic_conversation):
    """Verify speak() returns a Message with the correct structure:

    - Is a Message instance
    - speaker matches the expert role_name
    - turn is len(conversation.messages) + 1  (basic_conversation has 2 messages)
    - phase matches conversation.phase_name
    - content is the raw LLM response
    """
    expert = cls()
    msg = expert.speak(basic_conversation, context=None, llm=mock_llm)

    assert isinstance(msg, Message), f"{expected_role_name}.speak() should return a Message"
    assert msg.speaker == expected_role_name, (
        f"Expected speaker={expected_role_name!r}, got {msg.speaker!r}"
    )
    # basic_conversation has messages [expert_a, expert_b] = length 2
    assert msg.turn == len(basic_conversation.messages) + 1, (
        f"Expected turn {len(basic_conversation.messages) + 1}, got {msg.turn}"
    )
    assert msg.phase == basic_conversation.phase_name, (
        f"Expected phase={basic_conversation.phase_name!r}, got {msg.phase!r}"
    )
    assert msg.content == mock_llm.fixed_response, (
        f"Expected content={mock_llm.fixed_response!r}, got {msg.content!r}"
    )
    # structured should be None by default
    assert msg.structured is None


# ---------------------------------------------------------------------------
# C — Expert ABC cannot be instantiated directly
# ---------------------------------------------------------------------------

def test_expert_is_abstract():
    """Verify that the Expert ABC raises TypeError when instantiated directly."""
    with pytest.raises(TypeError):
        Expert()


# ---------------------------------------------------------------------------
# D — MockLLM tracks call_count and last_system_prompt
# ---------------------------------------------------------------------------

def test_mock_llm_tracks_calls(mock_llm):
    """Verify that speak() increments mock_llm.call_count and routes via AO metadata."""
    conv = Conversation(phase_name="test")
    conv.append(Message(speaker="user", turn=1, phase="test", content="build a chair"))

    designer = Designer()

    msg1 = designer.speak(conv, context=None, llm=mock_llm)
    assert mock_llm.call_count == 1, (
        f"Expected call_count=1 after first speak, got {mock_llm.call_count}"
    )
    assert mock_llm.last_system_prompt == ""
    assert mock_llm.agents[-1] == "moderator"
    assert mock_llm.contexts[-1]["agent_role"] == "designer"

    msg2 = designer.speak(conv, context=None, llm=mock_llm)
    assert mock_llm.call_count == 2, (
        f"Expected call_count=2 after second speak, got {mock_llm.call_count}"
    )


# ---------------------------------------------------------------------------
# E — Each expert passes conversation messages to the LLM
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls", [Designer, Specifier, Reviewer, Builder, Inspector])
def test_expert_passes_messages_to_llm(cls, mock_llm, basic_conversation):
    """Verify that speak() passes a structured AO turn payload to llm.call()."""
    expert = cls()
    expert.speak(
        basic_conversation,
        context={"phase_name": "design", "meeting_turn_kind": "proposal"},
        llm=mock_llm,
    )

    assert mock_llm.agents[-1] == "moderator"
    assert mock_llm.contexts[-1]["agent_role"] == expert.role_name
    assert mock_llm.last_system_prompt == ""
    assert len(mock_llm.last_messages) == 1
    assert mock_llm.last_messages[0]["role"] == "user"
    content = mock_llm.last_messages[0]["content"]
    assert '"ao_route": "moderator"' in content
    assert '"delegation_required": true' in content
    assert '"delegated_agent": "' + expert.role_name + '"' in content
    assert '"agent_role": "' + expert.role_name + '"' in content
    assert '"phase_name": "design"' in content
    assert '"turn_kind": "proposal"' in content
    assert "I propose we use a cube primitive" in content
