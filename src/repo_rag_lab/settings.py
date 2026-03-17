"""Shared repository path settings derived from a repository root."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepoSettings:
    """Resolved path settings for documentation, notebooks, and artifacts."""

    root: Path
    docs_dir: Path
    notebooks_dir: Path
    artifacts_dir: Path

    @classmethod
    def from_root(cls, root: Path) -> RepoSettings:
        """Build repository settings from a repository root directory."""

        return cls(
            root=root,
            docs_dir=root / "documentation",
            notebooks_dir=root / "notebooks",
            artifacts_dir=root / "artifacts",
        )
