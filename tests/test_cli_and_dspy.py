from __future__ import annotations

import json
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

    def fake_resolve_program_path(root: Path, program_path: Path | None = None) -> None:
        del root, program_path

    monkeypatch.setattr("repo_rag_lab.dspy_workflow.dspy", object())
    monkeypatch.setattr(
        "repo_rag_lab.dspy_workflow.build_repository_rag_program",
        fail_if_called,
    )
    monkeypatch.setattr(
        "repo_rag_lab.dspy_workflow.resolve_dspy_program_path",
        fake_resolve_program_path,
    )
    monkeypatch.setattr(RepositoryRetriever, "__call__", fake_retrieve)

    result = RepositoryRAG(REPO_ROOT)("What does this repository research?")

    assert result.context == ["context for What does this repository research?"]
    assert result.answer == "context for What does this repository research?"


def test_repository_rag_uses_latest_compiled_program_when_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    class FakeProgram:
        def __call__(self, *, question: str) -> object:
            return type(
                "Prediction",
                (),
                {
                    "answer": f"compiled answer for {question}",
                    "context": ["compiled context"],
                },
            )()

    def fake_build_program(*args: object, **kwargs: object) -> FakeProgram:
        captured.update(kwargs)
        return FakeProgram()

    def fake_resolve_program_path(root: Path, program_path: Path | None = None) -> Path:
        del root, program_path
        return tmp_path / "artifacts" / "dspy" / "latest-run" / "program.json"

    monkeypatch.setattr("repo_rag_lab.dspy_workflow.dspy", object())
    monkeypatch.setattr(
        "repo_rag_lab.dspy_workflow.resolve_dspy_program_path",
        fake_resolve_program_path,
    )
    monkeypatch.setattr(
        "repo_rag_lab.dspy_workflow.build_repository_rag_program",
        fake_build_program,
    )

    result = RepositoryRAG(
        REPO_ROOT,
        lm_config=DSPyLMConfig(model="openai/test-model", api_key="test-key"),
        require_configured_lm=True,
    )("What does this repository research?")

    assert (
        captured["program_path"] == tmp_path / "artifacts" / "dspy" / "latest-run" / "program.json"
    )
    assert captured["require_configured_lm"] is False
    assert result.context == ["compiled context"]
    assert result.answer == "compiled answer for What does this repository research?"


def test_repository_rag_requires_lm_when_latest_program_is_auto_discovered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_resolve_program_path(root: Path, program_path: Path | None = None) -> Path:
        del root, program_path
        return tmp_path / "artifacts" / "dspy" / "latest" / "program.json"

    monkeypatch.setattr("repo_rag_lab.dspy_workflow.dspy", object())
    monkeypatch.setattr(
        "repo_rag_lab.dspy_workflow.resolve_dspy_program_path",
        fake_resolve_program_path,
    )

    with pytest.raises(RuntimeError, match="DSPy LM configuration is required"):
        RepositoryRAG(REPO_ROOT, require_configured_lm=True)


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
    assert settings.docs_dir == REPO_ROOT / "docs"
    assert settings.notebooks_dir == REPO_ROOT / "notebooks"


def test_cli_main_ask_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_ask_repository(
        question: str, root: Path, *, retrieval_mode: str | None = None
    ) -> object:
        del root, retrieval_mode
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


def test_cli_main_ask_command_json_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    class FakeChunk:
        source = tmp_path / "README.md"
        text = "Repository research context."

    class FakeResult:
        def __init__(self, question: str) -> None:
            self.question = question
            self.answer = "Question: ..."
            self.summary = "Repository summary"
            self.context = [FakeChunk()]
            self.mcp_servers = [{"path": "servers/demo", "hint": "Demo MCP"}]

        def to_payload(self, *, root: Path) -> dict[str, object]:
            del root
            return {
                "question": self.question,
                "answer": "Repository summary",
                "response_text": "Question: ...",
                "sources": ["README.md"],
                "context": [
                    {
                        "source": "README.md",
                        "preview": "Repository research context.",
                        "text": "Repository research context.",
                    }
                ],
                "mcp_candidates": [{"path": "servers/demo", "hint": "Demo MCP"}],
            }

    def fake_ask_repository(
        question: str, root: Path, *, retrieval_mode: str | None = None
    ) -> object:
        del root, retrieval_mode
        return FakeResult(question=question)

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "ask",
                "question": "sample question",
                "root": str(tmp_path),
                "use_dspy": False,
                "output": "json",
            },
        )()

    monkeypatch.setattr(cli, "ask_repository", fake_ask_repository)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "ask"' in output
    assert '"command_status": "success"' in output
    assert '"mode": "baseline"' in output
    assert '"trace"' in output
    assert '"trace_kind": "repo-rag-runtime"' in output
    assert '"sources": [' in output
    assert '"README.md"' in output


def test_cli_main_serve_mcp_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_parse_args(self: object) -> object:
        del self
        return type("Args", (), {"command": "serve-mcp", "root": str(tmp_path)})()

    def fake_serve(root: Path, *, input_stream: object, output_stream: object) -> int:
        captured["root"] = root
        captured["input_stream"] = input_stream
        captured["output_stream"] = output_stream
        return 0

    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)
    monkeypatch.setattr(cli, "serve_repo_rag_mcp", fake_serve)

    assert cli.main() == 0
    assert captured["root"] == tmp_path


