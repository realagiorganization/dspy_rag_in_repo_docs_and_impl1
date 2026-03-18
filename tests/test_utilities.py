from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_rag_lab.utilities import (
    run_notebook_report,
    run_smoke_test,
    run_surface_verification,
    utility_summary,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_utility_summary_mentions_core_surfaces() -> None:
    summary = utility_summary(REPO_ROOT)
    assert "ask" in summary
    assert "discover-mcp" in summary
    assert "smoke-test" in summary
    assert "verify-surfaces" in summary
    assert "run-notebooks" in summary


def test_run_smoke_test_reports_expected_fields() -> None:
    payload = json.loads(run_smoke_test(REPO_ROOT))
    assert payload["answer_contains_repository"] is True
    assert payload["manifest_path"].startswith("artifacts/azure/")
    assert isinstance(payload["mcp_candidate_count"], int)


def test_run_surface_verification_reports_expected_fields() -> None:
    payload = json.loads(run_surface_verification(REPO_ROOT))
    assert payload["issue_count"] == 0
    assert payload["checked_notebook_count"] >= 2


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
