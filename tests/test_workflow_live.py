from __future__ import annotations

from pathlib import Path

import pytest

from repo_rag_lab.azure_runtime import ChatCompletionResult
from repo_rag_lab.retrieval import Chunk
from repo_rag_lab.workflow import ask_repository_live, build_live_answer_messages


def test_build_live_answer_messages_mentions_evidence_and_mcp_candidates() -> None:
    system_prompt, user_prompt = build_live_answer_messages(
        question="What does this repository research?",
        context=[Chunk(source=Path("README.md"), text="Repository RAG research and utilities.")],
        mcp_servers=[{"path": "mcp.json", "hint": "Candidate MCP server"}],
    )

    assert "current repository" in system_prompt
    assert "README.md" in user_prompt
    assert "mcp.json" in user_prompt
    assert "What does this repository research?" in user_prompt


def test_ask_repository_live_uses_openai_completion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_collect_repository_evidence(
        question: str, root: Path
    ) -> tuple[list[Chunk], list[dict[str, str]]]:
        del question, root
        return (
            [Chunk(source=Path("README.md"), text="Repository RAG research and utilities.")],
            [{"path": "mcp.json", "hint": "Candidate MCP server"}],
        )

    def fake_call_azure_openai_chat(
        system_prompt: str,
        user_prompt: str,
        *,
        root: Path,
        load_env_file: bool,
        max_tokens: int = 400,
    ) -> ChatCompletionResult:
        del root, max_tokens
        assert "README.md" in user_prompt
        assert load_env_file is True
        return ChatCompletionResult(
            provider="azure-openai",
            answer=f"live answer from {system_prompt[:7]}",
            model="gpt-4o-2024-11-20",
            finish_reason="stop",
        )

    monkeypatch.setattr(
        "repo_rag_lab.workflow.collect_repository_evidence",
        fake_collect_repository_evidence,
    )
    monkeypatch.setattr("repo_rag_lab.workflow.call_azure_openai_chat", fake_call_azure_openai_chat)

    answer = ask_repository_live(
        question="What does this repository research?",
        root=tmp_path,
        provider="azure-openai",
        load_env_file=True,
    )

    assert answer.answer == "live answer from You ans"
    assert answer.context[0].source == Path("README.md")


def test_ask_repository_live_falls_back_without_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_collect_repository_evidence(
        question: str, root: Path
    ) -> tuple[list[Chunk], list[dict[str, str]]]:
        del question, root
        return [], []

    def fail_openai_call(*args: object, **kwargs: object) -> ChatCompletionResult:
        del args, kwargs
        pytest.fail("cloud completion should not run without retrieved context")

    monkeypatch.setattr(
        "repo_rag_lab.workflow.collect_repository_evidence",
        fake_collect_repository_evidence,
    )
    monkeypatch.setattr("repo_rag_lab.workflow.call_azure_openai_chat", fail_openai_call)

    answer = ask_repository_live(
        question="What does this repository research?",
        root=tmp_path,
        provider="azure-openai",
        load_env_file=True,
    )

    assert "No repository evidence matched the question" in answer.answer
