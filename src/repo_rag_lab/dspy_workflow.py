"""DSPy-backed runtime wrappers around the repository retrieval workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dspy_training import DSPyLMConfig, build_repository_rag_program, resolve_dspy_program_path
from .retrieval import Chunk, RetrievalMode, resolve_retrieval_mode
from .retrieval_profile import load_retrieval_profile
from .workflow import collect_repository_context, serialize_chunk

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
    retrieved_context: list[Chunk]
    program_loaded: bool
    retrieval_mode: RetrievalMode

    def to_payload(self, *, root: Path) -> dict[str, object]:
        """Return a machine-readable payload for CLI and worker integrations."""

        return {
            "question": self.question,
            "answer": self.answer,
            "context": list(self.context),
            "sources": list(
                dict.fromkeys(
                    serialize_chunk(chunk, root=root)["source"] for chunk in self.retrieved_context
                )
            ),
            "retrieved_context": [
                serialize_chunk(chunk, root=root) for chunk in self.retrieved_context
            ],
            "program_loaded": self.program_loaded,
            "retrieval_mode": self.retrieval_mode,
        }


class RepositoryRetriever:
    """Retrieve top-ranked repository chunks as raw text snippets."""

    def __init__(
        self,
        root: Path,
        top_k: int = 4,
        *,
        retrieval_mode: RetrievalMode | None = None,
    ) -> None:
        self.root = root
        self.top_k = top_k
        self.retrieval_mode: RetrievalMode = resolve_retrieval_mode(
            load_retrieval_profile(root),
            retrieval_mode,
        )
        self.last_chunks: list[Chunk] = []

    def retrieve_chunks(self, query: str) -> list[Chunk]:
        """Return retrieved repository chunks for ``query`` and store them for inspection."""

        self.last_chunks = collect_repository_context(
            query,
            self.root,
            top_k=self.top_k,
            retrieval_mode=self.retrieval_mode,
        )
        return list(self.last_chunks)

    def __call__(self, query: str) -> list[str]:
        """Return the top repository chunks for ``query`` as plain text."""

        return [chunk.text for chunk in self.retrieve_chunks(query)]


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
        retrieval_mode: RetrievalMode | None = None,
    ) -> None:
        self.root = root
        self.retrieval_mode: RetrievalMode = resolve_retrieval_mode(
            load_retrieval_profile(root),
            retrieval_mode,
        )
        self.retriever = RepositoryRetriever(
            root=root,
            top_k=top_k,
            retrieval_mode=self.retrieval_mode,
        )
        self.top_k = top_k
        self.program: Any | None = None
        self.program_path: Path | None = None
        if dspy is None:
            return
        resolved_program_path = resolve_dspy_program_path(root, program_path=program_path)
        self.program_path = resolved_program_path
        if resolved_program_path is not None and lm_config is None and require_configured_lm:
            raise RuntimeError(
                "DSPy LM configuration is required. Pass CLI flags, export DSPY_* variables, "
                "or source the repository Azure/OpenAI environment before using DSPy. "
                f"A compiled DSPy program was found at {resolved_program_path}, but it still "
                "needs LM configuration to run."
            )
        if resolved_program_path is None and lm_config is None and not require_configured_lm:
            return
        self.program = build_repository_rag_program(
            root,
            top_k=top_k,
            program_path=resolved_program_path,
            lm_config=lm_config,
            retrieval_mode=retrieval_mode,
            require_configured_lm=(
                require_configured_lm if resolved_program_path is None else False
            ),
        )

    def __call__(self, question: str) -> DSPyRunResult:
        """Answer ``question`` with DSPy when configured, else fall back to context echoing."""

        if dspy is None or self.program is None:
            context = self.retriever(question)
            answer = " ".join(context[:1]) if context else "No context available."
            return DSPyRunResult(
                question=question,
                context=context,
                answer=answer,
                retrieved_context=list(self.retriever.last_chunks),
                program_loaded=False,
                retrieval_mode=self.retriever.retrieval_mode,
            )
        prediction: Any = self.program(question=question)
        retrieved_context = list(self.retriever.last_chunks)
        prediction_context = list(getattr(prediction, "context", []))
        if not prediction_context and retrieved_context:
            prediction_context = [chunk.text for chunk in retrieved_context]
        return DSPyRunResult(
            question=question,
            context=prediction_context,
            answer=str(prediction.answer),
            retrieved_context=retrieved_context,
            program_loaded=True,
            retrieval_mode=self.retriever.retrieval_mode,
        )
