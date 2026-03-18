from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_rag_lab.dspy_training import (
    DEFAULT_DSPY_MODEL,
    DSPyLMConfig,
    DSPyTrainingConfig,
    TrainingExample,
    build_dspy_trainset,
    build_repository_rag_program,
    evaluate_repository_program,
    latest_dspy_artifact_metadata,
    load_compiled_repository_rag,
    repository_answer_metric,
    resolve_dspy_artifact_paths,
    resolve_dspy_lm_config,
    train_repository_program,
)


def test_resolve_dspy_lm_config_prefers_explicit_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DSPY_MODEL", raising=False)
    config = resolve_dspy_lm_config(
        model="openai/explicit-model",
        api_key="explicit-key",
        api_base="https://example.invalid/v1",
        api_version="2025-01-01",
        model_type="chat",
        temperature=0.2,
        max_tokens=256,
    )
    assert config == DSPyLMConfig(
        model="openai/explicit-model",
        api_key="explicit-key",
        api_base="https://example.invalid/v1",
        api_version="2025-01-01",
        model_type="chat",
        temperature=0.2,
        max_tokens=256,
    )


def test_resolve_dspy_lm_config_uses_repo_azure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "repo-rag-ft")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-10-21")

    config = resolve_dspy_lm_config()

    assert config is not None
    assert config.model == "azure/repo-rag-ft"
    assert config.api_base == "https://example.openai.azure.com"
    assert config.api_version == "2024-10-21"


def test_resolve_dspy_lm_config_falls_back_to_openai_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_NAME", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")

    config = resolve_dspy_lm_config()

    assert config is not None
    assert config.model == DEFAULT_DSPY_MODEL
    assert config.api_key == "openai-secret"


def test_resolve_dspy_artifact_paths_and_latest_metadata(tmp_path: Path) -> None:
    paths = resolve_dspy_artifact_paths(tmp_path, "sample-run")
    paths.artifact_dir.mkdir(parents=True)
    paths.metadata_path.write_text('{"run_name": "sample-run"}', encoding="utf-8")

    assert paths.program_path.name == "program.json"
    assert latest_dspy_artifact_metadata(tmp_path) == paths.metadata_path


def test_latest_dspy_artifact_metadata_returns_none_without_artifacts(tmp_path: Path) -> None:
    assert latest_dspy_artifact_metadata(tmp_path) is None


def test_build_dspy_trainset_marks_question_as_input() -> None:
    trainset = build_dspy_trainset(
        [
            TrainingExample(
                question="What does this repository research?",
                expected_answer="Repository-grounded RAG workflows.",
                tags=("repo",),
                expected_sources=("README.md",),
            )
        ]
    )

    assert len(trainset) == 1
    assert trainset[0].inputs().question == "What does this repository research?"
    assert trainset[0].labels().answer == "Repository-grounded RAG workflows."


def test_repository_answer_metric_requires_answer_and_source_match() -> None:
    class Example:
        answer = "The files are stored under documentation/inspired."
        expected_sources = ("README.md",)

    class Prediction:
        answer = "The files are stored under documentation/inspired."
        context_sources = ("README.md",)

    example = Example()
    pred = Prediction()

    assert repository_answer_metric(example, pred) is True


def test_evaluate_repository_program_reports_pass_rate() -> None:
    class FakeProgram:
        def __call__(self, *, question: str) -> object:
            return type(
                "Prediction",
                (),
                {
                    "answer": f"Repository answer for {question}",
                    "context_sources": ["README.md"],
                },
            )()

    summary = evaluate_repository_program(
        FakeProgram(),
        Path("."),
        [
            TrainingExample(
                question="What does this repository research?",
                expected_answer="Repository answer",
                tags=("repo",),
                expected_sources=("README.md",),
            )
        ],
    )

    assert summary["case_count"] == 1
    assert summary["pass_count"] == 1
    assert summary["pass_rate"] == 1.0