def test_cli_main_other_commands(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_surface_verification(root: Path) -> str:
        del root
        return (
            '{"command": "verify-surfaces", "command_status": "success", '
            '"warnings": [], "artifact_metadata": {"input_paths": [], '
            '"generated_paths": [], "related_paths": []}, '
            '"issue_count": 0, "issues": []}'
        )

    def fake_notebook_report(root: Path, **_: object) -> str:
        return (
            '{"command": "run-notebooks", "command_status": "success", '
            '"warnings": [], "artifact_metadata": {"input_paths": [], '
            '"generated_paths": [], "related_paths": []}, '
            f'"status": "success", "failure_count": 0, "notebook_count": 1, "root": "{root}"}}'
        )

    def fake_file_summary_sync(root: Path) -> str:
        return (
            '{"command": "sync-file-summaries", "command_status": "success", '
            '"warnings": [], "artifact_metadata": {"input_paths": [], '
            '"generated_paths": [], "related_paths": []}, '
            '"tracked_file_count": 42, "markdown_path": "FILES.md", '
            f'"csv_path": "FILES.csv", "root": "{root}"}}'
        )

    def fake_todo_sync(root: Path) -> str:
        return (
            '{"command": "sync-todo-backlog", "command_status": "success", '
            '"warnings": [], "artifact_metadata": {"input_paths": [], '
            '"generated_paths": [], "related_paths": []}, '
            '"source_path": "todo-backlog.yaml", "markdown_path": "TODO.MD", '
            f'"latex_path": "publication/todo-backlog-table.tex", "root": "{root}"}}'
        )

    def fake_azure_openai_probe(root: Path, *, load_env_file: bool = False) -> str:
        return (
            '{"command": "azure-openai-probe", "command_status": "success", '
            '"warnings": [], "artifact_metadata": {"input_paths": [], '
            '"generated_paths": [], "related_paths": []}, '
            '"provider": "azure-openai", "reply": "OPENAI_OK", '
            f'"root": "{root}", "load_env_file": {str(load_env_file).lower()}}}'
        )

    def fake_azure_inference_probe(root: Path, *, load_env_file: bool = False) -> str:
        return (
            '{"command": "azure-inference-probe", "command_status": "success", '
            '"warnings": [], "artifact_metadata": {"input_paths": [], '
            '"generated_paths": [], "related_paths": []}, '
            '"provider": "azure-inference", "reply": "INFERENCE_OK", '
            f'"root": "{root}", "load_env_file": {str(load_env_file).lower()}}}'
        )

    def fake_exploratorium_sync(root: Path) -> str:
        return (
            '{"command": "sync-exploratorium-translation", "command_status": "success", '
            '"warnings": [], "artifact_metadata": {"input_paths": [], '
            '"generated_paths": [], "related_paths": []}, '
            '"tex_path": "publication/exploratorium_translation/generated/'
            'exploratorium-content.tex", '
            '"pdf_path": "publication/exploratorium_translation/'
            f'exploratorium_translation.pdf", "root": "{root}"}}'
        )

    def fake_github_pr_gate_sync(root: Path, **_: object) -> str:
        return (
            '{"command": "sync-github-pr-gates", "command_status": "success", '
            '"warnings": [], "artifact_metadata": {"input_paths": [], '
            '"generated_paths": [], "related_paths": []}, '
            '"repo": "realagiorganization/dspy_rag_in_repo_docs_and_impl1", '
            '"branch": "master", "mode": "apply", '
            f'"root": "{root}"}}'
        )

    def fake_retrieval_evaluation(root: Path, **_: object) -> str:
        return (
            '{"command": "retrieval-eval", "command_status": "success", '
            '"warnings": [], "artifact_metadata": {"input_paths": [], '
            '"generated_paths": [], "related_paths": []}, '
            '"training_path": "samples/training/repository_training_examples.yaml", '
            '"default_top_k": 4, "benchmark_count": 8, '
            f'"threshold_failures": [], "root": "{root}"}}'
        )

    def fake_dspy_artifacts(root: Path) -> str:
        return (
            '{"command": "dspy-artifacts", "command_status": "success", '
            '"warnings": [], "artifact_metadata": {"input_paths": [], '
            '"generated_paths": [], "related_paths": []}, '
            '"artifact_root": "artifacts/dspy", "run_count": 1, '
            '"latest_run_name": "sample", '
            f'"root": "{root}"}}'
        )

    def fake_pages_site_sync(
        root: Path,
        *,
        output_dir: Path,
        branch: str = "master",
        repo_url: str | None = None,
    ) -> str:
        return (
            '{"command": "sync-pages-site", "command_status": "success", '
            '"warnings": [], "artifact_metadata": {"input_paths": [], '
            '"generated_paths": [], "related_paths": []}, '
            '"output_dir": "artifacts/pages_docs", "page_count": 12, '
            f'"branch": "{branch}", "repo_url": "{repo_url}", "root": "{root}"}}'
        )

    monkeypatch.setattr(cli, "run_surface_verification", fake_surface_verification)
    monkeypatch.setattr(cli, "run_file_summary_sync", fake_file_summary_sync)
    monkeypatch.setattr(cli, "run_notebook_report", fake_notebook_report)
    monkeypatch.setattr(cli, "run_exploratorium_translation_sync", fake_exploratorium_sync)
    monkeypatch.setattr(cli, "run_github_pr_gate_sync", fake_github_pr_gate_sync)
    monkeypatch.setattr(cli, "run_retrieval_evaluation", fake_retrieval_evaluation)
    monkeypatch.setattr(cli, "run_dspy_artifacts", fake_dspy_artifacts)
    monkeypatch.setattr(cli, "run_pages_site_sync", fake_pages_site_sync)
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
        type("Args", (), {"command": "sync-file-summaries", "root": str(tmp_path)})(),
        type("Args", (), {"command": "dspy-artifacts", "root": str(tmp_path)})(),
        type(
            "Args",
            (),
            {
                "command": "retrieval-eval",
                "root": str(tmp_path),
                "training_path": "samples/training/repository_training_examples.yaml",
                "top_k": 4,
                "top_k_sweep": "1,2,4,8",
                "minimum_pass_rate": 1.0,
                "minimum_source_recall": 1.0,
            },
        )(),
        type("Args", (), {"command": "sync-todo-backlog", "root": str(tmp_path)})(),
        type("Args", (), {"command": "sync-exploratorium-translation", "root": str(tmp_path)})(),
        type(
            "Args",
            (),
            {
                "command": "sync-github-pr-gates",
                "root": str(tmp_path),
                "branch": "master",
                "repo": "realagiorganization/dspy_rag_in_repo_docs_and_impl1",
                "apply": True,
            },
        )(),
        type(
            "Args",
            (),
            {
                "command": "sync-pages-site",
                "root": str(tmp_path),
                "output_dir": "artifacts/pages_docs",
                "branch": "master",
                "repo_url": "https://github.com/example/demo",
            },
        )(),
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
    assert "FILES.md" in output
    assert '"latest_run_name": "sample"' in output
    assert '"mode": "apply"' in output
    assert '"page_count": 12' in output
    assert '"default_top_k": 4' in output
    assert "todo-backlog.yaml" in output
    assert "exploratorium_translation.pdf" in output


def test_cli_main_retrieval_eval_returns_nonzero_on_threshold_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_retrieval_evaluation(root: Path, **_: object) -> str:
        return (
            '{"command": "retrieval-eval", "command_status": "fail", '
            '"warnings": [], "artifact_metadata": {"input_paths": [], '
            '"generated_paths": [], "related_paths": []}, '
            '"training_path": "samples/training/repository_training_examples.yaml", '
            f'"default_top_k": 4, "benchmark_count": 8, "threshold_failures": ["regressed"], '
            f'"root": "{root}"}}'
        )

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "retrieval-eval",
                "root": str(tmp_path),
                "training_path": "samples/training/repository_training_examples.yaml",
                "top_k": 4,
                "top_k_sweep": "1,2,4,8",
                "minimum_pass_rate": 1.0,
                "minimum_source_recall": 1.0,
            },
        )()

    monkeypatch.setattr(cli, "run_retrieval_evaluation", fake_retrieval_evaluation)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 1
    assert "regressed" in capsys.readouterr().out


