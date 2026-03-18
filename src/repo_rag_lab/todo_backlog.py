"""Shared backlog rendering helpers for Markdown and LaTeX surfaces."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import yaml

DEFAULT_REPOSITORY_WEB_BASE = (
    "https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/blob/master"
)
TODO_SOURCE_PATH = Path("todo-backlog.yaml")
TODO_MARKDOWN_PATH = Path("TODO.MD")
TODO_LATEX_PATH = Path("publication/todo-backlog-table.tex")

LATEX_ICON_BY_EMOJI = {
    "🧠": r"\ding{72}",
    "🛠": r"\ding{46}",
    "📓": r"\ding{45}",
    "🔎": r"\ding{108}",
    "🧪": r"\ding{115}",
    "🗺": r"\ding{43}",
    "📚": r"\ding{44}",
    "🧾": r"\ding{63}",
    "📝": r"\ding{54}",
    "🚦": r"\ding{118}",
    "🧭": r"\ding{71}",
    "📦": r"\ding{111}",
    "🦀": r"\ding{76}",
    "🧹": r"\ding{33}",
}

LATEX_ESCAPE_TABLE = str.maketrans(
    {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
)


@dataclass(frozen=True)
class TodoSurface:
    """A repository surface linked from the backlog."""

    path: str
    label: str


@dataclass(frozen=True)
class TodoItem:
    """A single backlog row."""

    emoji: str
    area: str
    task: str
    surfaces: tuple[TodoSurface, ...]
    done_when: tuple[str, ...]


def _coerce_surface(entry: object) -> TodoSurface:
    if isinstance(entry, str):
        return TodoSurface(path=entry, label=entry)

    if not isinstance(entry, dict):
        raise TypeError(f"Unsupported surface entry: {entry!r}")

    path = str(entry["path"])
    label = str(entry.get("label", path))
    return TodoSurface(path=path, label=label)


def load_todo_backlog(root: Path) -> tuple[str, tuple[TodoItem, ...]]:
    """Load the structured backlog definition from ``root``."""

    payload = yaml.safe_load((root / TODO_SOURCE_PATH).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("todo-backlog.yaml must contain a mapping.")

    repository_web_base = str(payload.get("repository_web_base", DEFAULT_REPOSITORY_WEB_BASE))
    items_payload = payload.get("items", [])
    if not isinstance(items_payload, list):
        raise TypeError("todo-backlog.yaml items must be a list.")

    items: list[TodoItem] = []
    for item_payload in items_payload:
        if not isinstance(item_payload, dict):
            raise TypeError(f"Unsupported todo item: {item_payload!r}")

        surfaces = tuple(_coerce_surface(entry) for entry in item_payload.get("surfaces", []))
        done_when = tuple(str(step) for step in item_payload.get("done_when", []))
        items.append(
            TodoItem(
                emoji=str(item_payload["emoji"]),
                area=str(item_payload["area"]),
                task=str(item_payload["task"]),
                surfaces=surfaces,
                done_when=done_when,
            )
        )

    return repository_web_base, tuple(items)


def _escape_markdown_cell(text: str) -> str:
    return " ".join(text.replace("|", r"\|").splitlines())


def _escape_latex(text: str) -> str:
    return text.translate(LATEX_ESCAPE_TABLE)


def _markdown_link(surface: TodoSurface) -> str:
    return f"[{surface.label}]({surface.path})"


def _latex_link(surface: TodoSurface, repository_web_base: str) -> str:
    encoded_path = quote(surface.path, safe="/._-")
    label = _escape_latex(surface.label)
    base_url = repository_web_base
    if surface.path.endswith("/"):
        base_url = repository_web_base.replace("/blob/", "/tree/", 1)
    return rf"\href{{{base_url}/{encoded_path}}}{{\texttt{{{label}}}}}"


def _join_markdown_lines(lines: tuple[str, ...]) -> str:
    return "<br>".join(lines)


def _join_latex_lines(lines: tuple[str, ...]) -> str:
    return r"\newline ".join(lines)


def render_markdown_backlog(items: tuple[TodoItem, ...]) -> str:
    """Render the backlog as a linkified Markdown table."""

    lines = [
        "# TODO",
        "",
        (
            "This backlog is generated from [todo-backlog.yaml](todo-backlog.yaml) via "
            "`make todo-sync`."
        ),
        "",
        "| 🎯 | 🧭 Area | 📌 TODO | 🔗 Primary Surfaces | ✅ Done When |",
        "| --- | --- | --- | --- | --- |",
    ]

    for item in items:
        surfaces = _join_markdown_lines(tuple(_markdown_link(surface) for surface in item.surfaces))
        done_when = _join_markdown_lines(
            tuple(_escape_markdown_cell(step) for step in item.done_when)
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    item.emoji,
                    _escape_markdown_cell(item.area),
                    _escape_markdown_cell(item.task),
                    surfaces,
                    done_when,
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "Edit `todo-backlog.yaml`, then run `make todo-sync` to refresh this table and the",
            "publication-ready LaTeX include.",
        ]
    )
    return "\n".join(lines)


def render_latex_backlog(repository_web_base: str, items: tuple[TodoItem, ...]) -> str:
    """Render the backlog as a LaTeX longtable for the publication article."""

    header_row = (
        r"\rowcolor{PaperNavy}"
        r"\color{white}\textbf{Badge} & "
        r"\color{white}\textbf{Area} & "
        r"\color{white}\textbf{TODO} & "
        r"\color{white}\textbf{Linked surfaces} & "
        r"\color{white}\textbf{Done when} \\"
    )

    lines = [
        "% Generated by repo-rag sync-todo-backlog. Do not edit manually.",
        r"\begingroup",
        r"\small",
        r"\renewcommand{\arraystretch}{1.18}",
        r"\rowcolors{2}{PaperMist}{white}",
        (
            r"\begin{longtable}{>{\raggedright\arraybackslash}p{0.08\linewidth} "
            r">{\raggedright\arraybackslash}p{0.17\linewidth} "
            r">{\raggedright\arraybackslash}p{0.23\linewidth} "
            r">{\raggedright\arraybackslash}p{0.22\linewidth} "
            r">{\raggedright\arraybackslash}p{0.22\linewidth}}"
        ),
        r"\toprule",
        header_row,
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        header_row,
        r"\midrule",
        r"\endhead",
        r"\midrule",
        r"\multicolumn{5}{r}{\footnotesize\itshape Continued on the next page.} \\",
        r"\endfoot",
        r"\bottomrule",
        r"\endlastfoot",
    ]

    for item in items:
        surfaces = _join_latex_lines(
            tuple(_latex_link(surface, repository_web_base) for surface in item.surfaces)
        )
        done_when = _join_latex_lines(tuple(_escape_latex(step) for step in item.done_when))
        lines.append(
            " & ".join(
                [
                    LATEX_ICON_BY_EMOJI.get(item.emoji, r"\textbullet"),
                    _escape_latex(item.area),
                    _escape_latex(item.task),
                    surfaces,
                    done_when,
                ]
            )
            + r" \\"
        )
    lines.extend([r"\end{longtable}", r"\endgroup"])
    return "\n".join(lines)


def sync_todo_backlog(root: Path) -> dict[str, object]:
    """Write the generated Markdown and LaTeX backlog surfaces under ``root``."""

    repository_web_base, items = load_todo_backlog(root)
    missing_paths = sorted(
        {
            surface.path
            for item in items
            for surface in item.surfaces
            if not (root / surface.path).exists()
        }
    )
    if missing_paths:
        missing_json = json.dumps(missing_paths)
        raise FileNotFoundError(f"Todo backlog surfaces do not exist: {missing_json}")

    markdown_text = render_markdown_backlog(items)
    latex_text = render_latex_backlog(repository_web_base, items)
    (root / TODO_MARKDOWN_PATH).write_text(markdown_text + "\n", encoding="utf-8")
    (root / TODO_LATEX_PATH).write_text(latex_text + "\n", encoding="utf-8")
    return {
        "source_path": str(TODO_SOURCE_PATH),
        "markdown_path": str(TODO_MARKDOWN_PATH),
        "latex_path": str(TODO_LATEX_PATH),
        "item_count": len(items),
        "repository_web_base": repository_web_base,
    }
