from __future__ import annotations

import json
from pathlib import Path

from repo_rag_lab.training_samples import (
    batch_training_examples,
    load_training_examples,
    materialize_combined_training_examples,
    materialize_training_candidates,
    summarize_training_examples,
    validate_training_examples,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
HUSHWHEEL_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "hushwheel_lexiconarium"


def test_load_training_examples_reads_repository_samples() -> None:
    examples = load_training_examples(
        REPO_ROOT / "samples" / "training" / "repository_training_examples.yaml"
    )
    questions = {example.question for example in examples}
    assert len(examples) >= 8
    assert examples[0].question
    assert examples[0].expected_sources
    assert {
        "Which file explains the core workflow modules under src/repo_rag_lab?",
        "What should AZURE_INFERENCE_ENDPOINT contain for the Azure AI Inference SDK?",
        "Where can you read MCP discovery notes?",
        "How do you execute all tracked notebooks with monitored progress and report artifacts?",
        "How do you build the publication PDF locally?",
    }.issubset(questions)


def test_batch_training_examples_preserves_all_items() -> None:
    examples = load_training_examples(
        REPO_ROOT / "samples" / "training" / "repository_training_examples.yaml"
    )
    batches = batch_training_examples(examples, batch_size=2)
    assert sum(len(batch) for batch in batches) == len(examples)


def test_summarize_training_examples_lists_tags() -> None:
    examples = load_training_examples(
        REPO_ROOT / "samples" / "training" / "repository_training_examples.yaml"
    )
    summary = summarize_training_examples(examples)
    assert summary["example_count"] == len(examples)
    assert summary["benchmark_count"] == len(examples)
    assert "repo" in summary["unique_tags"]
    assert {"azure", "mcp", "notebooks", "publication"}.issubset(summary["unique_tags"])


def test_validate_training_examples_accepts_repository_samples() -> None:
    examples = load_training_examples(
        REPO_ROOT / "samples" / "training" / "repository_training_examples.yaml"
    )
    assert validate_training_examples(examples, root=REPO_ROOT) == []


def test_validate_training_examples_accepts_hushwheel_fixture_samples() -> None:
    examples = load_training_examples(
        REPO_ROOT / "samples" / "training" / "hushwheel_fixture_training_examples.yaml"
    )
    assert len(examples) == 6
    assert validate_training_examples(examples, root=HUSHWHEEL_FIXTURE_ROOT) == []


def test_materialize_training_candidates_and_combined_training_examples(tmp_path: Path) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    candidate_trace_path = imported_dir / "accepted.json"
    candidate_trace_path.write_text(
        """{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/accepted.json",
  "question": "What does this repository research?",
  "answer": "It researches repository-grounded RAG.",
  "sources": ["README.md"],
  "trace": {
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "2026-04-29T00:00:00+00:00",
    "question": "What does this repository research?",
    "mode": "baseline",
    "retrieval_mode": "idf-rerank",
    "sources": ["README.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "context",
    "mcp_candidate_count": 0,
    "answer_length": 20
  },
  "outcome": {
    "acceptance_status": "accepted",
    "accepted": true,
    "execution_status": "success",
    "method": "repo_rag_cli",
    "backend": "repo_rag_cli"
  }
}
""",
        encoding="utf-8",
    )

    candidates_summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )
    assert candidates_summary["candidate_count"] == 1
    assert candidates_summary["replaced_count"] == 0
    materialized = load_training_examples(
        tmp_path / "artifacts" / "trainer" / "training-candidates.yaml"
    )
    assert len(materialized) == 1
    assert materialized[0].expected_sources == ()

    base_training_path = tmp_path / "samples" / "training" / "base.yaml"
    base_training_path.parent.mkdir(parents=True, exist_ok=True)
    base_training_path.write_text(
        (
            '- question: "Where are logs stored?"\n'
            '  expected_answer: "samples/logs"\n'
            '  tags: ["logs"]\n'
        ),
        encoding="utf-8",
    )

    combined_summary = materialize_combined_training_examples(
        tmp_path,
        base_training_path=Path("samples/training/base.yaml"),
        candidates_path=Path("artifacts/trainer/training-candidates.yaml"),
        output_path=Path("artifacts/trainer/generated-training.yaml"),
        summary_path=Path("artifacts/trainer/generated-training-summary.json"),
    )
    assert combined_summary["base_example_count"] == 1
    assert combined_summary["candidate_example_count"] == 1
    assert combined_summary["combined_example_count"] == 2
    assert combined_summary["replaced_candidate_count"] == 0


def test_materialize_training_candidates_normalizes_legacy_worker_sources_and_duplicate_questions(
    tmp_path: Path,
) -> None:
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = trainer_dir / "training-candidates.yaml"
    candidates_path.write_text(
        (
            '- question: "What does this repository research?"\n'
            '  expected_answer: "Legacy answer A."\n'
            '  tags: ["trainer-candidate", "candidate"]\n'
            "  expected_sources:\n"
            '    - "prompt_artifacts/prompts_shards_of_lokar_game-p00000-355cca.txt"\n'
            '- question: "What does this repository research?"\n'
            '  expected_answer: "Legacy answer B."\n'
            '  tags: ["trainer-candidate", "candidate"]\n'
            "  expected_sources:\n"
            '    - "docs/USAGE.md"\n'
        ),
        encoding="utf-8",
    )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["candidate_count"] == 1
    assert summary["new_candidate_count"] == 0
    assert summary["replaced_count"] == 0
    materialized = load_training_examples(candidates_path)
    assert len(materialized) == 1
    assert materialized[0].question == "What does this repository research?"
    assert materialized[0].expected_sources == ()


