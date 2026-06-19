"""Layer 1 unit tests for the ConstraintChecker system and all 7 plugins.

Tests cover:
  - ConstraintViolation data model (Severity, overridable)
  - Each plugin: happy path (no violations) and violation path
  - Plugin-specific edge cases
  - ConstraintChecker orchestration: register, run, run_quick, check_corrections
  - Graceful handling of plugin exceptions
"""

from __future__ import annotations

import copy

import pytest

from ai_3d_modeling_agent.multi_expert.constraints import (
    AttachmentInBboxChecker,
    BboxRangeChecker,
    ChildSmallerThanParentChecker,
    ConstraintChecker,
    ConstraintViolation,
    NoOrphansPartsChecker,
    ParentHasAttachmentChecker,
    PrimitiveSupportedChecker,
    Severity,
    SymmetryValidityChecker,
)


# ===================================================================
# A. ConstraintViolation data model
# ===================================================================


class TestConstraintViolation:
    """Verify ConstraintViolation fields and the computed overridable property."""

    def test_overridable_error(self):
        err = ConstraintViolation(rule="test", detail="err", severity=Severity.ERROR)
        assert not err.overridable
        assert err.severity == Severity.ERROR

    def test_overridable_warning(self):
        warn = ConstraintViolation(rule="test", detail="warn", severity=Severity.WARNING)
        assert warn.overridable
        assert warn.severity == Severity.WARNING

    def test_overridable_info(self):
        info = ConstraintViolation(rule="test", detail="info", severity=Severity.INFO)
        assert info.overridable
        assert info.severity == Severity.INFO

    def test_fields(self):
        v = ConstraintViolation(rule="r1", detail="something broke", severity=Severity.ERROR)
        assert v.rule == "r1"
        assert v.detail == "something broke"
        assert v.severity == Severity.ERROR

    def test_repr(self):
        v = ConstraintViolation(rule="r1", detail="detail", severity=Severity.WARNING)
        s = repr(v)
        assert "r1" in s
        assert "detail" in s

    def test_severity_enum_values(self):
        assert Severity.ERROR.value == "error"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"


# ===================================================================
# B. PrimitiveSupportedChecker
# ===================================================================


class TestPrimitiveSupportedChecker:
    """Verify primitive_supported plugin."""

    def test_ok(self):
        """All parts use supported primitives → no violations."""
        plugin = PrimitiveSupportedChecker()
        artifact = {
            "parts": {
                "body": {"primitive": "cube"},
                "leg": {"primitive": "cylinder"},
                "top": {"primitive": "uv_sphere"},
                "base": {"primitive": "plane"},
            }
        }
        assert plugin.check(artifact) == []

    def test_unsupported(self):
        """Part with unsupported primitive → violation."""
        plugin = PrimitiveSupportedChecker()
        artifact = {"parts": {"body": {"primitive": "torus"}}}
        violations = plugin.check(artifact)
        assert len(violations) == 1
        assert violations[0].rule == "primitive_supported"
        assert violations[0].severity == Severity.ERROR

    def test_case_insensitive(self):
        """Primitive matching is case-insensitive."""
        plugin = PrimitiveSupportedChecker()
        artifact = {"parts": {"body": {"primitive": "CUBE"}}}
        assert plugin.check(artifact) == []

    def test_missing_primitive_field(self):
        """Part without primitive field → skipped (no violation)."""
        plugin = PrimitiveSupportedChecker()
        artifact = {"parts": {"body": {}}}
        assert plugin.check(artifact) == []

    def test_empty_parts(self):
        """Empty parts dict → no violations."""
        plugin = PrimitiveSupportedChecker()
        assert plugin.check({"parts": {}}) == []
        assert plugin.check({}) == []

    def test_custom_manifest_supported(self):
        """Manifest overrides supported primitives."""
        plugin = PrimitiveSupportedChecker()
        artifact = {"parts": {"ring": {"primitive": "torus"}}}
        manifests = {"supported_primitives": ["cube", "torus"]}
        assert plugin.check(artifact, manifests) == []

    def test_custom_manifest_rejects(self):
        """Manifest restricts supported set → violation for excluded primitives."""
        plugin = PrimitiveSupportedChecker()
        artifact = {"parts": {"body": {"primitive": "cylinder"}}}
        manifests = {"supported_primitives": ["cube", "plane"]}
        violations = plugin.check(artifact, manifests)
        assert len(violations) == 1
        assert "cylinder" in violations[0].detail

    def test_multiple_unsupported(self):
        """Multiple unsupported parts → multiple violations."""
        plugin = PrimitiveSupportedChecker()
        artifact = {"parts": {"a": {"primitive": "torus"}, "b": {"primitive": "cone"}}}
        violations = plugin.check(artifact)
        assert len(violations) == 2

    def test_manifest_none(self):
        """Manifest=None uses default supported set."""
        plugin = PrimitiveSupportedChecker()
        artifact = {"parts": {"body": {"primitive": "cube"}}}
        assert plugin.check(artifact, None) == []


# ===================================================================
# C. BboxRangeChecker
# ===================================================================


