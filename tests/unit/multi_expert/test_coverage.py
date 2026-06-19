from ai_3d_modeling_agent.multi_expert.artifacts import DesignArtifact, PlanArtifact, SpecArtifact
from ai_3d_modeling_agent.multi_expert.core.coverage import (
    build_plan_todos_from_spec,
    build_spec_todos_from_design,
    build_todo_groups,
    coverage_clarification_requests,
    coverage_open_issues,
    coverage_revision_requests,
    mark_plan_coverage,
    mark_spec_coverage,
    sync_todo_group_status_with_coverage,
)
from ai_3d_modeling_agent.schemas.part import PartFamily, SymmetryGroup


def test_chair_design_parts_generate_spec_todos() -> None:
    design = DesignArtifact(
        parts=[
            {"name": "seat", "instance_count": 1},
            {"name": "leg", "instance_count": 4},
            {"name": "backrest", "instance_count": 1},
        ]
    )

    todos = build_spec_todos_from_design(design)

    assert len(todos) == 9
    assert {todo["target_name"] for todo in todos} == {"seat", "leg", "backrest"}
    assert {todo["task"] for todo in todos} == {
        "spec_part_exists",
        "spec_geometry_defined",
        "spec_instance_count_preserved",
    }


def test_spec_todos_are_grouped_by_target_for_focused_dispatch() -> None:
    design = DesignArtifact(
        parts=[
            {"name": "seat", "instance_count": 1},
            {"name": "leg", "instance_count": 4},
            {"name": "backrest", "instance_count": 1},
        ]
    )

    groups = build_todo_groups(build_spec_todos_from_design(design), phase="spec", role="specifier")

    assert [group["id"] for group in groups] == ["spec:backrest", "spec:leg", "spec:seat"]
    leg = next(group for group in groups if group["id"] == "spec:leg")
    assert leg["role"] == "specifier"
    assert leg["review_role"] == "reviewer"
    assert leg["target_name"] == "leg"
    assert len(leg["todos"]) == 3
    assert "Focus only on `leg`" in leg["focused_prompt"]


def test_todo_group_status_follows_python_coverage_result() -> None:
    groups = [
        {"id": "spec:leg", "target_name": "leg", "status": "accepted"},
        {"id": "spec:seat", "target_name": "seat", "status": "accepted"},
    ]
    todos = [
        {"id": "spec:leg:geometry_defined", "target_name": "leg", "status": "missing", "required": True},
        {"id": "spec:seat:geometry_defined", "target_name": "seat", "status": "covered", "required": True},
    ]

    updated = sync_todo_group_status_with_coverage(groups, todos)

    assert next(group for group in updated if group["id"] == "spec:leg")["status"] == "needs_revision"
    assert next(group for group in updated if group["id"] == "spec:seat")["status"] == "accepted"


def test_coverage_revision_requests_group_missing_todos_by_target() -> None:
    groups = [{"id": "spec:leg", "phase": "spec", "target_name": "leg", "role": "specifier"}]
    todos = [
        {
            "id": "spec:leg:geometry_defined",
            "phase": "spec",
            "target_name": "leg",
            "target_kind": "part",
            "task": "spec_geometry_defined",
            "status": "missing",
            "required": True,
            "missing_reason": "missing geometry spec",
        }
    ]

    requests = coverage_revision_requests(todos, groups, owner="specifier")

    assert requests == [
        {
            "id": "revision:spec:leg",
            "phase": "spec",
            "group_id": "spec:leg",
            "target_name": "leg",
            "target_kind": "part",
            "owner": "specifier",
            "reviewer": "reviewer",
            "status": "needs_revision",
            "reason": "missing geometry spec",
            "missing_todos": todos,
            "focused_prompt": "",
            "agent_output": "",
            "review_output": "",
            "accepted_summary": "",
        }
    ]


def test_coverage_clarification_requests_turn_missing_todos_into_questions() -> None:
    revision_requests = [
        {
            "id": "revision:spec:leg",
            "phase": "spec",
            "target_name": "leg",
            "target_kind": "part",
            "reason": "missing geometry spec",
            "missing_todos": [
                {
                    "id": "spec:leg:geometry_defined",
                    "phase": "spec",
                    "target_name": "leg",
                    "target_kind": "part",
                    "task": "spec_geometry_defined",
                    "status": "missing",
                    "required": True,
                    "missing_reason": "missing geometry spec",
                }
            ],
        }
    ]

    requests = coverage_clarification_requests(revision_requests)

    assert requests[0]["id"] == "clarification:spec:leg"
    assert requests[0]["status"] == "pending"
    assert requests[0]["source_revision_request"] == "revision:spec:leg"
    assert "explicit dimensions" in requests[0]["questions"][0]
    assert "leg" in requests[0]["prompt"]


