from __future__ import annotations

from pathlib import Path

import pytest

from repo_rag_lab.corpus import RepoDocument
from repo_rag_lab.retrieval import Chunk
from repo_rag_lab.workflow import collect_repository_context

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_collect_repository_context_prefers_lookup_hit_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_lookup_candidate_paths(question: str, root: Path, *, limit: int = 8) -> list[Path]:
        del question, root, limit
        return [Path("README.md")]

    def fake_load_documents_for_paths(root: Path, paths: list[Path]) -> list[RepoDocument]:
        captured["root"] = root
        captured["paths"] = list(paths)
        return [RepoDocument(path=root / "README.md", text="Repository research overview.")]

    def fail_full_load(root: Path) -> list[RepoDocument]:
        del root
        return pytest.fail("full corpus load should not run when lookup-first context is enough")

    monkeypatch.setattr(
        "repo_rag_lab.workflow.lookup_candidate_paths",
        fake_lookup_candidate_paths,
    )
    monkeypatch.setattr(
        "repo_rag_lab.workflow.load_documents_for_paths",
        fake_load_documents_for_paths,
    )
    monkeypatch.setattr("repo_rag_lab.workflow.load_documents", fail_full_load)

    context = collect_repository_context("What does this repository research?", REPO_ROOT)

    assert captured["root"] == REPO_ROOT
    assert captured["paths"] == [Path("README.md")]
    assert context
    assert context[0].source.name == "README.md"


def test_collect_repository_context_falls_back_when_lookup_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_lookup_candidate_paths(question: str, root: Path, *, limit: int = 8) -> list[Path]:
        del question, root, limit
        return [Path("README.md")]

    def fake_load_documents_for_paths(root: Path, paths: list[Path]) -> list[RepoDocument]:
        del root, paths
        return []

    def fake_load_documents(root: Path) -> list[RepoDocument]:
        return [RepoDocument(path=root / "README.md", text="Repository research overview.")]

    monkeypatch.setattr(
        "repo_rag_lab.workflow.lookup_candidate_paths",
        fake_lookup_candidate_paths,
    )
    monkeypatch.setattr(
        "repo_rag_lab.workflow.load_documents_for_paths",
        fake_load_documents_for_paths,
    )
    monkeypatch.setattr("repo_rag_lab.workflow.load_documents", fake_load_documents)

    context = collect_repository_context("What does this repository research?", REPO_ROOT)

    assert context
    assert context[0].source.name == "README.md"


def test_repository_retriever_uses_lookup_first_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from repo_rag_lab.dspy_workflow import RepositoryRetriever

    def fake_collect_repository_context(
        question: str,
        root: Path,
        *,
        top_k: int = 4,
    ) -> list[Chunk]:
        del root, top_k
        return [
            Chunk(
                source=REPO_ROOT / "README.md",
                text=f"lookup-first context for {question}",
            )
        ]

    monkeypatch.setattr(
        "repo_rag_lab.dspy_workflow.collect_repository_context",
        fake_collect_repository_context,
    )

    context = RepositoryRetriever(REPO_ROOT)("What does this repository research?")

    assert context == ["lookup-first context for What does this repository research?"]
