"""Monitored batch execution helpers for repository notebooks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import MutableMapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO, TypedDict

import nbformat

from .settings import RepoSettings


class NotebookExecutionRecord(TypedDict):
    """A single notebook execution result."""

    source_path: str
    name: str
    status: str
    started_at: str
    completed_at: str
    duration_seconds: float
    returncode: int
    raw_log_path: str
    executed_notebook_path: str | None
    notebook_log_path: str | None
    code_cell_count: int
    executed_code_cell_count: int
    output_count: int
    failure_excerpt: str | None


class NotebookExecutionReport(TypedDict):
    """The overall notebook batch execution report."""

    run_id: str
    root: str
    run_dir: str
    status: str
    started_at: str
    completed_at: str
    duration_seconds: float
    timeout_seconds: int
    load_env_file: bool
    env_file_path: str
    env_file_found: bool
    loaded_env_keys: list[str]
    report_json_path: str
    report_markdown_path: str
    progress_path: str
    notebook_count: int
    success_count: int
    failure_count: int
    notebooks: list[NotebookExecutionRecord]


def _iso_utc_now() -> str:
    """Return an ISO8601 UTC timestamp suitable for logs and reports."""

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_id_now() -> str:
    """Return a compact UTC timestamp suitable for artifact names."""

    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _relative_to_root(path: Path, root: Path) -> str:
    """Return a repository-relative string path."""

    return str(path.relative_to(root))


def _notebook_slug(path: Path) -> str:
    """Return the hyphenated notebook slug used by notebook log files."""

    return path.stem.replace("_", "-")


def load_env_vars(
    path: Path,
    *,
    environ: MutableMapping[str, str] | None = None,
    override: bool = True,
) -> list[str]:
    """Load a simple `.env` file into the selected environment mapping."""

    target_env = os.environ if environ is None else environ
    if not path.exists():
        return []

    loaded_keys: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if override or key not in target_env:
            target_env[key] = value
        loaded_keys.append(key)
    return loaded_keys


def _collect_notebook_metrics(path: Path) -> tuple[int, int, int]:
    """Collect output and execution metrics from an executed notebook artifact."""

    notebook = nbformat.read(path, as_version=4)
    code_cell_count = 0
    executed_code_cell_count = 0
    output_count = 0

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        code_cell_count += 1
        if cell.execution_count is not None:
            executed_code_cell_count += 1
        output_count += len(cell.outputs)

    return code_cell_count, executed_code_cell_count, output_count


def _write_json(path: Path, payload: object) -> None:
    """Serialize a JSON artifact with stable indentation."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _emit_progress(stream: TextIO | None, notebook_name: str, message: str) -> None:
    """Emit a timestamped progress line when a stream is configured."""

    if stream is None:
        return
    timestamp = datetime.now(UTC).strftime("%H:%M:%S")
    stream.write(f"[{timestamp}Z] [{notebook_name}] {message}\n")
    stream.flush()


def _tail_text(path: Path, *, max_lines: int = 20) -> str | None:
    """Return the last lines from a text file or ``None`` when it is empty."""

    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return None
    return "\n".join(lines[-max_lines:])


def _find_notebook_log_path(
    notebook_path: Path,
    notebook_logs_dir: Path,
    before_logs: set[Path],
    root: Path,
) -> str | None:
    """Find the notebook-log artifact created by a notebook execution."""

    if not notebook_logs_dir.exists():
        return None
    created_logs = sorted(
        notebook_logs_dir.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
    )
    slug = _notebook_slug(notebook_path)
    new_matches = [path for path in created_logs if path not in before_logs and slug in path.name]
    if new_matches:
        return _relative_to_root(new_matches[-1], root)
    historical_matches = [path for path in created_logs if slug in path.name]
    if not historical_matches:
        return None
    return _relative_to_root(historical_matches[-1], root)


