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


class RepositoryAnswer(dspy.Signature if dspy else object):
    """Answer a question using repository context."""


@dataclass(frozen=True)
class DSPyRunResult:
    question: str
    context: list[str]
    answer: str


class RepositoryRetriever:
    def __init__(self, root: Path, top_k: int = 4) -> None:
        self.root = root
        self.top_k = top_k

    def __call__(self, query: str) -> list[str]:
        documents = load_documents(self.root)
        chunks = chunk_documents(documents)
        return [chunk.text for chunk in retrieve(query, chunks, top_k=self.top_k)]


class RepositoryRAG:
    def __init__(self, root: Path, top_k: int = 4) -> None:
        self.root = root
        self.retriever = RepositoryRetriever(root=root, top_k=top_k)
        self.top_k = top_k
        if dspy:
            self.respond = dspy.ChainOfThought("context, question -> answer")

    def __call__(self, question: str) -> DSPyRunResult:
        context = self.retriever(question)
        if dspy is None:
            answer = " ".join(context[:1]) if context else "No context available."
            return DSPyRunResult(question=question, context=context, answer=answer)
        prediction: Any = self.respond(context=context, question=question)
        return DSPyRunResult(question=question, context=context, answer=prediction.answer)

