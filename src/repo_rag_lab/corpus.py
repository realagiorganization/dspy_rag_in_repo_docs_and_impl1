"""Repository file loading helpers for the baseline text corpus."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    ".codex",
    ".git",
    ".github",
    ".mypy_cache",
    ".pre-commit-cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    ".repo_rag_cache",
    ".pytest_cache",
    "_context_repos",
    "artifacts",
    "prompt_artifacts",
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


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    resolved_root = root.resolve()
    for path in iter_text_files(resolved_root):
        docs.append(_read_document(path, root=resolved_root))
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
        docs.append(_read_document(path, root=resolved_root))
        seen_paths.add(path)
    return docs


def _read_document(path: Path, *, root: Path | None = None) -> RepoDocument:
    """Read a single text document with UTF-8 fallback behavior."""

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="ignore")
    if root is not None:
        with suppress(ValueError):
            path = path.relative_to(root)
    return RepoDocument(path=path, text=text)


def build_corpus_manifest(
    root: Path,
    *,
    documents: Iterable[RepoDocument] | None = None,
) -> dict[str, Any]:
    """Return a stable retrieval-corpus manifest for the current repository text set."""

    resolved_root = root.resolve()
    manifest_entries: list[dict[str, Any]] = []

    if documents is None:
        for path in iter_text_files(resolved_root):
            stat = path.stat()
            document = _read_document(path, root=resolved_root)
            manifest_entries.append(
                {
                    "path": document.path.as_posix(),
                    "size_bytes": int(stat.st_size),
                    "mtime_ns": int(stat.st_mtime_ns),
                    "text_sha256": _text_sha256(document.text),
                }
            )
    else:
        for document in documents:
            relative_path = document.path
            absolute_path = (
                relative_path
                if relative_path.is_absolute()
                else (resolved_root / relative_path).resolve()
            )
            stat = absolute_path.stat()
            manifest_entries.append(
                {
                    "path": relative_path.as_posix(),
                    "size_bytes": int(stat.st_size),
                    "mtime_ns": int(stat.st_mtime_ns),
                    "text_sha256": _text_sha256(document.text),
                }
            )

    manifest_entries.sort(key=lambda entry: str(entry["path"]))
    fingerprint_material = "\n".join(
        f'{entry["path"]}\t{entry["text_sha256"]}\t{entry["size_bytes"]}\t{entry["mtime_ns"]}'
        for entry in manifest_entries
    )
    return {
        "schema_version": 1,
        "root": str(resolved_root),
        "document_count": len(manifest_entries),
        "entries": manifest_entries,
        "corpus_fingerprint": hashlib.sha256(
            fingerprint_material.encode("utf-8")
        ).hexdigest(),
    }


def write_corpus_manifest(manifest_path: Path, manifest: dict[str, Any]) -> Path:
    """Persist one retrieval-corpus manifest to disk."""

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(f"{json.dumps(manifest, indent=2)}\n", encoding="utf-8")
    return manifest_path
