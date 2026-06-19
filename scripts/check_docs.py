"""Lightweight documentation hygiene checks."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
ARCHIVE_DIR = DOCS_DIR / "archive"

ACTIVE_FORBIDDEN = [
    "run_mvp",
    "llm_endpoint",
    "Verify LLM",
    "LLM:",
    "use_dnc",
    "legacy-dnc",
]

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+\.md)(?:#[^)]+)?\)")


def is_archive(path: Path) -> bool:
    try:
        path.relative_to(ARCHIVE_DIR)
    except ValueError:
        return False
    return True


def check_archive_notices(errors: list[str]) -> None:
    for path in sorted(ARCHIVE_DIR.glob("*.md")):
        if path.name == "index.md":
            continue
        first_line = path.read_text(encoding="utf-8").splitlines()[0:1]
        if first_line != ["# Archived Reference"]:
            errors.append(f"{path}: missing '# Archived Reference' notice")


def check_active_forbidden_terms(errors: list[str]) -> None:
    for path in sorted(DOCS_DIR.rglob("*.md")):
        if is_archive(path):
            continue
        text = path.read_text(encoding="utf-8")
        for term in ACTIVE_FORBIDDEN:
            if term in text:
                errors.append(f"{path}: active docs contain removed term {term!r}")


def normalize_link_target(path: Path, raw_target: str) -> Path | None:
    if raw_target.startswith(("http://", "https://", "mailto:")):
        return None
    target = raw_target.split("#", 1)[0].strip()
    if not target or target.startswith("<"):
        target = target.strip("<>")
    return (path.parent / target).resolve()


def check_markdown_links(errors: list[str]) -> None:
    for path in sorted(DOCS_DIR.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            target = normalize_link_target(path, match.group(1))
            if target is None:
                continue
            if not target.exists():
                rel = path.relative_to(REPO_ROOT)
                errors.append(f"{rel}: broken markdown link {match.group(1)!r}")


def main() -> int:
    errors: list[str] = []
    check_archive_notices(errors)
    check_active_forbidden_terms(errors)
    check_markdown_links(errors)

    if errors:
        print("Documentation checks failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Documentation checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
