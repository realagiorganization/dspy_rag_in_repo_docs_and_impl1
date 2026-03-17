"""DSPy-shaped wrappers around the baseline repository retrieval workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .corpus import load_documents
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
    """Execute the optional DSPy-shaped repository question-answering flow."""

    def __init__(self, root: Path, top_k: int = 4) -> None:
        self.root = root
        self.retriever = RepositoryRetriever(root=root, top_k=top_k)
        self.top_k = top_k
        self.respond: Any | None = None
        if dspy:
            self.respond = dspy.ChainOfThought("context, question -> answer")

    def __call__(self, question: str) -> DSPyRunResult:
        """Answer ``question`` with DSPy when available, else fall back to context echoing."""

        context = self.retriever(question)
        if dspy is None:
            answer = " ".join(context[:1]) if context else "No context available."
            return DSPyRunResult(question=question, context=context, answer=answer)
        if self.respond is None:  # pragma: no cover
            raise RuntimeError("DSPy responder was not initialized.")
        prediction: Any = self.respond(context=context, question=question)
        return DSPyRunResult(question=question, context=context, answer=prediction.answer)
