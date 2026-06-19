"""DAG builder and topological sorter for the D&C pipeline.

Determines the correct build order of part families and detects cycles
in the parent-child dependency graph.  All logic is pure and
deterministic — no LLM calls involved.
"""

from typing import Dict, List, Optional, Set

from ai_3d_modeling_agent.schemas.part import PartFamily, SymmetryGroup


def build_execution_dag(part_families: List[PartFamily]) -> List[List[PartFamily]]:
    """Partition part families into dependency-respecting build layers.

    Each layer is a list of families that can be built **in parallel**
    because they share the same depth in the dependency DAG.
    Layers are ordered sequentially — layer N must finish before
    layer N+1 begins.

    Parameters
    ----------
    part_families:
        All families from the decompose phase.

    Returns
    -------
    ``List[List[PartFamily]]``
        Layers ordered from root to deepest leaf.  Each inner list
        contains families that can build concurrently.

    Raises
    ------
    ValueError
        If the dependency graph contains a cycle.
    """
    cycle = detect_cycles(part_families)
    if cycle:
        raise ValueError(
            f"Circular dependency detected in part family graph: "
            f"{' → '.join(cycle)}"
        )

    # Build parent → children adjacency.
    children_of: Dict[str, List[PartFamily]] = {}
    name_to_family: Dict[str, PartFamily] = {}
    for family in part_families:
        name_to_family[family.name] = family
        parent_key = family.parent_name if family.parent_name else "__ROOT__"
        children_of.setdefault(parent_key, []).append(family)

    # BFS layering.
    layers: List[List[PartFamily]] = []
    visited: Set[str] = {"__ROOT__"}
    current: List[PartFamily] = children_of.get("__ROOT__", [])

    while current:
        layer: List[PartFamily] = []
        next_names: Set[str] = set()
        for family in current:
            if family.name in visited:
                continue
            visited.add(family.name)
            layer.append(family)
            for child in children_of.get(family.name, []):
                next_names.add(child.name)
        if layer:
            layers.append(layer)
        # Resolve next layer by name.
        current = [
            name_to_family[n] for n in next_names if n in name_to_family
        ]

    return layers


def detect_cycles(part_families: List[PartFamily]) -> Optional[List[str]]:
    """Detect circular parent references in the part family graph.

    Uses standard DFS with three-colour marking.

    Parameters
    ----------
    part_families:
        All families from the decompose phase.

    Returns
    -------
    ``List[str]``
        The cycle path (e.g. ``["A", "B", "A"]``) if a cycle exists.
    ``None``
        If the graph is acyclic.
    """
    # Build name → [child names] adjacency.
    adj: Dict[str, List[str]] = {}
    for f in part_families:
        adj.setdefault(f.name, [])
    for f in part_families:
        if f.parent_name and f.parent_name != "__ROOT__":
            adj.setdefault(f.parent_name, []).append(f.name)

    names = list(adj.keys())

    WHITE, GRAY, BLACK = 0, 1, 2
    colour = {n: WHITE for n in names}
    parent: Dict[str, Optional[str]] = {}

    cycle_path: List[str] = []

    def _dfs(node: str) -> bool:
        colour[node] = GRAY
        for neighbour in adj.get(node, []):
            if neighbour not in colour:
                continue  # neighbour not in part_families — skip
            if colour[neighbour] == GRAY:
                # Found a back edge → cycle.
                cycle_path.append(neighbour)
                cycle_path.append(node)
                n: Optional[str] = parent.get(node)
                while n is not None and n != neighbour:
                    cycle_path.append(n)
                    n = parent.get(n)
                cycle_path.reverse()
                return True
            if colour[neighbour] == WHITE:
                parent[neighbour] = node
                if _dfs(neighbour):
                    return True
        colour[node] = BLACK
        return False

    for name in names:
        if colour[name] == WHITE:
            if _dfs(name):
                return cycle_path

    return None


def validate_part_families(part_families: List[PartFamily]) -> List[str]:
    """Validate a list of part families against DAG rules.

    Returns a list of error messages (empty list = valid).

    Checks
    ------
    1. At least one family exists.
    2. All names are non-empty and unique.
    3. Exactly one root family (``parent_name is None``).
    4. ``parent_name`` values reference existing family names.
    5. No cycles in the dependency graph.
    6. ``instance_count`` >= 1.
    7. ``instance_count`` compatible with ``symmetry_group``.
    """
    errors: List[str] = []

    if not part_families:
        errors.append("part_families is empty")
        return errors

    names = [f.name for f in part_families]

    # ── non-empty names ──────────────────────────────────────────
    for f in part_families:
        if not f.name.strip():
            errors.append("Part family has empty name")
        elif names.count(f.name) > 1:
            errors.append(f"Duplicate part family name: '{f.name}'")

    # ── unique names ─────────────────────────────────────────────
    name_set = {f.name for f in part_families}
    if len(name_set) != len(part_families):
        # Duplicates already reported above.
        pass

    # ── single root ──────────────────────────────────────────────
    roots = [f for f in part_families if f.parent_name is None]
    if len(roots) == 0:
        errors.append("No root part family found (one must have parent_name=None)")
    elif len(roots) > 1:
        names_str = ", ".join(f"'{r.name}'" for r in roots)
        errors.append(f"Multiple root part families: {names_str}")

    # ── parent references ────────────────────────────────────────
    for f in part_families:
        if f.parent_name is not None and f.parent_name not in name_set:
            errors.append(
                f"'{f.name}' references unknown parent '{f.parent_name}'"
            )

    # ── cycles ───────────────────────────────────────────────────
    cycle = detect_cycles(part_families)
    if cycle:
        errors.append(f"Circular dependency: {' → '.join(cycle)}")

    # ── root part rules ──────────────────────────────────────────
    for f in part_families:
        if f.parent_name is None:
            if f.instance_count != 1:
                errors.append(
                    f"Root part '{f.name}' must have instance_count=1 "
                    f"(got {f.instance_count})"
                )
            if f.symmetry_group != SymmetryGroup.NONE:
                errors.append(
                    f"Root part '{f.name}' must have symmetry_group=NONE "
                    f"(got {f.symmetry_group.value})"
                )

    # ── instance_count ───────────────────────────────────────────
    for f in part_families:
        if f.instance_count < 1:
            errors.append(f"'{f.name}' has instance_count={f.instance_count} (< 1)")

        if f.symmetry_group == SymmetryGroup.QUADRANT_Z and f.instance_count != 4:
            errors.append(
                f"'{f.name}' has symmetry_group=QUADRANT_Z but "
                f"instance_count={f.instance_count} (must be 4)"
            )
        if f.symmetry_group == SymmetryGroup.RADIAL_4_Z and f.instance_count != 4:
            errors.append(
                f"'{f.name}' has symmetry_group=RADIAL_4_Z but "
                f"instance_count={f.instance_count} (must be 4)"
            )
        if f.symmetry_group in (
            SymmetryGroup.LEFT_RIGHT_X,
            SymmetryGroup.LEFT_RIGHT_Y,
        ) and f.instance_count % 2 != 0:
            errors.append(
                f"'{f.name}' has symmetry_group={f.symmetry_group.value} but "
                f"instance_count={f.instance_count} (must be even)"
            )

    return errors


def find_orphans(part_families: List[PartFamily]) -> List[str]:
    """Return names of families whose parent is not in *part_families*.

    Families whose parent is ``None`` (root) are never orphans.
    """
    names = {f.name for f in part_families}
    orphans = []
    for f in part_families:
        if f.parent_name is not None and f.parent_name not in names:
            orphans.append(f.name)
    return orphans
