from __future__ import annotations

import json
from pathlib import Path

from repo_rag_lab.app import RepositoryApp
from repo_rag_lab.mcp import discover_mcp_servers, dump_candidates
from repo_rag_lab.retrieval import Chunk
from repo_rag_lab.workflow import RAGAnswer, ask_repository

FEATURE_PATH = Path(__file__).resolve().parent / "features" / "repository_rag.feature"
REPO_ROOT = Path(__file__).resolve().parents[1]


def test_feature_file_exists() -> None:
    assert FEATURE_PATH.exists()
    assert "Feature: Repository RAG" in FEATURE_PATH.read_text(encoding="utf-8")


def test_answer_repository_scope_question() -> None:
    answer = ask_repository(
        question="What does this repository research?",
        root=REPO_ROOT,
    ).answer
    assert "repository" in answer.lower()


def test_discover_mcp_candidates() -> None:
    payload = dump_candidates(discover_mcp_servers(REPO_ROOT))
    parsed = json.loads(payload)
    assert isinstance(parsed, list)


def test_render_repository_answer_ui() -> None:
    def fake_answer(question: str, root: Path) -> RAGAnswer:
        del root
        return RAGAnswer(
            question=question,
            answer="The repository UI surfaces the repository answer.",
            context=[Chunk(source=Path("README.md"), text="Repository evidence snippet.")],
            mcp_servers=[{"path": "server.py", "hint": "Demo MCP"}],
        )

    html = RepositoryApp(answer_fn=fake_answer).render_question_page(
        "What does this repository research?",
        REPO_ROOT,
    )

    assert "<!doctype html>" in html.lower()
    assert "What does this repository research?" in html
    assert "The repository UI surfaces the repository answer." in html
    assert "Repository evidence snippet." in html
