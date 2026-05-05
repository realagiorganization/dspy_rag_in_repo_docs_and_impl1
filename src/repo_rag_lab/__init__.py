"""Public package surface for the repository-grounded RAG lab."""

from __future__ import annotations

from pathlib import Path

__all__ = ["ask_repository", "ask_repository_live"]


def ask_repository(
    question: str,
    root: Path,
    *,
    retrieval_mode: str | None = None,
):
    from .workflow import ask_repository as _ask_repository

    return _ask_repository(
        question=question,
        root=root,
        retrieval_mode=retrieval_mode,
    )


def ask_repository_live(
    question: str,
    root: Path,
    *,
    provider: str,
    load_env_file: bool = False,
    retrieval_mode: str | None = None,
):
    from .workflow import ask_repository_live as _ask_repository_live

    return _ask_repository_live(
        question=question,
        root=root,
        provider=provider,
        load_env_file=load_env_file,
        retrieval_mode=retrieval_mode,
    )
