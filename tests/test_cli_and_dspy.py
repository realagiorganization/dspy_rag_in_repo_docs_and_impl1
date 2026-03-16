from __future__ import annotations

from pathlib import Path

import repo_rag_lab.cli as cli
from repo_rag_lab.dspy_workflow import RepositoryRAG, RepositoryRetriever
from repo_rag_lab.settings import RepoSettings

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repository_retriever_returns_context_for_known_question() -> None:
    retriever = RepositoryRetriever(REPO_ROOT)
    context = retriever("What does this repository research?")
    assert context


def test_repository_rag_fallback_answer_contains_context(monkeypatch) -> None:
    monkeypatch.setattr("repo_rag_lab.dspy_workflow.dspy", None)
    result = RepositoryRAG(REPO_ROOT)("What does this repository research?")
    assert result.answer


def test_repo_settings_from_root_builds_expected_paths() -> None:
    settings = RepoSettings.from_root(REPO_ROOT)
    assert settings.docs_dir == REPO_ROOT / "documentation"
    assert settings.notebooks_dir == REPO_ROOT / "notebooks"


def test_cli_main_ask_command(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "ask_repository",
        lambda question, root: type("Result", (), {"answer": question})(),
    )
    monkeypatch.setattr(
        cli.argparse.ArgumentParser,
        "parse_args",
        lambda self: type(
            "Args",
            (),
            {"command": "ask", "question": "sample question", "root": ".", "use_dspy": False},
        )(),
    )
    assert cli.main() == 0
    assert "sample question" in capsys.readouterr().out


def test_cli_main_other_commands(monkeypatch, capsys, tmp_path: Path) -> None:
    commands = [
        type("Args", (), {"command": "discover-mcp", "root": str(tmp_path)})(),
        type(
            "Args",
            (),
            {
                "command": "azure-manifest",
                "root": str(tmp_path),
                "model_id": "model",
                "deployment_name": "deployment",
                "endpoint": "https://example.services.ai.azure.com/models",
            },
        )(),
        type("Args", (), {"command": "utility-summary", "root": str(tmp_path)})(),
        type("Args", (), {"command": "smoke-test", "root": str(tmp_path)})(),
    ]

    for args in commands:
        monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", lambda self, args=args: args)
        assert cli.main() == 0

    output = capsys.readouterr().out
    assert "Repository utility surfaces:" in output
