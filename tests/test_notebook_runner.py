from __future__ import annotations

import json
from pathlib import Path

import nbformat

from repo_rag_lab.notebook_runner import load_env_vars, run_notebooks


def test_load_env_vars_reads_simple_assignments(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "PLAIN=value\nexport QUOTED='other value'\n# ignored\nMISSING\n",
        encoding="utf-8",
    )

    payload: dict[str, str] = {}
    loaded_keys = load_env_vars(env_path, environ=payload)

    assert loaded_keys == ["PLAIN", "QUOTED"]
    assert payload["PLAIN"] == "value"
    assert payload["QUOTED"] == "other value"


def test_run_notebooks_writes_report_without_dirtying_source_notebook(tmp_path: Path) -> None:
    notebook_dir = tmp_path / "notebooks"
    notebook_dir.mkdir(parents=True)
    notebook_path = notebook_dir / "sample_notebook.ipynb"
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_markdown_cell("# Sample Notebook"),
            nbformat.v4.new_code_cell(
                "from pathlib import Path\n"
                "from repo_rag_lab.notebook_support import (\n"
                "    resolve_repo_root,\n"
                "    write_notebook_run_log,\n"
                ")\n"
                "root = resolve_repo_root(Path.cwd())\n"
                'log_path = write_notebook_run_log(root, "sample-notebook", {"ok": True})\n'
                "print(log_path.relative_to(root))\n"
            ),
        ],
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            }
        },
    )
    nbformat.write(notebook, notebook_path)

    report = run_notebooks(tmp_path, timeout_seconds=120)

    assert report["status"] == "success"
    assert report["success_count"] == 1
    assert report["failure_count"] == 0
    assert report["notebook_count"] == 1
    assert report["env_file_path"] == ".env"
    assert report["env_file_found"] is False

    record = report["notebooks"][0]
    assert record["status"] == "success"
    assert record["output_count"] >= 1
    assert record["executed_code_cell_count"] == record["code_cell_count"] == 1
    assert record["executed_notebook_path"] is not None
    assert record["notebook_log_path"] is not None
    assert record["raw_log_path"].startswith("artifacts/notebook_runs/")
    assert (tmp_path / report["report_json_path"]).exists()
    assert (tmp_path / report["report_markdown_path"]).exists()
    assert (tmp_path / report["progress_path"]).exists()
    assert (tmp_path / record["raw_log_path"]).exists()
    assert (tmp_path / record["executed_notebook_path"]).exists()
    assert (tmp_path / record["notebook_log_path"]).exists()

    source_notebook = nbformat.read(notebook_path, as_version=4)
    code_cell = source_notebook.cells[1]
    assert code_cell.execution_count is None
    assert code_cell.outputs == []

    payload = json.loads((tmp_path / report["report_json_path"]).read_text(encoding="utf-8"))
    assert payload["status"] == "success"
