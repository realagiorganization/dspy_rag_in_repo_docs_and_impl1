"""Generate tracked repository file-summary surfaces."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

MARKDOWN_OUTPUT_PATH = Path("FILES.md")
CSV_OUTPUT_PATH = Path("FILES.csv")
GUIDE_PATH = Path("AGENTS.md.d/FILES.md")
TEXT_KINDS = {
    "bibtex",
    "csv",
    "gherkin",
    "json",
    "latex",
    "lockfile",
    "makefile",
    "markdown",
    "notebook",
    "python",
    "rust",
    "text",
    "toml",
    "yaml",
}


@dataclass(frozen=True)
class FileSummaryRow:
    """One generated file-summary row."""

    path: str
    top_level: str
    kind: str
    line_count: int | None
    size_bytes: int
    summary: str


def _tracked_paths(root: Path) -> tuple[Path, ...]:
    """Return tracked paths from the Git index under ``root``."""

    git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    result = subprocess.run(
        ["git", "ls-files", "--cached", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
        env=git_env,
    )
    return tuple(
        Path(fragment.decode("utf-8")) for fragment in result.stdout.split(b"\0") if fragment
    )


def _classify_kind(path: Path) -> str:
    if path.name == "Makefile":
        return "makefile"
    if path.suffix == ".md":
        return "markdown"
    if path.suffix == ".py":
        return "python"
    if path.suffix == ".ipynb":
        return "notebook"
    if path.suffix in {".yaml", ".yml"}:
        return "yaml"
    if path.suffix == ".json":
        return "json"
    if path.suffix == ".toml":
        return "toml"
    if path.suffix == ".tex":
        return "latex"
    if path.suffix == ".bib":
        return "bibtex"
    if path.suffix == ".csv":
        return "csv"
    if path.suffix == ".feature":
        return "gherkin"
    if path.suffix == ".lock":
        return "lockfile"
    if path.suffix == ".rs":
        return "rust"
    return "text" if path.suffix in {".txt", ""} else "binary"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _first_content_line(text: str) -> str | None:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line in {"---", "```", "```bash", "```python", "```yaml"}:
            continue
        return line.lstrip("#/").strip()
    return None


def _notebook_heading(text: str) -> str | None:
    try:
        notebook = json.loads(text)
    except json.JSONDecodeError:
        return None
    cells = notebook.get("cells", [])
    if not isinstance(cells, list):
        return None
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("cell_type") != "markdown":
            continue
        source = cell.get("source", "")
        if isinstance(source, list):
            source_text = "".join(item for item in source if isinstance(item, str))
        elif isinstance(source, str):
            source_text = source
        else:
            continue
        heading = _first_content_line(source_text)
        if heading is not None:
            return heading
    return None


def _python_docstring(text: str) -> str | None:
    marker = '"""'
    if marker not in text:
        return None
    prefix, _, remainder = text.partition(marker)
    if prefix.strip():
        return None
    body, _, _ = remainder.partition(marker)
    first_line = body.strip().splitlines()
    return first_line[0].strip() if first_line else None


def summarize_path(root: Path, path: Path, kind: str) -> str:
    """Create a compact human summary for one tracked file."""

    relative = path.as_posix()
    if relative == "AGENTS.md":
        return "Repository-wide agent workflow, utility, and verification instructions"
    if relative == "README.md":
        return "Top-level repository overview, workflow map, and quality guidance"
    if relative == "README.AGENTS.md":
        return "Repository research narrative tying code, docs, and verification together"
    if relative == "README.DSPY.MD":
        return "DSPy workflow guide for training, runtime use, and compiled programs"
    if relative == GUIDE_PATH.as_posix():
        return "Agent instructions for maintaining FILES.md and FILES.csv"
    if path.parts[:2] == (".github", "workflows"):
        return f"GitHub Actions workflow for {path.stem.replace('-', ' ')}"
    if path.parts[:2] == ("docs", "audit"):
        return f"Repository audit note for {path.stem.replace('-', ' ')}"

    absolute_path = root / path
    if kind not in TEXT_KINDS:
        return f"Binary tracked asset at {relative}"

    text = _read_text(absolute_path)
    if kind == "python":
        return _python_docstring(text) or f"Python module for {path.stem.replace('_', ' ')}"
    if kind == "notebook":
        return _notebook_heading(text) or f"Notebook playbook for {path.stem.replace('_', ' ')}"
    if kind == "markdown":
        return _first_content_line(text) or f"Markdown document for {path.stem.replace('_', ' ')}"
    if kind == "json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return f"JSON data for {path.stem.replace('_', ' ')}"
        if isinstance(payload, dict):
            return "JSON object with keys: " + ", ".join(str(key) for key in list(payload)[:3])
    return _first_content_line(text) or f"Tracked {kind} file at {relative}"


