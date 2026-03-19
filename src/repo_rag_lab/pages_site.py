"""Generate a MkDocs-ready catalog of tracked repository Markdown files."""

from __future__ import annotations

import json
import posixpath
import re
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

DEFAULT_PAGES_DOCS_DIR = Path("artifacts/pages_docs")
MARKDOWN_EXTENSIONS = {".md", ".MD"}
MARKDOWN_IMAGE_PATTERN = re.compile(
    r"(?P<prefix>!\[(?:[^\[\]]|\[[^\]]*\])*\]\()(?P<target>[^)]+)(?P<suffix>\))"
)
MARKDOWN_LINK_PATTERN = re.compile(
    r"(?P<prefix>\[(?:[^\[\]]|\[[^\]]*\])*\]\()(?P<target>[^)]+)(?P<suffix>\))"
)


@dataclass(frozen=True)
class MarkdownSitePage:
    """Metadata for one tracked Markdown page mirrored into the Pages site."""

    source_path: PurePosixPath
    site_path: PurePosixPath
    top_level: str
    title: str


def _run_command(root: Path, args: list[str]) -> str:
    completed = subprocess.run(
        args,
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _tracked_markdown_paths(root: Path) -> list[PurePosixPath]:
    stdout = _run_command(root, ["git", "ls-files"])
    tracked_paths = [
        PurePosixPath(line.strip())
        for line in stdout.splitlines()
        if line.strip() and PurePosixPath(line.strip()).suffix in MARKDOWN_EXTENSIONS
    ]
    return sorted(tracked_paths, key=lambda path: path.as_posix())


def _resolve_repo_url(root: Path) -> str | None:
    try:
        remote = _run_command(root, ["git", "config", "--get", "remote.origin.url"])
    except subprocess.CalledProcessError:
        return None
    if not remote:
        return None
    if remote.startswith("git@github.com:"):
        return f"https://github.com/{remote.removeprefix('git@github.com:').removesuffix('.git')}"
    if remote.startswith("https://github.com/"):
        return remote.removesuffix(".git")
    return None


def _page_title(source_path: PurePosixPath, content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return source_path.stem.replace("-", " ").replace("_", " ")


def _site_path_for(source_path: PurePosixPath) -> PurePosixPath:
    normalized_parts = [
        f"dot-{part[1:]}" if part.startswith(".") else part for part in source_path.parts[:-1]
    ]
    normalized_name = (
        f"{source_path.stem}.md" if source_path.suffix in MARKDOWN_EXTENSIONS else source_path.name
    )
    if normalized_name.startswith("."):
        normalized_name = f"dot-{normalized_name[1:]}"
    return PurePosixPath("repo", *normalized_parts, normalized_name)


def _split_link_target(raw_target: str) -> tuple[str, str]:
    candidate = raw_target.strip()
    if candidate.startswith("<") and candidate.endswith(">"):
        candidate = candidate[1:-1]
    link_text, hash_mark, fragment = candidate.partition("#")
    return link_text, f"{hash_mark}{fragment}" if hash_mark else ""


def _should_leave_link_unchanged(link_text: str) -> bool:
    if not link_text:
        return True
    if link_text.startswith(("#", "mailto:", "tel:")):
        return True
    parsed = urlparse(link_text)
    return bool(parsed.scheme)


def _resolve_source_target(source_path: PurePosixPath, link_text: str) -> PurePosixPath | None:
    if link_text.startswith("/"):
        resolved = PurePosixPath(link_text.lstrip("/"))
    else:
        resolved = PurePosixPath(posixpath.normpath((source_path.parent / link_text).as_posix()))
    if resolved.as_posix().startswith("../"):
        return None
    if resolved.suffix not in MARKDOWN_EXTENSIONS:
        return None
    return resolved


def _resolve_repo_target(source_path: PurePosixPath, link_text: str) -> PurePosixPath | None:
    if link_text.startswith("/"):
        resolved = PurePosixPath(link_text.lstrip("/"))
    else:
        resolved = PurePosixPath(posixpath.normpath((source_path.parent / link_text).as_posix()))
    if resolved.as_posix().startswith("../"):
        return None
    return resolved


def _rewrite_markdown_links(
    content: str,
    *,
    root: Path,
    source_path: PurePosixPath,
    site_map: dict[PurePosixPath, PurePosixPath],
    repo_url: str | None,
    branch: str,
) -> str:
    current_site_path = site_map[source_path]

    def replace(match: re.Match[str]) -> str:
        link_text, fragment = _split_link_target(match.group("target"))
        if _should_leave_link_unchanged(link_text):
            return match.group(0)
        resolved_source_target = _resolve_source_target(source_path, link_text)
        if resolved_source_target is None or resolved_source_target not in site_map:
            resolved_repo_target = _resolve_repo_target(source_path, link_text)
            if resolved_repo_target is None or repo_url is None:
                return match.group(0)
            filesystem_target = root / resolved_repo_target
            if not filesystem_target.exists():
                return match.group(0)
            github_kind = "tree" if filesystem_target.is_dir() else "blob"
            rewritten_target = (
                f"{repo_url}/{github_kind}/{branch}/{resolved_repo_target.as_posix()}{fragment}"
            )
            return f"{match.group('prefix')}{rewritten_target}{match.group('suffix')}"
        destination_site_path = site_map[resolved_source_target]
        relative_target = PurePosixPath(
            posixpath.relpath(destination_site_path.as_posix(), current_site_path.parent.as_posix())
        )
        rewritten_target = f"{relative_target.as_posix()}{fragment}"
        return f"{match.group('prefix')}{rewritten_target}{match.group('suffix')}"

    rewritten = MARKDOWN_IMAGE_PATTERN.sub(replace, content)
    return MARKDOWN_LINK_PATTERN.sub(replace, rewritten)


def _top_level_name(path: PurePosixPath) -> str:
    return path.parts[0] if len(path.parts) > 1 else "root"


def _section_slug(top_level: str) -> str:
    return top_level.replace(".", "").replace("/", "-") or "root"


def _section_title(top_level: str) -> str:
    return "Root Markdown" if top_level == "root" else f"{top_level} Markdown"


def _source_link(repo_url: str | None, branch: str, path: PurePosixPath) -> str:
    if repo_url is None:
        return path.as_posix()
    return f"{repo_url}/blob/{branch}/{path.as_posix()}"


def _format_catalog_table(
    pages: list[MarkdownSitePage],
    *,
    current_doc_path: PurePosixPath,
    repo_url: str | None,
    branch: str,
) -> list[str]:
    lines = ["| Page | Rendered | Source |", "| --- | --- | --- |"]
    for page in pages:
        rendered = PurePosixPath(
            posixpath.relpath(page.site_path.as_posix(), current_doc_path.parent.as_posix())
        ).as_posix()
        source_link = _source_link(repo_url, branch, page.source_path)
        lines.append(
            f"| `{page.source_path.as_posix()}` | "
            f"[site page]({rendered}) | [source]({source_link}) |"
        )
    return lines


def sync_pages_site(
    root: Path,
    *,
    output_dir: Path = DEFAULT_PAGES_DOCS_DIR,
    branch: str = "master",
    repo_url: str | None = None,
) -> dict[str, object]:
    """Generate the GitHub Pages Markdown catalog under ``output_dir``."""

    resolved_root = root.resolve()
    resolved_output_dir = output_dir if output_dir.is_absolute() else resolved_root / output_dir
    tracked_paths = _tracked_markdown_paths(resolved_root)
    resolved_repo_url = repo_url or _resolve_repo_url(resolved_root)

    if resolved_output_dir.exists():
        shutil.rmtree(resolved_output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    contents = {
        tracked_path: (resolved_root / tracked_path).read_text(encoding="utf-8")
        for tracked_path in tracked_paths
    }
    pages = [
        MarkdownSitePage(
            source_path=tracked_path,
            site_path=_site_path_for(tracked_path),
            top_level=_top_level_name(tracked_path),
            title=_page_title(tracked_path, contents[tracked_path]),
        )
        for tracked_path in tracked_paths
    ]
    page_map = {page.source_path: page.site_path for page in pages}

    for page in pages:
        destination = resolved_output_dir / page.site_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        rewritten = _rewrite_markdown_links(
            contents[page.source_path],
            root=resolved_root,
            source_path=page.source_path,
            site_map=page_map,
            repo_url=resolved_repo_url,
            branch=branch,
        )
        generated_header = (
            f"<!-- Generated from {page.source_path.as_posix()} "
            "by repo-rag sync-pages-site. -->\n\n"
        )
        destination.write_text(
            generated_header + rewritten,
            encoding="utf-8",
        )

    pages_by_section: dict[str, list[MarkdownSitePage]] = defaultdict(list)
    for page in pages:
        pages_by_section[page.top_level].append(page)

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    section_items = sorted(
        pages_by_section.items(),
        key=lambda item: (item[0] != "root", item[0]),
    )

    index_lines = [
        "# Repository Markdown Atlas",
        "",
        "This GitHub Pages site is generated from the repository's tracked Markdown files.",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Tracked Markdown pages: `{len(pages)}`",
        f"- Top-level sections: `{len(section_items)}`",
        "- Generator: `uv run repo-rag sync-pages-site --root .`",
        "",
        "## Primary Links",
        "",
        "- [Full catalog](catalog.md)",
        "- [Repository README](repo/README.md)",
    ]
    if PurePosixPath("docs/audit/README.md") in page_map:
        index_lines.append("- [Audit index](repo/docs/audit/README.md)")
    if PurePosixPath("README.DSPY.MD") in page_map:
        index_lines.append("- [DSPy guide](repo/README.DSPY.md)")
    index_lines.extend(["", "## Sections", ""])
    for top_level, section_pages in section_items:
        index_lines.append(
            f"- [{_section_title(top_level)}](sections/{_section_slug(top_level)}.md) "
            f"({len(section_pages)})"
        )

    (resolved_output_dir / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    catalog_lines = [
        "# Markdown Catalog",
        "",
        f"Generated at `{generated_at}` from `{len(pages)}` tracked Markdown files.",
        "",
        "## Sections",
        "",
    ]
    for top_level, section_pages in section_items:
        catalog_lines.append(
            f"- [{_section_title(top_level)}](sections/{_section_slug(top_level)}.md) "
            f"({len(section_pages)})"
        )
    catalog_lines.extend(["", "## All Pages", ""])
    catalog_lines.extend(
        _format_catalog_table(
            pages,
            current_doc_path=PurePosixPath("catalog.md"),
            repo_url=resolved_repo_url,
            branch=branch,
        )
    )
    (resolved_output_dir / "catalog.md").write_text(
        "\n".join(catalog_lines) + "\n",
        encoding="utf-8",
    )

    sections_dir = resolved_output_dir / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)
    for top_level, section_pages in section_items:
        section_lines = [
            f"# {_section_title(top_level)}",
            "",
            f"Tracked Markdown pages under `{top_level}`.",
            "",
        ]
        section_lines.extend(
            _format_catalog_table(
                section_pages,
                current_doc_path=PurePosixPath("sections", f"{_section_slug(top_level)}.md"),
                repo_url=resolved_repo_url,
                branch=branch,
            )
        )
        (sections_dir / f"{_section_slug(top_level)}.md").write_text(
            "\n".join(section_lines) + "\n",
            encoding="utf-8",
        )

    manifest_path = resolved_output_dir / "site-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "page_count": len(pages),
                "section_count": len(section_items),
                "repo_url": resolved_repo_url,
                "branch": branch,
                "index_path": "index.md",
                "catalog_path": "catalog.md",
                "manifest_path": "site-manifest.json",
                "pages": [
                    {
                        "source_path": page.source_path.as_posix(),
                        "site_path": page.site_path.as_posix(),
                        "top_level": page.top_level,
                        "title": page.title,
                    }
                    for page in pages
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        output_dir_text = str(resolved_output_dir.relative_to(resolved_root))
    except ValueError:
        output_dir_text = str(resolved_output_dir)

    return {
        "output_dir": output_dir_text,
        "index_path": f"{output_dir_text}/index.md",
        "catalog_path": f"{output_dir_text}/catalog.md",
        "manifest_path": f"{output_dir_text}/site-manifest.json",
        "page_count": len(pages),
        "section_count": len(section_items),
        "repo_url": resolved_repo_url,
        "branch": branch,
    }
