from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepoSettings:
    root: Path
    docs_dir: Path
    notebooks_dir: Path
    artifacts_dir: Path

    @classmethod
    def from_root(cls, root: Path) -> "RepoSettings":
        return cls(
            root=root,
            docs_dir=root / "documentation",
            notebooks_dir=root / "notebooks",
            artifacts_dir=root / "artifacts",
        )

