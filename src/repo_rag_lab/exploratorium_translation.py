"""Generate the bilingual exploratorium translation publication surfaces."""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import nbformat

EXPLORATORIUM_DIR = Path("publication/exploratorium_translation")
EXPLORATORIUM_MAIN_TEX_PATH = EXPLORATORIUM_DIR / "exploratorium_translation.tex"
EXPLORATORIUM_PDF_PATH = EXPLORATORIUM_DIR / "exploratorium_translation.pdf"
EXPLORATORIUM_GENERATED_DIR = EXPLORATORIUM_DIR / "generated"
EXPLORATORIUM_TEX_PATH = EXPLORATORIUM_GENERATED_DIR / "exploratorium-content.tex"
EXPLORATORIUM_MANIFEST_PATH = EXPLORATORIUM_GENERATED_DIR / "exploratorium-manifest.json"
REFERENCES_BIB_PATH = Path("publication/references.bib")
FILE_SUMMARY_EXCLUDED_PATHS = {
    str(EXPLORATORIUM_TEX_PATH),
    str(EXPLORATORIUM_MANIFEST_PATH),
    str(EXPLORATORIUM_PDF_PATH),
}
LINK_SCAN_EXCLUDED_PATHS = {
    "uv.lock",
}
LINK_SCAN_EXCLUDED_PREFIXES = (
    "samples/logs/",
    "publication/exploratorium_translation/generated/",
)
FALLBACK_EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "artifacts",
    "dist",
    "publication/.build",
    "publication/exploratorium_translation/.build",
}
TEXT_EXTENSIONS = {
    "",
    ".bib",
    ".c",
    ".feature",
    ".h",
    ".ipynb",
    ".json",
    ".log",
    ".md",
    ".py",
    ".rs",
    ".tex",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
SPECIAL_TEXT_FILENAMES = {
    ".env.sample",
    ".gitignore",
    ".python-version",
    ".yamllint.yml",
    "AGENTS.md",
    "Makefile",
    "VERSION",
}
URL_PATTERN = re.compile(r"https?://[^\s<>{}\\|\"']+")
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
REFERENCE_COMPANION_PATHS = {
    "lewis2020rag": (
        "README.DSPY.MD",
        "documentation/inspired/implementing-rag-with-dspy-technical-guide.md",
    ),
    "khattab2024dspy": (
        "README.DSPY.MD",
        "documentation/inspired/dspy-rag-tutorial.md",
        "documentation/hushwheel-fixture-rag-guide.md",
    ),
    "mcp2024": ("documentation/mcp-discovery.md",),
    "azureinference2025": ("documentation/azure-deployment.md",),
}
URL_COMPANION_PATHS = {
    "learn.microsoft.com": ("documentation/azure-deployment.md",),
    "modelcontextprotocol.io": ("documentation/mcp-discovery.md",),
    "astral.sh": ("README.md",),
}
REPO_REMOTE = "github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1"


@dataclass(frozen=True)
class FileSummary:
    """A compact bilingual description of one tracked file."""

    path: str
    kind: str
    byte_size: int
    line_count: int | None
    url_count: int
    summary_en: str
    summary_ru: str


@dataclass(frozen=True)
class LinkSummary:
    """A compact bilingual description of one explicit project URL."""

    url: str
    host: str
    source_paths: tuple[str, ...]
    occurrence_count: int
    fetch_state_en: str
    fetch_state_ru: str


@dataclass(frozen=True)
class ReferenceFetchState:
    """One bibliography entry and the repository's local fetch state for it."""

    key: str
    kind: str
    title: str
    related_paths: tuple[str, ...]
    state_en: str
    state_ru: str


@dataclass(frozen=True)
class ExploratoriumInventory:
    """The generated repository inventory for the exploratorium document."""

    generated_at: str
    tracked_file_count: int
    summarized_file_count: int
    excluded_generated_file_count: int
    explicit_link_count: int
    machine_link_occurrence_count: int
    machine_link_unique_count: int
    bibliography_entry_count: int
    local_documentation_count: int
    file_summaries: tuple[FileSummary, ...]
    link_summaries: tuple[LinkSummary, ...]
    reference_fetch_states: tuple[ReferenceFetchState, ...]


def _iso_utc_now() -> str:
    """Return the current UTC time in a stable ISO-8601 form."""

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _escape_latex(text: str) -> str:
    """Escape plain text so it is safe inside LaTeX prose."""

    return text.translate(LATEX_ESCAPE_TABLE)


def _escape_url_for_latex(url: str) -> str:
    """Escape percent signs while leaving the URL otherwise intact."""

    return url.replace("%", r"\%")


def _repo_relative(path: Path, root: Path) -> str:
    """Convert ``path`` to a repository-relative string."""

    return str(path.relative_to(root))


def _is_text_path(path: Path) -> bool:
    """Return whether ``path`` should be treated as a human-readable text surface."""

    if path.name in SPECIAL_TEXT_FILENAMES:
        return True
    return path.suffix.lower() in TEXT_EXTENSIONS


def _trim_url(raw_url: str) -> str:
    """Strip common trailing punctuation from a detected URL."""

    trimmed = raw_url.rstrip(".,;:")
    while trimmed.endswith(")") and trimmed.count("(") < trimmed.count(")"):
        trimmed = trimmed[:-1]
    return trimmed


def _extract_urls(text: str) -> tuple[str, ...]:
    """Extract and normalize explicit URLs from ``text``."""

    return tuple(_trim_url(match.group(0)) for match in URL_PATTERN.finditer(text))


def _read_text(path: Path) -> str:
    """Read a text file using UTF-8 with replacement for invalid bytes."""

    return path.read_text(encoding="utf-8", errors="replace")


def _read_text_preview(path: Path, *, max_chars: int = 6000) -> str:
    """Read a preview slice from ``path`` for lightweight heuristics."""

    return _read_text(path)[:max_chars]


def _first_heading(text: str) -> str | None:
    """Return the first Markdown heading found in ``text``."""

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return None


def _first_nonempty_line(text: str) -> str | None:
    """Return the first non-empty line found in ``text``."""

    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _python_docstring(text: str) -> str | None:
    """Return the first top-level Python docstring line when present."""

    match = re.search(r'^\s*(?:"""|\'\'\')(?P<body>.*?)(?:"""|\'\'\')', text, re.S)
    if match is None:
        return None
    body = match.group("body").strip().splitlines()
    return body[0].strip() if body else None


def _count_lines(path: Path) -> int | None:
    """Return the line count for a text file or ``None`` for binary files."""

    if not _is_text_path(path):
        return None
    return _read_text(path).count("\n") + 1


def _json_top_keys(path: Path) -> tuple[str, ...]:
    """Return the top-level keys for a JSON file when it is an object."""

    try:
        payload = json.loads(_read_text(path))
    except json.JSONDecodeError:
        return ()
    if isinstance(payload, dict):
        return tuple(str(key) for key in list(payload.keys())[:3])
    return ()


def _toml_top_keys(path: Path) -> tuple[str, ...]:
    """Return the top-level keys for a TOML file when it is an object."""

    try:
        payload = tomllib.loads(_read_text(path))
    except tomllib.TOMLDecodeError:
        return ()
    return tuple(str(key) for key in list(payload.keys())[:3])


def _yaml_top_keys(path: Path) -> tuple[str, ...]:
    """Return the top-level keys for a YAML file when it is a mapping."""

    import yaml

    try:
        payload = yaml.safe_load(_read_text(path))
    except yaml.YAMLError:
        return ()
    if isinstance(payload, dict):
        return tuple(str(key) for key in list(payload.keys())[:3])
    return ()


def _notebook_heading_and_count(path: Path) -> tuple[str | None, int]:
    """Return the first notebook heading and the total cell count."""

    notebook = nbformat.read(path, as_version=4)
    for cell in notebook.cells:
        if cell.cell_type == "markdown":
            heading = _first_heading(cell.source)
            if heading is not None:
                return heading, len(notebook.cells)
    return None, len(notebook.cells)


def _bib_entry_count(text: str) -> int:
    """Count the BibTeX entries in a bibliography file."""

    return len(re.findall(r"^@\w+\{", text, re.M))


def _summarize_file(root: Path, relative_path: str) -> FileSummary:
    """Summarize one tracked file in English and Russian."""

    path = root / relative_path
    byte_size = path.stat().st_size
    line_count = _count_lines(path)
    url_count = len(_extract_urls(_read_text(path))) if _is_text_path(path) else 0
    preview = _read_text_preview(path) if _is_text_path(path) else ""
    suffix = path.suffix.lower()
    line_detail_en = (
        f"{line_count} lines" if line_count is not None else f"{byte_size} bytes of binary data"
    )
    line_detail_ru = (
        f"{line_count} строк" if line_count is not None else f"{byte_size} байт бинарных данных"
    )

    if path.name == "Makefile":
        summary_en = (
            f"Repository Makefile, {line_detail_en}, {url_count} explicit URLs. "
            "It exposes the shared automation surfaces."
        )
        summary_ru = (
            f"Makefile репозитория, {line_detail_ru}, явных URL: {url_count}. "
            "Он открывает общие поверхности автоматизации."
        )
        kind = "make"
    elif suffix == ".md":
        heading = _first_heading(preview) or path.stem.replace("-", " ").replace("_", " ")
        summary_en = (
            f"Markdown document, {line_detail_en}, {url_count} explicit URLs. "
            f"Lead heading: {heading}."
        )
        summary_ru = (
            f"Документ Markdown, {line_detail_ru}, явных URL: {url_count}. "
            f"Главный заголовок: {heading}."
        )
        kind = "markdown"
    elif suffix == ".py":
        docstring = _python_docstring(preview) or "No module docstring detected."
        summary_en = (
            f"Python module, {line_detail_en}, {url_count} explicit URLs. "
            f"Module intent: {docstring}"
        )
        summary_ru = (
            f"Модуль Python, {line_detail_ru}, явных URL: {url_count}. "
            f"Назначение модуля: {docstring}"
        )
        kind = "python"
    elif suffix == ".ipynb":
        notebook_heading, cell_count = _notebook_heading_and_count(path)
        summary_en = (
            f"Notebook, {cell_count} cells, {url_count} explicit URLs. "
            f"Opening heading: {notebook_heading or 'none'}."
        )
        summary_ru = (
            f"Ноутбук, {cell_count} ячеек, явных URL: {url_count}. "
            f"Первый заголовок: {notebook_heading or 'нет'}."
        )
        kind = "notebook"
    elif suffix in {".yaml", ".yml"}:
        keys = ", ".join(_yaml_top_keys(path)) or "no top-level mapping keys"
        summary_en = (
            f"YAML data or workflow file, {line_detail_en}, {url_count} explicit URLs. "
            f"Top keys: {keys}."
        )
        summary_ru = (
            f"Файл YAML с данными или workflow, {line_detail_ru}, явных URL: {url_count}. "  # noqa: RUF001
            f"Верхние ключи: {keys}."
        )
        kind = "yaml"
    elif suffix == ".toml":
        keys = ", ".join(_toml_top_keys(path)) or "no top-level tables"
        summary_en = (
            f"TOML configuration file, {line_detail_en}, {url_count} explicit URLs. "
            f"Top keys: {keys}."
        )
        summary_ru = (
            f"Конфигурация TOML, {line_detail_ru}, явных URL: {url_count}. Верхние ключи: {keys}."
        )
        kind = "toml"
    elif suffix == ".json":
        keys = ", ".join(_json_top_keys(path)) or "non-object JSON payload"
        summary_en = (
            f"JSON data file, {line_detail_en}, {url_count} explicit URLs. Top keys: {keys}."
        )
        summary_ru = f"Файл JSON, {line_detail_ru}, явных URL: {url_count}. Верхние ключи: {keys}."
        kind = "json"
    elif suffix == ".tex":
        section_count = len(re.findall(r"\\section", preview))
        summary_en = (
            f"LaTeX source, {line_detail_en}, {url_count} explicit URLs. "
            f"Sections declared in preview: {section_count}."
        )
        summary_ru = (
            f"Исходник LaTeX, {line_detail_ru}, явных URL: {url_count}. "
            f"Секций в превью: {section_count}."
        )
        kind = "latex"
    elif suffix == ".bib":
        entry_count = _bib_entry_count(preview)
        summary_en = (
            f"Bibliography file, {line_detail_en}, {url_count} explicit URLs. "
            f"Entries counted in preview: {entry_count}."
        )
        summary_ru = (
            f"Библиографический файл, {line_detail_ru}, явных URL: {url_count}. "
            f"Записей в превью: {entry_count}."
        )
        kind = "bibliography"
    elif suffix in {".c", ".h", ".rs"}:
        first_line = _first_nonempty_line(preview) or "No non-empty preview line."
        summary_en = (
            f"Source file, {line_detail_en}, {url_count} explicit URLs. Opening line: {first_line}"
        )
        summary_ru = (
            f"Исходный файл, {line_detail_ru}, явных URL: {url_count}. Первая строка: {first_line}"
        )
        kind = "source"
    elif suffix in {".png", ".pdf"}:
        summary_en = f"Binary asset, {line_detail_en}. It is tracked for stable publication output."
        summary_ru = (
            f"Бинарный артефакт, {line_detail_ru}. Он хранится в Git "
            "для стабильного публикационного вывода."
        )
        kind = "binary"
    else:
        first_line = _first_nonempty_line(preview) or "No non-empty preview line."
        summary_en = (
            f"Tracked repository file, {line_detail_en}, {url_count} explicit URLs. "
            f"Opening line: {first_line}"
        )
        summary_ru = (
            f"Отслеживаемый файл репозитория, {line_detail_ru}, явных URL: {url_count}. "
            f"Первая строка: {first_line}"
        )
        kind = "generic"

    return FileSummary(
        path=relative_path,
        kind=kind,
        byte_size=byte_size,
        line_count=line_count,
        url_count=url_count,
        summary_en=summary_en,
        summary_ru=summary_ru,
    )


def _companion_paths_for_url(url: str) -> tuple[str, ...]:
    """Return repository-local paths that explain or mirror ``url``."""

    parsed = urlparse(url)
    host = parsed.netloc
    if host == REPO_REMOTE:
        path = parsed.path.strip("/")
        prefix = "realagiorganization/dspy_rag_in_repo_docs_and_impl1/blob/master/"
        tree_prefix = "realagiorganization/dspy_rag_in_repo_docs_and_impl1/tree/master/"
        if path.startswith(prefix):
            return (path.removeprefix(prefix),)
        if path.startswith(tree_prefix):
            return (path.removeprefix(tree_prefix),)
        if path.endswith("/actions/workflows/ci.yml"):
            return (".github/workflows/ci.yml",)
        if path.endswith("/actions/workflows/publish.yml"):
            return (".github/workflows/publish.yml",)
        return ("README.md",)
    for companion_host, companion_paths in URL_COMPANION_PATHS.items():
        if host.endswith(companion_host):
            return companion_paths
    return ()


def _link_fetch_state(url: str, source_paths: tuple[str, ...]) -> tuple[str, str]:
    """Describe the repository-local fetch state for one URL."""

    parsed = urlparse(url)
    host = parsed.netloc
    companion_paths = _companion_paths_for_url(url)
    joined_companions = ", ".join(companion_paths) or "none"

    if host == REPO_REMOTE:
        return (
            f"Repository-hosted URL. Related local path(s): {joined_companions}.",
            f"URL репозитория. Связанные локальные пути: {joined_companions}.",
        )
    if host.endswith("learn.microsoft.com"):
        return (
            "External Azure documentation URL. No mirrored upstream copy is tracked, but "
            f"local companion notes exist at {joined_companions}.",
            "Внешний URL документации Azure. Зеркальная копия upstream не хранится, но есть "
            f"локальные сопроводительные заметки: {joined_companions}.",
        )
    if host.endswith("modelcontextprotocol.io"):
        return (
            "External MCP documentation URL. No mirrored upstream copy is tracked, but local "
            f"companion notes exist at {joined_companions}.",
            "Внешний URL документации MCP. Зеркальная копия upstream не хранится, но есть "
            f"локальные сопроводительные заметки: {joined_companions}.",
        )
    if host.endswith("github.com"):
        return (
            f"External GitHub URL referenced from {len(source_paths)} file(s). Local companion "
            f"path(s): {joined_companions}.",
            f"Внешний URL GitHub, упомянутый в {len(source_paths)} файле(ах). Локальные "  # noqa: RUF001
            f"сопроводительные пути: {joined_companions}.",
        )
    return (
        "Referenced by URL only. No repository-local mirror is currently tracked.",
        "Ссылка хранится только как URL. Локальное зеркало в репозитории сейчас не отслеживается.",
    )


def _summarize_links(
    root: Path, tracked_paths: tuple[str, ...]
) -> tuple[tuple[LinkSummary, ...], int, int]:
    """Collect unique authored URLs and machine-link counts."""

    link_occurrences: dict[str, list[str]] = {}
    machine_occurrences = 0
    machine_unique_urls: set[str] = set()

    for relative_path in tracked_paths:
        if relative_path in FILE_SUMMARY_EXCLUDED_PATHS:
            continue
        if relative_path in LINK_SCAN_EXCLUDED_PATHS:
            text = _read_text(root / relative_path)
            urls = _extract_urls(text)
            machine_occurrences += len(urls)
            machine_unique_urls.update(urls)
            continue
        if any(relative_path.startswith(prefix) for prefix in LINK_SCAN_EXCLUDED_PREFIXES):
            text = _read_text(root / relative_path)
            urls = _extract_urls(text)
            machine_occurrences += len(urls)
            machine_unique_urls.update(urls)
            continue
        path = root / relative_path
        if not _is_text_path(path):
            continue
        for url in _extract_urls(_read_text(path)):
            link_occurrences.setdefault(url, []).append(relative_path)

    summaries: list[LinkSummary] = []
    for url, source_paths in sorted(link_occurrences.items()):
        unique_sources = tuple(sorted(set(source_paths)))
        fetch_state_en, fetch_state_ru = _link_fetch_state(url, unique_sources)
        summaries.append(
            LinkSummary(
                url=url,
                host=urlparse(url).netloc,
                source_paths=unique_sources,
                occurrence_count=len(source_paths),
                fetch_state_en=fetch_state_en,
                fetch_state_ru=fetch_state_ru,
            )
        )

    return tuple(summaries), machine_occurrences, len(machine_unique_urls)


def _parse_bibliography_entries(text: str) -> tuple[dict[str, str], ...]:
    """Parse a small BibTeX file into simple field mappings."""

    entries: list[dict[str, str]] = []
    for match in re.finditer(r"@(?P<kind>\w+)\{(?P<key>[^,]+),(?P<body>.*?)\n\}", text, re.S):
        body = match.group("body")
        fields: dict[str, str] = {
            "kind": match.group("kind"),
            "key": match.group("key").strip(),
        }
        for field_match in re.finditer(
            r"(?P<field>\w+)\s*=\s*\{(?P<value>(?:[^{}]|\{[^{}]*\})*)\}",
            body,
            re.S,
        ):
            field = field_match.group("field").strip().lower()
            value = " ".join(field_match.group("value").replace("{", "").replace("}", "").split())
            fields[field] = value
        entries.append(fields)
    return tuple(entries)


def _summarize_reference_fetch_state(root: Path) -> tuple[ReferenceFetchState, ...]:
    """Describe the local fetch state for bibliography entries."""

    bib_text = _read_text(root / REFERENCES_BIB_PATH)
    states: list[ReferenceFetchState] = []
    for entry in _parse_bibliography_entries(bib_text):
        key = entry["key"]
        kind = entry["kind"]
        title = entry.get("title", key)
        related_paths = tuple(
            path for path in REFERENCE_COMPANION_PATHS.get(key, ()) if (root / path).exists()
        )
        if key in {"lewis2020rag", "khattab2024dspy"}:
            state_en = (
                "Cited in the bibliography, but no local PDF or paper mirror is tracked. "
                f"Closest local companion paths: {', '.join(related_paths) or 'none'}."
            )
            state_ru = (
                "Источник есть в библиографии, но локальный PDF или зеркало статьи не "
                f"отслеживаются. Ближайшие локальные сопроводительные пути: "
                f"{', '.join(related_paths) or 'нет'}."
            )
        else:
            state_en = (
                "External documentation is cited by URL. No mirrored upstream copy is tracked, "
                f"but local companion paths exist at {', '.join(related_paths) or 'none'}."
            )
            state_ru = (
                "Внешняя документация цитируется по URL. Зеркальная копия upstream не "
                f"отслеживается, но есть локальные сопроводительные пути: "
                f"{', '.join(related_paths) or 'нет'}."
            )
        states.append(
            ReferenceFetchState(
                key=key,
                kind=kind,
                title=title,
                related_paths=related_paths,
                state_en=state_en,
                state_ru=state_ru,
            )
        )
    return tuple(states)


def _tracked_files_from_git(root: Path) -> tuple[str, ...] | None:
    """Return tracked file paths from Git when the repository metadata is available."""

    if not (root / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        return None
    return tuple(path for path in result.stdout.splitlines() if path)


def _fallback_tracked_files(root: Path) -> tuple[str, ...]:
    """Walk ``root`` when Git metadata is unavailable."""

    tracked_paths: list[str] = []
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        relative_path = _repo_relative(path, root)
        if any(
            relative_path == prefix or relative_path.startswith(f"{prefix}/")
            for prefix in FALLBACK_EXCLUDED_DIRS
        ):
            continue
        tracked_paths.append(relative_path)
    return tuple(sorted(tracked_paths))


def collect_exploratorium_inventory(root: Path) -> ExploratoriumInventory:
    """Collect the current repository inventory for the exploratorium translation."""

    tracked_paths = _tracked_files_from_git(root) or _fallback_tracked_files(root)
    summarized_paths = tuple(
        path
        for path in tracked_paths
        if path not in FILE_SUMMARY_EXCLUDED_PATHS and (root / path).is_file()
    )
    file_summaries = tuple(_summarize_file(root, path) for path in summarized_paths)
    link_summaries, machine_occurrence_count, machine_unique_count = _summarize_links(
        root,
        tracked_paths,
    )
    reference_states = _summarize_reference_fetch_state(root)
    return ExploratoriumInventory(
        generated_at=_iso_utc_now(),
        tracked_file_count=len(tracked_paths),
        summarized_file_count=len(file_summaries),
        excluded_generated_file_count=len(tracked_paths) - len(file_summaries),
        explicit_link_count=len(link_summaries),
        machine_link_occurrence_count=machine_occurrence_count,
        machine_link_unique_count=machine_unique_count,
        bibliography_entry_count=len(reference_states),
        local_documentation_count=len(
            [path for path in (root / "documentation").rglob("*") if path.is_file()]
        ),
        file_summaries=file_summaries,
        link_summaries=link_summaries,
        reference_fetch_states=reference_states,
    )


def _render_side_by_side_rows(
    title_en: str, title_ru: str, rows: tuple[tuple[str, str], ...]
) -> list[str]:
    """Render one bilingual side-by-side longtable section."""

    lines = [
        rf"\subsection*{{{_escape_latex(title_en)} / {_escape_latex(title_ru)}}}",
        r"\begingroup",
        r"\small",
        r"\renewcommand{\arraystretch}{1.16}",
        (
            r"\begin{longtable}{>{\raggedright\arraybackslash}p{0.47\linewidth} "
            r">{\raggedright\arraybackslash}p{0.47\linewidth}}"
        ),
        r"\toprule",
        r"\textbf{English} & \textbf{Русский} \\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        r"\textbf{English} & \textbf{Русский} \\",
        r"\midrule",
        r"\endhead",
    ]
    for english, russian in rows:
        lines.append(f"{english} & {russian} \\\\")
    lines.extend([r"\bottomrule", r"\end{longtable}", r"\endgroup"])
    return lines


def _render_line_by_line_section(
    title_en: str, title_ru: str, rows: tuple[tuple[str, str], ...]
) -> list[str]:
    """Render one bilingual line-by-line section."""

    lines = [rf"\subsection*{{{_escape_latex(title_en)} / {_escape_latex(title_ru)}}}"]
    for english, russian in rows:
        lines.extend([english + r"\\", russian + r"\par\medskip"])
    return lines


def _render_page_by_page_language_section(title: str, rows: tuple[str, ...]) -> list[str]:
    """Render one monolingual page-by-page section."""

    lines = [rf"\subsection*{{{_escape_latex(title)}}}"]
    for row in rows:
        lines.extend([row + r"\par\medskip"])
    return lines


def _reference_rows(
    reference_states: tuple[ReferenceFetchState, ...],
) -> tuple[tuple[str, str], ...]:
    """Render bilingual reference-fetch state rows."""

    rows: list[tuple[str, str]] = []
    for state in reference_states:
        related = ", ".join(state.related_paths) or "none"
        rows.append(
            (
                rf"\textbf{{{_escape_latex(state.key)}}}: {_escape_latex(state.title)}. "
                rf"Kind: {_escape_latex(state.kind)}. {_escape_latex(state.state_en)} "
                rf"Related paths: \path{{{_escape_latex(related)}}}.",
                rf"\textbf{{{_escape_latex(state.key)}}}: {_escape_latex(state.title)}. "
                rf"Тип: {_escape_latex(state.kind)}. {_escape_latex(state.state_ru)} "
                rf"Связанные пути: \path{{{_escape_latex(related)}}}.",
            )
        )
    return tuple(rows)


def _file_rows(file_summaries: tuple[FileSummary, ...]) -> tuple[tuple[str, str], ...]:
    """Render bilingual file-summary rows."""

    rows: list[tuple[str, str]] = []
    for summary in file_summaries:
        line_count_en = (
            f"{summary.line_count} lines" if summary.line_count is not None else "binary surface"
        )
        line_count_ru = (
            f"{summary.line_count} строк"
            if summary.line_count is not None
            else "бинарная поверхность"
        )
        rows.append(
            (
                rf"\textbf{{\path{{{summary.path}}}}}. Kind: {_escape_latex(summary.kind)}. "
                rf"Size: {summary.byte_size} bytes. Shape: {_escape_latex(line_count_en)}. "
                rf"{_escape_latex(summary.summary_en)}",
                rf"\textbf{{\path{{{summary.path}}}}}. Тип: {_escape_latex(summary.kind)}. "
                rf"Размер: {summary.byte_size} байт. Форма: {_escape_latex(line_count_ru)}. "
                rf"{_escape_latex(summary.summary_ru)}",
            )
        )
    return tuple(rows)


def _link_rows(link_summaries: tuple[LinkSummary, ...]) -> tuple[tuple[str, str], ...]:
    """Render bilingual link-summary rows."""

    rows: list[tuple[str, str]] = []
    for summary in link_summaries:
        sources = r"\newline ".join(rf"\path{{{path}}}" for path in summary.source_paths)
        rows.append(
            (
                rf"\textbf{{\url{{{_escape_url_for_latex(summary.url)}}}}}. Host: "
                rf"{_escape_latex(summary.host)}. Occurrences: {summary.occurrence_count}. "
                rf"{_escape_latex(summary.fetch_state_en)} Sources: {sources}.",
                rf"\textbf{{\url{{{_escape_url_for_latex(summary.url)}}}}}. Хост: "
                rf"{_escape_latex(summary.host)}. Упоминаний: {summary.occurrence_count}. "
                rf"{_escape_latex(summary.fetch_state_ru)} Источники: {sources}.",
            )
        )
    return tuple(rows)


def render_exploratorium_latex(inventory: ExploratoriumInventory) -> str:
    """Render the generated LaTeX include for the exploratorium document."""

    reference_rows = _reference_rows(inventory.reference_fetch_states)
    file_rows = _file_rows(inventory.file_summaries)
    link_rows = _link_rows(inventory.link_summaries)
    english_reference_rows = tuple(row[0] for row in reference_rows)
    russian_reference_rows = tuple(row[1] for row in reference_rows)
    english_file_rows = tuple(row[0] for row in file_rows)
    russian_file_rows = tuple(row[1] for row in file_rows)
    english_link_rows = tuple(row[0] for row in link_rows)
    russian_link_rows = tuple(row[1] for row in link_rows)

    lines = [
        "% Generated by repo-rag sync-exploratorium-translation. Do not edit manually.",
        r"\section*{Repository Fetching State / Состояние загрузки источников}",
        (
            rf"Generated at \texttt{{{inventory.generated_at}}}. The repository currently tracks "
            rf"{inventory.summarized_file_count} summarized files, "
            rf"{inventory.explicit_link_count} authored explicit URL references, and "
            rf"{inventory.bibliography_entry_count} bibliography entries. "
            rf"The exploratorium excludes its own generated outputs "
            rf"({inventory.excluded_generated_file_count} tracked path(s)) "
            rf"to avoid recursive drift."
        ),
        (
            rf"\par\smallskip Сгенерировано в \texttt{{{inventory.generated_at}}}. Сейчас "
            rf"репозиторий содержит {inventory.summarized_file_count} суммаризированных файлов, "
            rf"{inventory.explicit_link_count} авторских явных URL и "
            rf"{inventory.bibliography_entry_count} библиографических записей. "
            rf"Сам exploratorium исключает собственные сгенерированные выходы "
            rf"({inventory.excluded_generated_file_count} путей), чтобы не раздувать рекурсию."
        ),
        (
            rf"\par\smallskip Machine-generated link surfaces excluded from the authored "
            rf"link table: "
            rf"{inventory.machine_link_occurrence_count} URL occurrences "
            rf"({inventory.machine_link_unique_count} unique URLs), mostly from lockfiles "
            rf"or raw logs."
        ),
        (
            rf"\par\smallskip Машинно-сгенерированные ссылки, исключенные из авторской таблицы: "
            rf"{inventory.machine_link_occurrence_count} вхождений URL "
            rf"({inventory.machine_link_unique_count} уникальных URL), в основном из lockfile "
            rf"или сырых логов."
        ),
        r"\section{Side-By-Side / Параллельный показ}",
    ]
    lines.extend(
        _render_side_by_side_rows(
            "Referenced Papers And Documentation Fetch State",
            "Состояние загрузки статей и документации",
            reference_rows,
        )
    )
    lines.extend(
        _render_side_by_side_rows(
            "Summaries Of All Files",
            "Сводки по всем файлам",
            file_rows,
        )
    )
    lines.extend(
        _render_side_by_side_rows(
            "Summaries Of All Authored URLs",
            "Сводки по всем авторским URL",
            link_rows,
        )
    )
    lines.append(r"\section{Line-By-Line / Построчный показ}")
    lines.extend(
        _render_line_by_line_section(
            "Referenced Papers And Documentation Fetch State",
            "Состояние загрузки статей и документации",
            reference_rows,
        )
    )
    lines.extend(
        _render_line_by_line_section(
            "Summaries Of All Files",
            "Сводки по всем файлам",
            file_rows,
        )
    )
    lines.extend(
        _render_line_by_line_section(
            "Summaries Of All Authored URLs",
            "Сводки по всем авторским URL",
            link_rows,
        )
    )
    lines.append(r"\section{Page-By-Page / Постраничный показ}")
    lines.extend(
        _render_page_by_page_language_section(
            "English: Referenced Papers And Documentation Fetch State",
            english_reference_rows,
        )
    )
    lines.extend(
        _render_page_by_page_language_section(
            "English: Summaries Of All Files",
            english_file_rows,
        )
    )
    lines.extend(
        _render_page_by_page_language_section(
            "English: Summaries Of All Authored URLs",
            english_link_rows,
        )
    )
    lines.append(r"\newpage")
    lines.extend(
        _render_page_by_page_language_section(
            "Русский: Состояние загрузки статей и документации",
            russian_reference_rows,
        )
    )
    lines.extend(
        _render_page_by_page_language_section(
            "Русский: Сводки по всем файлам",
            russian_file_rows,
        )
    )
    lines.extend(
        _render_page_by_page_language_section(
            "Русский: Сводки по всем авторским URL",
            russian_link_rows,
        )
    )
    return "\n".join(lines) + "\n"


def sync_exploratorium_translation(root: Path) -> dict[str, object]:
    """Write the generated exploratorium manifest and LaTeX include under ``root``."""

    inventory = collect_exploratorium_inventory(root)
    generated_dir = root / EXPLORATORIUM_GENERATED_DIR
    generated_dir.mkdir(parents=True, exist_ok=True)
    (root / EXPLORATORIUM_TEX_PATH).write_text(
        render_exploratorium_latex(inventory),
        encoding="utf-8",
    )
    manifest_payload = asdict(inventory)
    (root / EXPLORATORIUM_MANIFEST_PATH).write_text(
        json.dumps(manifest_payload, indent=2),
        encoding="utf-8",
    )
    return {
        "tex_path": str(EXPLORATORIUM_TEX_PATH),
        "manifest_path": str(EXPLORATORIUM_MANIFEST_PATH),
        "main_tex_path": str(EXPLORATORIUM_MAIN_TEX_PATH),
        "pdf_path": str(EXPLORATORIUM_PDF_PATH),
        "summarized_file_count": inventory.summarized_file_count,
        "explicit_link_count": inventory.explicit_link_count,
        "bibliography_entry_count": inventory.bibliography_entry_count,
        "machine_link_occurrence_count": inventory.machine_link_occurrence_count,
    }
