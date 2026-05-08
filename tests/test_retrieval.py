from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

import repo_rag_lab.retrieval as retrieval_module
from repo_rag_lab.corpus import load_documents
from repo_rag_lab.retrieval import (
    Chunk,
    chunk_documents,
    resolve_retrieval_mode,
    retrieve,
    retrieve_with_metadata,
    score,
)
from repo_rag_lab.retrieval_profile import RetrievalProfile, load_retrieval_profile
from repo_rag_lab.training_samples import load_training_examples

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_PROFILE = load_retrieval_profile(REPO_ROOT)


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

    retrieved = retrieve(
        "What does this repository research?", chunks, top_k=4, profile=REPO_PROFILE
    )
    sources = [str(chunk.source) for chunk in retrieved]

    assert sources[0] == "README.md"
    assert "README.md" in sources
    assert "src/repo_rag_lab/utilities.py" in sources
    assert all(
        not source.startswith(("data/", "tests/", "samples/training/")) for source in sources
    )


def test_retrieve_surfaces_inspired_docs_for_inspired_summary_question() -> None:
    chunks = chunk_documents(load_documents(REPO_ROOT))

    retrieved = retrieve(
        "Where are inspired implementation summaries stored?",
        chunks,
        top_k=4,
        profile=REPO_PROFILE,
    )
    sources = [str(chunk.source) for chunk in retrieved]

    assert sources[:2] == [
        "docs/architecture/inspired/implementing-rag-with-dspy-technical-guide.md",
        "docs/architecture/inspired/dspy-rag-tutorial.md",
    ]


