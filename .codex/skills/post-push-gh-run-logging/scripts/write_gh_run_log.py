#!/usr/bin/env python3
"""Write a repo-style GitHub Actions run log from `gh run view --json` output."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUN_FIELDS = ",".join(
    [
        "databaseId",
        "displayTitle",
        "workflowName",
        "event",
        "status",
        "conclusion",
        "headBranch",
        "headSha",
        "createdAt",
        "updatedAt",
        "url",
        "jobs",
    ]
)


def run_gh(*args: str, cwd: Path) -> str:
    completed = subprocess.run(
        ["gh", *args],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def newest_run_id(repo_root: Path) -> str:
    output = run_gh("run", "list", "--limit", "1", "--json", "databaseId", cwd=repo_root)
    rows = json.loads(output)
    if not rows:
        raise SystemExit("No GitHub Actions runs found.")
    return str(rows[0]["databaseId"])


def load_run(repo_root: Path, run_id: str) -> dict[str, Any]:
    output = run_gh("run", "view", run_id, "--json", RUN_FIELDS, cwd=repo_root)
    return json.loads(output)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:48] or "gh-run"


def format_run_section(run_data: dict[str, Any]) -> list[str]:
    lines = [
        f"- Workflow: `{run_data.get('workflowName', 'unknown')}`",
        f"- Display title: `{run_data.get('displayTitle', 'unknown')}`",
        f"- Run ID: `{run_data.get('databaseId', 'unknown')}`",
        f"- Event: `{run_data.get('event', 'unknown')}`",
        f"- Branch: `{run_data.get('headBranch', 'unknown')}`",
        f"- Head SHA: `{run_data.get('headSha', 'unknown')}`",
        f"- Status: `{run_data.get('status', 'unknown')}`",
        f"- Conclusion: `{run_data.get('conclusion') or 'n/a'}`",
        f"- Created at: `{run_data.get('createdAt', 'unknown')}`",
        f"- Updated at: `{run_data.get('updatedAt', 'unknown')}`",
        f"- URL: `{run_data.get('url', 'unknown')}`",
    ]
    return lines


def format_job_lines(run_data: dict[str, Any]) -> list[str]:
    jobs = run_data.get("jobs") or []
    if not jobs:
        return ["- No jobs returned by `gh run view`."]
    lines: list[str] = []
    for job in jobs:
        name = job.get("name", "unknown")
        database_id = job.get("databaseId", "unknown")
        conclusion = job.get("conclusion") or job.get("status") or "unknown"
        started = job.get("startedAt", "unknown")
        completed = job.get("completedAt", "unknown")
        lines.append(
            f"- `{name}` (`{database_id}`): `{conclusion}`, started `{started}`, completed `{completed}`"
        )
    return lines


def format_notes(run_data_list: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    failed_ids = [str(run["databaseId"]) for run in run_data_list if run.get("conclusion") == "failure"]
    pending_ids = [
        str(run["databaseId"])
        for run in run_data_list
        if run.get("status") != "completed" or run.get("conclusion") is None
    ]
    if failed_ids:
        joined = ", ".join(f"`{run_id}`" for run_id in failed_ids)
        notes.append(f"- At least one run failed. Inspect it with `RUN_ID=<id> make gh-failed-logs`; failed run IDs: {joined}.")
    if pending_ids:
        joined = ", ".join(f"`{run_id}`" for run_id in pending_ids)
        notes.append(f"- At least one run was logged before reaching a terminal state: {joined}.")
    return notes


def default_output_path(repo_root: Path, run_data_list: list[dict[str, Any]], timestamp: str) -> Path:
    first_title = run_data_list[0].get("displayTitle") or run_data_list[0].get("workflowName") or "gh-run"
    name = f"{timestamp.replace(':', '').replace('-', '')}-gh-runs-{slugify(first_title)}.md"
    return repo_root / "samples" / "logs" / name


def build_markdown(repo_root: Path, run_ids: list[str], run_data_list: list[dict[str, Any]], logged_at: str) -> str:
    lines = [
        "# GitHub Actions Run Log",
        "",
        f"- Log captured at: `{logged_at}`",
        f"- Repository root: `{repo_root}`",
        "- Command sequence:",
        "  - `make gh-runs GH_RUN_LIMIT=10`",
    ]
    for run_id in run_ids:
        lines.append(f"  - `RUN_ID={run_id} make gh-watch`")
    lines.append(f"  - `gh run view <id> --json {RUN_FIELDS}`")
    lines.append("")
    lines.append("## Latest Runs")
    lines.append("")
    for run_data in run_data_list:
        lines.extend(format_run_section(run_data))
        lines.append("")
    lines.append("## Job Summary")
    lines.append("")
    for run_data in run_data_list:
        run_id = run_data.get("databaseId", "unknown")
        lines.append(f"### Run `{run_id}`")
        lines.extend(format_job_lines(run_data))
        lines.append("")
    notes = format_notes(run_data_list)
    if notes:
        lines.append("## Notes")
        lines.append("")
        lines.extend(notes)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", help="Path to the repository root.")
    parser.add_argument("run_id", nargs="*", help="One or more GitHub Actions run IDs. Defaults to the newest run.")
    parser.add_argument("--output", help="Explicit output file path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    run_ids = list(args.run_id) or [newest_run_id(repo_root)]
    run_data_list = [load_run(repo_root, run_id) for run_id in run_ids]
    logged_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    timestamp = logged_at.replace("-", "").replace(":", "")
    output_path = Path(args.output).expanduser().resolve() if args.output else default_output_path(
        repo_root, run_data_list, timestamp
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_markdown(repo_root, run_ids, run_data_list, logged_at), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
