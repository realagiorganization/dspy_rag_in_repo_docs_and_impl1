from __future__ import annotations

from pathlib import Path

import pytest

import repo_rag_lab.cli as cli
from repo_rag_lab.dspy_training import DSPyLMConfig
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


def test_repository_rag_skips_program_without_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> object:
        del args, kwargs
        return pytest.fail("program builder should not run without configuration")

    def fake_retrieve(self: RepositoryRetriever, question: str) -> list[str]:
        del self
        return [f"context for {question}"]

    monkeypatch.setattr("repo_rag_lab.dspy_workflow.dspy", object())
    monkeypatch.setattr(
        "repo_rag_lab.dspy_workflow.build_repository_rag_program",
        fail_if_called,
    )
    monkeypatch.setattr(RepositoryRetriever, "__call__", fake_retrieve)

    result = RepositoryRAG(REPO_ROOT)("What does this repository research?")

    assert result.context == ["context for What does this repository research?"]
    assert result.answer == "context for What does this repository research?"


def test_repository_rag_uses_program_prediction_context(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProgram:
        def __call__(self, *, question: str) -> object:
            return type(
                "Prediction",
                (),
                {
                    "answer": f"answer for {question}",
                    "context": ["program context"],
                },
            )()

    def fake_build_program(*args: object, **kwargs: object) -> FakeProgram:
        del args, kwargs
        return FakeProgram()

    def fake_retrieve(self: RepositoryRetriever, question: str) -> list[str]:
        del self, question
        return ["retrieved context"]

    monkeypatch.setattr("repo_rag_lab.dspy_workflow.dspy", object())
    monkeypatch.setattr(
        "repo_rag_lab.dspy_workflow.build_repository_rag_program",
        fake_build_program,
    )
    monkeypatch.setattr(RepositoryRetriever, "__call__", fake_retrieve)

    result = RepositoryRAG(
        REPO_ROOT,
        lm_config=DSPyLMConfig(model="openai/test-model"),
        require_configured_lm=True,
    )("What does this repository research?")

    assert result.context == ["program context"]
    assert result.answer == "answer for What does this repository research?"


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

    def fake_notebook_report(root: Path, **_: object) -> str:
        return f'{{"status": "success", "failure_count": 0, "notebook_count": 1, "root": "{root}"}}'

    def fake_todo_sync(root: Path) -> str:
        return (
            '{"source_path": "todo-backlog.yaml", "markdown_path": "TODO.MD", '
            f'"latex_path": "publication/todo-backlog-table.tex", "root": "{root}"}}'
        )

    def fake_azure_openai_probe(root: Path, *, load_env_file: bool = False) -> str:
        return (
            '{"provider": "azure-openai", "reply": "OPENAI_OK", '
            f'"root": "{root}", "load_env_file": {str(load_env_file).lower()}}}'
        )

    def fake_azure_inference_probe(root: Path, *, load_env_file: bool = False) -> str:
        return (
            '{"provider": "azure-inference", "reply": "INFERENCE_OK", '
            f'"root": "{root}", "load_env_file": {str(load_env_file).lower()}}}'
        )

    monkeypatch.setattr(cli, "run_surface_verification", fake_surface_verification)
    monkeypatch.setattr(cli, "run_notebook_report", fake_notebook_report)
    monkeypatch.setattr(cli, "run_todo_backlog_sync", fake_todo_sync)
    monkeypatch.setattr(cli, "run_azure_openai_probe", fake_azure_openai_probe)
    monkeypatch.setattr(cli, "run_azure_inference_probe", fake_azure_inference_probe)
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
        type("Args", (), {"command": "sync-todo-backlog", "root": str(tmp_path)})(),
        type("Args", (), {"command": "smoke-test", "root": str(tmp_path)})(),
        type(
            "Args",
            (),
            {
                "command": "azure-openai-probe",
                "root": str(tmp_path),
                "load_env_file": True,
            },
        )(),
        type(
            "Args",
            (),
            {
                "command": "azure-inference-probe",
                "root": str(tmp_path),
                "load_env_file": True,
            },
        )(),
        type("Args", (), {"command": "verify-surfaces", "root": str(tmp_path)})(),
        type(
            "Args",
            (),
            {
                "command": "run-notebooks",
                "root": str(tmp_path),
                "timeout_seconds": 60,
                "load_env_file": False,
                "fail_fast": False,
            },
        )(),
    ]

    for args in commands:

        def fake_parse_args(self: object, *, command_args: object = args) -> object:
            del self
            return command_args

        monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)
        assert cli.main() == 0

    output = capsys.readouterr().out
    assert "Repository utility surfaces:" in output
    assert "OPENAI_OK" in output
    assert "INFERENCE_OK" in output
    assert "todo-backlog.yaml" in output


