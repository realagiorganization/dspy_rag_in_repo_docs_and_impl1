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
    run_github_pr_gate_sync,
    run_notebook_report,
    run_pages_site_sync,
    run_retrieval_evaluation,
    run_smoke_test,
    run_surface_verification,
    run_todo_backlog_sync,
    utility_summary,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_demo_repo_for_exploratorium(tmp_path: Path) -> None:
    (tmp_path / "documentation").mkdir(parents=True)
    (tmp_path / "publication").mkdir(parents=True)
    (tmp_path / "src" / "repo_rag_lab").mkdir(parents=True)

    (tmp_path / "README.md").write_text(
        "# Demo Repo\n\nSee https://github.com/example/project and https://astral.sh/.\n",
        encoding="utf-8",
    )
    (tmp_path / "Makefile").write_text(".PHONY: setup\nsetup:\n\t@true\n", encoding="utf-8")
    (tmp_path / "documentation" / "azure-deployment.md").write_text(
        "# Azure Deployment\n\nCompanion note.\n",
        encoding="utf-8",
    )
    (tmp_path / "documentation" / "mcp-discovery.md").write_text(
        "# MCP Discovery\n\nCompanion note.\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "repo_rag_lab" / "example.py").write_text(
        '"""Example module."""\n\nVALUE = 1\n',
        encoding="utf-8",
    )
    (tmp_path / "publication" / "references.bib").write_text(
        "@misc{mcp2024,\n"
        "  title = {Model Context Protocol},\n"
        "  howpublished = {\\url{https://modelcontextprotocol.io/}}\n"
        "}\n\n"
        "@misc{azureinference2025,\n"
        "  title = {Azure AI Inference Documentation},\n"
        "  howpublished = {\\url{https://learn.microsoft.com/azure/ai-services/}}\n"
        "}\n",
        encoding="utf-8",
    )


def test_utility_summary_mentions_core_surfaces() -> None:
    summary = utility_summary(REPO_ROOT)
    assert "ask" in summary
    assert "lookup-first" in summary
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
    assert "github-pr-gates" in summary
    assert "pages-build" in summary
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
    markdown_path = REPO_ROOT / "FILES.md"
    csv_path = REPO_ROOT / "FILES.csv"
    original_markdown = markdown_path.read_text(encoding="utf-8")
    original_csv = csv_path.read_text(encoding="utf-8")

    try:
        payload = json.loads(run_file_summary_sync(REPO_ROOT))
        assert payload["markdown_path"] == "FILES.md"
        assert payload["csv_path"] == "FILES.csv"
        assert payload["guide_path"] == "AGENTS.md.d/FILES.md"
        assert payload["tracked_file_count"] >= 10
    finally:
        markdown_path.write_text(original_markdown, encoding="utf-8")
        csv_path.write_text(original_csv, encoding="utf-8")


def test_run_exploratorium_translation_sync_reports_expected_fields(tmp_path: Path) -> None:
    _write_demo_repo_for_exploratorium(tmp_path)

    payload = json.loads(run_exploratorium_translation_sync(tmp_path))
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
    assert payload["summarized_file_count"] >= 5


def test_run_github_pr_gate_sync_returns_machine_readable_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_sync_github_pr_gates(
        root: Path,
        *,
        branch: str = "master",
        repo: str | None = None,
        apply: bool = False,
    ) -> dict[str, object]:
        return {
            "repo": repo or "realagiorganization/dspy_rag_in_repo_docs_and_impl1",
            "branch": branch,
            "mode": "apply" if apply else "dry-run",
            "required_checks": [
                "Python Quality, Tests, And Build",
                "Rust Wrapper",
                "Build Publication PDF",
                "Hushwheel Fixture Quality",
            ],
            "root": str(root),
        }

    monkeypatch.setattr("repo_rag_lab.utilities.sync_github_pr_gates", fake_sync_github_pr_gates)
    payload = json.loads(
        run_github_pr_gate_sync(
            REPO_ROOT,
            branch="master",
            repo="realagiorganization/dspy_rag_in_repo_docs_and_impl1",
            apply=True,
        )
    )
    assert payload["repo"] == "realagiorganization/dspy_rag_in_repo_docs_and_impl1"
    assert payload["branch"] == "master"
    assert payload["mode"] == "apply"
    assert payload["required_checks"] == [
        "Python Quality, Tests, And Build",
        "Rust Wrapper",
        "Build Publication PDF",
        "Hushwheel Fixture Quality",
    ]


def test_run_pages_site_sync_returns_machine_readable_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_sync_pages_site(
        root: Path,
        *,
        output_dir: Path,
        branch: str = "master",
        repo_url: str | None = None,
    ) -> dict[str, object]:
        return {
            "output_dir": str(output_dir),
            "page_count": 12,
            "branch": branch,
            "repo_url": repo_url,
            "root": str(root),
        }

    monkeypatch.setattr("repo_rag_lab.utilities.sync_pages_site", fake_sync_pages_site)
    payload = json.loads(
        run_pages_site_sync(
            REPO_ROOT,
            output_dir=Path("artifacts/pages_docs"),
            branch="master",
            repo_url="https://github.com/example/demo",
        )
    )
    assert payload["output_dir"] == "artifacts/pages_docs"
    assert payload["page_count"] == 12
    assert payload["branch"] == "master"
    assert payload["repo_url"] == "https://github.com/example/demo"


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
