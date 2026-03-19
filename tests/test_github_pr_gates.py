from __future__ import annotations

from pathlib import Path

from repo_rag_lab.github_pr_gates import (
    GATE_WORKFLOW_PATHS,
    REQUIRED_PR_CHECK_CONTEXTS,
    build_branch_protection_payload,
    sync_github_pr_gates,
)


def test_build_branch_protection_payload_matches_required_pr_checks() -> None:
    payload = build_branch_protection_payload()

    assert payload["required_status_checks"] == {
        "strict": True,
        "contexts": list(REQUIRED_PR_CHECK_CONTEXTS),
    }
    assert payload["required_pull_request_reviews"] is None
    assert payload["restrictions"] is None
    assert payload["allow_force_pushes"] is False
    assert payload["allow_deletions"] is False


def test_sync_github_pr_gates_dry_run_reports_expected_shape(tmp_path: Path) -> None:
    payload = sync_github_pr_gates(
        tmp_path,
        branch="master",
        repo="realagiorganization/dspy_rag_in_repo_docs_and_impl1",
        apply=False,
    )

    assert payload["repo"] == "realagiorganization/dspy_rag_in_repo_docs_and_impl1"
    assert payload["branch"] == "master"
    assert payload["mode"] == "dry-run"
    assert payload["required_checks"] == list(REQUIRED_PR_CHECK_CONTEXTS)
    assert payload["workflow_paths"] == list(GATE_WORKFLOW_PATHS)
