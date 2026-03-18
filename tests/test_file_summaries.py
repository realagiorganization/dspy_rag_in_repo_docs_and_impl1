from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import nbformat
import pytest

from repo_rag_lab import file_summaries as file_summary_module


@pytest.fixture(autouse=True)
def _clear_git_hook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in tuple(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key, raising=False)


def _write_text(root: Path, relative_path: str, text: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_notebook(root: Path, relative_path: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_markdown_cell("# Demo Notebook"),
            nbformat.v4.new_code_cell("VALUE = 1"),
        ]
    )
    nbformat.write(notebook, path)


def _init_git_repo(root: Path, *paths: str) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", *paths], cwd=root, check=True)


def test_sync_file_summaries_writes_expected_outputs_for_tracked_repo(tmp_path: Path) -> None:
    _write_text(tmp_path, "README.md", "# Demo Repo\n")
    _write_text(tmp_path, "AGENTS.md", "# Agents\n")
    _write_text(tmp_path, "README.AGENTS.md", "# Narrative\n")
    _write_text(tmp_path, "README.DSPY.MD", "# DSPy\n")
    _write_text(tmp_path, "Makefile", ".PHONY: sync\nsync:\n\t@true\n")
    _write_text(tmp_path, ".github/workflows/ci.yml", "name: CI\n")
    _write_text(tmp_path, "docs/audit/README.md", "# Audit Index\n")
    _write_text(tmp_path, "src/repo_rag_lab/example.py", '"""Example module."""\n')
    _write_notebook(tmp_path, "notebooks/demo.ipynb")
    _write_text(tmp_path, "samples/logs/run.md", "# Run Log\n")
    _write_text(tmp_path, "rust-cli/main.rs", "fn main() {}\n")

    _init_git_repo(
        tmp_path,
        "README.md",
        "AGENTS.md",
        "README.AGENTS.md",
        "README.DSPY.MD",
        "Makefile",
        ".github/workflows/ci.yml",
        "docs/audit/README.md",
        "src/repo_rag_lab/example.py",
        "notebooks/demo.ipynb",
        "samples/logs/run.md",
        "rust-cli/main.rs",
    )

    payload = file_summary_module.sync_file_summaries(tmp_path)
    markdown = (tmp_path / "FILES.md").read_text(encoding="utf-8")
    csv_text = (tmp_path / "FILES.csv").read_text(encoding="utf-8")

    assert payload["tracked_file_count"] == 11
    assert payload["guide_path"] == "AGENTS.md.d/FILES.md"
    assert "`README.md`" in markdown
    assert "GitHub Actions workflow for ci" in markdown
    assert "Demo Notebook" in markdown
    assert "src/repo_rag_lab/example.py" in csv_text
    assert "python" in csv_text


def test_build_rows_classifies_text_binary_and_structured_summaries(tmp_path: Path) -> None:
    _write_text(tmp_path, "README.md", "# Demo Repo\n")
    _write_text(tmp_path, "data/config.json", json.dumps({"alpha": 1, "beta": 2}))
    _write_text(tmp_path, "notes/plain.txt", "first meaningful line\n")
    _write_text(tmp_path, "src/repo_rag_lab/example.py", '"""Example module."""\n')
    _write_notebook(tmp_path, "notebooks/demo.ipynb")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "banner.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    _init_git_repo(
        tmp_path,
        "README.md",
        "data/config.json",
        "notes/plain.txt",
        "src/repo_rag_lab/example.py",
        "notebooks/demo.ipynb",
        "assets/banner.png",
    )

    rows = {row.path: row for row in file_summary_module.build_rows(tmp_path)}

    assert rows["README.md"].kind == "markdown"
    assert rows["README.md"].summary == (
        "Top-level repository overview, workflow map, and quality guidance"
    )
    assert rows["data/config.json"].summary == "JSON object with keys: alpha, beta"
    assert rows["src/repo_rag_lab/example.py"].summary == "Example module."
    assert rows["notebooks/demo.ipynb"].summary == "Demo Notebook"
    assert rows["assets/banner.png"].line_count is None


def test_build_rows_cover_additional_kinds_and_public_fallbacks(tmp_path: Path) -> None:
    _write_text(tmp_path, "Makefile", ".PHONY: demo\ndemo:\n\t@true\n")
    _write_text(tmp_path, "stories/demo.feature", "Feature: Demo\n")
    _write_text(tmp_path, ".env.sample", "OPENAI_API_KEY=replace-me\n")
    _write_text(tmp_path, "notes/plain.txt", "\n---\nfirst line\n")
    _write_text(tmp_path, "README.DSPY.MD", "# DSPy Runtime Guide\n")
    _write_text(tmp_path, "src/repo_rag_lab/no_doc.py", "value = 1\n")
    _write_text(tmp_path, "src/repo_rag_lab/late.py", 'prefix\n"""Late doc"""\n')
    _write_text(tmp_path, "data/broken.json", "{oops\n")
    _write_text(tmp_path, "notebooks/bad.ipynb", "not-json\n")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    _init_git_repo(
        tmp_path,
        "Makefile",
        "stories/demo.feature",
        ".env.sample",
        "notes/plain.txt",
        "README.DSPY.MD",
        "src/repo_rag_lab/no_doc.py",
        "src/repo_rag_lab/late.py",
        "data/broken.json",
        "notebooks/bad.ipynb",
        "assets/image.png",
    )

    rows = {row.path: row for row in file_summary_module.build_rows(tmp_path)}

    assert rows["Makefile"].kind == "makefile"
    assert rows["stories/demo.feature"].kind == "gherkin"
    assert rows[".env.sample"].kind == "text"
    assert rows["notes/plain.txt"].kind == "text"
    assert rows["README.DSPY.MD"].kind == "markdown"
    assert rows["assets/image.png"].kind == "binary"
    assert rows[".env.sample"].summary == "OPENAI_API_KEY=replace-me"
    assert rows["notes/plain.txt"].summary == "first line"
    assert (
        rows["README.DSPY.MD"].summary
        == "DSPy workflow guide for training, runtime use, and compiled programs"
    )
    assert rows["src/repo_rag_lab/no_doc.py"].summary == "Python module for no doc"
    assert rows["src/repo_rag_lab/late.py"].summary == "Python module for late"
    assert rows["data/broken.json"].summary == "JSON data for broken"
    assert rows["notebooks/bad.ipynb"].summary == "Notebook playbook for bad"