def test_materialize_training_candidates_replaces_existing_candidate_with_new_trace(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = trainer_dir / "training-candidates.yaml"
    candidates_path.write_text(
        (
            '- question: "What does this repository research?"\n'
            '  expected_answer: "Legacy answer."\n'
            '  tags: ["trainer-candidate", "candidate"]\n'
            "  expected_sources:\n"
            '    - "prompt_artifacts/prompts_shards_of_lokar_game-p00000-355cca.txt"\n'
        ),
        encoding="utf-8",
    )
    (imported_dir / "accepted.json").write_text(
        """{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/accepted.json",
  "question": "What does this repository research?",
  "answer": "It researches repository-grounded RAG.",
  "sources": ["README.md"],
  "trace": {
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "2026-05-01T00:00:00+00:00",
    "question": "What does this repository research?",
    "mode": "codex-proxy",
    "retrieval_mode": "rag_heuristic_dspy",
    "sources": ["README.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "context",
    "mcp_candidate_count": 0,
    "answer_length": 20
  },
  "outcome": {
    "acceptance_status": "candidate",
    "accepted": null,
    "execution_status": "success",
    "method": "codex_cli",
    "backend": "codex_cli_repo_rag_proxy"
  }
}
""",
        encoding="utf-8",
    )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["candidate_count"] == 1
    assert summary["new_candidate_count"] == 1
    assert summary["replaced_count"] == 1
    materialized = load_training_examples(candidates_path)
    assert len(materialized) == 1
    assert materialized[0].expected_answer == "It researches repository-grounded RAG."
    assert materialized[0].expected_sources == ()


def test_materialize_training_candidates_reports_no_new_candidates_for_unchanged_full_ledger(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = trainer_dir / "training-candidates.yaml"
    summary_path = trainer_dir / "training-candidates-summary.json"
    trace_path = imported_dir / "accepted.json"
    trace_path.write_text(
        """{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/accepted.json",
  "question": "What does this repository research?",
  "answer": "It researches repository-grounded RAG.",
  "sources": ["README.md"],
  "trace": {
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "2026-05-01T00:00:00+00:00",
    "question": "What does this repository research?",
    "mode": "codex-proxy",
    "retrieval_mode": "rag_heuristic_dspy",
    "sources": ["README.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "context",
    "mcp_candidate_count": 0,
    "answer_length": 20
  },
  "outcome": {
    "acceptance_status": "candidate",
    "accepted": null,
    "execution_status": "success",
    "method": "codex_cli",
    "backend": "codex_cli_repo_rag_proxy"
  }
}
""",
        encoding="utf-8",
    )

    first_summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )
    second_summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert first_summary["candidate_count"] == 1
    assert first_summary["new_candidate_count"] == 1
    assert second_summary["candidate_count"] == 1
    assert second_summary["new_candidate_count"] == 0
    assert second_summary["replaced_count"] == 0
    assert load_training_examples(candidates_path)[0].expected_answer == (
        "It researches repository-grounded RAG."
    )
    assert json.loads(summary_path.read_text(encoding="utf-8"))["new_candidate_count"] == 0


def test_materialize_combined_training_examples_replaces_duplicate_questions_and_strips_legacy_worker_sources(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    base_training_path = tmp_path / "samples" / "training" / "base.yaml"
    base_training_path.parent.mkdir(parents=True, exist_ok=True)
    base_training_path.write_text(
        (
            '- question: "What does this repository research?"\n'
            '  expected_answer: "Base answer."\n'
            '  tags: ["repo"]\n'
            "  expected_sources:\n"
            '    - "README.md"\n'
            '- question: "Where are logs stored?"\n'
            '  expected_answer: "samples/logs"\n'
            '  tags: ["logs"]\n'
        ),
        encoding="utf-8",
    )

    candidates_path = tmp_path / "artifacts" / "trainer" / "training-candidates.yaml"
    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    candidates_path.write_text(
        (
            '- question: "What does this repository research?"\n'
            '  expected_answer: "Legacy worker answer."\n'
            '  tags: ["trainer-candidate", "candidate"]\n'
            "  expected_sources:\n"
            '    - "prompt_artifacts/prompts_shards_of_lokar_game-p00000-355cca.txt"\n'
            '- question: "What does this repository research?"\n'
            '  expected_answer: "Fresh worker answer."\n'
            '  tags: ["trainer-candidate", "candidate"]\n'
            "  expected_sources:\n"
            '    - "docs/USAGE.md"\n'
        ),
        encoding="utf-8",
    )

    combined_summary = materialize_combined_training_examples(
        tmp_path,
        base_training_path=Path("samples/training/base.yaml"),
        candidates_path=Path("artifacts/trainer/training-candidates.yaml"),
        output_path=Path("artifacts/trainer/generated-training.yaml"),
        summary_path=Path("artifacts/trainer/generated-training-summary.json"),
    )

    assert combined_summary["base_example_count"] == 2
    assert combined_summary["candidate_example_count"] == 2
    assert combined_summary["combined_example_count"] == 2
    assert combined_summary["new_candidate_count"] == 0
    assert combined_summary["duplicate_candidate_count"] == 0
    assert combined_summary["replaced_candidate_count"] == 2

    combined_examples = load_training_examples(
        tmp_path / "artifacts" / "trainer" / "generated-training.yaml"
    )
    assert len(combined_examples) == 2
    first_example = combined_examples[0]
    assert first_example.question == "What does this repository research?"
    assert first_example.expected_answer == "Fresh worker answer."
    assert first_example.expected_sources == ()
    assert validate_training_examples(combined_examples, root=tmp_path) == []
