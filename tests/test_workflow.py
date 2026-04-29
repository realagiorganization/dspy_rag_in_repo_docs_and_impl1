from __future__ import annotations

from pathlib import Path

from repo_rag_lab.retrieval import Chunk
from repo_rag_lab.workflow import RAGAnswer, synthesize_answer


def test_synthesize_answer_includes_explicit_answer_and_evidence_sections() -> None:
    context = [
        Chunk(
            source=Path("README.md"),
            text=(
                "Repository RAG research and utilities. "
                "This repository studies retrieval, notebook workflows, and deployment surfaces."
            ),
        ),
        Chunk(
            source=Path("docs/architecture/package-api.md"),
            text="The package exposes a CLI, retrieval helpers, and workflow orchestration.",
        ),
    ]

    answer = synthesize_answer("What does this repository research?", context, [])

    assert "Question: What does this repository research?" in answer
    assert "\nAnswer:\n" in answer
    assert "`README.md` says" in answer
    assert "`docs/architecture/package-api.md`" in answer
    assert "\nEvidence:\n- README.md:" in answer


def test_synthesize_answer_prefers_direct_answer_chunks_over_question_lists() -> None:
    context = [
        Chunk(
            source=Path("README.md"),
            text=(
                "Suggested Retrieval Questions\n"
                "- What is the ember index?\n"
                "- Which function handles prefix search?\n"
            ),
        ),
        Chunk(
            source=Path("src/hushwheel.c"),
            text=(
                "/* print_prefix_matches handles prefix search across the core entries and every"
                " spoke table. */"
            ),
        ),
        Chunk(
            source=Path("docs/operations.md"),
            text=(
                "The function print_prefix_matches handles prefix search. "
                "It scans the core entries first and then walks every spoke table."
            ),
        ),
    ]

    answer = synthesize_answer(
        "How does print_prefix_matches handle prefix search?",
        context,
        [],
    )

    answer_section = answer.split("\n\nEvidence:", maxsplit=1)[0]
    assert "`README.md` says" not in answer_section
    assert (
        "`src/hushwheel.c` says" in answer_section or "`docs/operations.md` says" in answer_section
    )
    assert "`src/hushwheel.c`" in answer_section or "`docs/operations.md`" in answer_section
    assert "print_prefix_matches" in answer_section
    assert "prefix search" in answer_section.lower()


def test_rag_answer_payload_normalizes_absolute_paths_to_repo_relative() -> None:
    root = Path("/tmp/demo-repo")
    chunk = Chunk(
        source=root / "README.md",
        text="Repository RAG research and utilities.",
    )
    result = RAGAnswer(
        question="What does this repository research?",
        answer=f"Question: ...\n- {chunk.source.as_posix()}: preview",
        context=[chunk],
        mcp_servers=[],
        summary=f"`{chunk.source.as_posix()}` says 'Repository RAG research and utilities.'",
        retrieval_mode="lexical",
    )

    payload = result.to_payload(root=root)
    context = payload["context"]

    assert payload["answer"] == "`README.md` says 'Repository RAG research and utilities.'"
    assert "README.md: preview" in str(payload["response_text"])
    assert payload["sources"] == ["README.md"]
    assert isinstance(context, list)
    assert isinstance(context[0], dict)
    assert context[0]["source"] == "README.md"
