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
        docs.append(_read_document(path))
    return docs


def load_documents_for_paths(root: Path, paths: Iterable[Path]) -> list[RepoDocument]:
    """Load a selected subset of repository documents."""

    docs: list[RepoDocument] = []
    seen_paths: set[Path] = set()
    resolved_root = root.resolve()
    for raw_path in paths:
        path = raw_path if raw_path.is_absolute() else resolved_root / raw_path
        try:
            relative_path = path.relative_to(resolved_root)
        except ValueError:
            continue
        if path in seen_paths:
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in EXCLUDED_PARTS for part in relative_path.parts):
            continue
        docs.append(_read_document(path))
        seen_paths.add(path)
    return docs


def _read_document(path: Path) -> RepoDocument:
    """Read a single text document with UTF-8 fallback behavior."""

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="ignore")
    return RepoDocument(path=path, text=text)
