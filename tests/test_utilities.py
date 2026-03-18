from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_rag_lab.utilities import (
    run_azure_inference_probe,
    run_azure_openai_probe,
    run_dspy_artifacts,
    run_exploratorium_translation_sync,
    run_file_summary_sync,
    run_notebook_report,
    run_retrieval_evaluation,
    run_smoke_test,
    run_surface_verification,
    run_todo_backlog_sync,
    utility_summary,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_utility_summary_mentions_core_surfaces() -> None:
    summary = utility_summary(REPO_ROOT)
    assert "ask" in summary
    assert "ask-live" in summary
    assert "discover-mcp" in summary
    assert "dspy-train" in summary
    assert "dspy-artifacts" in summary
    assert "azure-openai-probe" in summary
    assert "azure-inference-probe" in summary
    assert "files-sync" in summary
    assert "rust-lookup-index" in summary
    assert "rust-lookup" in summary
    assert "exploratorium-sync" in summary
    assert "retrieval-eval" in summary
    assert "todo-sync" in summary
    assert "smoke-test" in summary
    assert "verify-surfaces" in summary
    assert "run-notebooks" in summary


def test_run_smoke_test_reports_expected_fields() -> None:
    payload = json.loads(run_smoke_test(REPO_ROOT))
    assert payload["answer_contains_repository"] is True
    assert payload["manifest_path"].startswith("artifacts/azure/")
    assert isinstance(payload["mcp_candidate_count"], int)


def test_run_retrieval_evaluation_reports_expected_fields() -> None:
    payload = json.loads(run_retrieval_evaluation(REPO_ROOT, top_k=4, top_k_sweep="1,4"))
    assert payload["training_path"] == "samples/training/repository_training_examples.yaml"
    assert payload["benchmark_count"] >= 1
    assert payload["default_top_k"] == 4
    assert payload["default_summary"]["top_k"] == 4
    assert payload["default_summary"]["tag_summaries"]
    assert [summary["top_k"] for summary in payload["top_k_summaries"]] == [1, 4]
    assert "average_reciprocal_rank" in payload["default_summary"]
    assert payload["thresholds_enabled"] is False
    assert payload["thresholds"]["minimum_pass_rate"] is None
    assert payload["thresholds"]["minimum_source_recall"] is None
    assert payload["threshold_failures"] == []
    assert payload["status"] == "pass"


def test_run_retrieval_evaluation_reports_threshold_failures() -> None:
    payload = json.loads(
        run_retrieval_evaluation(
            REPO_ROOT,
            top_k=4,
            top_k_sweep="1,4",
            minimum_pass_rate=1.1,
            minimum_source_recall=1.1,
        )
    )

    assert payload["status"] == "fail"
    assert len(payload["threshold_failures"]) == 2


def test_run_surface_verification_reports_expected_fields() -> None:
    payload = json.loads(run_surface_verification(REPO_ROOT))
    assert payload["issue_count"] == 0
    assert payload["checked_notebook_count"] >= 2


def test_run_dspy_artifacts_reports_expected_fields(tmp_path: Path) -> None:
    payload = json.loads(run_dspy_artifacts(tmp_path))
    assert payload["artifact_root"] == "artifacts/dspy"
    assert payload["run_count"] == 0
    assert payload["runs"] == []


def test_run_todo_backlog_sync_reports_expected_fields() -> None:
    payload = json.loads(run_todo_backlog_sync(REPO_ROOT))
    assert payload["source_path"] == "todo-backlog.yaml"
    assert payload["markdown_path"] == "TODO.MD"
    assert payload["latex_path"] == "publication/todo-backlog-table.tex"
    assert payload["item_count"] >= 10


def test_run_azure_openai_probe_returns_machine_readable_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_probe(root: Path, *, load_env_file: bool = False) -> dict[str, object]:
        return {
            "provider": "azure-openai",
            "root": str(root),
            "load_env_file": load_env_file,
            "reply": "OPENAI_OK",
        }

    monkeypatch.setattr("repo_rag_lab.utilities.probe_azure_openai", fake_probe)
    payload = json.loads(run_azure_openai_probe(REPO_ROOT, load_env_file=True))
    assert payload["provider"] == "azure-openai"
    assert payload["load_env_file"] is True
    assert payload["reply"] == "OPENAI_OK"


def test_run_azure_inference_probe_returns_machine_readable_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_probe(root: Path, *, load_env_file: bool = False) -> dict[str, object]:
        return {
            "provider": "azure-inference",
            "root": str(root),
            "load_env_file": load_env_file,
            "reply": "INFERENCE_OK",
        }

    monkeypatch.setattr("repo_rag_lab.utilities.probe_azure_inference", fake_probe)
    payload = json.loads(run_azure_inference_probe(REPO_ROOT, load_env_file=True))
    assert payload["provider"] == "azure-inference"
    assert payload["load_env_file"] is True
    assert payload["reply"] == "INFERENCE_OK"


def test_run_file_summary_sync_reports_expected_fields() -> None:
    payload = json.loads(run_file_summary_sync(REPO_ROOT))
    assert payload["markdown_path"] == "FILES.md"
    assert payload["csv_path"] == "FILES.csv"
    assert payload["guide_path"] == "AGENTS.md.d/FILES.md"
    assert payload["tracked_file_count"] >= 10


def test_run_exploratorium_translation_sync_reports_expected_fields() -> None:
    payload = json.loads(run_exploratorium_translation_sync(REPO_ROOT))
    assert (
        payload["tex_path"]
        == "publication/exploratorium_translation/generated/exploratorium-content.tex"
    )
    assert (
        payload["manifest_path"]
        == "publication/exploratorium_translation/generated/exploratorium-manifest.json"
    )
    assert (
        payload["main_tex_path"]
        == "publication/exploratorium_translation/exploratorium_translation.tex"
    )
    assert (
        payload["pdf_path"] == "publication/exploratorium_translation/exploratorium_translation.pdf"
    )
    assert payload["summarized_file_count"] >= 10


def test_run_notebook_report_returns_machine_readable_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_notebooks(root: Path, **_: object) -> dict[str, object]:
        return {
            "root": str(root),
            "run_id": "sample",
            "status": "success",
            "failure_count": 0,
            "notebook_count": 1,
            "notebooks": [],
        }

    monkeypatch.setattr("repo_rag_lab.utilities.run_notebooks", fake_run_notebooks)
    payload = json.loads(run_notebook_report(REPO_ROOT))
    assert payload["status"] == "success"
    assert payload["failure_count"] == 0