class TestBboxRangeChecker:
    """Verify bbox_range plugin."""

    def test_ok(self):
        """Parts within default range → no violations."""
        plugin = BboxRangeChecker()
        artifact = {
            "parts": {
                "body": {"target_bbox": {"width": 1.0, "depth": 2.0, "height": 0.5}},
                "leg": {"target_bbox": {"width": 0.1, "depth": 0.1, "height": 0.1}},
            }
        }
        assert plugin.check(artifact) == []

    def test_too_small(self):
        """Part below minimum → violation."""
        plugin = BboxRangeChecker()
        artifact = {"parts": {"leg": {"target_bbox": {"width": 1e-6, "depth": 0.5, "height": 0.5}}}}
        violations = plugin.check(artifact)
        assert len(violations) == 1
        assert violations[0].rule == "bbox_range"
        assert violations[0].severity == Severity.ERROR
        assert "below minimum" in violations[0].detail

    def test_too_large(self):
        """Part exceeds maximum → violation."""
        plugin = BboxRangeChecker()
        artifact = {"parts": {"body": {"target_bbox": {"width": 200.0, "depth": 0.5, "height": 0.5}}}}
        violations = plugin.check(artifact)
        assert len(violations) == 1
        assert "exceeds maximum" in violations[0].detail

    def test_missing_bbox(self):
        """Part without target_bbox → skipped."""
        plugin = BboxRangeChecker()
        artifact = {"parts": {"body": {}}}
        assert plugin.check(artifact) == []

    def test_missing_bbox_dim(self):
        """Part with partial bbox dims → only present dims checked."""
        plugin = BboxRangeChecker()
        artifact = {"parts": {"body": {"target_bbox": {"width": 200.0}}}}
        violations = plugin.check(artifact)
        assert len(violations) == 1
        assert "width" in violations[0].detail

    def test_empty_parts(self):
        """Empty parts → no violations."""
        plugin = BboxRangeChecker()
        assert plugin.check({"parts": {}}) == []
        assert plugin.check({}) == []

    def test_custom_manifest_ranges(self):
        """Manifest overrides min/max bbox ranges."""
        plugin = BboxRangeChecker()
        artifact = {"parts": {"leg": {"target_bbox": {"width": 0.5, "depth": 0.5, "height": 0.5}}}}
        manifests = {"min_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0}}
        violations = plugin.check(artifact, manifests)
        assert len(violations) == 3  # all three dims below custom min

    def test_custom_manifest_max_only(self):
        """Manifest overrides only max bbox."""
        plugin = BboxRangeChecker()
        artifact = {"parts": {"body": {"target_bbox": {"width": 0.5, "depth": 0.5, "height": 0.5}}}}
        manifests = {"max_bbox": {"width": 0.1, "depth": 0.1, "height": 0.1}}
        violations = plugin.check(artifact, manifests)
        assert len(violations) == 3

    def test_boundary_values(self):
        """Values exactly at boundaries → no violation (within tolerance)."""
        plugin = BboxRangeChecker()
        artifact = {
            "parts": {
                "leg": {"target_bbox": {"width": 0.001, "depth": 0.001, "height": 0.001}},
                "body": {"target_bbox": {"width": 100.0, "depth": 100.0, "height": 100.0}},
            }
        }
        assert plugin.check(artifact) == []

    def test_mixed_valid_and_invalid(self):
        """Some parts valid, some invalid → only invalid reported."""
        plugin = BboxRangeChecker()
        artifact = {
            "parts": {
                "good": {"target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0}},
                "bad": {"target_bbox": {"width": 200.0, "depth": 200.0, "height": 200.0}},
            }
        }
        violations = plugin.check(artifact)
        assert len(violations) == 3  # all three dims on "bad"


# ===================================================================
# D. AttachmentInBboxChecker
# ===================================================================


class TestAttachmentInBboxChecker:
    """Verify attachment_in_bbox plugin."""

    def test_ok(self):
        """Attachment points inside bbox → no violations."""
        plugin = AttachmentInBboxChecker()
        artifact = {
            "parts": {
                "body": {
                    "target_bbox": {"width": 2.0, "depth": 2.0, "height": 2.0},
                    "attachment_points": [
                        {"name": "top", "local_offset": [0.0, 0.0, 0.9]},
                        {"name": "side", "local_offset": [0.8, 0.0, 0.0]},
                    ],
                }
            }
        }
        assert plugin.check(artifact) == []

    def test_outside_bbox_x(self):
        """Attachment outside bbox on X axis → violation."""
        plugin = AttachmentInBboxChecker()
        artifact = {
            "parts": {
                "body": {
                    "target_bbox": {"width": 2.0, "depth": 2.0, "height": 2.0},
                    "attachment_points": [
                        {"name": "far_side", "local_offset": [2.0, 0.0, 0.0]},
                    ],
                }
            }
        }
        violations = plugin.check(artifact)
        assert len(violations) == 1
        assert violations[0].rule == "attachment_in_bbox"
        assert violations[0].severity == Severity.ERROR
        assert "local_offset[0]" in violations[0].detail

    def test_outside_bbox_y(self):
        """Attachment outside bbox on Y (depth) axis → violation."""
        plugin = AttachmentInBboxChecker()
        artifact = {
            "parts": {
                "body": {
                    "target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0},
                    "attachment_points": [
                        {"name": "deep", "local_offset": [0.0, 1.0, 0.0]},
                    ],
                }
            }
        }
        violations = plugin.check(artifact)
        assert len(violations) == 1
        assert "local_offset[1]" in violations[0].detail

    def test_outside_bbox_z(self):
        """Attachment outside bbox on Z (height) axis → violation."""
        plugin = AttachmentInBboxChecker()
        artifact = {
            "parts": {
                "body": {
                    "target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0},
                    "attachment_points": [
                        {"name": "high", "local_offset": [0.0, 0.0, 1.0]},
                    ],
                }
            }
        }
        violations = plugin.check(artifact)
        assert len(violations) == 1
        assert "local_offset[2]" in violations[0].detail

    def test_missing_bbox(self):
        """Part without target_bbox → skipped."""
        plugin = AttachmentInBboxChecker()
        artifact = {
            "parts": {
                "body": {
                    "attachment_points": [
                        {"name": "top", "local_offset": [0.0, 0.0, 10.0]},
                    ],
                }
            }
        }
        assert plugin.check(artifact) == []

    def test_no_attachment_points(self):
        """Part without attachment_points → skipped."""
        plugin = AttachmentInBboxChecker()
        artifact = {"parts": {"body": {"target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0}}}}
        assert plugin.check(artifact) == []

    def test_empty_attachment_points(self):
        """Part with empty attachment_points list → skipped."""
        plugin = AttachmentInBboxChecker()
        artifact = {
            "parts": {
                "body": {
                    "target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0},
                    "attachment_points": [],
                }
            }
        }
        assert plugin.check(artifact) == []

    def test_multiple_violations_same_part(self):
        """Single attachment violating multiple axes → multiple violations."""
        plugin = AttachmentInBboxChecker()
        artifact = {
            "parts": {
                "body": {
                    "target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0},
                    "attachment_points": [
                        {"name": "corner", "local_offset": [1.0, 1.0, 1.0]},
                    ],
                }
            }
        }
        violations = plugin.check(artifact)
        assert len(violations) == 3

    def test_missing_local_offset(self):
        """Attachment without local_offset → skipped."""
        plugin = AttachmentInBboxChecker()
        artifact = {
            "parts": {
                "body": {
                    "target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0},
                    "attachment_points": [{"name": "test"}],
                }
            }
        }
        assert plugin.check(artifact) == []

    def test_empty_parts(self):
        """Empty parts → no violations."""
        plugin = AttachmentInBboxChecker()
        assert plugin.check({"parts": {}}) == []


# ===================================================================
# E. ParentHasAttachmentChecker
# ===================================================================


class TestParentHasAttachmentChecker:
    """Verify parent_has_attachment plugin."""

    def test_ok(self):
        """Parent has attachment points → no violations."""
        plugin = ParentHasAttachmentChecker()
        artifact = {
            "parts": {
                "body": {
                    "attachment_points": [{"name": "top", "local_offset": [0.0, 0.0, 1.0]}],
                },
                "leg": {"parent_name": "body"},
            }
        }
        assert plugin.check(artifact) == []

    def test_parent_no_attachments(self):
        """Child references parent that has no attachments → violation."""
        plugin = ParentHasAttachmentChecker()
        artifact = {
            "parts": {
                "body": {},
                "leg": {"parent_name": "body"},
            }
        }
        violations = plugin.check(artifact)
        assert len(violations) == 1
        assert violations[0].rule == "parent_has_attachment"
        assert violations[0].severity == Severity.WARNING
        assert "body" in violations[0].detail

    def test_no_parent_relationship(self):
        """No part has parent_name → no violations."""
        plugin = ParentHasAttachmentChecker()
        artifact = {
            "parts": {
                "body": {},
                "leg": {},
            }
        }
        assert plugin.check(artifact) == []

    def test_parent_with_empty_attachments(self):
        """Parent with empty attachment_points list → violation."""
        plugin = ParentHasAttachmentChecker()
        artifact = {
            "parts": {
                "body": {"attachment_points": []},
                "leg": {"parent_name": "body"},
            }
        }
        violations = plugin.check(artifact)
        assert len(violations) == 1

    def test_dangling_parent_reference(self):
        """Child references a parent that doesn't exist → skipped (no violation)."""
        plugin = ParentHasAttachmentChecker()
        artifact = {
            "parts": {
                "leg": {"parent_name": "nonexistent"},
            }
        }
        assert plugin.check(artifact) == []

    def test_multiple_children_same_parent(self):
        """Multiple children referencing same parent → single violation."""
        plugin = ParentHasAttachmentChecker()
        artifact = {
            "parts": {
                "body": {},
                "leg1": {"parent_name": "body"},
                "leg2": {"parent_name": "body"},
                "leg3": {"parent_name": "body"},
            }
        }
        violations = plugin.check(artifact)
        assert len(violations) == 1

    def test_empty_parts(self):
        """Empty parts → no violations."""
        plugin = ParentHasAttachmentChecker()
        assert plugin.check({"parts": {}}) == []


# ===================================================================
# F. NoOrphansPartsChecker
# ===================================================================


class TestNoOrphansPartsChecker:
    """Verify no_orphans plugin."""

    def test_one_root(self):
        """Exactly one root part → OK."""
        plugin = NoOrphansPartsChecker()
        artifact = {
            "parts": {
                "body": {},
                "leg": {"parent_name": "body"},
                "arm": {"parent_name": "body"},
            }
        }
        assert plugin.check(artifact) == []

    def test_zero_roots(self):
        """Zero root parts → violation (also catches dangling refs)."""
        plugin = NoOrphansPartsChecker()
        artifact = {
            "parts": {
                "leg": {"parent_name": "body"},
                "arm": {"parent_name": "body"},
            }
        }
        violations = plugin.check(artifact)
        # Both violations: no root AND dangling parent reference 'body'
        assert len(violations) == 2
        assert violations[0].rule == "no_orphans"
        assert violations[0].severity == Severity.ERROR
        assert "No root part" in violations[0].detail

    def test_multiple_roots(self):
        """Multiple root parts → violation."""
        plugin = NoOrphansPartsChecker()
        artifact = {
            "parts": {
                "body_a": {},
                "body_b": {},
                "leg": {"parent_name": "body_a"},
            }
        }
        violations = plugin.check(artifact)
        assert len(violations) == 1
        assert "Multiple root parts" in violations[0].detail
        assert "body_a" in violations[0].detail
        assert "body_b" in violations[0].detail

    def test_dangling_parent_reference(self):
        """Child references non-existent parent → violation."""
        plugin = NoOrphansPartsChecker()
        artifact = {
            "parts": {
                "body": {},
                "leg": {"parent_name": "ghost"},
            }
        }
        violations = plugin.check(artifact)
        # "body" is a root → one root OK; "ghost" is dangling → 1 violation
        assert len(violations) == 1
        assert "Dangling" in violations[0].detail
        assert "ghost" in violations[0].detail

    def test_empty_parts(self):
        """Empty parts → no violations."""
        plugin = NoOrphansPartsChecker()
        assert plugin.check({"parts": {}}) == []
        assert plugin.check({}) == []

    def test_both_zero_roots_and_dangling(self):
        """Zero roots AND dangling references → two violations."""
        plugin = NoOrphansPartsChecker()
        artifact = {
            "parts": {
                "leg": {"parent_name": "ghost"},
            }
        }
        violations = plugin.check(artifact)
        assert len(violations) == 2
        rules = [v.rule for v in violations]
        assert all(r == "no_orphans" for r in rules)

    def test_both_multiple_roots_and_dangling(self):
        """Multiple roots AND dangling references → two violations."""
        plugin = NoOrphansPartsChecker()
        artifact = {
            "parts": {
                "a": {},
                "b": {},
                "c": {"parent_name": "phantom"},
            }
        }
        violations = plugin.check(artifact)
        assert len(violations) == 2

    def test_implicit_root_via_empty_parent(self):
        """Empty string parent_name → treated as root."""
        plugin = NoOrphansPartsChecker()
        artifact = {
            "parts": {
                "body": {"parent_name": ""},
                "leg": {"parent_name": "body"},
            }
        }
        assert plugin.check(artifact) == []


# ===================================================================
# G. SymmetryValidityChecker
# ===================================================================


class TestSymmetryValidityChecker:
    """Verify symmetry_validity plugin."""

    def test_none_any_count(self):
        """NONE symmetry with any count → OK."""
        plugin = SymmetryValidityChecker()
        for count in [0, 1, 2, 3, 5, 10]:
            artifact = {"parts": {"part": {"symmetry_group": "NONE", "instance_count": count}}}
            assert plugin.check(artifact) == []

    def test_left_right_x_count_2(self):
        """LEFT_RIGHT_X with count=2 → OK."""
        plugin = SymmetryValidityChecker()
        artifact = {"parts": {"part": {"symmetry_group": "LEFT_RIGHT_X", "instance_count": 2}}}
        assert plugin.check(artifact) == []

    def test_left_right_x_count_4(self):
        """LEFT_RIGHT_X with count=4 → OK (even ≥ 2)."""
        plugin = SymmetryValidityChecker()
        artifact = {"parts": {"part": {"symmetry_group": "LEFT_RIGHT_X", "instance_count": 4}}}
        assert plugin.check(artifact) == []

    def test_left_right_x_count_3(self):
        """LEFT_RIGHT_X with count=3 → violation (odd)."""
        plugin = SymmetryValidityChecker()
        artifact = {"parts": {"part": {"symmetry_group": "LEFT_RIGHT_X", "instance_count": 3}}}
        violations = plugin.check(artifact)
        assert len(violations) == 1
        assert violations[0].rule == "symmetry_validity"
        assert violations[0].severity == Severity.ERROR
        assert "instance_count=3" in violations[0].detail

    def test_left_right_x_count_0(self):
        """LEFT_RIGHT_X with count=0 → violation (< 2)."""
        plugin = SymmetryValidityChecker()
        artifact = {"parts": {"part": {"symmetry_group": "LEFT_RIGHT_X", "instance_count": 0}}}
        violations = plugin.check(artifact)
        assert len(violations) == 1

    def test_left_right_y_count_4(self):
        """LEFT_RIGHT_Y with count=4 → OK."""
        plugin = SymmetryValidityChecker()
        artifact = {"parts": {"part": {"symmetry_group": "LEFT_RIGHT_Y", "instance_count": 4}}}
        assert plugin.check(artifact) == []

    def test_left_right_y_count_1(self):
        """LEFT_RIGHT_Y with count=1 → violation (< 2)."""
        plugin = SymmetryValidityChecker()
        artifact = {"parts": {"part": {"symmetry_group": "LEFT_RIGHT_Y", "instance_count": 1}}}
        violations = plugin.check(artifact)
        assert len(violations) == 1

    def test_quadrant_z_count_4(self):
        """QUADRANT_Z with count=4 → OK."""
        plugin = SymmetryValidityChecker()
        artifact = {"parts": {"part": {"symmetry_group": "QUADRANT_Z", "instance_count": 4}}}
        assert plugin.check(artifact) == []

    def test_quadrant_z_count_3(self):
        """QUADRANT_Z with count=3 → violation."""
        plugin = SymmetryValidityChecker()
        artifact = {"parts": {"part": {"symmetry_group": "QUADRANT_Z", "instance_count": 3}}}
        violations = plugin.check(artifact)
        assert len(violations) == 1

    def test_quadrant_z_count_5(self):
        """QUADRANT_Z with count=5 → violation."""
        plugin = SymmetryValidityChecker()
        artifact = {"parts": {"part": {"symmetry_group": "QUADRANT_Z", "instance_count": 5}}}
        violations = plugin.check(artifact)
        assert len(violations) == 1

    def test_radial_4_z_count_4(self):
        """RADIAL_4_Z with count=4 → OK."""
        plugin = SymmetryValidityChecker()
        artifact = {"parts": {"part": {"symmetry_group": "RADIAL_4_Z", "instance_count": 4}}}
        assert plugin.check(artifact) == []

    def test_radial_4_z_count_2(self):
        """RADIAL_4_Z with count=2 → violation."""
        plugin = SymmetryValidityChecker()
        artifact = {"parts": {"part": {"symmetry_group": "RADIAL_4_Z", "instance_count": 2}}}
        violations = plugin.check(artifact)
        assert len(violations) == 1

    def test_radial_4_z_missing_count(self):
        """RADIAL_4_Z with default instance_count (1) → violation (not 4)."""
        plugin = SymmetryValidityChecker()
        artifact = {"parts": {"part": {"symmetry_group": "RADIAL_4_Z"}}}
        violations = plugin.check(artifact)
        assert len(violations) == 1

    def test_invalid_symmetry_group(self):
        """Invalid symmetry_group string → skipped."""
        plugin = SymmetryValidityChecker()
        artifact = {"parts": {"part": {"symmetry_group": "INVALID_GROUP", "instance_count": 1}}}
        assert plugin.check(artifact) == []

    def test_missing_symmetry_group(self):
        """Missing symmetry_group → skipped."""
        plugin = SymmetryValidityChecker()
        artifact = {"parts": {"part": {"instance_count": 1}}}
        assert plugin.check(artifact) == []

    def test_none_symmetry_group(self):
        """symmetry_group=None → skipped."""
        plugin = SymmetryValidityChecker()
        artifact = {"parts": {"part": {"symmetry_group": None, "instance_count": 1}}}
        assert plugin.check(artifact) == []

    def test_empty_parts(self):
        """Empty parts → no violations."""
        plugin = SymmetryValidityChecker()
        assert plugin.check({"parts": {}}) == []

    def test_multiple_parts_some_invalid(self):
        """Mixed valid and invalid symmetries → only invalid reported."""
        plugin = SymmetryValidityChecker()
        artifact = {
            "parts": {
                "good": {"symmetry_group": "NONE", "instance_count": 5},
                "bad": {"symmetry_group": "QUADRANT_Z", "instance_count": 3},
            }
        }
        violations = plugin.check(artifact)
        assert len(violations) == 1


# ===================================================================
# H. ChildSmallerThanParentChecker
# ===================================================================


class TestChildSmallerThanParentChecker:
    """Verify child_smaller_than_parent plugin."""

    def test_ok(self):
        """Child smaller in at least one dimension → no violations."""
        plugin = ChildSmallerThanParentChecker()
        artifact = {
            "parts": {
                "body": {"target_bbox": {"width": 2.0, "depth": 2.0, "height": 2.0}},
                "leg": {
                    "parent_name": "body",
                    "target_bbox": {"width": 0.5, "depth": 0.5, "height": 1.5},
                },
            }
        }
        assert plugin.check(artifact) == []

    def test_child_larger_all_dims(self):
        """Child larger in ALL dimensions → violation."""
        plugin = ChildSmallerThanParentChecker()
        artifact = {
            "parts": {
                "body": {"target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0}},
                "child": {
                    "parent_name": "body",
                    "target_bbox": {"width": 2.0, "depth": 2.0, "height": 2.0},
                },
            }
        }
        violations = plugin.check(artifact)
        assert len(violations) == 1
        assert violations[0].rule == "child_smaller_than_parent"
        assert violations[0].severity == Severity.ERROR

    def test_child_within_5_percent_tolerance(self):
        """Child up to 5% larger still counts as 'smaller' in that dimension."""
        plugin = ChildSmallerThanParentChecker()
        artifact = {
            "parts": {
                "body": {"target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0}},
                "child": {
                    "parent_name": "body",
                    "target_bbox": {"width": 1.05, "depth": 10.0, "height": 10.0},
                },
            }
        }
        # width is 1.05 <= 1.0 * 1.05 → within tolerance → counted as smaller
        # So smaller_dims >= 1 → OK
        assert plugin.check(artifact) == []

    def test_child_exceeds_tolerance(self):
        """Child > 5% larger in all dims → violation."""
        plugin = ChildSmallerThanParentChecker()
        artifact = {
            "parts": {
                "body": {"target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0}},
                "child": {
                    "parent_name": "body",
                    "target_bbox": {"width": 1.06, "depth": 1.06, "height": 1.06},
                },
            }
        }
        # 1.06 > 1.0 * 1.05 → exceeds tolerance → not counted as smaller
        # smaller_dims == 0 → violation
        violations = plugin.check(artifact)
        assert len(violations) == 1

    def test_child_smaller_in_two_dims_larger_in_one(self):
        """Child smaller in 2 dims, larger in 1 → OK (at least one dim smaller)."""
        plugin = ChildSmallerThanParentChecker()
        artifact = {
            "parts": {
                "body": {"target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0}},
                "child": {
                    "parent_name": "body",
                    "target_bbox": {"width": 0.5, "depth": 0.5, "height": 2.0},
                },
            }
        }
        assert plugin.check(artifact) == []

    def test_no_parent(self):
        """Part without parent_name → skipped."""
        plugin = ChildSmallerThanParentChecker()
        artifact = {
            "parts": {
                "body": {"target_bbox": {"width": 2.0, "depth": 2.0, "height": 2.0}},
                "child": {"target_bbox": {"width": 10.0, "depth": 10.0, "height": 10.0}},
            }
        }
        assert plugin.check(artifact) == []

    def test_missing_child_bbox(self):
        """Child without target_bbox → skipped."""
        plugin = ChildSmallerThanParentChecker()
        artifact = {
            "parts": {
                "body": {"target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0}},
                "child": {"parent_name": "body"},
            }
        }
        assert plugin.check(artifact) == []

    def test_missing_parent_bbox(self):
        """Parent without target_bbox → skipped."""
        plugin = ChildSmallerThanParentChecker()
        artifact = {
            "parts": {
                "body": {},
                "child": {
                    "parent_name": "body",
                    "target_bbox": {"width": 0.5, "depth": 0.5, "height": 0.5},
                },
            }
        }
        assert plugin.check(artifact) == []

    def test_parent_not_in_parts(self):
        """Parent reference not in parts dict → skipped."""
        plugin = ChildSmallerThanParentChecker()
        artifact = {
            "parts": {
                "child": {
                    "parent_name": "nonexistent",
                    "target_bbox": {"width": 0.5, "depth": 0.5, "height": 0.5},
                },
            }
        }
        assert plugin.check(artifact) == []

    def test_empty_parts(self):
        """Empty parts → no violations."""
        plugin = ChildSmallerThanParentChecker()
        assert plugin.check({"parts": {}}) == []

    def test_partial_bbox_dims(self):
        """Partial bbox dims on parent → missing dims skipped."""
        plugin = ChildSmallerThanParentChecker()
        artifact = {
            "parts": {
                "body": {"target_bbox": {"width": 1.0}},  # missing depth and height
                "child": {
                    "parent_name": "body",
                    "target_bbox": {"width": 0.5, "depth": 0.5, "height": 0.5},
                },
            }
        }
        # child.width=0.5 <= parent.width=1.0 → smaller_dims >= 1 → OK
        assert plugin.check(artifact) == []


# ===================================================================
# I. ConstraintChecker orchestration
# ===================================================================


class TestConstraintChecker:
    """Verify ConstraintChecker registry and run methods."""

    def test_register_and_run_all(self):
        """Register multiple plugins → run returns all violations."""
        checker = ConstraintChecker()
        checker.register(PrimitiveSupportedChecker())
        checker.register(SymmetryValidityChecker())

        artifact = {
            "parts": {
                "body": {"primitive": "torus"},  # unsupported
                "arm": {
                    "primitive": "cube",
                    "symmetry_group": "QUADRANT_Z",
                    "instance_count": 3,  # invalid: QUADRANT_Z needs 4
                },
            }
        }
        violations = checker.run(artifact)
        assert len(violations) == 2
        assert all(isinstance(v, ConstraintViolation) for v in violations)
        rules = {v.rule for v in violations}
        assert rules == {"primitive_supported", "symmetry_validity"}

    def test_run_quick(self):
        """run_quick only runs plugins with quick=True."""
        checker = ConstraintChecker()
        checker.register(PrimitiveSupportedChecker())  # quick=True

        artifact = {"parts": {"body": {"primitive": "cube"}}}
        assert checker.run_quick(artifact) == []

    def test_run_quick_with_violations(self):
        """run_quick returns violations from quick plugins."""
        checker = ConstraintChecker()
        checker.register(BboxRangeChecker())  # quick=True

        artifact = {"parts": {"body": {"target_bbox": {"width": 200.0, "depth": 0.5, "height": 0.5}}}}
        violations = checker.run_quick(artifact)
        assert len(violations) == 1

    def test_run_empty_checker(self):
        """Checker with no plugins → empty violations."""
        checker = ConstraintChecker()
        assert checker.run({"parts": {}}) == []
        assert checker.run_quick({"parts": {}}) == []

    def test_run_passes_manifests(self):
        """Manifest data forwarded to plugins."""
        checker = ConstraintChecker()
        checker.register(PrimitiveSupportedChecker())

        artifact = {"parts": {"ring": {"primitive": "torus"}}}
        manifests = {"supported_primitives": ["cube", "torus"]}
        assert checker.run(artifact, manifests) == []

    def test_run_multiple_plugins_aggregate(self):
        """Violations from multiple plugins are aggregated."""
        checker = ConstraintChecker()
        checker.register(PrimitiveSupportedChecker())
        checker.register(BboxRangeChecker())

        artifact = {
            "parts": {
                "body": {
                    "primitive": "torus",
                    "target_bbox": {"width": 200.0, "depth": 0.5, "height": 0.5},
                },
            }
        }
        violations = checker.run(artifact)
        assert len(violations) == 2  # one from each plugin

    def test_register_replaces_existing(self):
        """Registering a plugin with the same name replaces the old one."""
        checker = ConstraintChecker()

        class PluginA:
            name = "test_plugin"
            quick = True
            def check(self, artifact, manifests=None):
                return [ConstraintViolation(rule="test_plugin", detail="from A", severity=Severity.ERROR)]

        class PluginB:
            name = "test_plugin"
            quick = True
            def check(self, artifact, manifests=None):
                return [ConstraintViolation(rule="test_plugin", detail="from B", severity=Severity.WARNING)]

        checker.register(PluginA())
        checker.register(PluginB())
        violations = checker.run(None)
        assert len(violations) == 1
        assert violations[0].detail == "from B"

    def test_check_corrections(self):
        """check_corrections applies fix to a copy and runs quick plugins."""
        checker = ConstraintChecker()
        checker.register(BboxRangeChecker())

        artifact = {
            "parts": {
                "leg": {"target_bbox": {"width": 200.0, "depth": 0.5, "height": 0.5}},
            }
        }

        def fix(a):
            a["parts"]["leg"]["target_bbox"]["width"] = 0.5

        violations = checker.check_corrections(fix, artifact)
        assert violations == []  # After fix, bbox within range

        # Original artifact unchanged
        assert artifact["parts"]["leg"]["target_bbox"]["width"] == 200.0

    def test_check_corrections_preserves_original_deep(self):
        """Deep copy ensures nested mutations don't leak."""
        checker = ConstraintChecker()
        checker.register(BboxRangeChecker())

        artifact = {
            "parts": {
                "leg": {"target_bbox": {"width": 200.0, "depth": 0.5, "height": 0.5}},
            }
        }

        def fix(a):
            a["parts"]["leg"]["target_bbox"]["width"] = 0.5

        checker.check_corrections(fix, artifact)
        assert artifact["parts"]["leg"]["target_bbox"]["width"] == 200.0

    def test_check_corrections_still_detects_violations(self):
        """check_corrections returns violations when fix is insufficient."""
        checker = ConstraintChecker()
        checker.register(BboxRangeChecker())

        artifact = {
            "parts": {
                "leg": {"target_bbox": {"width": 200.0, "depth": 0.5, "height": 0.5}},
            }
        }

        def bad_fix(a):
            a["parts"]["leg"]["target_bbox"]["width"] = 150.0  # still too large

        violations = checker.check_corrections(bad_fix, artifact)
        assert len(violations) == 1


# ===================================================================
# J. Plugin exception handling
# ===================================================================


class TestCheckerPluginException:
    """Verify checker handles plugin exceptions gracefully."""

    def test_plugin_raises_exception(self):
        """Plugin that raises an exception → single ERROR violation."""
        checker = ConstraintChecker()

        class BadPlugin:
            name = "bad"
            quick = True
            def check(self, artifact, manifests=None):
                raise RuntimeError("oops")

        checker.register(BadPlugin())
        violations = checker.run(None)
        assert len(violations) == 1
        assert violations[0].rule == "bad"
        assert violations[0].severity == Severity.ERROR
        assert "oops" in violations[0].detail

    def test_run_quick_plugin_exception(self):
        """run_quick catches plugin exceptions too."""
        checker = ConstraintChecker()

        class BadPlugin:
            name = "bad"
            quick = True
            def check(self, artifact, manifests=None):
                raise ValueError("fail")

        checker.register(BadPlugin())
        violations = checker.run_quick(None)
        assert len(violations) == 1
        assert violations[0].rule == "bad"

    def test_good_plugin_still_runs_after_bad(self):
        """Checker continues with next plugin after a failing one."""
        checker = ConstraintChecker()

        class BadPlugin:
            name = "bad"
            quick = True
            def check(self, artifact, manifests=None):
                raise RuntimeError("oops")

        checker.register(BadPlugin())
        checker.register(PrimitiveSupportedChecker())

        artifact = {"parts": {"body": {"primitive": "torus"}}}
        violations = checker.run(artifact)
        assert len(violations) == 2  # one from BadPlugin, one from PrimitiveSupportedChecker
        rules = {v.rule for v in violations}
        assert rules == {"bad", "primitive_supported"}

    def test_plugin_not_quick_skipped_in_run_quick(self):
        """Plugin with quick=False is skipped by run_quick."""
        checker = ConstraintChecker()

        class SlowPlugin:
            name = "slow"
            quick = False
            def check(self, artifact, manifests=None):
                return [ConstraintViolation(rule="slow", detail="slow check", severity=Severity.ERROR)]

        checker.register(SlowPlugin())
        assert checker.run_quick(None) == []

    def test_plugin_not_quick_included_in_run(self):
        """Plugin with quick=False is still included in full run."""
        checker = ConstraintChecker()

        class SlowPlugin:
            name = "slow"
            quick = False
            def check(self, artifact, manifests=None):
                return [ConstraintViolation(rule="slow", detail="slow check", severity=Severity.ERROR)]

        checker.register(SlowPlugin())
        violations = checker.run(None)
        assert len(violations) == 1
        assert violations[0].rule == "slow"


# ===================================================================
# K. Integration scenarios (multiple plugins, realistic artifacts)
# ===================================================================


class TestIntegrationScenarios:
    """Higher-level scenarios combining multiple plugins."""

    def test_complete_valid_artifact(self):
        """A fully valid artifact passes all checks."""
        checker = ConstraintChecker()
        checker.register(PrimitiveSupportedChecker())
        checker.register(BboxRangeChecker())
        checker.register(AttachmentInBboxChecker())
        checker.register(ParentHasAttachmentChecker())
        checker.register(NoOrphansPartsChecker())
        checker.register(SymmetryValidityChecker())
        checker.register(ChildSmallerThanParentChecker())

        artifact = {
            "parts": {
                "body": {
                    "primitive": "cube",
                    "target_bbox": {"width": 2.0, "depth": 2.0, "height": 1.0},
                    "attachment_points": [
                        {"name": "top", "local_offset": [0.0, 0.0, 0.5]},
                    ],
                },
                "leg": {
                    "primitive": "cylinder",
                    "parent_name": "body",
                    "target_bbox": {"width": 0.3, "depth": 0.3, "height": 0.8},
                    "attachment_points": [
                        {"name": "wheel_mount", "local_offset": [0.0, 0.0, 0.0]},
                    ],
                },
                "wheel": {
                    "primitive": "cylinder",
                    "parent_name": "leg",
                    "target_bbox": {"width": 0.5, "depth": 0.5, "height": 0.2},
                    "symmetry_group": "LEFT_RIGHT_X",
                    "instance_count": 2,
                },
            }
        }
        violations = checker.run(artifact)
        assert violations == []

    def test_complete_invalid_artifact(self):
        """An artifact with many violations reports them all."""
        checker = ConstraintChecker()
        checker.register(PrimitiveSupportedChecker())
        checker.register(BboxRangeChecker())
        checker.register(AttachmentInBboxChecker())
        checker.register(ParentHasAttachmentChecker())
        checker.register(NoOrphansPartsChecker())
        checker.register(SymmetryValidityChecker())
        checker.register(ChildSmallerThanParentChecker())

        artifact = {
            "parts": {
                "body": {
                    "primitive": "torus",  # unsupported
                    "target_bbox": {"width": 200.0, "depth": 0.5, "height": 0.5},  # too wide
                },
                "leg": {
                    "primitive": "cube",
                    "parent_name": "body",
                    "target_bbox": {"width": 5.0, "depth": 5.0, "height": 5.0},  # larger than parent in all dims
                },
                "orphan": {
                    "primitive": "cube",
                    "parent_name": "nonexistent",  # dangling ref
                    "symmetry_group": "RADIAL_4_Z",
                    "instance_count": 2,  # should be 4
                },
            }
        }
        violations = checker.run(artifact)
        # Expected violations:
        #   primitive_supported: torus
        #   bbox_range: body width too large
        #   child_smaller_than_parent: leg larger than body in all dims
        #   parent_has_attachment: body has no attachments (referenced by leg) — WARNING
        #   no_orphans: dangling ref "nonexistent" (also zero roots — leg is not root since has parent, body root, orphan parent is non-existent)
        #   symmetry_validity: orphan RADIAL_4_Z count=2
        # Let's be precise:
        #   roots: body (parent_name=None), orphan (parent_name="nonexistent" → not None, so not root)
        #   → one root (body) → OK for roots
        #   dangling: {"nonexistent"} → violation
        #   parent_has_attachment: body has no attachments → WARNING
        #   child_smaller_than_parent: leg (5,5,5) vs body (200,0.5,0.5)
        #     - width: 5 <= 200*1.05=210 → smaller ✓
        #     - depth: 5 > 0.5*1.05=0.525 → not smaller
        #     - height: 5 > 0.5*1.05=0.525 → not smaller
        #     → smaller_dims=1 → OK! No violation
        assert len(violations) >= 4  # at least 4 distinct violations
        rules = {v.rule for v in violations}
        assert "primitive_supported" in rules
        assert "bbox_range" in rules
        assert "no_orphans" in rules
        assert "symmetry_validity" in rules

    def test_artifact_as_object(self):
        """Plugins work with non-dict artifacts (object-style)."""
        from dataclasses import dataclass, field

        @dataclass
        class PartSpec:
            primitive: str = ""
            target_bbox: dict = field(default_factory=dict)
            parent_name: str = ""
            attachment_points: list = field(default_factory=list)
            symmetry_group: str = ""
            instance_count: int = 1

        @dataclass
        class Artifact:
            parts: dict = field(default_factory=dict)

        artifact = Artifact(parts={
            "body": PartSpec(primitive="cube", target_bbox={"width": 1.0, "depth": 1.0, "height": 1.0}),
            "leg": PartSpec(primitive="cylinder", parent_name="body",
                            target_bbox={"width": 0.5, "depth": 0.5, "height": 0.5}),
        })

        checker = ConstraintChecker()
        checker.register(PrimitiveSupportedChecker())
        checker.register(BboxRangeChecker())
        checker.register(ChildSmallerThanParentChecker())
        assert checker.run(artifact) == []
