from __future__ import annotations

from pathlib import Path

import nbformat

from repo_rag_lab.verification import validate_makefile, validate_notebook


def test_validate_makefile_flags_missing_targets(tmp_path: Path) -> None:
    makefile = tmp_path / "Makefile"
    makefile.write_text(".PHONY: setup\nsetup:\n\t@true\n", encoding="utf-8")

    issues = validate_makefile(makefile)

    assert any(issue.message == "Missing target `coverage`." for issue in issues)
    assert any(issue.message == "Missing target `gh-runs`." for issue in issues)
    assert any(issue.message == "Missing target `gh-watch`." for issue in issues)
    assert any(issue.message == "Missing target `gh-failed-logs`." for issue in issues)
    assert any(issue.message == "Missing target `hooks-install`." for issue in issues)
    assert any(issue.message == "Missing target `quality`." for issue in issues)
    assert any(issue.message == "Target `quality` must be listed in .PHONY." for issue in issues)


def test_validate_notebook_accepts_research_playbook_shape(tmp_path: Path) -> None:
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_markdown_cell("# Goal\n\nDescribe the experiment."),
            nbformat.v4.new_code_cell("value = 1\nprint(value)\n"),
        ]
    )
    path = tmp_path / "research.ipynb"
    nbformat.write(notebook, path)

    issues = validate_notebook(path)

    assert issues == []


def test_validate_notebook_rejects_missing_heading(tmp_path: Path) -> None:
    notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell("print('x')\n")])
    path = tmp_path / "broken.ipynb"
    nbformat.write(notebook, path)

    issues = validate_notebook(path)

    assert any(
        issue.message == "Notebook must include at least one Markdown heading cell."
        for issue in issues
    )
