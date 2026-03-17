from __future__ import annotations

from pathlib import Path

from repo_rag_lab.population_samples import (
    extend_population_candidates,
    group_population_candidates,
    load_population_candidates,
    rerank_population_candidates,
    summarize_population_candidates,
    validate_population_candidates,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_load_population_candidates_reads_repository_samples() -> None:
    candidates = load_population_candidates(
        REPO_ROOT / "samples" / "population" / "repository_population_candidates.yaml"
    )
    assert len(candidates) >= 4
    assert candidates[0].priority == 1


def test_group_population_candidates_preserves_order() -> None:
    candidates = load_population_candidates(
        REPO_ROOT / "samples" / "population" / "repository_population_candidates.yaml"
    )
    batches = group_population_candidates(candidates, batch_size=2)
    assert batches[0][0].priority == 1
    assert sum(len(batch) for batch in batches) == len(candidates)


def test_summarize_population_candidates_exposes_top_source() -> None:
    candidates = load_population_candidates(
        REPO_ROOT / "samples" / "population" / "repository_population_candidates.yaml"
    )
    summary = summarize_population_candidates(candidates)
    assert summary["candidate_count"] == len(candidates)
    assert summary["highest_priority_source"] == "README.md"


def test_extend_population_candidates_adds_scaffold_docs() -> None:
    candidates = load_population_candidates(
        REPO_ROOT / "samples" / "population" / "repository_population_candidates.yaml"
    )
    extended = extend_population_candidates(REPO_ROOT, candidates)
    assert any(candidate.source == "documentation/package-api.md" for candidate in extended)
    assert any(candidate.source == "documentation/mcp-discovery.md" for candidate in extended)


def test_validate_population_candidates_accepts_extended_repository_samples() -> None:
    candidates = load_population_candidates(
        REPO_ROOT / "samples" / "population" / "repository_population_candidates.yaml"
    )
    extended = extend_population_candidates(REPO_ROOT, candidates)
    assert validate_population_candidates(extended, root=REPO_ROOT) == []


def test_rerank_population_candidates_promotes_empirical_hits() -> None:
    candidates = load_population_candidates(
        REPO_ROOT / "samples" / "population" / "repository_population_candidates.yaml"
    )
    reranked = rerank_population_candidates(candidates, {"utilities/README.md": 4})
    assert reranked[0].source == "utilities/README.md"
    assert reranked[0].priority == 1
