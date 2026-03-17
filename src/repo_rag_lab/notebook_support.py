"""Helpers shared by notebooks so their setup logic stays in tested Python code."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path


def resolve_repo_root(current: Path) -> Path:
    """
    Resolve the repository root from a notebook directory or repository root.

    >>> resolve_repo_root(Path('/tmp/example/notebooks'))
    PosixPath('/tmp/example')
    >>> resolve_repo_root(Path('/tmp/example'))
    PosixPath('/tmp/example')
    """

    return current.parent if current.name == "notebooks" else current


def configure_notebook_logger(name: str) -> logging.Logger:
    """
    Configure a stream logger suitable for notebook execution.

    >>> logger = configure_notebook_logger('repo_rag_lab.notebook.test')
    >>> logger.name
    'repo_rag_lab.notebook.test'
    """

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def assert_no_validation_issues(issues: list[str], *, context: str) -> None:
    """Fail fast in notebooks when sample validation issues are present."""

    if issues:
        joined = "; ".join(issues)
        raise AssertionError(f"{context} validation failed: {joined}")


def assert_minimum_pass_rate(summary: dict[str, object], minimum_pass_rate: float = 1.0) -> None:
    """Fail fast in notebooks when retrieval assertions regress."""

    pass_rate_value = summary.get("pass_rate", 0.0)
    if isinstance(pass_rate_value, (int, float, str)):
        pass_rate = float(pass_rate_value)
    else:  # pragma: no cover - defensive guard for malformed notebook payloads
        raise AssertionError("Benchmark summary pass_rate must be numeric.")
    if pass_rate < minimum_pass_rate:
        raise AssertionError(
            f"Benchmark pass rate {pass_rate:.2f} is below required "
            f"threshold {minimum_pass_rate:.2f}."
        )


def write_notebook_run_log(root: Path, notebook_name: str, payload: dict[str, object]) -> Path:
    """Persist notebook scaffold output for later inspection."""

    output_dir = root / "artifacts" / "notebook_logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"{timestamp}-{notebook_name}.json"
    output_path.write_text(
        json.dumps(
            {
                "notebook_name": notebook_name,
                "logged_at": timestamp,
                "payload": payload,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return output_path