def test_cli_main_ask_live_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_ask_repository_live(
        question: str,
        root: Path,
        *,
        provider: str,
        load_env_file: bool,
        retrieval_mode: str | None = None,
    ) -> object:
        del root, retrieval_mode
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


def test_cli_main_ask_live_command_json_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    class FakeLiveResult:
        def __init__(self, question: str, provider: str) -> None:
            self.question = question
            self.provider = provider

        def to_payload(self, *, root: Path) -> dict[str, object]:
            del root
            return {
                "question": self.question,
                "answer": f"{self.provider}:{self.question}",
                "response_text": f"{self.provider}:{self.question}",
                "sources": ["README.md"],
                "context": [],
                "mcp_candidates": [],
            }

    def fake_ask_repository_live(
        question: str,
        root: Path,
        *,
        provider: str,
        load_env_file: bool,
        retrieval_mode: str | None = None,
    ) -> object:
        del root, load_env_file, retrieval_mode
        return FakeLiveResult(question=question, provider=provider)

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
                "output": "json",
            },
        )()

    monkeypatch.setattr(cli, "ask_repository_live", fake_ask_repository_live)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "ask-live"' in output
    assert '"mode": "live"' in output
    assert '"provider": "azure-openai"' in output
    assert '"trace_kind": "repo-rag-runtime"' in output
    assert '"load_env_file": true' in output


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


def test_cli_main_dspy_ask_command_json_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    class FakeDSPyResult:
        def __init__(self, question: str) -> None:
            self.question = question

        def to_payload(self, *, root: Path) -> dict[str, object]:
            del root
            return {
                "question": self.question,
                "answer": f"DSPY:{self.question}",
                "context": ["compiled context"],
                "sources": ["README.md"],
                "retrieved_context": [
                    {
                        "source": "README.md",
                        "preview": "compiled context",
                        "text": "compiled context",
                    }
                ],
                "program_loaded": True,
            }

    class FakeRepositoryRAG:
        def __init__(self, *_: object, **__: object) -> None:
            self.program_path = tmp_path / "artifacts" / "dspy" / "sample" / "program.json"

        def __call__(self, question: str) -> object:
            return FakeDSPyResult(question=question)

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
                "output": "json",
            },
        )()

    monkeypatch.setattr(cli, "RepositoryRAG", FakeRepositoryRAG)
    monkeypatch.setattr(
        cli, "resolve_dspy_lm_config_from_args", fake_resolve_dspy_lm_config_from_args
    )
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "ask"' in output
    assert '"mode": "dspy"' in output
    assert '"bundle_version": "sample"' in output
    assert '"trace_kind": "repo-rag-runtime"' in output
    assert '"program_loaded": true' in output
    assert '"program_path": "artifacts/dspy/sample/program.json"' in output


