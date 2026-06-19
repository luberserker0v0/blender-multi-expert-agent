"""Tests for ExpertMemory three-tier system and ContextWindowStrategy."""

import pytest

from ai_3d_modeling_agent.multi_expert.memory.expert_memory import ExpertMemory
from ai_3d_modeling_agent.multi_expert.memory.context_window import ContextWindowStrategy


class TestExpertMemory:
    """Verify three-tier memory: ephemeral, persistent, permanent."""

    def test_default_tiers_are_empty(self):
        mem = ExpertMemory()
        assert mem.ephemeral == {}
        assert mem.persistent == {}
        assert mem.permanent == {}

    def test_set_and_get_ephemeral(self):
        mem = ExpertMemory()
        mem.set("key1", "round1", tier="ephemeral")
        assert mem.get("key1", tier="ephemeral") == "round1"

    def test_set_and_get_persistent(self):
        mem = ExpertMemory()
        mem.set("decision", "cube", tier="persistent")
        assert mem.get("decision", tier="persistent") == "cube"

    def test_set_and_get_permanent(self):
        mem = ExpertMemory()
        mem.set("lesson", "use cylinders for legs", tier="permanent")
        assert mem.get("lesson", tier="permanent") == "use cylinders for legs"

    def test_get_nonexistent_key(self):
        mem = ExpertMemory()
        assert mem.get("nothing") is None

    def test_get_falls_back_to_ephemeral_for_unknown_tier(self):
        mem = ExpertMemory()
        mem.set("x", 42, tier="ephemeral")
        assert mem.get("x", tier="unknown_tier") == 42

    def test_set_falls_back_to_ephemeral_for_unknown_tier(self):
        mem = ExpertMemory()
        mem.set("x", 99, tier="unknown_tier")
        assert mem.get("x") == 99

    def test_clear_ephemeral_preserves_other_tiers(self):
        mem = ExpertMemory()
        mem.set("round", 3, tier="ephemeral")
        mem.set("decision", "approved", tier="persistent")
        mem.set("lesson", "important", tier="permanent")
        mem.clear_ephemeral()
        assert mem.ephemeral == {}
        assert mem.persistent == {"decision": "approved"}
        assert mem.permanent == {"lesson": "important"}

    def test_clear_persistent_preserves_other_tiers(self):
        mem = ExpertMemory()
        mem.set("round", 3, tier="ephemeral")
        mem.set("decision", "approved", tier="persistent")
        mem.clear_persistent()
        assert mem.ephemeral == {"round": 3}
        assert mem.persistent == {}
        assert mem.permanent == {}

    def test_multiple_keys_in_same_tier(self):
        mem = ExpertMemory()
        mem.set("a", 1, tier="ephemeral")
        mem.set("b", 2, tier="ephemeral")
        mem.set("c", 3, tier="ephemeral")
        assert len(mem.ephemeral) == 3
        assert mem.get("a") == 1
        assert mem.get("b") == 2
        assert mem.get("c") == 3

    def test_overwrite_existing_key(self):
        mem = ExpertMemory()
        mem.set("x", "old", tier="persistent")
        mem.set("x", "new", tier="persistent")
        assert mem.get("x", tier="persistent") == "new"
        assert len(mem.persistent) == 1

    def test_tiers_are_independent(self):
        mem = ExpertMemory()
        mem.set("key", "ephemeral_val", tier="ephemeral")
        mem.set("key", "persistent_val", tier="persistent")
        mem.set("key", "permanent_val", tier="permanent")
        assert mem.get("key", tier="ephemeral") == "ephemeral_val"
        assert mem.get("key", tier="persistent") == "persistent_val"
        assert mem.get("key", tier="permanent") == "permanent_val"

    def test_default_tier_is_ephemeral(self):
        mem = ExpertMemory()
        mem.set("x", 10)
        assert mem.get("x") == 10
        assert mem.ephemeral == {"x": 10}

    def test_clear_ephemeral_many_keys(self):
        mem = ExpertMemory()
        for i in range(100):
            mem.set(f"k{i}", i, tier="ephemeral")
        assert len(mem.ephemeral) == 100
        mem.clear_ephemeral()
        assert mem.ephemeral == {}


class TestContextWindowStrategy:
    """Verify ContextWindowStrategy placeholder behavior."""

    def test_summarize_returns_no_summary(self):
        strategy = ContextWindowStrategy()
        assert strategy.summarize(None) == "No summary"

    def test_should_summarize_default_threshold(self):
        strategy = ContextWindowStrategy()
        assert strategy.should_summarize(9000) is True
        assert strategy.should_summarize(8192) is False
        assert strategy.should_summarize(5000) is False

    def test_should_summarize_custom_threshold(self):
        strategy = ContextWindowStrategy()
        assert strategy.should_summarize(500, max_tokens=1000) is False
        assert strategy.should_summarize(1500, max_tokens=1000) is True

    def test_should_summarize_at_boundary(self):
        strategy = ContextWindowStrategy()
        assert strategy.should_summarize(8192, max_tokens=8192) is False
        assert strategy.should_summarize(8193, max_tokens=8192) is True
