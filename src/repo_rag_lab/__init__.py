"""Public package surface for the repository-grounded RAG lab."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .retrieval import RetrievalMode
    from .workflow import LiveProvider, RAGAnswer

__all__ = ["ask_repository", "ask_repository_live"]


def ask_repository(
    question: str,
    root: Path,
    *,
    retrieval_mode: RetrievalMode | None = None,
) -> RAGAnswer:
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
    provider: LiveProvider,
    load_env_file: bool = False,
    retrieval_mode: RetrievalMode | None = None,
) -> RAGAnswer:
    from .workflow import ask_repository_live as _ask_repository_live

    return _ask_repository_live(
        question=question,
        root=root,
        provider=provider,
        load_env_file=load_env_file,
        retrieval_mode=retrieval_mode,
    )
