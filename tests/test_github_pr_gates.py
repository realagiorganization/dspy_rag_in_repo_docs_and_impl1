# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from repo_rag_lab.github_pr_gates import (
    GATE_WORKFLOW_PATHS,
    REQUIRED_PR_CHECK_CONTEXTS,
    _extract_required_contexts,
    _run_command,
    _run_gh_json,
    build_branch_protection_payload,
    resolve_current_repo,
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


def test_run_command_and_run_gh_json_use_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_run(
        args: list[str],
        *,
        cwd: Path,
        input: str | None,
        text: bool,
        capture_output: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["cwd"] = cwd
        captured["input"] = input
        captured["text"] = text
        captured["capture_output"] = capture_output
        captured["check"] = check
        return subprocess.CompletedProcess(args, 0, stdout='{"ok": true}\n', stderr="")

    monkeypatch.setattr("repo_rag_lab.github_pr_gates.subprocess.run", fake_run)

    assert (
        _run_command(["gh", "repo", "view"], root=tmp_path, stdin_text="payload") == '{"ok": true}'
    )
    assert _run_gh_json(["repo", "view"], root=tmp_path) == {"ok": True}
    assert captured == {
        "args": ["gh", "repo", "view"],
        "cwd": tmp_path,
        "input": None,
        "text": True,
        "capture_output": True,
        "check": True,
    }


def test_run_gh_json_returns_empty_dict_for_empty_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run_command(
        args: list[str],
        *,
        root: Path,
        stdin_text: str | None = None,
    ) -> str:
        del args, root, stdin_text
        return ""

    monkeypatch.setattr("repo_rag_lab.github_pr_gates._run_command", fake_run_command)

    assert _run_gh_json(["repo", "view"], root=tmp_path) == {}


def test_resolve_current_repo_uses_gh_repo_view(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run_gh_json(
        args: list[str],
        *,
        root: Path,
        stdin_text: str | None = None,
    ) -> dict[str, object]:
        del args, root, stdin_text
        return {"nameWithOwner": "example/demo"}

    monkeypatch.setattr(
        "repo_rag_lab.github_pr_gates._run_gh_json",
        fake_run_gh_json,
    )

    assert resolve_current_repo(tmp_path) == "example/demo"


def test_extract_required_contexts_supports_contexts_and_checks_shapes() -> None:
    assert _extract_required_contexts({"required_status_checks": {"contexts": ["one", "two"]}}) == [
        "one",
        "two",
    ]
    assert _extract_required_contexts(
        {
            "required_status_checks": {
                "checks": [
                    {"context": "alpha"},
                    {"context": "beta"},
                    "skip-me",
                ]
            }
        }
    ) == ["alpha", "beta"]
    assert _extract_required_contexts({}) == []


def test_sync_github_pr_gates_apply_updates_branch_protection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], str | None]] = []
    live_payload: dict[str, object] = {
        "required_status_checks": {
            "strict": True,
            "checks": [{"context": context} for context in REQUIRED_PR_CHECK_CONTEXTS],
        },
        "url": "https://api.github.com/repos/example/demo/branches/master/protection",
    }

    def fake_run_gh_json(
        args: list[str],
        *,
        root: Path,
        stdin_text: str | None = None,
    ) -> dict[str, object]:
        calls.append((args, stdin_text))
        if args[:3] == ["repo", "view", "--json"]:
            return {"nameWithOwner": "example/demo"}
        if args[:3] == ["api", "--method", "PUT"]:
            assert json.loads(stdin_text or "{}") == build_branch_protection_payload()
            return {}
        return live_payload

    monkeypatch.setattr("repo_rag_lab.github_pr_gates._run_gh_json", fake_run_gh_json)

    payload = sync_github_pr_gates(tmp_path, apply=True)

    assert payload["repo"] == "example/demo"
    assert payload["mode"] == "apply"
    assert payload["live_required_checks"] == list(REQUIRED_PR_CHECK_CONTEXTS)
    assert payload["strict_status_checks"] is True
    assert payload["protection_url"] == live_payload["url"]
    assert calls[0][0] == ["repo", "view", "--json", "nameWithOwner"]
    assert calls[1][0][:3] == ["api", "--method", "PUT"]
    assert calls[2][0][:2] == ["api", "-H"]
