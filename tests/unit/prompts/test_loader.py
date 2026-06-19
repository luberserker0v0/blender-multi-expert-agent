from pathlib import Path

from ai_3d_modeling_agent.prompts import load_chat_examples


REPO_ROOT = Path(__file__).resolve().parents[3]
AGENTS_ROOT = REPO_ROOT / ".opencode" / "agents"


def _frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    return text.split("---", 2)[1]


def test_opencode_agent_markdown_uses_official_frontmatter() -> None:
    expected_modes = {
        "moderator.md": "primary",
        "designer.md": "subagent",
        "specifier.md": "subagent",
        "planner.md": "subagent",
        "reviewer.md": "subagent",
        "builder.md": "subagent",
        "inspector.md": "subagent",
    }

    for filename, mode in expected_modes.items():
        frontmatter = _frontmatter(AGENTS_ROOT / filename)
        assert "description:" in frontmatter
        assert f"mode: {mode}" in frontmatter
        assert "model:" in frontmatter
        assert "temperature:" in frontmatter
        if filename == "moderator.md":
            assert "permission:" in frontmatter
            assert "task:" in frontmatter
            for subagent in ("designer", "specifier", "planner", "reviewer", "builder", "inspector"):
                assert f"{subagent}: allow" in frontmatter
            assert "edit: deny" in frontmatter
            assert "bash: deny" in frontmatter
        elif filename == "builder.md":
            assert "tools:" in frontmatter
            assert "read: true" in frontmatter
            assert "write: false" in frontmatter
            assert "edit: false" in frontmatter
            assert "bash: false" in frontmatter
            assert "permission:" in frontmatter
            assert "read:" in frontmatter
            assert "docs/blender_build_capabilities.md: allow" in frontmatter
            assert "edit: deny" in frontmatter
            assert "bash: deny" in frontmatter
        else:
            assert "tools:" in frontmatter
            assert "write: false" in frontmatter
            assert "edit: false" in frontmatter
            assert "bash: false" in frontmatter
            assert "permission:" not in frontmatter


def test_load_chat_examples_from_markdown() -> None:
    examples = load_chat_examples("decision/decompose_few_shot.md")

    assert len(examples) == 4
    assert examples[0]["role"] == "user"
    assert 'build an apple' in examples[0]["content"]
    assert examples[1]["role"] == "assistant"
    assert '"part_families"' in examples[1]["content"]


def test_agent_scope_guard_rejects_material_driven_subparts() -> None:
    shared = (REPO_ROOT / ".opencode" / "AGENTS.md").read_text(encoding="utf-8")
    moderator = (AGENTS_ROOT / "moderator.md").read_text(encoding="utf-8")
    designer = (AGENTS_ROOT / "designer.md").read_text(encoding="utf-8")
    reviewer = (AGENTS_ROOT / "reviewer.md").read_text(encoding="utf-8")
    specifier = (AGENTS_ROOT / "specifier.md").read_text(encoding="utf-8")
    planner = (AGENTS_ROOT / "planner.md").read_text(encoding="utf-8")

    assert "Do not split a requested part because of optional material" in shared
    assert "A simple cube is one cube object, not six face parts" in shared
    assert "Missing numeric dimensions are not blocking" in shared
    assert "simple chair request with one seat, four legs, and one backrest must stay as `seat`, `leg`, and `backrest`" in moderator
    assert "A simple cube must resolve as one `cube` part" in moderator
    assert "Treat missing exact dimensions in simple modeling requests as non-blocking" in moderator
    assert "do not turn `seat` into `seat_body` plus `upholstery_pad`" in designer
    assert "For a simple cube, output one `cube` part only" in designer
    assert "Do not challenge optional material/color/upholstery/finish choices as blocking design issues" in reviewer
    assert "A simple cube must stay one `cube` part" in reviewer
    assert "Do not challenge missing exact numeric dimensions as blocking for simple modeling tasks" in reviewer
    assert "choose small conventional default dimensions" in specifier
    assert "plan with conventional dimensions/placement assumptions" in planner
