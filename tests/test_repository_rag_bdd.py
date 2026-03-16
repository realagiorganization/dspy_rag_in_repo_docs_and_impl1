from __future__ import annotations

import json
from pathlib import Path

from repo_rag_lab.mcp import discover_mcp_servers, dump_candidates
from repo_rag_lab.workflow import ask_repository

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
