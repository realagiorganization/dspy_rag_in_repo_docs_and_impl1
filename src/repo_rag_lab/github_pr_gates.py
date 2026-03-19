"""GitHub branch-protection helpers for required pull-request gate checks."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

REQUIRED_PR_CHECK_CONTEXTS: tuple[str, ...] = (
    "Python Quality, Tests, And Build",
    "Rust Wrapper",
    "Build Publication PDF",
    "Hushwheel Fixture Quality",
)

GATE_WORKFLOW_PATHS: tuple[str, ...] = (
    ".github/workflows/ci.yml",
    ".github/workflows/publication-pdf.yml",
    ".github/workflows/hushwheel-quality.yml",
)


def _run_command(
    args: list[str],
    *,
    root: Path,
    stdin_text: str | None = None,
) -> str:
    completed = subprocess.run(
        args,
        cwd=root,
        input=stdin_text,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def _run_gh_json(
    args: list[str],
    *,
    root: Path,
    stdin_text: str | None = None,
) -> dict[str, Any]:
    output = _run_command(["gh", *args], root=root, stdin_text=stdin_text)
    return json.loads(output) if output else {}


def resolve_current_repo(root: Path) -> str:
    """Resolve the current GitHub repository name via ``gh``."""

    payload = _run_gh_json(["repo", "view", "--json", "nameWithOwner"], root=root)
    return str(payload["nameWithOwner"])


def build_branch_protection_payload() -> dict[str, object]:
    """Build the branch-protection payload for required PR gate checks."""

    return {
        "required_status_checks": {
            "strict": True,
            "contexts": list(REQUIRED_PR_CHECK_CONTEXTS),
        },
        "enforce_admins": False,
        "required_pull_request_reviews": None,
        "restrictions": None,
        "required_linear_history": False,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "required_conversation_resolution": False,
        "lock_branch": False,
        "allow_fork_syncing": False,
    }


def _extract_required_contexts(payload: dict[str, Any]) -> list[str]:
    required_status_checks = payload.get("required_status_checks") or {}
    if "contexts" in required_status_checks:
        return [str(context) for context in required_status_checks["contexts"]]
    checks = required_status_checks.get("checks") or []
    return [str(check["context"]) for check in checks if isinstance(check, dict)]


def sync_github_pr_gates(
    root: Path,
    *,
    branch: str = "master",
    repo: str | None = None,
    apply: bool = False,
) -> dict[str, object]:
    """Prepare or apply the GitHub required-check protection for pull-request merges."""

    resolved_root = root.resolve()
    resolved_repo = repo or resolve_current_repo(resolved_root)
    payload = build_branch_protection_payload()
    result: dict[str, object] = {
        "repo": resolved_repo,
        "branch": branch,
        "mode": "apply" if apply else "dry-run",
        "required_checks": list(REQUIRED_PR_CHECK_CONTEXTS),
        "workflow_paths": list(GATE_WORKFLOW_PATHS),
        "payload": payload,
    }

    if not apply:
        return result

    _run_gh_json(
        [
            "api",
            "--method",
            "PUT",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{resolved_repo}/branches/{branch}/protection",
            "--input",
            "-",
        ],
        root=resolved_root,
        stdin_text=json.dumps(payload),
    )
    protection = _run_gh_json(
        [
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{resolved_repo}/branches/{branch}/protection",
        ],
        root=resolved_root,
    )
    result["live_required_checks"] = _extract_required_contexts(protection)
    result["strict_status_checks"] = bool(
        (protection.get("required_status_checks") or {}).get("strict")
    )
    result["protection_url"] = protection.get("url")
    return result