def test_complete_spec_marks_all_spec_todos_covered() -> None:
    design = DesignArtifact(parts=[{"name": "leg", "instance_count": 4}])
    spec = SpecArtifact(parts={"leg": {"primitive": "cylinder", "target_bbox": {"width": 0.1, "depth": 0.1, "height": 1.0}, "instance_count": 4}})

    marked = mark_spec_coverage(build_spec_todos_from_design(design), spec, design)

    assert {todo["status"] for todo in marked} == {"covered"}


def test_assumed_spec_geometry_does_not_cover_required_geometry() -> None:
    design = DesignArtifact(parts=[{"name": "seat", "instance_count": 1}])
    spec = SpecArtifact(
        parts={
            "seat": {
                "primitive": "cube",
                "geometry_source": "assumed",
                "target_bbox": {"width": 0.5, "depth": 0.4, "height": 0.1},
            }
        }
    )

    marked = mark_spec_coverage(build_spec_todos_from_design(design), spec, design)

    geometry = next(todo for todo in marked if todo["task"] == "spec_geometry_defined")
    assert geometry["status"] == "missing"


def test_markdown_spec_primitive_and_description_cover_required_geometry() -> None:
    design = DesignArtifact(parts=[{"name": "backrest", "instance_count": 1}])
    spec = SpecArtifact(
        parts={
            "backrest": {
                "primitive": "cube",
                "geometry_source": "markdown_spec",
                "description": "Backrest is a single upright rectangular slab attached to the rear of the seat.",
                "target_bbox": {},
                "instance_count": 1,
            }
        }
    )

    marked = mark_spec_coverage(build_spec_todos_from_design(design), spec, design)

    geometry = next(todo for todo in marked if todo["task"] == "spec_geometry_defined")
    assert geometry["status"] == "covered"


def test_missing_leg_spec_marks_required_todos_missing() -> None:
    design = DesignArtifact(parts=[{"name": "seat", "instance_count": 1}, {"name": "leg", "instance_count": 4}])
    spec = SpecArtifact(parts={"seat": {"primitive": "cube", "target_bbox": {}}})

    marked = mark_spec_coverage(build_spec_todos_from_design(design), spec, design)
    issues = coverage_open_issues(marked)

    assert any("leg" in issue and "spec_part_exists" in issue for issue in issues)
    assert any("leg" in issue and "spec_instance_count_preserved" in issue for issue in issues)


def test_plan_missing_leg_assembly_responsibility_yields_open_issue() -> None:
    spec = SpecArtifact(parts={"seat": {"primitive": "cube"}, "leg": {"primitive": "cylinder"}})
    families = [
        PartFamily(name="seat", description="seat", instance_count=1, parent_name=None, symmetry_group=SymmetryGroup.NONE),
        PartFamily(name="leg", description="leg", instance_count=4, parent_name="seat", symmetry_group=SymmetryGroup.QUADRANT_Z),
    ]
    plan = PlanArtifact(
        build_responsibilities=[{"family": "seat"}, {"family": "leg"}],
        assembly_responsibilities=[{"family": "seat"}],
        steps=[{"family": "seat", "instance_count": 1}, {"family": "leg", "instance_count": 4}],
    )

    marked = mark_plan_coverage(build_plan_todos_from_spec(spec, families), plan, families)
    issues = coverage_open_issues(marked)

    assert any("leg" in issue and "plan_assembly_responsibility" in issue for issue in issues)


def test_single_cube_does_not_require_generic_family_instance_split() -> None:
    design = DesignArtifact(parts=[{"name": "E2E_Cube", "instance_count": 1}])
    spec = SpecArtifact(parts={"E2E_Cube": {"primitive": "cube", "target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0}}})

    marked = mark_spec_coverage(build_spec_todos_from_design(design), spec, design)

    assert {todo["status"] for todo in marked} == {"covered"}
