from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

import pytest

from repo_rag_lab.app import RepositoryApp
from repo_rag_lab.retrieval import Chunk
from repo_rag_lab.server import build_ui_response, serve_ui
from repo_rag_lab.ui import render_answer_page
from repo_rag_lab.workflow import RAGAnswer

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_render_answer_page_handles_empty_evidence() -> None:
    html = render_answer_page(
        RAGAnswer(
            question="Where is the UI?",
            answer="No repository evidence matched the question.",
            context=[],
            mcp_servers=[],
        )
    )

    assert "No repository evidence was found." in html
    assert "Repository RAG UI" in html


def test_repository_app_supports_mocked_integration() -> None:
    def fake_answer(question: str, root: Path) -> RAGAnswer:
        del root
        return RAGAnswer(
            question=question,
            answer="Mocked integration answer.",
            context=[Chunk(source=Path("docs/mock.md"), text="Mocked repository evidence.")],
            mcp_servers=[],
        )

    html = RepositoryApp(answer_fn=fake_answer).render_question_page(
        "What does the mocked UI show?",
        REPO_ROOT,
    )

    assert "Mocked integration answer." in html
    assert "docs/mock.md" in html


def test_build_ui_response_serves_html_with_query_override() -> None:
    def fake_answer(question: str, root: Path) -> RAGAnswer:
        del root
        return RAGAnswer(
            question=question,
            answer=f"Rendered answer for {question}.",
            context=[Chunk(source=Path("README.md"), text="Repository UI evidence.")],
            mcp_servers=[],
        )

    response = build_ui_response(
        request_target="/?question=Served%20question",
        root=REPO_ROOT,
        question="Fallback question",
        app=RepositoryApp(answer_fn=fake_answer),
    )

    html = response.body.decode("utf-8")
    assert response.status == HTTPStatus.OK
    assert "Rendered answer for Served question." in html
    assert "Repository UI evidence." in html


def test_build_ui_response_rejects_unknown_paths() -> None:
    response = build_ui_response(
        request_target="/missing",
        root=REPO_ROOT,
        question="Fallback question",
    )

    assert response.status == HTTPStatus.NOT_FOUND
    assert response.body == b"Path not found."


def test_serve_ui_announces_address_and_handles_one_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class FakeServer:
        server_name = "127.0.0.1"
        server_port = 9100

        def handle_request(self) -> None:
            events.append("handled")

        def serve_forever(self) -> None:
            events.append("forever")

        def server_close(self) -> None:
            events.append("closed")

    def fake_build_ui_server(**_: object) -> FakeServer:
        return FakeServer()

    monkeypatch.setattr(
        "repo_rag_lab.server.build_ui_server",
        fake_build_ui_server,
    )

    exit_code = serve_ui(
        root=REPO_ROOT,
        question="Served question",
        port=0,
        once=True,
        announce=events.append,
    )

    assert exit_code == 0
    assert events == ["http://127.0.0.1:9100/", "handled", "closed"]