def render_notebook_run_report(report: NotebookExecutionReport) -> str:
    """Render a concise Markdown summary for a notebook batch run."""

    lines = [
        "# Notebook Run Report",
        "",
        f"- Run ID: `{report['run_id']}`",
        f"- Status: `{report['status']}`",
        f"- Root: `{report['root']}`",
        f"- Started at: `{report['started_at']}`",
        f"- Completed at: `{report['completed_at']}`",
        f"- Duration: `{report['duration_seconds']:.2f}` seconds",
        f"- Timeout per notebook: `{report['timeout_seconds']}` seconds",
        f"- `.env` loaded: `{report['load_env_file']}`",
        f"- `.env` path: `{report['env_file_path']}`",
        f"- `.env` present: `{report['env_file_found']}`",
        (
            "- Loaded env keys: "
            + (", ".join(f"`{key}`" for key in report["loaded_env_keys"]) or "`none`")
        ),
        "",
        "## Notebooks",
        "",
    ]

    for notebook in report["notebooks"]:
        line = (
            f"- `{notebook['source_path']}`: `{notebook['status']}` in "
            f"`{notebook['duration_seconds']:.2f}` seconds; outputs "
            f"`{notebook['output_count']}`; executed cells "
            f"`{notebook['executed_code_cell_count']}/{notebook['code_cell_count']}`; "
            f"raw log `{notebook['raw_log_path']}`"
        )
        if notebook["executed_notebook_path"] is not None:
            line += f"; executed copy `{notebook['executed_notebook_path']}`"
        if notebook["notebook_log_path"] is not None:
            line += f"; notebook log `{notebook['notebook_log_path']}`"
        lines.append(line)
        if notebook["failure_excerpt"] is not None:
            lines.append("")
            lines.append("```text")
            lines.append(notebook["failure_excerpt"])
            lines.append("```")

    return "\n".join(lines) + "\n"


def _build_progress_payload(
    *,
    run_id: str,
    root: Path,
    timeout_seconds: int,
    load_env_file: bool,
    env_file_path: str,
    env_file_found: bool,
    loaded_env_keys: list[str],
    current_notebook: str | None,
    started_at: str,
    records: Sequence[NotebookExecutionRecord | dict[str, object]],
) -> dict[str, object]:
    """Build the incremental JSON payload used by the notebook monitor."""

    success_count = sum(1 for record in records if record["status"] == "success")
    failure_count = sum(1 for record in records if record["status"] == "failure")
    return {
        "run_id": run_id,
        "root": str(root),
        "started_at": started_at,
        "timeout_seconds": timeout_seconds,
        "load_env_file": load_env_file,
        "env_file_path": env_file_path,
        "env_file_found": env_file_found,
        "loaded_env_keys": loaded_env_keys,
        "current_notebook": current_notebook,
        "completed_count": success_count + failure_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "notebooks": records,
    }


