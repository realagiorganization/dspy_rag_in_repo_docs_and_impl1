from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
import yaml

from repo_rag_lab.azure import write_deployment_manifest, write_tuning_run_metadata
from repo_rag_lab.notebook_support import (
    assert_contains_text,
    assert_minimum_pass_rate,
    assert_no_validation_issues,
    configure_notebook_logger,
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


def test_resolve_repo_root_for_repo_root_is_identity() -> None:
    assert resolve_repo_root(REPO_ROOT) == REPO_ROOT


def test_configure_notebook_logger_reuses_existing_handler() -> None:
    logger = configure_notebook_logger("repo_rag_lab.notebook.test_project_surfaces")
    handler_count = len(logger.handlers)

    same_logger = configure_notebook_logger("repo_rag_lab.notebook.test_project_surfaces")

    assert same_logger is logger
    assert len(same_logger.handlers) == handler_count
    assert same_logger.propagate is False


def test_write_notebook_run_log_creates_artifact(tmp_path: Path) -> None:
    output_path = write_notebook_run_log(
        tmp_path,
        notebook_name="training-lab",
        payload={"case_count": 1},
    )
    assert output_path.exists()
    assert output_path.parent.name == "notebook_logs"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["notebook_name"] == "training-lab"
    assert payload["payload"]["case_count"] == 1
    assert payload["logged_at"]


def test_assert_helpers_raise_on_failure() -> None:
    assert_contains_text(
        "ask smoke-test utility-summary",
        ["ask", "smoke-test"],
        context="utility summary",
    )
    assert_no_validation_issues([], context="training samples")
    assert_minimum_pass_rate({"pass_rate": "1.0"}, minimum_pass_rate=1.0)

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


def test_publication_surface_files_exist_and_are_linked() -> None:
    publication_dir = REPO_ROOT / "publication"
    exploratorium_dir = publication_dir / "exploratorium_translation"
    assert (publication_dir / "README.md").exists()
    assert (publication_dir / "Makefile").exists()
    assert (publication_dir / "references.bib").exists()
    assert (publication_dir / "repository-rag-lab-article.tex").exists()
    assert (publication_dir / "todo-backlog-table.tex").exists()
    assert (publication_dir / "repository-rag-lab-article.pdf").exists()
    assert (publication_dir / "article-banner.png").exists()
    assert (exploratorium_dir / "README.md").exists()
    assert (exploratorium_dir / "Makefile").exists()
    assert (exploratorium_dir / "exploratorium_translation.tex").exists()
    assert (exploratorium_dir / "generated" / "exploratorium-content.tex").exists()
    assert (exploratorium_dir / "generated" / "exploratorium-manifest.json").exists()
    assert (exploratorium_dir / "exploratorium_translation.pdf").exists()
    assert (REPO_ROOT / "FILES.md").exists()
    assert (REPO_ROOT / "FILES.csv").exists()

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "publication/repository-rag-lab-article.pdf" in readme
    assert "publication/exploratorium_translation/exploratorium_translation.pdf" in readme
    assert "publication/article-banner.png" in readme
    assert "FILES.md" in readme
    assert "make paper-build" in readme
    assert "make files-sync" in readme
    assert "make rust-lookup-index" in readme
    assert 'make rust-lookup QUERY="' in readme
    assert "make todo-sync" in readme
    assert "make exploratorium-sync" in readme
    assert "make dspy-artifacts" in readme

    todo_text = (REPO_ROOT / "TODO.MD").read_text(encoding="utf-8")
    assert "| 🎯 | 🧭 Area | 📌 TODO | 🔗 Primary Surfaces | ✅ Done When |" in todo_text
    assert "todo-backlog.yaml" in todo_text


def test_rust_wrapper_surface_keeps_committed_lockfile_policy() -> None:
    checklist = (REPO_ROOT / "REPO_COMPLETENESS_CHECKLIST.md").read_text(encoding="utf-8")

    assert (REPO_ROOT / "rust-cli" / "Cargo.lock").exists()
    assert "rust-cli/Cargo.lock" in checklist
    assert "committed intentionally" in checklist


def test_publication_workflow_builds_and_uploads_pdf() -> None:
    workflow_path = REPO_ROOT / ".github" / "workflows" / "publication-pdf.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    workflow_on = workflow.get("on", workflow.get(True))
    assert workflow_on is not None
    assert "todo-backlog.yaml" in workflow_on["push"]["paths"]
    assert "src/repo_rag_lab/todo_backlog.py" in workflow_on["push"]["paths"]
    assert "src/repo_rag_lab/exploratorium_translation.py" in workflow_on["push"]["paths"]

    assert workflow["name"] == "Publication PDF"
    job = workflow["jobs"]["publication-pdf"]
    steps = job["steps"]

    assert any(step.get("uses") == "actions/checkout@v6" for step in steps)
    assert any(step.get("uses") == "actions/setup-python@v6" for step in steps)
    assert any(step.get("uses") == "astral-sh/setup-uv@v6" for step in steps)
    assert any(
        step.get("name") == "Sync publication inventories"
        and "repo-rag sync-todo-backlog" in step.get("run", "")
        and "repo-rag sync-exploratorium-translation" in step.get("run", "")
        for step in steps
    )
    assert any(
        step.get("uses") == "actions/cache@v4"
        and "publication/*.aux" in step.get("with", {}).get("path", "")
        and "publication/repository-rag-lab-article.tex" in step.get("with", {}).get("key", "")
        and "publication/todo-backlog-table.tex" in step.get("with", {}).get("key", "")
        and "publication/exploratorium_translation/exploratorium_translation.tex"
        in step.get("with", {}).get("key", "")
        and "publication/exploratorium_translation/generated/exploratorium-content.tex"
        in step.get("with", {}).get("key", "")
        for step in steps
    )
    assert sum(1 for step in steps if step.get("uses") == "xu-cheng/latex-action@v4") == 2
    assert any(
        step.get("uses") == "actions/upload-artifact@v6"
        and step.get("id") == "upload_publication_pdf"
        and "publication/repository-rag-lab-article.pdf" in step.get("with", {}).get("path", "")
        and "publication/exploratorium_translation/exploratorium_translation.pdf"
        in step.get("with", {}).get("path", "")
        for step in steps
    )
    assert any(
        step.get("uses") == "sarisia/actions-status-discord@v1"
        and step.get("env", {}).get("DISCORD_WEBHOOK") == "${{ secrets.DISCORD_WEBHOOK }}"
        and step.get("with", {}).get("webhook") == "${{ env.DISCORD_WEBHOOK }}"
        and "nofail" not in step.get("with", {})
        and "steps.upload_publication_pdf.outputs['artifact-url']"
        in step.get("with", {}).get("description", "")
        and "publication/exploratorium_translation/exploratorium_translation.pdf"
        in step.get("with", {}).get("description", "")
        and "publication/repository-rag-lab-article.pdf" in step.get("with", {}).get("url", "")
        for step in steps
    )


def test_repo_local_todo_skill_is_recorded() -> None:
    agents_text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    skill_path = REPO_ROOT / ".codex" / "skills" / "todo-backlog-sync" / "SKILL.md"

    assert "todo-backlog-sync" in agents_text
    assert "make todo-sync" in agents_text
    assert skill_path.exists()
    skill_text = skill_path.read_text(encoding="utf-8")
    assert "todo-backlog.yaml" in skill_text
    assert "make paper-build" in skill_text


def test_repo_local_exploratorium_skill_is_recorded() -> None:
    agents_text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    skill_path = REPO_ROOT / ".codex" / "skills" / "exploratorium-translation-sync" / "SKILL.md"

    assert "exploratorium-translation-sync" in agents_text
    assert "make exploratorium-sync" in agents_text
    assert skill_path.exists()
    skill_text = skill_path.read_text(encoding="utf-8")
    assert "src/repo_rag_lab/exploratorium_translation.py" in skill_text
    assert "make exploratorium-build" in skill_text


def test_repo_local_file_summary_skill_is_recorded() -> None:
    agents_text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    skill_path = REPO_ROOT / ".codex" / "skills" / "file-summary-sync" / "SKILL.md"

    assert "file-summary-sync" in agents_text
    assert "make files-sync" in agents_text
    assert skill_path.exists()
    skill_text = skill_path.read_text(encoding="utf-8")
    assert "FILES.md" in skill_text
    assert "AGENTS.md.d/FILES.md" in skill_text


def test_repo_local_rust_lookup_skill_is_recorded() -> None:
    agents_text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    skill_path = REPO_ROOT / ".codex" / "skills" / "rust-sqlite-lookup" / "SKILL.md"
    guidance_path = REPO_ROOT / "AGENTS.md.d" / "RUST_LOOKUP.md"

    assert "rust-sqlite-lookup" in agents_text
    assert "make rust-lookup-index" in agents_text
    assert "make rust-lookup QUERY=" in agents_text
    assert skill_path.exists()
    assert guidance_path.exists()
    skill_text = skill_path.read_text(encoding="utf-8")
    assert "lookup" in skill_text
    assert "ask-dspy" in skill_text


def test_ci_and_publish_workflows_cache_python_and_dependencies() -> None:
    ci_workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    publish_workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    )

    ci_python_steps = ci_workflow["jobs"]["python"]["steps"]
    ci_rust_steps = ci_workflow["jobs"]["rust-wrapper"]["steps"]
    publish_steps = publish_workflow["jobs"]["publish"]["steps"]

    for steps in (ci_python_steps, ci_rust_steps, publish_steps):
        assert any(
            step.get("uses") == "actions/setup-python@v6"
            and step.get("with", {}).get("python-version-file") == ".python-version"
            for step in steps
        )
        assert any(
            step.get("uses") == "astral-sh/setup-uv@v6"
            and step.get("with", {}).get("enable-cache") is True
            and ".python-version" in step.get("with", {}).get("cache-dependency-glob", "")
            and "pyproject.toml" in step.get("with", {}).get("cache-dependency-glob", "")
            and "uv.lock" in step.get("with", {}).get("cache-dependency-glob", "")
            for step in steps
        )

    assert any(step.get("uses") == "Swatinem/rust-cache@v2" for step in ci_rust_steps)
