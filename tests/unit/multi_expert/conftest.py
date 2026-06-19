"""Pytest fixtures for multi-expert pipeline tests."""

from dataclasses import dataclass, field
from typing import Optional
import pytest

from ai_3d_modeling_agent.multi_expert.core.conversation import Message, Conversation
from ai_3d_modeling_agent.multi_expert.core.expert import Expert, LlmInterface, SamplingOptions
from ai_3d_modeling_agent.multi_expert.core.termination import TerminationPolicy, StopReason


class MockLLM:
    """Mock LLM that returns a fixed response."""

    def __init__(self, fixed_response: str = '{"status": "ok"}'):
        self.fixed_response = fixed_response
        self.call_count = 0
        self.last_system_prompt = ""
        self.last_messages = []
        self.system_prompts = []
        self.last_sampling = None
        self.samplings = []
        self.last_kwargs = {}
        self.kwargs_history = []
        self.agents = []
        self.labels = []
        self.skills = []
        self.contexts = []

    def call(self, system_prompt: str = "", messages: Optional[list] = None,
             response_model=None, sampling: Optional[SamplingOptions] = None,
             **kwargs) -> str:
        self.call_count += 1
        self.last_system_prompt = system_prompt
        self.system_prompts.append(system_prompt)
        self.last_messages = messages or []
        self.last_sampling = sampling
        self.samplings.append(sampling)
        self.last_kwargs = dict(kwargs)
        self.kwargs_history.append(dict(kwargs))
        self.agents.append(str(kwargs.get("agent", "")))
        self.labels.append(str(kwargs.get("label", "")))
        self.skills.append(str(kwargs.get("skill", "")))
        self.contexts.append(kwargs.get("context"))
        return self.fixed_response


@pytest.fixture
def mock_llm():
    return MockLLM()


@pytest.fixture
def mock_llm_with_response():
    def _make(response: str = '{"status": "ok"}'):
        return MockLLM(fixed_response=response)
    return _make


def make_message(speaker: str = "test_expert", turn: int = 1,
                 phase: str = "test", content: str = "test message",
                 structured: Optional[dict] = None) -> Message:
    return Message(
        speaker=speaker,
        turn=turn,
        phase=phase,
        content=content,
        structured=structured,
    )


@pytest.fixture
def basic_conversation():
    conv = Conversation(phase_name="test")
    conv.append(make_message(speaker="expert_a", turn=1,
                             content="I propose we use a cube primitive"))
    conv.append(make_message(speaker="expert_b", turn=2,
                             content="[DONE] Agreed"))
    return conv


@pytest.fixture
def basic_termination():
    return TerminationPolicy(max_rounds=10, early_consensus=True)


# Minimal concrete Expert for testing
class TestExpert(Expert):
    def __init__(self, role_name: str = "test_expert",
                 description: str = "A test expert",
                 capabilities: Optional[list[str]] = None,
                 system_prompt: str = "You are a test expert."):
        self.role_name = role_name
        self.description = description
        self.capabilities = capabilities or ["test"]
        self.system_prompt = system_prompt
        self.memory = None  # Will be ExpertMemory in Stage 4b

    def speak(self, conversation, context, llm):
        raw = llm.call(system_prompt=self.system_prompt)
        return Message(
            speaker=self.role_name,
            turn=len(conversation.messages) + 1,
            phase=conversation.phase_name,
            content=raw,
        )


@pytest.fixture
def test_expert():
    return TestExpert()


@pytest.fixture
def test_expert_pair():
    return [TestExpert(role_name="expert_a"), TestExpert(role_name="expert_b")]
