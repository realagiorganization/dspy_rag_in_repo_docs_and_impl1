from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_rag_lab.todo_backlog import (
    TODO_LATEX_PATH,
    TODO_MARKDOWN_PATH,
    load_todo_backlog,
    render_latex_backlog,
    render_markdown_backlog,
    sync_todo_backlog,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_load_todo_backlog_reads_repo_items() -> None:
    repository_web_base, items = load_todo_backlog(REPO_ROOT)
    assert repository_web_base.endswith("/blob/master")
    assert len(items) >= 10
    assert any(
        item.task.startswith("Build the missing automated DSPy training path") for item in items
    )


def test_render_markdown_backlog_contains_links_and_emoji() -> None:
    _, items = load_todo_backlog(REPO_ROOT)
    rendered = render_markdown_backlog(items)
    assert "| 🎯 | 🧭 Area | 📌 TODO | 🔗 Primary Surfaces | ✅ Done When |" in rendered
    assert "[README.DSPY.MD](README.DSPY.MD)" in rendered
    assert "🧠" in rendered


def test_render_latex_backlog_contains_longtable_and_links() -> None:
    repository_web_base, items = load_todo_backlog(REPO_ROOT)
    rendered = render_latex_backlog(repository_web_base, items)
    assert r"\begin{longtable}" in rendered
    assert r"\href{" in rendered
    assert "README.DSPY.MD" in rendered


def test_sync_todo_backlog_writes_generated_outputs(tmp_path: Path) -> None:
    (tmp_path / "publication").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "surface.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "docs" / "note.md").write_text("# note\n", encoding="utf-8")
    (tmp_path / "todo-backlog.yaml").write_text(
        "\n".join(
            [
                "repository_web_base: https://example.com/org/repo/blob/main",
                "items:",
                '  - emoji: "🧠"',
                '    area: "Examples"',
                '    task: "Keep the example synced."',
                "    surfaces:",
                '      - path: "surface.py"',
                '      - path: "docs/note.md"',
                "    done_when:",
                '      - "Both surfaces render into the generated outputs."',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = sync_todo_backlog(tmp_path)

    assert payload["source_path"] == "todo-backlog.yaml"
    assert json.loads(json.dumps(payload))["item_count"] == 1
    assert (tmp_path / TODO_MARKDOWN_PATH).exists()
    assert (tmp_path / TODO_LATEX_PATH).exists()


def test_sync_todo_backlog_rejects_missing_surface_paths(tmp_path: Path) -> None:
    (tmp_path / "publication").mkdir()
    (tmp_path / "todo-backlog.yaml").write_text(
        "\n".join(
            [
                "items:",
                '  - emoji: "🧠"',
                '    area: "Examples"',
                '    task: "Keep the example synced."',
                "    surfaces:",
                '      - path: "missing.py"',
                "    done_when:",
                '      - "The missing file should be detected."',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match=r"missing\.py"):
        sync_todo_backlog(tmp_path)
