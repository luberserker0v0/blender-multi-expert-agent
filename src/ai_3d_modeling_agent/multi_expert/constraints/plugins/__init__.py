"""Constraint plugin registry — exports all 7 built-in plugins."""

from __future__ import annotations

from .attachment_in_bbox import AttachmentInBboxChecker
from .bbox_range import BboxRangeChecker
from .child_smaller_than_parent import ChildSmallerThanParentChecker
from .no_orphans import NoOrphansPartsChecker
from .parent_has_attachment import ParentHasAttachmentChecker
from .primitive_supported import PrimitiveSupportedChecker
from .symmetry_validity import SymmetryValidityChecker

__all__ = [
    "AttachmentInBboxChecker",
    "BboxRangeChecker",
    "ChildSmallerThanParentChecker",
    "NoOrphansPartsChecker",
    "ParentHasAttachmentChecker",
    "PrimitiveSupportedChecker",
    "SymmetryValidityChecker",
]