def build_rows(root: Path) -> tuple[FileSummaryRow, ...]:
    """Build summary rows for all tracked files under ``root``."""

    rows: list[FileSummaryRow] = []
    for path in _tracked_paths(root):
        kind = _classify_kind(path)
        absolute_path = root / path
        if path in {MARKDOWN_OUTPUT_PATH, CSV_OUTPUT_PATH}:
            line_count = None
            size_bytes = 0
        elif kind in TEXT_KINDS:
            text = _read_text(absolute_path)
            line_count = text.count("\n") + 1
            size_bytes = absolute_path.stat().st_size
        else:
            line_count = None
            size_bytes = absolute_path.stat().st_size
        rows.append(
            FileSummaryRow(
                path=path.as_posix(),
                top_level=path.parts[0] if path.parts else "root",
                kind=kind,
                line_count=line_count,
                size_bytes=size_bytes,
                summary=summarize_path(root, path, kind),
            )
        )
    return tuple(rows)


def render_markdown(rows: tuple[FileSummaryRow, ...]) -> str:
    """Render the human-readable Markdown inventory."""

    lines = [
        (
            "<!-- Generated by uv run python -m repo_rag_lab.file_summaries --root . "
            "Do not edit manually. -->"
        ),
        "# Repository File Inventory",
        "",
        "This inventory is generated from the current Git index.",
        "",
        "| Path | Top Level | Kind | Lines | Bytes | Summary |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for row in rows:
        line_count = "" if row.line_count is None else str(row.line_count)
        lines.append(
            f"| `{row.path}` | {row.top_level} | {row.kind} | {line_count} | "
            f"{row.size_bytes} | {row.summary} |"
        )
    lines.extend(
        [
            "",
            "Run `uv run python -m repo_rag_lab.file_summaries --root .` after tracked file",
            "changes so this table and `FILES.csv` stay aligned.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_csv(rows: tuple[FileSummaryRow, ...]) -> str:
    """Render the script-friendly CSV inventory."""

    stream = StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["path", "top_level", "kind", "line_count", "bytes", "summary"])
    for row in rows:
        writer.writerow(
            [
                row.path,
                row.top_level,
                row.kind,
                "" if row.line_count is None else str(row.line_count),
                str(row.size_bytes),
                row.summary,
            ]
        )
    return stream.getvalue()


def sync_file_summaries(root: Path) -> dict[str, object]:
    """Write FILES.md and FILES.csv under ``root`` and return the output metadata."""

    rows = build_rows(root)
    (root / MARKDOWN_OUTPUT_PATH).write_text(render_markdown(rows), encoding="utf-8")
    (root / CSV_OUTPUT_PATH).write_text(render_csv(rows), encoding="utf-8")
    return {
        "tracked_file_count": len(rows),
        "markdown_path": MARKDOWN_OUTPUT_PATH.as_posix(),
        "csv_path": CSV_OUTPUT_PATH.as_posix(),
        "guide_path": GUIDE_PATH.as_posix(),
    }


def check_outputs(root: Path) -> int:
    """Return ``0`` when FILES outputs match the current tracked-file snapshot."""

    rows = build_rows(root)
    expected_markdown = render_markdown(rows)
    expected_csv = render_csv(rows)
    problems: list[str] = []
    for relative_path, expected in (
        (MARKDOWN_OUTPUT_PATH, expected_markdown),
        (CSV_OUTPUT_PATH, expected_csv),
    ):
        absolute_path = root / relative_path
        if not absolute_path.exists():
            problems.append(f"missing {relative_path.as_posix()}")
            continue
        if absolute_path.read_text(encoding="utf-8") != expected:
            problems.append(f"stale {relative_path.as_posix()}")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the file-summary module."""

    parser = argparse.ArgumentParser(prog="python -m repo_rag_lab.file_summaries")
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true")
    return parser


def main() -> int:
    """Run the file-summary generator or freshness check."""

    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    if args.check:
        return check_outputs(root)
    print(json.dumps(sync_file_summaries(root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
