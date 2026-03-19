# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import subprocess
from pathlib import Path, PurePosixPath

from repo_rag_lab.pages_site import (
    MarkdownSitePage,
    _format_catalog_table,
    _page_title,
    _resolve_repo_target,
    _resolve_repo_url,
    _resolve_source_target,
    _rewrite_markdown_links,
    _section_slug,
    _section_title,
    _should_leave_link_unchanged,
    _site_path_for,
    _source_link,
    _split_link_target,
    _top_level_name,
    sync_pages_site,
)


def _run_git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def test_sync_pages_site_builds_catalog_and_mirrors_tracked_markdown(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _run_git(root, "init")
    _run_git(root, "config", "user.name", "Test User")
    _run_git(root, "config", "user.email", "test@example.com")
    (root / "README.md").write_text(
        "# Demo\n\nSee [Guide](documentation/guide.md).\n",
        encoding="utf-8",
    )
    docs_dir = root / "documentation"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text(
        "# Guide\n\nRead the [todo](../TODO.MD).\n",
        encoding="utf-8",
    )
    (root / "TODO.MD").write_text("# TODO\n\nBacklog items.\n", encoding="utf-8")
    _run_git(root, "add", "README.md", "documentation/guide.md", "TODO.MD")
    _run_git(root, "commit", "-m", "seed markdown fixtures")

    payload = sync_pages_site(
        root,
        output_dir=Path("artifacts/pages_docs"),
        branch="main",
        repo_url="https://github.com/example/demo",
    )

    output_dir = root / "artifacts" / "pages_docs"
    assert payload["output_dir"] == "artifacts/pages_docs"
    assert payload["page_count"] == 3
    assert (output_dir / "index.md").exists()
    assert (output_dir / "catalog.md").exists()
    assert (output_dir / "sections" / "root.md").exists()
    assert (output_dir / "sections" / "documentation.md").exists()
    assert (output_dir / "repo" / "README.md").exists()
    assert (output_dir / "repo" / "documentation" / "guide.md").exists()
    assert (output_dir / "repo" / "TODO.md").exists()

    readme_copy = (output_dir / "repo" / "README.md").read_text(encoding="utf-8")
    guide_copy = (output_dir / "repo" / "documentation" / "guide.md").read_text(encoding="utf-8")
    assert "documentation/guide.md" in readme_copy
    assert "../TODO.md" in guide_copy

    manifest = json.loads((output_dir / "site-manifest.json").read_text(encoding="utf-8"))
    assert manifest["repo_url"] == "https://github.com/example/demo"
    assert manifest["branch"] == "main"
    assert {page["site_path"] for page in manifest["pages"]} == {
        "repo/README.md",
        "repo/TODO.md",
        "repo/documentation/guide.md",
    }


def test_pages_site_helper_functions_cover_path_and_link_edge_cases() -> None:
    assert _page_title(PurePosixPath("docs/no-heading.md"), "plain text only") == "no heading"
    assert _site_path_for(PurePosixPath(".codex/guide.MD")) == PurePosixPath(
        "repo/dot-codex/guide.md"
    )
    assert _site_path_for(PurePosixPath(".index.md")) == PurePosixPath("repo/dot-index.md")
    assert _split_link_target("<guide.md#part>") == ("guide.md", "#part")
    assert _should_leave_link_unchanged("")
    assert _should_leave_link_unchanged("#jump")
    assert _should_leave_link_unchanged("mailto:test@example.com")
    assert _should_leave_link_unchanged("https://example.com/docs")
    assert not _should_leave_link_unchanged("docs/guide.md")
    assert _resolve_source_target(PurePosixPath("docs/guide.md"), "../README.md") == PurePosixPath(
        "README.md"
    )
    assert _resolve_source_target(PurePosixPath("docs/guide.md"), "/README.md") == PurePosixPath(
        "README.md"
    )
    assert _resolve_source_target(PurePosixPath("docs/guide.md"), "../../outside.md") is None
    assert _resolve_source_target(PurePosixPath("docs/guide.md"), "asset.png") is None
    assert _resolve_repo_target(
        PurePosixPath("docs/guide.md"), "../assets/logo.png"
    ) == PurePosixPath("assets/logo.png")
    assert _resolve_repo_target(PurePosixPath("docs/guide.md"), "../../outside/logo.png") is None
    assert _top_level_name(PurePosixPath("README.md")) == "root"
    assert _top_level_name(PurePosixPath("documentation/guide.md")) == "documentation"
    assert _section_slug(".codex") == "codex"
    assert _section_title("root") == "Root Markdown"
    assert _section_title("documentation") == "documentation Markdown"
    assert _source_link(None, "master", PurePosixPath("README.md")) == "README.md"
    assert _source_link("https://github.com/example/demo", "main", PurePosixPath("README.md")) == (
        "https://github.com/example/demo/blob/main/README.md"
    )


def test_rewrite_markdown_links_handles_repo_assets_dirs_and_unchanged_targets(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "assets").mkdir()
    (root / "src").mkdir()
    (root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (root / "assets" / "logo.png").write_bytes(b"png")
    (root / "src" / "tool.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    site_map = {
        PurePosixPath("README.md"): PurePosixPath("repo/README.md"),
        PurePosixPath("docs/guide.md"): PurePosixPath("repo/docs/guide.md"),
    }
    rewritten = _rewrite_markdown_links(
        (
            "[Guide](docs/guide.md)\n"
            "![Logo](assets/logo.png)\n"
            "[Source](src/tool.c)\n"
            "[Docs dir](docs/)\n"
            "[Missing](missing.txt)\n"
            "[External](https://example.com)\n"
            "[Jump](#section)\n"
            "[Mail](mailto:test@example.com)\n"
        ),
        root=root,
        source_path=PurePosixPath("README.md"),
        site_map=site_map,
        repo_url="https://github.com/example/demo",
        branch="main",
    )

    assert "[Guide](docs/guide.md)" in rewritten
    assert "![Logo](https://github.com/example/demo/blob/main/assets/logo.png)" in rewritten
    assert "[Source](https://github.com/example/demo/blob/main/src/tool.c)" in rewritten
    assert "[Docs dir](https://github.com/example/demo/tree/main/docs)" in rewritten
    assert "[Missing](missing.txt)" in rewritten
    assert "[External](https://example.com)" in rewritten
    assert "[Jump](#section)" in rewritten
    assert "[Mail](mailto:test@example.com)" in rewritten


def test_sync_pages_site_resolves_repo_url_and_rebuilds_existing_absolute_output_dir(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _run_git(root, "init")
    _run_git(root, "config", "user.name", "Test User")
    _run_git(root, "config", "user.email", "test@example.com")
    _run_git(root, "remote", "add", "origin", "git@github.com:example/demo.git")

    (root / "README.md").write_text(
        "# Demo\n\nSee [audit](docs/audit/README.md).\n", encoding="utf-8"
    )
    (root / "README.DSPY.MD").write_text("# DSPy\n\n", encoding="utf-8")
    (root / "docs" / "audit").mkdir(parents=True)
    (root / "docs" / "audit" / "README.md").write_text("# Audit\n\n", encoding="utf-8")
    (root / ".codex").mkdir()
    (root / ".codex" / "notes.MD").write_text("no heading\n", encoding="utf-8")
    _run_git(root, "add", "README.md", "README.DSPY.MD", "docs/audit/README.md", ".codex/notes.MD")
    _run_git(root, "commit", "-m", "seed markdown fixtures")

    output_dir = tmp_path / "published-site"
    output_dir.mkdir()
    (output_dir / "stale.txt").write_text("stale\n", encoding="utf-8")

    payload = sync_pages_site(root, output_dir=output_dir, branch="main")

    assert payload["output_dir"] == str(output_dir)
    assert payload["repo_url"] == "https://github.com/example/demo"
    assert not (output_dir / "stale.txt").exists()
    assert (output_dir / "repo" / "dot-codex" / "notes.md").exists()
    assert _resolve_repo_url(root) == "https://github.com/example/demo"

    index_text = (output_dir / "index.md").read_text(encoding="utf-8")
    assert "[Audit index](repo/docs/audit/README.md)" in index_text
    assert "[DSPy guide](repo/README.DSPY.md)" in index_text

    manifest = json.loads((output_dir / "site-manifest.json").read_text(encoding="utf-8"))
    titles = {page["source_path"]: page["title"] for page in manifest["pages"]}
    assert titles[".codex/notes.MD"] == "notes"

    table_lines = _format_catalog_table(
        [
            MarkdownSitePage(
                source_path=PurePosixPath("README.md"),
                site_path=PurePosixPath("repo/README.md"),
                top_level="root",
                title="Demo",
            ),
        ],
        current_doc_path=PurePosixPath("sections/root.md"),
        repo_url="https://github.com/example/demo",
        branch="main",
    )
    assert "[site page](../repo/README.md)" in table_lines[2]
