from __future__ import annotations

import tomllib
from pathlib import Path

from repo_rag_lab.azure import write_deployment_manifest
from repo_rag_lab.notebook_support import resolve_repo_root

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


def test_resolve_repo_root_for_notebooks_dir() -> None:
    root = resolve_repo_root(REPO_ROOT / "notebooks")
    assert root == REPO_ROOT


def test_pyproject_exposes_uv_build_and_console_script() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["build-system"]["build-backend"] == "uv_build"
    assert pyproject["project"]["scripts"]["repo-rag"] == "repo_rag_lab.cli:main"
