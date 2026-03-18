from __future__ import annotations

from pathlib import Path

from repo_rag_lab.corpus import load_documents
from repo_rag_lab.retrieval import Chunk, chunk_documents, retrieve, score
from repo_rag_lab.training_samples import load_training_examples

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_retrieve_diversifies_sources_before_returning_duplicates() -> None:
    chunks = [
        Chunk(source=Path("README.md"), text="repository research utilities"),
        Chunk(source=Path("README.md"), text="repository research utilities"),
        Chunk(source=Path("utilities/README.md"), text="repository research utilities"),
    ]

    retrieved = retrieve("What does this repository research?", chunks, top_k=2)

    assert [chunk.source for chunk in retrieved] == [
        Path("README.md"),
        Path("utilities/README.md"),
    ]


def test_retrieve_prioritizes_repo_summary_docs_over_question_echo_files() -> None:
    chunks = chunk_documents(load_documents(REPO_ROOT))

    retrieved = retrieve("What does this repository research?", chunks, top_k=4)
    sources = [str(chunk.source.relative_to(REPO_ROOT)) for chunk in retrieved]

    assert sources[0] == "README.md"
    assert "README.md" in sources
    assert all(
        not source.startswith(("data/", "tests/", "samples/training/")) for source in sources
    )


def test_retrieve_surfaces_inspired_docs_for_inspired_summary_question() -> None:
    chunks = chunk_documents(load_documents(REPO_ROOT))

    retrieved = retrieve("Where are inspired implementation summaries stored?", chunks, top_k=4)
    sources = [str(chunk.source.relative_to(REPO_ROOT)) for chunk in retrieved]

    assert sources[:2] == [
        "documentation/inspired/implementing-rag-with-dspy-technical-guide.md",
        "documentation/inspired/dspy-rag-tutorial.md",
    ]


def test_retrieve_doc_seeking_question_prefers_package_api_doc_over_tests() -> None:
    chunks = chunk_documents(load_documents(REPO_ROOT))

    retrieved = retrieve(
        "Which file explains the core workflow modules under src/repo_rag_lab?",
        chunks,
        top_k=4,
    )
    sources = [str(chunk.source.relative_to(REPO_ROOT)) for chunk in retrieved]

    assert sources[0] == "documentation/package-api.md"
    assert all(not source.startswith(("tests/", "samples/training/")) for source in sources)


def test_retrieve_training_questions_avoid_meta_and_synthetic_sources_in_top4() -> None:
    chunks = chunk_documents(load_documents(REPO_ROOT))
    examples = load_training_examples(
        REPO_ROOT / "samples" / "training" / "repository_training_examples.yaml"
    )
    blocked_prefixes = (
        ".codex/",
        "AGENTS.md.d/",
        "docs/audit/",
        "publication/exploratorium_translation/generated/",
        "samples/population/",
        "samples/training/",
        "tests/",
    )
    blocked_paths = {
        "FILES.md",
        "README.AGENTS.md",
        "TODO.MD",
        "env.md",
        "todo-backlog.yaml",
    }

    for example in examples:
        sources = [
            str(chunk.source.relative_to(REPO_ROOT))
            for chunk in retrieve(example.question, chunks, top_k=4)
        ]
        assert all(
            source not in blocked_paths and not source.startswith(blocked_prefixes)
            for source in sources
        ), (example.question, sources)


def test_score_prefers_definition_chunk_for_stopword_heavy_question() -> None:
    question = "What is the ember index?"
    question_echo_chunk = (
        "## Suggested Retrieval Questions - What is the ember index? - Which function handles "
        "prefix search?"
    )
    definition_chunk = (
        "The ember index is a three-digit heat-memory score used when two terms share the same "
        "lantern vowel."
    )

    assert score(question, definition_chunk, source=Path("README.md")) > score(
        question,
        question_echo_chunk,
        source=Path("README.md"),
    )


def test_score_penalizes_question_echo_test_paths_relative_to_readme() -> None:
    question = "What does this repository research?"
    noisy_score = score(
        question,
        'Feature: Repository RAG When I ask "What does this repository research?"',
        source=Path("tests/features/repository_rag.feature"),
    )
    readme_score = score(
        question,
        "This repository researches repository-grounded RAG workflows with shared utilities.",
        source=Path("README.md"),
    )

    assert readme_score > noisy_score