def test_summarize_path_covers_special_cases_and_fallbacks(tmp_path: Path) -> None:
    _write_text(tmp_path, "AGENTS.md", "# Agents\n")
    _write_text(tmp_path, "README.AGENTS.md", "# Narrative\n")
    _write_text(tmp_path, "README.DSPY.MD", "# DSPy\n")
    _write_text(tmp_path, "docs/audit/demo.md", "# Audit\n")
    _write_text(tmp_path, "docs/audit/README.md", "# Audit Index\n")
    _write_text(tmp_path, "docs/config.yaml", "name: demo\n")
    _write_text(tmp_path, "data/broken.json", "{oops\n")
    _write_text(tmp_path, "notes/plain.txt", "first line\n")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "banner.bin").write_bytes(b"\x00\x01")

    assert (
        file_summary_module.summarize_path(tmp_path, Path("AGENTS.md"), "markdown")
        == "Repository-wide agent workflow, utility, and verification instructions"
    )
    assert (
        file_summary_module.summarize_path(tmp_path, Path("README.AGENTS.md"), "markdown")
        == "Repository research narrative tying code, docs, and verification together"
    )
    assert (
        file_summary_module.summarize_path(tmp_path, Path("README.DSPY.MD"), "markdown")
        == "DSPy workflow guide for training, runtime use, and compiled programs"
    )
    assert (
        file_summary_module.summarize_path(tmp_path, Path("docs/audit/demo.md"), "markdown")
        == "Repository audit note for demo"
    )
    assert (
        file_summary_module.summarize_path(tmp_path, Path("docs/audit/README.md"), "markdown")
        == "Audit index for dated repository verification notes"
    )
    assert (
        file_summary_module.summarize_path(tmp_path, Path("docs/config.yaml"), "yaml")
        == "name: demo"
    )
    assert (
        file_summary_module.summarize_path(tmp_path, Path("data/broken.json"), "json")
        == "JSON data for broken"
    )
    assert (
        file_summary_module.summarize_path(tmp_path, Path("notes/plain.txt"), "text")
        == "first line"
    )
    assert (
        file_summary_module.summarize_path(tmp_path, Path("assets/banner.bin"), "binary")
        == "Binary tracked asset at assets/banner.bin"
    )


def test_build_rows_and_check_outputs_cover_generated_outputs(tmp_path: Path) -> None:
    _write_text(tmp_path, "README.md", "# Demo Repo\n")
    _write_text(tmp_path, "AGENTS.md.d/FILES.md", "# Guide\n")

    _init_git_repo(tmp_path, "README.md", "AGENTS.md.d/FILES.md")

    file_summary_module.sync_file_summaries(tmp_path)
    subprocess.run(["git", "add", "FILES.md", "FILES.csv"], cwd=tmp_path, check=True)
    file_summary_module.sync_file_summaries(tmp_path)
    rows = {row.path: row for row in file_summary_module.build_rows(tmp_path)}

    assert rows["FILES.md"].line_count is None
    assert rows["FILES.md"].size_bytes == 0
    assert rows["FILES.md"].summary == "Generated Markdown inventory of tracked repository files"
    assert rows["FILES.csv"].line_count is None
    assert rows["FILES.csv"].size_bytes == 0
    assert rows["FILES.csv"].summary == "Generated CSV inventory of tracked repository files"
    assert file_summary_module.check_outputs(tmp_path) == 0

    (tmp_path / "FILES.md").write_text("stale\n", encoding="utf-8")
    assert file_summary_module.check_outputs(tmp_path) == 1


def test_main_supports_write_and_check_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_text(tmp_path, "README.md", "# Demo Repo\n")

    _init_git_repo(tmp_path, "README.md")

    monkeypatch.setattr(sys, "argv", ["file_summaries", "--root", str(tmp_path)])
    assert file_summary_module.main() == 0
    stdout = capsys.readouterr().out
    assert '"markdown_path": "FILES.md"' in stdout

    monkeypatch.setattr(sys, "argv", ["file_summaries", "--root", str(tmp_path), "--check"])
    assert file_summary_module.main() == 0

    (tmp_path / "FILES.csv").write_text("stale\n", encoding="utf-8")
    assert file_summary_module.main() == 1