def test_retrieve_doc_seeking_question_prefers_package_api_doc_over_tests() -> None:
    chunks = chunk_documents(load_documents(REPO_ROOT))

    retrieved = retrieve(
        "Which file explains the core workflow modules under src/repo_rag_lab?",
        chunks,
        top_k=4,
        profile=REPO_PROFILE,
    )
    sources = [str(chunk.source) for chunk in retrieved]

    assert sources[0] == "docs/architecture/package-api.md"
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
        "docs/architecture/research-narrative.md",
        "TODO.MD",
        "docs/operations/environment.md",
        "todo-backlog.yaml",
    }

    for example in examples:
        sources = [
            str(chunk.source.relative_to(REPO_ROOT))
            if chunk.source.is_absolute()
            else str(chunk.source)
            for chunk in retrieve(example.question, chunks, top_k=4, profile=REPO_PROFILE)
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


def test_load_retrieval_profile_reads_repo_local_overrides(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "retrieval-profile.json").write_text(
        json.dumps(
            {
                "name": "demo-profile",
                "retrieval_mode": "idf-rerank",
                "rerank_candidate_pool_size": 12,
                "source_adjustments_by_name": {"README.md": 3.5},
                "excluded_subpaths": [["generated"]],
                "contextual_rules": [
                    {
                        "path_name": "README.md",
                        "required_terms": ["demo"],
                        "value": 1.25,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    profile = load_retrieval_profile(tmp_path)

    assert profile.name == "demo-profile"
    assert profile.retrieval_mode == "idf-rerank"
    assert profile.rerank_candidate_pool_size == 12
    assert profile.source_adjustments_by_name["README.md"] == 3.5
    assert profile.excluded_subpaths == (("generated",),)
    assert profile.contextual_rules[0].path_name == "README.md"


def test_retrieve_profile_can_exclude_sources() -> None:
    chunks = [
        Chunk(source=Path("tests/example.md"), text="demo retrieval target"),
        Chunk(source=Path("docs/guide.md"), text="demo retrieval target"),
    ]
    profile = RetrievalProfile(
        source_adjustments_by_part={"docs": 1.0},
        excluded_parts=frozenset({"tests"}),
    )

    retrieved = retrieve(
        "Where is the demo retrieval target documented?", chunks, top_k=1, profile=profile
    )

    assert [chunk.source for chunk in retrieved] == [Path("docs/guide.md")]


def test_load_documents_excludes_runtime_generated_prompt_and_context_scaffolding(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    prompt_dir = tmp_path / "prompt_artifacts"
    prompt_dir.mkdir()
    (prompt_dir / "prompt.txt").write_text("runtime prompt echo", encoding="utf-8")
    context_dir = tmp_path / "_context_repos"
    context_dir.mkdir()
    (context_dir / "shadow.md").write_text("runtime context repo link target", encoding="utf-8")
    cache_dir = tmp_path / ".repo_rag_cache"
    cache_dir.mkdir()
    (cache_dir / "cache.txt").write_text("cached retrieval data", encoding="utf-8")

    sources = {str(document.path) for document in load_documents(tmp_path)}

    assert sources == {"README.md"}


def test_retrieve_idf_rerank_prefers_phrase_coherent_chunk() -> None:
    question = "Where are inspired implementation summaries stored?"
    chunks = [
        Chunk(
            source=Path("docs/scrambled.md"),
            text="Stored summaries inspired implementation under docs architecture notes.",
        ),
        Chunk(
            source=Path("docs/ordered.md"),
            text="Inspired implementation summaries are stored under docs architecture notes.",
        ),
    ]

    reranked = retrieve(question, chunks, top_k=1, retrieval_mode="idf-rerank")

    assert reranked[0].source == Path("docs/ordered.md")


def test_resolve_retrieval_mode_uses_profile_default() -> None:
    assert resolve_retrieval_mode(REPO_PROFILE) == "hybrid-vector"


def test_retrieve_vector_mode_uses_semantic_rankings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    chunks = [
        Chunk(source=Path("docs/auth.md"), text="Session login orchestration and access flow."),
        Chunk(source=Path("docs/cache.md"), text="Cache eviction and invalidation rules."),
    ]

    def fake_rank_semantic_chunks(
        question: str,
        *,
        root: Path,
        chunk_records: Sequence[tuple[str, str]],
        max_candidates: int | None = None,
    ) -> tuple[list[tuple[int, float]], list[str]]:
        del question, root, chunk_records, max_candidates
        return ([(0, 0.95), (1, 0.2)], [])

    monkeypatch.setattr(retrieval_module, "rank_semantic_chunks", fake_rank_semantic_chunks)

    result = retrieve_with_metadata(
        "Where is the sign-in flow explained?",
        chunks,
        top_k=1,
        retrieval_mode="vector",
        root=tmp_path,
    )

    assert result.retrieval_mode == "vector"
    assert result.warnings == ()
    assert [chunk.source for chunk in result.chunks] == [Path("docs/auth.md")]


def test_retrieve_hybrid_vector_falls_back_to_idf_rerank_when_embeddings_are_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    chunks = [
        Chunk(
            source=Path("docs/ordered.md"),
            text="Inspired implementation summaries are stored under docs architecture notes.",
        ),
        Chunk(
            source=Path("docs/scrambled.md"),
            text="Stored summaries inspired implementation under docs architecture notes.",
        ),
    ]

    def fake_rank_semantic_chunks_unavailable(
        question: str,
        *,
        root: Path,
        chunk_records: Sequence[tuple[str, str]],
        max_candidates: int | None = None,
    ) -> tuple[list[tuple[int, float]], list[str]]:
        del question, root, chunk_records, max_candidates
        return ([], ["Semantic retrieval unavailable: missing embedding deployment."])

    monkeypatch.setattr(
        retrieval_module,
        "rank_semantic_chunks",
        fake_rank_semantic_chunks_unavailable,
    )

    result = retrieve_with_metadata(
        "Where are inspired implementation summaries stored?",
        chunks,
        top_k=1,
        retrieval_mode="hybrid-vector",
        root=tmp_path,
    )

    assert result.retrieval_mode == "idf-rerank"
    assert result.warnings == (
        "Semantic retrieval unavailable: missing embedding deployment.",
        "Semantic retrieval fell back to idf-rerank.",
    )
    assert [chunk.source for chunk in result.chunks] == [Path("docs/ordered.md")]


def test_retrieve_hybrid_vector_keeps_strong_lexical_doc_hits_ahead_of_semantic_noise(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    question = "Where are inspired implementation summaries stored?"
    chunks = [
        Chunk(
            source=Path("docs/architecture/inspired/implementing-rag-with-dspy-technical-guide.md"),
            text=(
                "Inspired implementation summaries are stored under docs architecture inspired "
                "and include the implementing rag with dspy technical guide."
            ),
        ),
        Chunk(
            source=Path("docs/architecture/inspired/dspy-rag-tutorial.md"),
            text=(
                "Inspired implementation summaries are stored under docs architecture inspired "
                "and include the DSPy RAG tutorial."
            ),
        ),
        Chunk(
            source=Path("publication/exploratorium_translation/README.md"),
            text=(
                "Publication translation notes mention inspired implementation work and where "
                "summaries are discussed for publication output."
            ),
        ),
        Chunk(
            source=Path("src/repo_rag_lab/benchmarks.py"),
            text=(
                "Benchmark helpers describe repository questions about where inspired "
                "implementation summaries are stored."
            ),
        ),
    ]

    def fake_rank_semantic_chunks(
        question: str,
        *,
        root: Path,
        chunk_records: Sequence[tuple[str, str]],
        max_candidates: int | None = None,
    ) -> tuple[list[tuple[int, float]], list[str]]:
        del question, root, chunk_records, max_candidates
        return ([(2, 0.99), (3, 0.98), (0, 0.25), (1, 0.24)], [])

    monkeypatch.setattr(retrieval_module, "rank_semantic_chunks", fake_rank_semantic_chunks)

    result = retrieve_with_metadata(
        question,
        chunks,
        top_k=2,
        profile=REPO_PROFILE,
        retrieval_mode="hybrid-vector",
        root=tmp_path,
    )

    assert result.retrieval_mode == "hybrid-vector"
    assert set(chunk.source for chunk in result.chunks) == {
        Path("docs/architecture/inspired/implementing-rag-with-dspy-technical-guide.md"),
        Path("docs/architecture/inspired/dspy-rag-tutorial.md"),
    }
