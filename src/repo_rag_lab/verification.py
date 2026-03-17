"""Verification helpers for Makefile and notebook contract checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import nbformat
from nbformat.validator import validate as validate_notebook_document

REQUIRED_MAKE_TARGETS = {
    "setup",
    "sync",
    "lock",
    "hooks-install",
    "ask",
    "discover-mcp",
    "utility-summary",
    "smoke-test",
    "verify-surfaces",
    "gh-runs",
    "gh-watch",
    "gh-failed-logs",
    "compile",
    "coverage",
    "lint",
    "typecheck",
    "test",
    "build",
    "publish",
    "quality",
}
MAX_NOTEBOOK_CODE_LINES = 25


@dataclass(frozen=True)
class VerificationIssue:
    """A user-facing repository-surface verification issue."""

    path: str
    message: str


def _collect_phony_targets(makefile_text: str) -> set[str]:
    """Collect all `.PHONY` target names declared in the Makefile."""

    phony_targets: set[str] = set()
    for line in makefile_text.splitlines():
        if line.startswith(".PHONY:"):
            _, _, targets = line.partition(":")
            phony_targets.update(targets.split())
    return phony_targets


def validate_makefile(path: Path) -> list[VerificationIssue]:
    """Validate that the Makefile exposes the required repository targets."""

    makefile_text = path.read_text(encoding="utf-8")
    issues: list[VerificationIssue] = []
    phony_targets = _collect_phony_targets(makefile_text)

    for target in sorted(REQUIRED_MAKE_TARGETS):
        if f"{target}:" not in makefile_text:
            issues.append(VerificationIssue(path=str(path), message=f"Missing target `{target}`."))
        if target not in phony_targets:
            issues.append(
                VerificationIssue(
                    path=str(path),
                    message=f"Target `{target}` must be listed in .PHONY.",
                )
            )

    return issues


def validate_notebook(path: Path) -> list[VerificationIssue]:
    """Validate that a notebook matches the repository's playbook conventions."""

    notebook = nbformat.read(path, as_version=4)
    validate_notebook_document(notebook)
    issues: list[VerificationIssue] = []
    markdown_headings = 0

    for index, cell in enumerate(notebook.cells, start=1):
        if cell.cell_type == "markdown" and cell.source.lstrip().startswith("#"):
            markdown_headings += 1

        if cell.cell_type != "code":
            continue

        non_empty_lines = [line for line in cell.source.splitlines() if line.strip()]
        if len(non_empty_lines) > MAX_NOTEBOOK_CODE_LINES:
            issues.append(
                VerificationIssue(
                    path=str(path),
                    message=(
                        f"Code cell {index} has {len(non_empty_lines)} non-empty lines; "
                        f"limit is {MAX_NOTEBOOK_CODE_LINES}."
                    ),
                )
            )

    if markdown_headings == 0:
        issues.append(
            VerificationIssue(
                path=str(path),
                message="Notebook must include at least one Markdown heading cell.",
            )
        )

    return issues


def verify_repository_surfaces(root: Path) -> dict[str, object]:
    """Validate the Makefile and all tracked notebooks under ``root``."""

    issues = validate_makefile(root / "Makefile")
    notebooks = sorted((root / "notebooks").glob("*.ipynb"))
    for notebook_path in notebooks:
        issues.extend(validate_notebook(notebook_path))

    return {
        "checked_makefile": "Makefile",
        "checked_notebook_count": len(notebooks),
        "issue_count": len(issues),
        "issues": [issue.__dict__ for issue in issues],
    }