def test_cli_main_ask_live_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_ask_repository_live(
        question: str,
        root: Path,
        *,
        provider: str,
        load_env_file: bool,
    ) -> object:
        del root
        return type(
            "Result",
            (),
            {"answer": f"{provider}:{str(load_env_file).lower()}:{question}"},
        )()

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "ask-live",
                "question": "sample question",
                "root": str(tmp_path),
                "provider": "azure-openai",
                "load_env_file": True,
            },
        )()

    monkeypatch.setattr(cli, "ask_repository_live", fake_ask_repository_live)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)
    assert cli.main() == 0
    assert "azure-openai:true:sample question" in capsys.readouterr().out


def test_cli_main_dspy_ask_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_repository_rag(*_: object, **__: object) -> object:
        def respond(question: str) -> object:
            return type("Result", (), {"answer": f"DSPY:{question}"})()

        return respond

    def fake_resolve_dspy_lm_config_from_args(args: object) -> DSPyLMConfig:
        del args
        return DSPyLMConfig(model="openai/test-model", api_key="test-key")

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "ask",
                "question": "sample question",
                "root": str(tmp_path),
                "use_dspy": True,
                "dspy_top_k": 4,
                "dspy_program_path": None,
            },
        )()

    monkeypatch.setattr(cli, "RepositoryRAG", fake_repository_rag)
    monkeypatch.setattr(
        cli,
        "resolve_dspy_lm_config_from_args",
        fake_resolve_dspy_lm_config_from_args,
    )
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)
    assert cli.main() == 0
    assert "DSPY:sample question" in capsys.readouterr().out


def test_cli_main_dspy_train_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_train_repository_program(
        root: Path, *, training_config: object, lm_config: DSPyLMConfig
    ) -> object:
        del training_config

        def to_json(self: object) -> str:
            del self
            return (
                '{"run_name": "sample", "artifact_dir": "artifacts/dspy/sample", '
                f'"root": "{root}", "lm_model": "{lm_config.model}"}}'
            )

        return type(
            "Result",
            (),
            {"to_json": to_json},
        )()

    def fake_resolve_dspy_lm_config_from_args(args: object) -> DSPyLMConfig:
        del args
        return DSPyLMConfig(model="openai/test-model", api_key="test-key")

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "dspy-train",
                "root": str(tmp_path),
                "training_path": "samples/training/repository_training_examples.yaml",
                "run_name": "sample",
                "optimizer": "bootstrapfewshot",
                "dspy_top_k": 4,
                "max_bootstrapped_demos": 2,
                "max_labeled_demos": 2,
                "mipro_auto": "light",
                "num_threads": 4,
                "mipro_num_trials": None,
            },
        )()

    monkeypatch.setattr(cli, "train_repository_program", fake_train_repository_program)
    monkeypatch.setattr(
        cli,
        "resolve_dspy_lm_config_from_args",
        fake_resolve_dspy_lm_config_from_args,
    )
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)
    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"run_name": "sample"' in output
    assert '"lm_model": "openai/test-model"' in output