def test_cli_main_dspy_train_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_train_repository_program(
        root: Path, *, training_config: object, lm_config: DSPyLMConfig
    ) -> object:
        del training_config

        def to_payload(self: object) -> dict[str, object]:
            del self
            return {
                "run_name": "sample",
                "artifact_dir": "artifacts/dspy/sample",
                "lm_model": lm_config.model,
                "artifact_metadata": {
                    "input_paths": ["samples/training/repository_training_examples.yaml"],
                    "generated_paths": ["artifacts/dspy/sample"],
                    "related_paths": [],
                },
            }

        return type(
            "Result",
            (),
            {"to_payload": to_payload},
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
    assert '"command": "dspy-train"' in output
    assert '"command_status": "success"' in output
    assert '"run_name": "sample"' in output
    assert '"lm_model": "openai/test-model"' in output


def test_cli_main_bundle_inspect_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_run_bundle_inspection(
        root: Path,
        *,
        run_name: str | None = None,
        bundle_version: str | None = None,
        channel: str | None = None,
    ) -> str:
        return json.dumps(
            {
                "command": "bundle-inspect",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "bundle_found": True,
                "channel": channel,
                "bundle_version": bundle_version or run_name or "latest",
            }
        )

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "bundle-inspect",
                "root": str(tmp_path),
                "run_name": "sample",
                "bundle_version": None,
                "channel": None,
            },
        )()

    monkeypatch.setattr(cli, "run_bundle_inspection", fake_run_bundle_inspection)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "bundle-inspect"' in output
    assert '"bundle_version": "sample"' in output


def test_cli_main_bundle_fetch_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_run_bundle_fetch(
        root: Path,
        *,
        bundle_version: str | None = None,
        channel: str | None = None,
    ) -> str:
        return json.dumps(
            {
                "command": "bundle-fetch",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": ["artifacts/dspy/remote/stable-run"],
                    "related_paths": [],
                },
                "bundle_found": True,
                "bundle_version": bundle_version or "stable-run",
                "requested_channel": channel,
                "program_path": "artifacts/dspy/remote/stable-run/program.json",
            }
        )

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "bundle-fetch",
                "root": str(tmp_path),
                "bundle_version": None,
                "channel": "stable",
            },
        )()

    monkeypatch.setattr(cli, "run_bundle_fetch", fake_run_bundle_fetch)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "bundle-fetch"' in output
    assert '"requested_channel": "stable"' in output
    assert '"program_path": "artifacts/dspy/remote/stable-run/program.json"' in output


def test_cli_main_bundle_publish_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_run_bundle_publish(
        root: Path,
        *,
        run_name: str | None = None,
        bundle_version: str | None = None,
        note: str | None = None,
    ) -> str:
        return json.dumps(
            {
                "command": "bundle-publish",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "run_name": run_name,
                "bundle_version": bundle_version or run_name,
                "note": note,
                "published_bundle_path": "artifacts/dspy/published/sample.json",
            }
        )

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "bundle-publish",
                "root": str(tmp_path),
                "run_name": "sample",
                "bundle_version": None,
                "note": "ready",
            },
        )()

    monkeypatch.setattr(cli, "run_bundle_publish", fake_run_bundle_publish)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "bundle-publish"' in output
    assert '"published_bundle_path": "artifacts/dspy/published/sample.json"' in output


def test_cli_main_bundle_promote_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_run_bundle_promote(
        root: Path,
        *,
        channel: str,
        run_name: str | None = None,
        bundle_version: str | None = None,
        note: str | None = None,
    ) -> str:
        return json.dumps(
            {
                "command": "bundle-promote",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "channel_name": channel,
                "run_name": run_name,
                "bundle_version": bundle_version or run_name,
                "note": note,
            }
        )

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "bundle-promote",
                "root": str(tmp_path),
                "channel": "stable",
                "run_name": "sample",
                "bundle_version": None,
                "note": "promote",
            },
        )()

    monkeypatch.setattr(cli, "run_bundle_promote", fake_run_bundle_promote)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "bundle-promote"' in output
    assert '"channel_name": "stable"' in output


def test_cli_main_bundle_rollback_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_run_bundle_rollback(
        root: Path,
        *,
        channel: str,
        bundle_version: str | None = None,
        note: str | None = None,
    ) -> str:
        return json.dumps(
            {
                "command": "bundle-rollback",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "channel_name": channel,
                "bundle_version": bundle_version,
                "note": note,
            }
        )

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "bundle-rollback",
                "root": str(tmp_path),
                "channel": "stable",
                "bundle_version": "older-run",
                "note": "rollback",
            },
        )()

    monkeypatch.setattr(cli, "run_bundle_rollback", fake_run_bundle_rollback)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "bundle-rollback"' in output
    assert '"bundle_version": "older-run"' in output


