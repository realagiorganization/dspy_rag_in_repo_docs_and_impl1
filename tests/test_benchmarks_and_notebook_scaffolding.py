from __future__ import annotations

import shutil
from pathlib import Path

from repo_rag_lab.benchmarks import (
    build_retrieval_benchmarks,
    evaluate_retrieval_benchmarks,
    summarize_benchmark_results,
)
from repo_rag_lab.notebook_scaffolding import (
    build_agent_workflow_context,
    build_population_lab_context,
    build_research_playbook_context,
    build_training_lab_context,
)
from repo_rag_lab.training_samples import load_training_examples

REPO_ROOT = Path(__file__).resolve().parents[1]


def _copy_scaffold_inputs(tmp_path: Path) -> Path:
    for relative_path in [
        Path("AGENTS.md"),
        Path("README.md"),
        Path("utilities/README.md"),
        Path("documentation/azure-deployment.md"),
        Path("documentation/package-api.md"),
        Path("documentation/mcp-discovery.md"),
        Path("documentation/inspired/dspy-rag-tutorial.md"),
        Path("documentation/inspired/implementing-rag-with-dspy-technical-guide.md"),
        Path("samples/training/repository_training_examples.yaml"),
        Path("samples/population/repository_population_candidates.yaml"),
        Path("src/repo_rag_lab/utilities.py"),
    ]:
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative_path, destination)
    return tmp_path


def test_repository_benchmarks_pass_with_current_training_samples() -> None:
    examples = load_training_examples(
        REPO_ROOT / "samples" / "training" / "repository_training_examples.yaml"
    )
    benchmarks = build_retrieval_benchmarks(examples)
    results = evaluate_retrieval_benchmarks(REPO_ROOT, benchmarks)
    summary = summarize_benchmark_results(results)
    assert len(benchmarks) == len(examples)
    assert summary["case_count"] == len(examples)
    assert summary["pass_rate"] == 1.0


def test_build_training_lab_context_writes_metadata_and_reports_clean_validation(
    tmp_path: Path,
) -> None:
    root = _copy_scaffold_inputs(tmp_path)
    payload = build_training_lab_context(root)
    assert payload["training_summary"]["example_count"] == 3
    assert payload["validation_issues"] == []
    assert payload["benchmark_summary"]["pass_rate"] == 1.0
    assert (root / payload["tuning_metadata_path"]).exists()


def test_build_population_lab_context_extends_and_reranks_candidates(tmp_path: Path) -> None:
    root = _copy_scaffold_inputs(tmp_path)
    payload = build_population_lab_context(root)
    assert (
        payload["extended_summary"]["candidate_count"] > payload["base_summary"]["candidate_count"]
    )
    assert payload["validation_issues"] == []
    assert "documentation/package-api.md" in payload["reranked_sources"]


def test_build_agent_workflow_context_reports_validation_and_benchmarks() -> None:
    payload = build_agent_workflow_context(REPO_ROOT)
    assert payload["training_validation_issues"] == []
    assert payload["population_validation_issues"] == []
    assert payload["benchmark_summary"]["pass_rate"] == 1.0


def test_build_research_playbook_context_reports_smoke_and_baseline_details() -> None:
    payload = build_research_playbook_context(REPO_ROOT)
    assert "ask" in payload["utility_summary"]
    assert payload["baseline_question"] == "What does this repository research?"
    assert "Question:" in payload["baseline_answer"]
    assert payload["smoke_test"]["answer_contains_repository"] is True
    assert payload["smoke_test"]["mcp_candidate_count"] == len(payload["mcp_candidates"])
