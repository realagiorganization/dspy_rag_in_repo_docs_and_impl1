from __future__ import annotations

from pathlib import Path

from repo_rag_lab.training_samples import (
    batch_training_examples,
    load_training_examples,
    summarize_training_examples,
    validate_training_examples,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
HUSHWHEEL_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "hushwheel_lexiconarium"


def test_load_training_examples_reads_repository_samples() -> None:
    examples = load_training_examples(
        REPO_ROOT / "samples" / "training" / "repository_training_examples.yaml"
    )
    assert len(examples) >= 3
    assert examples[0].question
    assert examples[0].expected_sources


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