def test_cli_main_overlay_init_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_run_overlay_init(
        root: Path,
        *,
        overlay_name: str = "default",
        bundle_version: str | None = None,
        retrieval_mode: str | None = None,
    ) -> str:
        del retrieval_mode
        return json.dumps(
            {
                "command": "overlay-init",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "overlay_name": overlay_name,
                "bundle_version": bundle_version,
            }
        )

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "overlay-init",
                "root": str(tmp_path),
                "overlay_name": "worker-default",
                "bundle_version": "bundle-v1",
                "retrieval_mode": "idf-rerank",
            },
        )()

    monkeypatch.setattr(cli, "run_overlay_init", fake_run_overlay_init)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "overlay-init"' in output
    assert '"overlay_name": "worker-default"' in output
    assert '"bundle_version": "bundle-v1"' in output


def test_cli_main_trace_export_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_run_trace_export(
        root: Path,
        *,
        payload_path: Path | None = None,
        payload_text: str | None = None,
        trace_name: str | None = None,
    ) -> str:
        del payload_text
        return json.dumps(
            {
                "command": "trace-export",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "trace_record_kind": "repo-rag-trace-record",
                "trace_record_path": "artifacts/traces/demo.json",
                "payload_path": str(payload_path) if payload_path is not None else None,
                "trace_name": trace_name,
            }
        )

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "trace-export",
                "root": str(tmp_path),
                "payload_path": "ask.json",
                "stdin": False,
                "trace_name": "demo-trace",
            },
        )()

    monkeypatch.setattr(cli, "run_trace_export", fake_run_trace_export)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "trace-export"' in output
    assert '"trace_record_path": "artifacts/traces/demo.json"' in output
    assert '"trace_name": "demo-trace"' in output


def test_cli_main_trace_import_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_run_trace_import(
        root: Path,
        *,
        trace_path: Path,
        trace_name: str | None = None,
        outcome_path: Path | None = None,
    ) -> str:
        return json.dumps(
            {
                "command": "trace-import",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "trace_record_kind": "repo-rag-trace-record",
                "trace_record_path": "artifacts/traces/imported/demo.json",
                "trace_path": str(trace_path),
                "trace_name": trace_name,
                "outcome_path": str(outcome_path) if outcome_path is not None else None,
            }
        )

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "trace-import",
                "root": str(tmp_path),
                "trace_path": "external.json",
                "trace_name": "imported-demo",
                "outcome_path": "accepted.json",
            },
        )()

    monkeypatch.setattr(cli, "run_trace_import", fake_run_trace_import)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "trace-import"' in output
    assert '"trace_record_path": "artifacts/traces/imported/demo.json"' in output
    assert '"trace_name": "imported-demo"' in output
    assert '"outcome_path": "accepted.json"' in output


def test_cli_main_trace_enqueue_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_run_trace_enqueue(
        root: Path,
        *,
        trace_path: Path,
        queue_name: str = "default",
        trace_name: str | None = None,
        outcome_path: Path | None = None,
    ) -> str:
        return json.dumps(
            {
                "command": "trace-enqueue",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "queue_item_kind": "repo-rag-trace-queue-item",
                "queue_item_path": "artifacts/traces/queued/dataset/demo.json",
                "trace_path": str(trace_path),
                "queue_name": queue_name,
                "trace_name": trace_name,
                "outcome_path": str(outcome_path) if outcome_path is not None else None,
            }
        )

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "trace-enqueue",
                "root": str(tmp_path),
                "trace_path": "external.json",
                "trace_name": "queued-demo",
                "queue_name": "dataset",
                "outcome_path": "accepted.json",
            },
        )()

    monkeypatch.setattr(cli, "run_trace_enqueue", fake_run_trace_enqueue)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "trace-enqueue"' in output
    assert '"queue_item_path": "artifacts/traces/queued/dataset/demo.json"' in output
    assert '"queue_name": "dataset"' in output


def test_cli_main_trace_drain_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_run_trace_drain(
        root: Path,
        *,
        queue_name: str = "default",
        limit: int | None = None,
        keep_queued: bool = False,
    ) -> str:
        return json.dumps(
            {
                "command": "trace-drain",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "queue_name": queue_name,
                "drained_count": 1,
                "limit": limit,
                "keep_queued": keep_queued,
            }
        )

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "trace-drain",
                "root": str(tmp_path),
                "queue_name": "dataset",
                "limit": 3,
                "keep_queued": False,
            },
        )()

    monkeypatch.setattr(cli, "run_trace_drain", fake_run_trace_drain)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "trace-drain"' in output
    assert '"queue_name": "dataset"' in output
    assert '"drained_count": 1' in output


