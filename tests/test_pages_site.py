from __future__ import annotations

import json
import subprocess
from pathlib import Path

from repo_rag_lab.pages_site import sync_pages_site


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
