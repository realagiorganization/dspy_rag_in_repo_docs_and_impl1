from __future__ import annotations

from pathlib import Path

import pytest

import repo_rag_lab.cli as cli
from repo_rag_lab.dspy_workflow import RepositoryRAG, RepositoryRetriever
from repo_rag_lab.settings import RepoSettings

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repository_retriever_returns_context_for_known_question() -> None:
    retriever = RepositoryRetriever(REPO_ROOT)
    context = retriever("What does this repository research?")
    assert context


def test_repository_rag_fallback_answer_contains_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("repo_rag_lab.dspy_workflow.dspy", None)
    result = RepositoryRAG(REPO_ROOT)("What does this repository research?")
    assert result.answer


def test_repo_settings_from_root_builds_expected_paths() -> None:
    settings = RepoSettings.from_root(REPO_ROOT)
    assert settings.docs_dir == REPO_ROOT / "documentation"
    assert settings.notebooks_dir == REPO_ROOT / "notebooks"


def test_cli_main_ask_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_ask_repository(question: str, root: Path) -> object:
        del root
        return type("Result", (), {"answer": question})()

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {"command": "ask", "question": "sample question", "root": ".", "use_dspy": False},
        )()

    monkeypatch.setattr(
        cli,
        "ask_repository",
        fake_ask_repository,
    )
    monkeypatch.setattr(
        cli.argparse.ArgumentParser,
        "parse_args",
        fake_parse_args,
    )
    assert cli.main() == 0
    assert "sample question" in capsys.readouterr().out


def test_cli_main_other_commands(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_surface_verification(root: Path) -> str:
        del root
        return '{"issue_count": 0, "issues": []}'

    def fake_serve_ui(
        *,
        root: Path,
        question: str,
        host: str,
        port: int,
        once: bool,
    ) -> int:
        del root, question, host, port, once
        return 0

    monkeypatch.setattr(cli, "run_surface_verification", fake_surface_verification)
    monkeypatch.setattr(cli, "serve_ui", fake_serve_ui)
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
        type(
            "Args",
            (),
            {
                "command": "render-ui",
                "question": "sample question",
                "root": str(tmp_path),
                "output": None,
            },
        )(),
        type(
            "Args",
            (),
            {
                "command": "serve-ui",
                "question": "sample question",
                "root": str(tmp_path),
                "host": "127.0.0.1",
                "port": 8000,
                "once": True,
            },
        )(),
        type("Args", (), {"command": "smoke-test", "root": str(tmp_path)})(),
        type("Args", (), {"command": "verify-surfaces", "root": str(tmp_path)})(),
    ]

    for args in commands:

        def fake_parse_args(self: object, *, command_args: object = args) -> object:
            del self
            return command_args

        monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)
        assert cli.main() == 0

    output = capsys.readouterr().out
    assert "Repository utility surfaces:" in output


def test_cli_render_ui_writes_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_path = tmp_path / "answer.html"

    def fake_render_question_page(question: str, root: Path) -> str:
        del question, root
        return "<!doctype html><html><body>ui</body></html>"

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "render-ui",
                "question": "sample question",
                "root": str(tmp_path),
                "output": str(output_path),
            },
        )()

    fake_app = type(
        "FakeApp",
        (),
        {"render_question_page": staticmethod(fake_render_question_page)},
    )()
    monkeypatch.setattr(cli, "RepositoryApp", lambda: fake_app)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    assert output_path.read_text(encoding="utf-8") == "<!doctype html><html><body>ui</body></html>"
    assert str(output_path) in capsys.readouterr().out