def test_cli_main_trainer_cycle_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_run_trainer_cycle(
        root: Path,
        *,
        queue_name: str = "default",
        limit: int | None = None,
        keep_queued: bool = False,
        run_name: str | None = None,
        bundle_version: str | None = None,
        recompile_run_name: str | None = None,
        recompile_base_training_path: Path = Path(
            "samples/training/repository_training_examples.yaml"
        ),
        recompile_candidates_path: Path = Path("artifacts/trainer/training-candidates.yaml"),
        recompile_generated_training_path: Path = Path("artifacts/trainer/generated-training.yaml"),
        recompile_generated_training_summary_path: Path = Path(
            "artifacts/trainer/generated-training-summary.json"
        ),
        recompile_optimizer: str = "bootstrapfewshot",
        recompile_top_k: int = 4,
        recompile_max_bootstrapped_demos: int = 2,
        recompile_max_labeled_demos: int = 2,
        recompile_mipro_auto: str = "light",
        recompile_num_threads: int = 4,
        recompile_mipro_num_trials: int | None = None,
        recompile_lm_config: object | None = None,
        promote_channel: str | None = None,
        note: str | None = None,
        training_path: Path,
        top_k: int = 4,
        top_k_sweep: str | None = None,
        retrieval_mode: str | None = None,
        minimum_pass_rate: float | None = None,
        minimum_source_recall: float | None = None,
        minimum_bundle_pass_rate: float | None = None,
        min_new_candidates_for_recompile: int = 1,
    ) -> str:
        return json.dumps(
            {
                "command": "trainer-cycle",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [str(training_path)],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "queue_name": queue_name,
                "limit": limit,
                "keep_queued": keep_queued,
                "run_name": run_name,
                "bundle_version": bundle_version,
                "recompile_run_name": recompile_run_name,
                "promote_channel": promote_channel,
                "note": note,
                "top_k": top_k,
                "top_k_sweep": top_k_sweep,
                "retrieval_mode": retrieval_mode,
                "minimum_pass_rate": minimum_pass_rate,
                "minimum_source_recall": minimum_source_recall,
                "minimum_bundle_pass_rate": minimum_bundle_pass_rate,
                "min_new_candidates_for_recompile": min_new_candidates_for_recompile,
            }
        )

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "trainer-cycle",
                "root": str(tmp_path),
                "queue_name": "dataset",
                "limit": 5,
                "keep_queued": False,
                "run_name": "demo-run",
                "bundle_version": None,
                "recompile_run_name": None,
                "recompile_base_training_path": (
                    "samples/training/repository_training_examples.yaml"
                ),
                "recompile_candidates_path": None,
                "recompile_generated_training_path": None,
                "recompile_generated_training_summary_path": None,
                "recompile_optimizer": "bootstrapfewshot",
                "recompile_top_k": 4,
                "recompile_max_bootstrapped_demos": 2,
                "recompile_max_labeled_demos": 2,
                "recompile_mipro_auto": "light",
                "recompile_num_threads": 4,
                "recompile_mipro_num_trials": None,
                "dspy_model": None,
                "dspy_api_key": None,
                "dspy_api_base": None,
                "dspy_api_version": None,
                "dspy_model_type": "chat",
                "dspy_temperature": None,
                "dspy_max_tokens": None,
                "promote_channel": "stable",
                "note": "nightly",
                "training_path": "samples/training/repository_training_examples.yaml",
                "top_k": 4,
                "top_k_sweep": "1,4",
                "retrieval_mode": "idf-rerank",
                "minimum_pass_rate": 1.0,
                "minimum_source_recall": 1.0,
                "minimum_bundle_pass_rate": 1.0,
                "min_new_candidates_for_recompile": 2,
            },
        )()

    monkeypatch.setattr(cli, "run_trainer_cycle", fake_run_trainer_cycle)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "trainer-cycle"' in output
    assert '"queue_name": "dataset"' in output
    assert '"run_name": "demo-run"' in output
    assert '"promote_channel": "stable"' in output
    assert '"minimum_bundle_pass_rate": 1.0' in output
    assert '"min_new_candidates_for_recompile": 2' in output


