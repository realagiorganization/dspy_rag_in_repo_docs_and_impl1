from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from repo_rag_lab.rust_lookup import (
    lookup_candidate_paths,
    lookup_repository,
    supports_native_lookup,
)
from repo_rag_lab.workflow import collect_repository_context

HAS_NATIVE_LOOKUP_TOOLCHAIN = shutil.which("cargo") is not None and shutil.which("git") is not None


def _run_git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _write_demo_git_repo(tmp_path: Path) -> Path:
    root = tmp_path / "demo-repo"
    root.mkdir()
    _run_git(root, "init")
    _run_git(root, "config", "user.name", "Test User")
    _run_git(root, "config", "user.email", "test@example.com")
    (root / "README.md").write_text(
        "# Demo Repo\n\nThe nebula scheduler coordinates worker retries and repository overlays.\n",
        encoding="utf-8",
    )
    docs_dir = root / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text(
        "# Guide\n\nUse the orbit registry for publishing stable bundles.\n",
        encoding="utf-8",
    )
    _run_git(root, "add", "README.md", "docs/guide.md")
    _run_git(root, "commit", "-m", "seed demo repository")
    return root


@pytest.mark.skipif(
    not HAS_NATIVE_LOOKUP_TOOLCHAIN,
    reason="Rust lookup integration tests require both git and cargo.",
)
def test_supports_native_lookup_accepts_arbitrary_git_repo_roots(tmp_path: Path) -> None:
    root = _write_demo_git_repo(tmp_path)

    assert supports_native_lookup(root)
    assert not supports_native_lookup(root / "docs")


@pytest.mark.skipif(
    not HAS_NATIVE_LOOKUP_TOOLCHAIN,
    reason="Rust lookup integration tests require both git and cargo.",
)
def test_lookup_repository_returns_hits_for_arbitrary_git_repo_root(tmp_path: Path) -> None:
    root = _write_demo_git_repo(tmp_path)

    hits = lookup_repository("nebula scheduler", root, limit=4)

    assert hits
    assert hits[0].path == Path("README.md")
    assert "nebula" in hits[0].snippet.lower()


def test_lookup_candidate_paths_returns_empty_for_non_git_directory(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("Plain directory without git metadata.\n", encoding="utf-8")

    assert lookup_candidate_paths("plain directory", tmp_path) == []


@pytest.mark.skipif(
    not HAS_NATIVE_LOOKUP_TOOLCHAIN,
    reason="Rust lookup integration tests require both git and cargo.",
)
def test_collect_repository_context_uses_native_lookup_for_arbitrary_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _write_demo_git_repo(tmp_path)

    def fail_full_load(unused_root: Path) -> list[object]:
        del unused_root
        return pytest.fail("full corpus load should not run when native lookup narrowing succeeds")

    monkeypatch.setattr("repo_rag_lab.workflow.load_documents", fail_full_load)

    context = collect_repository_context("What does the nebula scheduler coordinate?", root)

    assert context
    assert context[0].source == Path("README.md")
