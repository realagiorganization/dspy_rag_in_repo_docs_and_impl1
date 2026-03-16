from __future__ import annotations

from pathlib import Path


def resolve_repo_root(current: Path) -> Path:
    """
    Resolve the repository root from a notebook or repository working directory.

    >>> resolve_repo_root(Path('/tmp/example/notebooks'))
    PosixPath('/tmp/example')
    >>> resolve_repo_root(Path('/tmp/example'))
    PosixPath('/tmp/example')
    """

    return current.parent if current.name == "notebooks" else current