def test_cli_main_trainer_service_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_run_trainer_service(
        root: Path,
        *,
        queue_name: str = "default",
        limit: int | None = None,
        keep_queued: bool = False,
        run_name: str | None = None,
        bundle_version: str | None = None,
        recompile_run_name: str | None = None,
        recompile_base_training_path: Path = Path(
            "samples/training/repository_training_examples.yaml"
        ),
        recompile_candidates_path: Path = Path("artifacts/trainer/training-candidates.yaml"),
        recompile_generated_training_path: Path = Path("artifacts/trainer/generated-training.yaml"),
        recompile_generated_training_summary_path: Path = Path(
            "artifacts/trainer/generated-training-summary.json"
        ),
        recompile_optimizer: str = "bootstrapfewshot",
        recompile_top_k: int = 4,
        recompile_max_bootstrapped_demos: int = 2,
        recompile_max_labeled_demos: int = 2,
        recompile_mipro_auto: str = "light",
        recompile_num_threads: int = 4,
        recompile_mipro_num_trials: int | None = None,
        recompile_lm_config: object | None = None,
        promote_channel: str | None = None,
        note: str | None = None,
        training_path: Path,
        top_k: int = 4,
        top_k_sweep: str | None = None,
        retrieval_mode: str | None = None,
        minimum_pass_rate: float | None = None,
        minimum_source_recall: float | None = None,
        minimum_bundle_pass_rate: float | None = None,
        min_new_candidates_for_recompile: int = 1,
        poll_interval_seconds: float = 60.0,
        max_cycles: int | None = None,
        max_idle_cycles: int | None = None,
        state_path: Path = Path("artifacts/trainer/service-state.json"),
        history_dir: Path = Path("artifacts/trainer/history"),
    ) -> str:
        return json.dumps(
            {
                "command": "trainer-service",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [str(training_path)],
                    "generated_paths": [str(state_path), str(history_dir)],
                    "related_paths": [],
                },
                "queue_name": queue_name,
                "limit": limit,
                "keep_queued": keep_queued,
                "run_name": run_name,
                "bundle_version": bundle_version,
                "recompile_run_name": recompile_run_name,
                "promote_channel": promote_channel,
                "note": note,
                "top_k": top_k,
                "top_k_sweep": top_k_sweep,
                "retrieval_mode": retrieval_mode,
                "minimum_pass_rate": minimum_pass_rate,
                "minimum_source_recall": minimum_source_recall,
                "minimum_bundle_pass_rate": minimum_bundle_pass_rate,
                "min_new_candidates_for_recompile": min_new_candidates_for_recompile,
                "poll_interval_seconds": poll_interval_seconds,
                "max_cycles": max_cycles,
                "max_idle_cycles": max_idle_cycles,
                "state_path": str(state_path),
                "history_dir": str(history_dir),
            }
        )

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "trainer-service",
                "root": str(tmp_path),
                "queue_name": "dataset",
                "limit": 2,
                "keep_queued": False,
                "run_name": "demo-run",
                "bundle_version": None,
                "recompile_run_name": None,
                "recompile_base_training_path": (
                    "samples/training/repository_training_examples.yaml"
                ),
                "recompile_candidates_path": None,
                "recompile_generated_training_path": None,
                "recompile_generated_training_summary_path": None,
                "recompile_optimizer": "bootstrapfewshot",
                "recompile_top_k": 4,
                "recompile_max_bootstrapped_demos": 2,
                "recompile_max_labeled_demos": 2,
                "recompile_mipro_auto": "light",
                "recompile_num_threads": 4,
                "recompile_mipro_num_trials": None,
                "dspy_model": None,
                "dspy_api_key": None,
                "dspy_api_base": None,
                "dspy_api_version": None,
                "dspy_model_type": "chat",
                "dspy_temperature": None,
                "dspy_max_tokens": None,
                "promote_channel": "canary",
                "note": "watcher",
                "training_path": "samples/training/repository_training_examples.yaml",
                "top_k": 4,
                "top_k_sweep": "1,4",
                "retrieval_mode": "idf-rerank",
                "minimum_pass_rate": 1.0,
                "minimum_source_recall": 1.0,
                "minimum_bundle_pass_rate": 1.0,
                "min_new_candidates_for_recompile": 3,
                "poll_interval_seconds": 0.0,
                "max_cycles": 3,
                "max_idle_cycles": 1,
                "state_path": "artifacts/custom/state.json",
                "history_dir": "artifacts/custom/history",
            },
        )()

    monkeypatch.setattr(cli, "run_trainer_service", fake_run_trainer_service)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "trainer-service"' in output
    assert '"queue_name": "dataset"' in output
    assert '"promote_channel": "canary"' in output
    assert '"max_cycles": 3' in output
    assert '"minimum_bundle_pass_rate": 1.0' in output
    assert '"min_new_candidates_for_recompile": 3' in output


def test_cli_main_trainer_k8s_manifests_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_run_trainer_k8s_manifest_generation(
        root: Path,
        *,
        image: str,
        namespace: str,
        service_account_name: str,
        config_map_name: str,
        secret_name: str,
        pvc_name: str,
        pvc_storage_class_name: str | None,
        pvc_size: str,
        pvc_access_modes: tuple[str, ...],
        image_pull_secret_name: str | None,
        output_dir: Path,
        queue_name: str,
        cycle_schedule: str,
        poll_interval_seconds: float,
        service_max_idle_cycles: int | None,
        promote_channel: str | None,
        retrieval_training_path: Path,
        retrieval_top_k: int,
        retrieval_top_k_sweep: str,
        retrieval_mode: str | None,
        minimum_pass_rate: float | None,
        minimum_source_recall: float | None,
        minimum_bundle_pass_rate: float | None,
        recompile_run_name: str | None,
        min_new_candidates_for_recompile: int,
        recompile_base_training_path: Path,
    ) -> str:
        return json.dumps(
            {
                "command": "trainer-k8s-manifests",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [str(retrieval_training_path)],
                    "generated_paths": [str(output_dir / "trainer-service.deployment.yaml")],
                    "related_paths": [],
                },
                "image": image,
                "namespace": namespace,
                "pvc_storage_class_name": pvc_storage_class_name,
                "pvc_size": pvc_size,
                "pvc_access_modes": list(pvc_access_modes),
                "queue_name": queue_name,
                "cycle_schedule": cycle_schedule,
                "minimum_bundle_pass_rate": minimum_bundle_pass_rate,
                "min_new_candidates_for_recompile": min_new_candidates_for_recompile,
                "image_pull_secret_name": image_pull_secret_name,
                "manifest_dir": str(output_dir),
            }
        )

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "trainer-k8s-manifests",
                "root": str(tmp_path),
                "image": "ghcr.io/example/repo-rag:latest",
                "namespace": "repo-rag",
                "service_account_name": "repo-rag-trainer",
                "config_map_name": "repo-rag-trainer-config",
                "secret_name": "repo-rag-trainer-secrets",
                "pvc_name": "repo-rag-trainer-artifacts",
                "pvc_storage_class": "azurefile-csi",
                "pvc_size": "10Gi",
                "pvc_access_modes": "ReadWriteMany",
                "image_pull_secret": "acr-secret",
                "output_dir": "artifacts/kubernetes",
                "queue_name": "dataset",
                "cycle_schedule": "*/15 * * * *",
                "poll_interval_seconds": 60.0,
                "service_max_idle_cycles": None,
                "promote_channel": None,
                "training_path": "samples/training/repository_training_examples.yaml",
                "top_k": 4,
                "top_k_sweep": "1,2,4,8",
                "retrieval_mode": "idf-rerank",
                "minimum_pass_rate": None,
                "minimum_source_recall": None,
                "minimum_bundle_pass_rate": None,
                "recompile_run_name": None,
                "min_new_candidates_for_recompile": 3,
                "recompile_base_training_path": (
                    "samples/training/repository_training_examples.yaml"
                ),
            },
        )()

    monkeypatch.setattr(
        cli, "run_trainer_k8s_manifest_generation", fake_run_trainer_k8s_manifest_generation
    )
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "trainer-k8s-manifests"' in output
    assert '"pvc_storage_class_name": "azurefile-csi"' in output
    assert '"queue_name": "dataset"' in output
    assert '"minimum_bundle_pass_rate": null' in output
    assert '"min_new_candidates_for_recompile": 3' in output


