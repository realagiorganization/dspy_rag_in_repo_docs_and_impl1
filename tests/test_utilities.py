from __future__ import annotations

import json
from pathlib import Path

from repo_rag_lab.utilities import run_smoke_test, run_surface_verification, utility_summary

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_utility_summary_mentions_core_surfaces() -> None:
    summary = utility_summary(REPO_ROOT)
    assert "ask" in summary
    assert "discover-mcp" in summary
    assert "docs-site" in summary
    assert "render-ui" in summary
    assert "serve-ui" in summary
    assert "smoke-test" in summary
    assert "verify-surfaces" in summary


def test_run_smoke_test_reports_expected_fields() -> None:
    payload = json.loads(run_smoke_test(REPO_ROOT))
    assert payload["answer_contains_repository"] is True
    assert payload["manifest_path"].startswith("artifacts/azure/")
    assert isinstance(payload["mcp_candidate_count"], int)


def test_run_surface_verification_reports_expected_fields() -> None:
    payload = json.loads(run_surface_verification(REPO_ROOT))
    assert payload["issue_count"] == 0
    assert payload["checked_notebook_count"] >= 2
