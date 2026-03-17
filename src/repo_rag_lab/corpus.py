"""Repository file loading helpers for the baseline text corpus."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

TEXT_SUFFIXES = {
    ".c",
    ".h",
    ".md",
    ".txt",
    ".py",
    ".rs",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".feature",
}

EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pre-commit-cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "artifacts",
    "target",
    "build",
    "dist",
    "htmlcov",
}


@dataclass(frozen=True)
class RepoDocument:
    """A repository file loaded as text for retrieval."""

    path: Path
    text: str


def iter_text_files(root: Path) -> Iterable[Path]:
    """Yield supported text files while skipping generated and cache directories."""

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        yield path


def load_documents(root: Path) -> list[RepoDocument]:
    """Load the repository corpus into in-memory text documents."""

    docs: list[RepoDocument] = []
    for path in iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")
        docs.append(RepoDocument(path=path, text=text))
    return docs
