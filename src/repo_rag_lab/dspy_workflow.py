"""DSPy-backed runtime wrappers around the repository retrieval workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .corpus import load_documents
from .dspy_training import DSPyLMConfig, build_repository_rag_program
from .retrieval import chunk_documents, retrieve

try:
    import dspy
except ImportError:  # pragma: no cover - optional runtime dependency during scaffolding
    dspy = None


@dataclass(frozen=True)
class DSPyRunResult:
    """Result payload returned by the optional DSPy execution path."""

    question: str
    context: list[str]
    answer: str


class RepositoryRetriever:
    """Retrieve top-ranked repository chunks as raw text snippets."""

    def __init__(self, root: Path, top_k: int = 4) -> None:
        self.root = root
        self.top_k = top_k

    def __call__(self, query: str) -> list[str]:
        """Return the top repository chunks for ``query`` as plain text."""

        documents = load_documents(self.root)
        chunks = chunk_documents(documents)
        return [chunk.text for chunk in retrieve(query, chunks, top_k=self.top_k)]


class RepositoryRAG:
    """Execute the optional DSPy repository question-answering flow."""

    def __init__(
        self,
        root: Path,
        top_k: int = 4,
        *,
        program_path: Path | None = None,
        lm_config: DSPyLMConfig | None = None,
        require_configured_lm: bool = False,
    ) -> None:
        self.root = root
        self.retriever = RepositoryRetriever(root=root, top_k=top_k)
        self.top_k = top_k
        self.program: Any | None = None
        if dspy is None:
            return
        resolved_program_path = program_path.resolve() if program_path is not None else None
        if resolved_program_path is None and lm_config is None and not require_configured_lm:
            return
        self.program = build_repository_rag_program(
            root,
            top_k=top_k,
            program_path=resolved_program_path,
            lm_config=lm_config,
            require_configured_lm=require_configured_lm,
        )

    def __call__(self, question: str) -> DSPyRunResult:
        """Answer ``question`` with DSPy when configured, else fall back to context echoing."""

        context = self.retriever(question)
        if dspy is None or self.program is None:
            answer = " ".join(context[:1]) if context else "No context available."
            return DSPyRunResult(question=question, context=context, answer=answer)
        prediction: Any = self.program(question=question)
        prediction_context = list(getattr(prediction, "context", context))
        return DSPyRunResult(
            question=question,
            context=prediction_context,
            answer=str(prediction.answer),
        )