def test_build_repository_rag_program_loads_saved_state_without_lm(tmp_path: Path) -> None:
    source_program = build_repository_rag_program(
        tmp_path,
        top_k=2,
        require_configured_lm=False,
    )
    artifact_path = tmp_path / "program.json"
    source_program.save(artifact_path)

    loaded_program = build_repository_rag_program(
        tmp_path,
        top_k=2,
        program_path=artifact_path,
        require_configured_lm=False,
    )

    persisted_state = json.loads(artifact_path.read_text(encoding="utf-8"))
    persisted_state.pop("metadata", None)

    assert persisted_state == loaded_program.dump_state()


def test_build_repository_rag_program_requires_lm_without_saved_program(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="DSPy LM configuration is required"):
        build_repository_rag_program(tmp_path, require_configured_lm=True)


def test_load_compiled_repository_rag_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Compiled DSPy program does not exist"):
        load_compiled_repository_rag(
            program_path=tmp_path / "missing-program.json",
            root=tmp_path,
            top_k=2,
        )


def test_train_repository_program_writes_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "README.md").write_text("# sample\n", encoding="utf-8")
    samples_dir = tmp_path / "samples" / "training"
    samples_dir.mkdir(parents=True)
    training_path = samples_dir / "sample-training.yaml"
    training_path.write_text(
        "\n".join(
            [
                '- question: "What does this repository research?"',
                '  expected_answer: "Repository answer"',
                "  tags:",
                '    - "repo"',
                "  expected_sources:",
                '    - "README.md"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    class FakeProgram:
        def __call__(self, *, question: str) -> object:
            return type(
                "Prediction",
                (),
                {"answer": f"Repository answer for {question}", "context_sources": ("README.md",)},
            )()

        def save(
            self,
            path: str | Path,
            save_program: bool = False,
            modules_to_serialize: object | None = None,
        ) -> object:
            del save_program, modules_to_serialize
            Path(path).write_text('{"compiled": true, "metadata": {}}', encoding="utf-8")
            return None

        def load(self, path: str | Path, allow_pickle: bool = False) -> object:
            del path, allow_pickle
            return None

        def dump_state(self) -> dict[str, object]:
            return {"compiled": True}

        def get_lm(self) -> object:
            return "fake-lm"

        def set_lm(self, lm: object) -> object:
            del lm
            return None

    class FakeOptimizer:
        def __init__(self, compiled_program: FakeProgram) -> None:
            self.compiled_program = compiled_program

        def compile(self, program: object, **_: object) -> FakeProgram:
            del program
            return self.compiled_program

    fake_program = FakeProgram()

    def fake_configure_dspy_lm(lm_config: object) -> object:
        del lm_config
        return object()

    def fake_repository_program(root: Path, top_k: int = 4) -> FakeProgram:
        del root, top_k
        return fake_program

    def fake_build_optimizer(training_config: object) -> FakeOptimizer:
        del training_config
        return FakeOptimizer(fake_program)

    monkeypatch.setattr("repo_rag_lab.dspy_training.configure_dspy_lm", fake_configure_dspy_lm)
    monkeypatch.setattr(
        "repo_rag_lab.dspy_training.RepositoryRAGProgram",
        fake_repository_program,
    )
    monkeypatch.setattr("repo_rag_lab.dspy_training._build_optimizer", fake_build_optimizer)

    result = train_repository_program(
        tmp_path,
        training_config=DSPyTrainingConfig(
            training_path=Path("samples/training/sample-training.yaml"),
            run_name="sample run",
        ),
        lm_config=DSPyLMConfig(model="openai/test-model"),
    )

    assert result.run_name == "sample-run"
    assert (tmp_path / result.program_path).exists()
    metadata_path = tmp_path / result.metadata_path
    assert metadata_path.exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["run_name"] == "sample-run"
    assert metadata["training_example_count"] == 1
