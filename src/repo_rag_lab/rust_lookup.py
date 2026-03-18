"""Helpers for the native Rust-backed SQLite lookup index."""

from __future__ import annotations

import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_PATH = Path("artifacts/sqlite/repo-file-index.sqlite3")
DEFAULT_LOOKUP_LIMIT = 8
DEFAULT_MAX_TEXT_BYTES = 1_000_000
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "does",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "use",
    "using",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUST_MANIFEST_PATH = _REPO_ROOT / "rust-cli" / "Cargo.toml"


@dataclass(frozen=True)
class LookupHit:
    """A ranked file hit returned from the native SQLite lookup index."""

    path: Path
    line_count: int
    snippet: str
    score: float


def supports_native_lookup(root: Path) -> bool:
    """Return ``True`` when ``root`` matches the repository root with the Rust wrapper."""

    return root.resolve() == _REPO_ROOT and _RUST_MANIFEST_PATH.exists()


def lookup_candidate_paths(
    question: str,
    root: Path,
    *,
    limit: int = DEFAULT_LOOKUP_LIMIT,
) -> list[Path]:
    """Return lookup-ranked relative file paths for ``question`` when native lookup is usable."""

    try:
        return [hit.path for hit in lookup_repository(question, root, limit=limit)]
    except LookupUnavailableError:
        return []


def lookup_repository(
    question: str,
    root: Path,
    *,
    limit: int = DEFAULT_LOOKUP_LIMIT,
) -> list[LookupHit]:
    """Query the Rust-managed SQLite FTS index for ``question``."""

    resolved_root = root.resolve()
    if not supports_native_lookup(resolved_root):
        return []

    match_query = _build_match_query(question)
    if match_query is None:
        return []

    db_path = resolved_root / DEFAULT_DB_PATH
    _ensure_index_is_fresh(resolved_root, db_path)

    try:
        connection = sqlite3.connect(db_path)
    except sqlite3.Error as error:
        raise LookupUnavailableError(f"failed to open {db_path}: {error}") from error

    try:
        rows = connection.execute(
            """
            SELECT file_lookup.path,
                   indexed_files.line_count,
                   snippet(file_lookup, 1, '[', ']', ' ... ', 18),
                   bm25(file_lookup) AS score
            FROM file_lookup
            JOIN indexed_files ON indexed_files.path = file_lookup.path
            WHERE file_lookup MATCH ?
            ORDER BY score, file_lookup.path
            LIMIT ?
            """,
            (match_query, limit),
        ).fetchall()
    except sqlite3.Error as error:
        raise LookupUnavailableError(f"failed to query native lookup index: {error}") from error
    finally:
        connection.close()

    return [
        LookupHit(
            path=Path(path_text),
            line_count=int(line_count),
            snippet=str(snippet).replace("\n", " "),
            score=float(score),
        )
        for path_text, line_count, snippet, score in rows
    ]


class LookupUnavailableError(RuntimeError):
    """Raised when the native lookup index cannot be used safely."""


def _ensure_index_is_fresh(root: Path, db_path: Path) -> None:
    if _db_needs_refresh(root, db_path):
        _run_rust_indexer(root, db_path)


def _db_needs_refresh(root: Path, db_path: Path) -> bool:
    if not db_path.exists():
        return True

    tracked_files = _list_tracked_files(root)
    db_modified = db_path.stat().st_mtime
    try:
        connection = sqlite3.connect(db_path)
    except sqlite3.Error:
        return True

    try:
        indexed_head = _read_meta_value(connection, "head")
        indexed_tracked_count = _read_meta_value(connection, "tracked_file_count")
    except sqlite3.Error:
        return True
    finally:
        connection.close()

    current_head = _git_stdout(root, "rev-parse", "HEAD").strip()
    if indexed_head != current_head:
        return True
    if indexed_tracked_count != str(len(tracked_files)):
        return True

    for relative_path in tracked_files:
        absolute_path = root / relative_path
        try:
            if not absolute_path.is_file():
                continue
            if absolute_path.stat().st_mtime >= db_modified:
                return True
        except OSError:
            return True

    return False


def _read_meta_value(connection: sqlite3.Connection, key: str) -> str | None:
    exists_row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'repo_meta'"
    ).fetchone()
    if exists_row is None:
        return None
    row = connection.execute(
        "SELECT value FROM repo_meta WHERE key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    return str(row[0])


def _run_rust_indexer(root: Path, db_path: Path) -> None:
    command = [
        "cargo",
        "run",
        "--quiet",
        "--manifest-path",
        str(_RUST_MANIFEST_PATH),
        "--",
        "index",
        "--root",
        str(root),
        "--db",
        str(db_path),
        "--max-bytes",
        str(DEFAULT_MAX_TEXT_BYTES),
    ]
    result = subprocess.run(
        command,
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or "native index refresh failed"
        raise LookupUnavailableError(detail)


def _list_tracked_files(root: Path) -> list[Path]:
    output = _git_stdout(root, "ls-files", "--cached", "-z")
    return [Path(chunk) for chunk in output.split("\0") if chunk]


def _git_stdout(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise LookupUnavailableError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def _build_match_query(question: str) -> str | None:
    tokens = {
        token.strip().lower()
        for token in _split_query_terms(question)
        if len(token) >= 2 and token.lower() not in STOP_WORDS
    }
    if not tokens:
        return None
    return " AND ".join(f"{token}*" for token in sorted(tokens))


def _split_query_terms(question: str) -> list[str]:
    token = []
    tokens: list[str] = []
    for character in question:
        if character.isalnum():
            token.append(character)
            continue
        if token:
            tokens.append("".join(token))
            token = []
    if token:
        tokens.append("".join(token))
    return tokens