def test_cli_main_trainer_recompile_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_run_trainer_recompile(
        root: Path,
        *,
        run_name: str,
        base_training_path: Path,
        candidates_path: Path,
        generated_training_path: Path,
        generated_training_summary_path: Path,
        lm_config: object,
        optimizer: str,
        top_k: int,
        retrieval_mode: str | None,
        max_bootstrapped_demos: int,
        max_labeled_demos: int,
        mipro_auto: str,
        num_threads: int,
        mipro_num_trials: int | None,
    ) -> str:
        del (
            lm_config,
            retrieval_mode,
            max_bootstrapped_demos,
            max_labeled_demos,
            mipro_auto,
            num_threads,
            mipro_num_trials,
        )
        return json.dumps(
            {
                "command": "trainer-recompile",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [str(base_training_path), str(candidates_path)],
                    "generated_paths": [
                        str(generated_training_path),
                        str(generated_training_summary_path),
                    ],
                    "related_paths": [],
                },
                "run_name": run_name,
                "optimizer": optimizer,
                "top_k": top_k,
            }
        )

    def fake_resolve_dspy_lm_config_from_args(args: object) -> object:
        del args
        return object()

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "trainer-recompile",
                "root": str(tmp_path),
                "run_name": "trainer-auto",
                "base_training_path": "samples/training/repository_training_examples.yaml",
                "candidates_path": "artifacts/trainer/training-candidates.yaml",
                "generated_training_path": "artifacts/trainer/generated-training.yaml",
                "generated_training_summary_path": (
                    "artifacts/trainer/generated-training-summary.json"
                ),
                "optimizer": "bootstrapfewshot",
                "dspy_top_k": 4,
                "retrieval_mode": "idf-rerank",
                "max_bootstrapped_demos": 2,
                "max_labeled_demos": 2,
                "mipro_auto": "light",
                "num_threads": 4,
                "mipro_num_trials": None,
                "dspy_model": None,
                "dspy_api_key": None,
                "dspy_api_base": None,
                "dspy_api_version": None,
                "dspy_model_type": "chat",
                "dspy_temperature": None,
                "dspy_max_tokens": None,
            },
        )()

    monkeypatch.setattr(cli, "run_trainer_recompile", fake_run_trainer_recompile)
    monkeypatch.setattr(
        cli, "resolve_dspy_lm_config_from_args", fake_resolve_dspy_lm_config_from_args
    )
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "trainer-recompile"' in output
    assert '"run_name": "trainer-auto"' in output


def test_cli_main_trainer_candidates_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fake_run_trainer_candidates(
        root: Path,
        *,
        trace_paths: list[Path] | tuple[Path, ...] = (),
        output_path: Path = Path("artifacts/trainer/training-candidates.yaml"),
        summary_path: Path = Path("artifacts/trainer/training-candidates-summary.json"),
        include_statuses: list[str] | tuple[str, ...] = ("accepted", "candidate"),
    ) -> str:
        return json.dumps(
            {
                "command": "trainer-candidates",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [str(path) for path in trace_paths],
                    "generated_paths": [str(output_path), str(summary_path)],
                    "related_paths": [],
                },
                "candidate_count": 2,
                "new_candidate_count": 1,
                "output_path": str(output_path),
                "summary_path": str(summary_path),
                "include_statuses": list(include_statuses),
            }
        )

    def fake_parse_args(self: object) -> object:
        del self
        return type(
            "Args",
            (),
            {
                "command": "trainer-candidates",
                "root": str(tmp_path),
                "trace_paths": ["artifacts/traces/imported/one.json"],
                "output_path": "artifacts/custom/candidates.yaml",
                "summary_path": "artifacts/custom/candidates-summary.json",
                "include_statuses": "accepted,candidate",
            },
        )()

    monkeypatch.setattr(cli, "run_trainer_candidates", fake_run_trainer_candidates)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", fake_parse_args)

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '"command": "trainer-candidates"' in output
    assert '"candidate_count": 2' in output
    assert '"output_path": "artifacts/custom/candidates.yaml"' in output
