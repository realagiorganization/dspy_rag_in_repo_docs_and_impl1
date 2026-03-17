from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from repo_rag_lab.azure import write_deployment_manifest, write_tuning_run_metadata
from repo_rag_lab.notebook_support import (
    assert_contains_text,
    assert_minimum_pass_rate,
    assert_no_validation_issues,
    resolve_repo_root,
    write_notebook_run_log,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_write_deployment_manifest_creates_json_file(tmp_path: Path) -> None:
    output_path = write_deployment_manifest(
        root=tmp_path,
        model_id="test-model",
        deployment_name="test-deployment",
        endpoint="https://example.services.ai.azure.com/models",
    )
    assert output_path.exists()
    assert output_path.name == "test-deployment.json"


def test_write_tuning_run_metadata_creates_json_file(tmp_path: Path) -> None:
    output_path = write_tuning_run_metadata(
        root=tmp_path,
        run_name="training-lab",
        training_data_path=tmp_path / "samples" / "training.yaml",
        benchmark_summary={"case_count": 1, "pass_count": 1, "pass_rate": 1.0},
        deployment_name="test-deployment",
    )
    assert output_path.exists()
    assert output_path.name == "training-lab.json"


def test_resolve_repo_root_for_notebooks_dir() -> None:
    root = resolve_repo_root(REPO_ROOT / "notebooks")
    assert root == REPO_ROOT


def test_write_notebook_run_log_creates_artifact(tmp_path: Path) -> None:
    output_path = write_notebook_run_log(
        tmp_path,
        notebook_name="training-lab",
        payload={"case_count": 1},
    )
    assert output_path.exists()
    assert output_path.parent.name == "notebook_logs"


def test_assert_helpers_raise_on_failure() -> None:
    assert_contains_text(
        "ask smoke-test utility-summary",
        ["ask", "smoke-test"],
        context="utility summary",
    )

    with pytest.raises(AssertionError, match="missing required content"):
        assert_contains_text("utility-summary", ["ask", "smoke-test"], context="utility summary")

    with pytest.raises(AssertionError, match="training samples validation failed"):
        assert_no_validation_issues(["broken"], context="training samples")

    with pytest.raises(AssertionError, match="below required threshold"):
        assert_minimum_pass_rate({"pass_rate": 0.5}, minimum_pass_rate=1.0)


def test_pyproject_exposes_uv_build_and_console_script() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["build-system"]["build-backend"] == "uv_build"
    assert pyproject["project"]["scripts"]["repo-rag"] == "repo_rag_lab.cli:main"