def run_notebooks(
    root: Path,
    *,
    timeout_seconds: int = 600,
    load_env_file: bool = False,
    fail_fast: bool = False,
    stream: TextIO | None = None,
) -> NotebookExecutionReport:
    """Execute all tracked notebooks and write monitored batch-run artifacts."""

    settings = RepoSettings.from_root(root)
    notebook_paths = sorted(settings.notebooks_dir.glob("*.ipynb"))
    run_id = _run_id_now()
    run_dir = settings.artifacts_dir / "notebook_runs" / run_id
    logs_dir = run_dir / "logs"
    executed_notebooks_dir = run_dir / "executed_notebooks"
    progress_path = run_dir / "progress.json"
    report_json_path = run_dir / "report.json"
    report_markdown_path = run_dir / "report.md"
    notebook_logs_dir = settings.artifacts_dir / "notebook_logs"
    env_file_path = root / ".env"
    env_file_found = env_file_path.exists()

    run_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    executed_notebooks_dir.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    loaded_env_keys: list[str] = []
    if load_env_file:
        loaded_env_keys = load_env_vars(env_file_path, environ=env)

    started_at = _iso_utc_now()
    started_monotonic = time.monotonic()
    records: list[NotebookExecutionRecord] = []

    _write_json(
        progress_path,
        _build_progress_payload(
            run_id=run_id,
            root=root,
            timeout_seconds=timeout_seconds,
            load_env_file=load_env_file,
            env_file_path=_relative_to_root(env_file_path, root),
            env_file_found=env_file_found,
            loaded_env_keys=loaded_env_keys,
            current_notebook=None,
            started_at=started_at,
            records=[],
        ),
    )

    for notebook_path in notebook_paths:
        relative_path = _relative_to_root(notebook_path, root)
        notebook_name = notebook_path.name
        raw_log_path = logs_dir / f"{notebook_path.stem}.log"
        executed_notebook_path = executed_notebooks_dir / notebook_name
        before_logs = set(notebook_logs_dir.glob("*.json")) if notebook_logs_dir.exists() else set()
        notebook_started_at = _iso_utc_now()
        notebook_started_monotonic = time.monotonic()

        _write_json(
            progress_path,
            _build_progress_payload(
                run_id=run_id,
                root=root,
                timeout_seconds=timeout_seconds,
                load_env_file=load_env_file,
                env_file_path=_relative_to_root(env_file_path, root),
                env_file_found=env_file_found,
                loaded_env_keys=loaded_env_keys,
                current_notebook=relative_path,
                started_at=started_at,
                records=[
                    *records,
                    {
                        "source_path": relative_path,
                        "name": notebook_name,
                        "status": "running",
                        "started_at": notebook_started_at,
                    },
                ],
            ),
        )

        command = [
            sys.executable,
            "-m",
            "jupyter",
            "nbconvert",
            "--to",
            "notebook",
            "--execute",
            f"--ExecutePreprocessor.timeout={timeout_seconds}",
            "--output-dir",
            str(executed_notebooks_dir),
            relative_path,
        ]

        _emit_progress(
            stream,
            notebook_name,
            f"starting execution with timeout {timeout_seconds}s -> {relative_path}",
        )

        with raw_log_path.open("w", encoding="utf-8") as raw_log_handle:
            raw_log_handle.write(
                f"started_at={notebook_started_at}\ncommand={' '.join(command)}\n\n"
            )
            process = subprocess.Popen(
                command,
                cwd=root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            stdout = process.stdout
            if stdout is None:
                raise RuntimeError("Notebook subprocess stdout pipe was not created.")
            for line in stdout:
                raw_log_handle.write(line)
                _emit_progress(stream, notebook_name, line.rstrip("\n"))
            returncode = process.wait()

        notebook_completed_at = _iso_utc_now()
        duration_seconds = round(time.monotonic() - notebook_started_monotonic, 2)
        status = "success" if returncode == 0 else "failure"
        executed_path_str: str | None = None
        notebook_log_path = _find_notebook_log_path(
            notebook_path,
            notebook_logs_dir,
            before_logs,
            root,
        )
        if executed_notebook_path.exists():
            executed_path_str = _relative_to_root(executed_notebook_path, root)
            metrics = _collect_notebook_metrics(executed_notebook_path)
        else:
            metrics = (0, 0, 0)

        record: NotebookExecutionRecord = {
            "source_path": relative_path,
            "name": notebook_name,
            "status": status,
            "started_at": notebook_started_at,
            "completed_at": notebook_completed_at,
            "duration_seconds": duration_seconds,
            "returncode": returncode,
            "raw_log_path": _relative_to_root(raw_log_path, root),
            "executed_notebook_path": executed_path_str,
            "notebook_log_path": notebook_log_path,
            "code_cell_count": metrics[0],
            "executed_code_cell_count": metrics[1],
            "output_count": metrics[2],
            "failure_excerpt": None if returncode == 0 else _tail_text(raw_log_path),
        }
        records.append(record)
        _emit_progress(
            stream,
            notebook_name,
            f"{status} in {duration_seconds:.2f}s -> {record['raw_log_path']}",
        )

        _write_json(
            progress_path,
            _build_progress_payload(
                run_id=run_id,
                root=root,
                timeout_seconds=timeout_seconds,
                load_env_file=load_env_file,
                env_file_path=_relative_to_root(env_file_path, root),
                env_file_found=env_file_found,
                loaded_env_keys=loaded_env_keys,
                current_notebook=None,
                started_at=started_at,
                records=records,
            ),
        )

        if fail_fast and returncode != 0:
            break

    completed_at = _iso_utc_now()
    duration_seconds = round(time.monotonic() - started_monotonic, 2)
    success_count = sum(1 for record in records if record["status"] == "success")
    failure_count = sum(1 for record in records if record["status"] == "failure")
    if failure_count == 0:
        status = "success"
    elif success_count == 0:
        status = "failure"
    else:
        status = "partial_failure"

    report: NotebookExecutionReport = {
        "run_id": run_id,
        "root": str(root),
        "run_dir": _relative_to_root(run_dir, root),
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": duration_seconds,
        "timeout_seconds": timeout_seconds,
        "load_env_file": load_env_file,
        "env_file_path": _relative_to_root(env_file_path, root),
        "env_file_found": env_file_found,
        "loaded_env_keys": loaded_env_keys,
        "report_json_path": _relative_to_root(report_json_path, root),
        "report_markdown_path": _relative_to_root(report_markdown_path, root),
        "progress_path": _relative_to_root(progress_path, root),
        "notebook_count": len(records),
        "success_count": success_count,
        "failure_count": failure_count,
        "notebooks": records,
    }
    _write_json(progress_path, report)
    _write_json(report_json_path, report)
    report_markdown_path.write_text(render_notebook_run_report(report), encoding="utf-8")
    return report
