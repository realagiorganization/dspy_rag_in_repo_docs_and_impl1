from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from repo_rag_lab.dspy_training import (
    DEFAULT_DSPY_MODEL,
    DSPyLMConfig,
    DSPyTrainingConfig,
    build_dspy_trainset,
    build_repository_rag_program,
    describe_dspy_artifacts,
    evaluate_repository_program,
    latest_dspy_artifact_metadata,
    latest_dspy_artifact_summary,
    list_dspy_artifacts,
    load_compiled_repository_rag,
    load_dspy_artifact_metadata,
    repository_answer_metric,
    resolve_dspy_artifact_paths,
    resolve_dspy_lm_config,
    resolve_dspy_program_path,
    train_repository_program,
)
from repo_rag_lab.runtime_artifacts import load_bundle_manifest
from repo_rag_lab.training_samples import TrainingExample


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


def test_resolve_dspy_lm_config_uses_chat_completions_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "repo-rag-ft")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.setenv(
        "AZURE_OPENAI_CHAT_COMPLETIONS_URI",
        "https://example.openai.azure.com/openai/deployments/repo-rag-ft/chat/completions",
    )
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
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_CHAT_COMPLETIONS_URI", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")

    config = resolve_dspy_lm_config()

    assert config is not None
    assert config.model == DEFAULT_DSPY_MODEL
    assert config.api_key == "openai-secret"


def test_resolve_dspy_lm_config_returns_none_without_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in [
        "DSPY_MODEL",
        "DSPY_API_KEY",
        "DSPY_API_BASE",
        "DSPY_API_VERSION",
        "AZURE_OPENAI_DEPLOYMENT_NAME",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_CHAT_COMPLETIONS_URI",
        "AZURE_OPENAI_API_VERSION",
        "OPENAI_API_KEY",
    ]:
        monkeypatch.delenv(name, raising=False)

    assert resolve_dspy_lm_config() is None


def test_resolve_dspy_artifact_paths_and_latest_metadata(tmp_path: Path) -> None:
    paths = resolve_dspy_artifact_paths(tmp_path, "sample-run")
    paths.artifact_dir.mkdir(parents=True)
    paths.metadata_path.write_text('{"run_name": "sample-run"}', encoding="utf-8")

    assert paths.program_path.name == "program.json"
    assert latest_dspy_artifact_metadata(tmp_path) == paths.metadata_path


def test_resolve_dspy_artifact_paths_sanitizes_run_name(tmp_path: Path) -> None:
    paths = resolve_dspy_artifact_paths(tmp_path, " Sample run / with spaces ")

    assert paths.artifact_dir == tmp_path / "artifacts" / "dspy" / "Sample-run-with-spaces"


def test_latest_dspy_artifact_metadata_returns_none_without_artifacts(tmp_path: Path) -> None:
    assert latest_dspy_artifact_metadata(tmp_path) is None


def test_list_and_describe_dspy_artifacts_report_latest_run(tmp_path: Path) -> None:
    older_paths = resolve_dspy_artifact_paths(tmp_path, "older-run")
    older_paths.artifact_dir.mkdir(parents=True)
    older_paths.program_path.write_text('{"compiled": true}', encoding="utf-8")
    older_paths.metadata_path.write_text(
        json.dumps(
            {
                "run_name": "older-run",
                "recorded_at": "2026-03-18T00:00:01+00:00",
                "program_path": "artifacts/dspy/older-run/program.json",
                "training_path": "samples/training/repository_training_examples.yaml",
                "optimizer": "bootstrapfewshot",
                "training_example_count": 2,
                "benchmark_summary": {"case_count": 2, "pass_rate": 0.5},
                "compiled_program_summary": {"program_type": "RepositoryRAGProgram"},
                "lm": {"model": "openai/test-old"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    newer_paths = resolve_dspy_artifact_paths(tmp_path, "newer-run")
    newer_paths.artifact_dir.mkdir(parents=True)
    newer_paths.program_path.write_text('{"compiled": true}', encoding="utf-8")
    newer_paths.metadata_path.write_text(
        json.dumps(
            {
                "run_name": "newer-run",
                "recorded_at": "2026-03-18T00:00:02+00:00",
                "program_path": "artifacts/dspy/newer-run/program.json",
                "training_path": "samples/training/repository_training_examples.yaml",
                "optimizer": "miprov2",
                "training_example_count": 3,
                "benchmark_summary": {"case_count": 3, "pass_rate": 1.0},
                "compiled_program_summary": {"program_type": "RepositoryRAGProgram"},
                "lm": {"model": "openai/test-new"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    older_metadata = load_dspy_artifact_metadata(older_paths.metadata_path)
    artifacts = list_dspy_artifacts(tmp_path)
    latest_summary = latest_dspy_artifact_summary(tmp_path)
    description = describe_dspy_artifacts(tmp_path)

    assert older_metadata["run_name"] == "older-run"
    assert [artifact["run_name"] for artifact in artifacts] == ["newer-run", "older-run"]
    assert latest_summary is not None
    assert latest_summary["run_name"] == "newer-run"
    assert latest_summary["program_path"] == "artifacts/dspy/newer-run/program.json"
    assert description["artifact_root"] == "artifacts/dspy"
    assert description["run_count"] == 2
    assert description["latest_run_name"] == "newer-run"
    assert description["latest_program_path"] == "artifacts/dspy/newer-run/program.json"
    assert description["latest_bundle_path"] == "artifacts/dspy/newer-run/bundle.json"
    assert description["latest_bundle_version"] == "newer-run"
    assert artifacts[0]["bundle_version"] == "newer-run"
    assert artifacts[0]["bundle_path"] == "artifacts/dspy/newer-run/bundle.json"
    assert artifacts[0]["bundle_benchmark_status"] == "pass"


def test_resolve_dspy_program_path_prefers_explicit_over_latest(tmp_path: Path) -> None:
    latest_paths = resolve_dspy_artifact_paths(tmp_path, "latest-run")
    latest_paths.artifact_dir.mkdir(parents=True)
    latest_paths.program_path.write_text('{"compiled": true}', encoding="utf-8")
    latest_paths.metadata_path.write_text(
        json.dumps(
            {
                "run_name": "latest-run",
                "recorded_at": "2026-03-18T00:00:03+00:00",
                "program_path": "artifacts/dspy/latest-run/program.json",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    explicit_program_path = tmp_path / "custom-program.json"
    explicit_program_path.write_text('{"compiled": "explicit"}', encoding="utf-8")

    assert resolve_dspy_program_path(tmp_path) == latest_paths.program_path.resolve()
    assert (
        resolve_dspy_program_path(tmp_path, explicit_program_path)
        == explicit_program_path.resolve()
    )


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
        answer = "The files are stored under docs/architecture/inspired."
        expected_sources = ("README.md",)

    class Prediction:
        answer = "The files are stored under docs/architecture/inspired."
        context_sources = ("README.md",)

    example = Example()
    pred = Prediction()

    assert repository_answer_metric(example, pred) is True


def test_repository_answer_metric_accepts_strong_paraphrase() -> None:
    class Example:
        answer = (
            "The repository researches repository-grounded RAG workflows with shared uv-managed "
            "utilities and Azure deployment manifests."
        )
        expected_sources = ("README.md",)

    class Prediction:
        answer = (
            "This repo studies repository-grounded RAG workflows with shared uv utilities and "
            "Azure deployment manifests."
        )
        context_sources = ("README.md",)

    assert repository_answer_metric(Example(), Prediction()) is True


def test_repository_answer_metric_accepts_live_repo_summary_style_answer() -> None:
    class Example:
        answer = (
            "This repository researches repository-grounded question answering and RAG "
            "workflows over repository files, with shared utilities, notebooks, evaluation, "
            "and Azure deployment support."
        )
        expected_sources = ("README.md", "src/repo_rag_lab/utilities.py")

    class Prediction:
        answer = (
            "This repository researches repository-grounded question answering: a baseline "
            "RAG workflow that retrieves files from a code/documentation repository to answer "
            "questions, with supporting work on notebooks, evaluation, utilities, and "
            "deployment."
        )
        context_sources = (
            "README.md",
            "src/repo_rag_lab/utilities.py",
            "src/repo_rag_lab/workflow.py",
        )

    assert repository_answer_metric(Example(), Prediction()) is True


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


def test_evaluate_repository_program_uses_benchmark_context_when_available() -> None:
    class FakeProgram:
        def __call__(self, *, question: str) -> object:
            raise AssertionError(f"unexpected live retrieval call for {question}")

        def answer_from_context(
            self,
            *,
            question: str,
            context: tuple[str, ...],
            context_sources: tuple[str, ...],
        ) -> object:
            assert question == "Draft the Goat Labs scope split"
            assert context == ("Goat Labs needs a scope split and implementation outline.",)
            assert context_sources == ("README.md",)
            return type(
                "Prediction",
                (),
                {
                    "answer": "Prepared the Goat Labs scope split.",
                    "context_sources": ("README.md",),
                },
            )()

    summary = evaluate_repository_program(
        FakeProgram(),
        Path("."),
        [
            TrainingExample(
                question="Draft the Goat Labs scope split",
                expected_answer="Prepared the Goat Labs scope split.",
                tags=("trainer-candidate", "candidate"),
                benchmark_context=("Goat Labs needs a scope split and implementation outline.",),
                benchmark_context_sources=("README.md",),
            )
        ],
    )

    assert summary["case_count"] == 1
    assert summary["pass_count"] == 1
    assert summary["results"][0]["benchmark_context_sources"] == ["README.md"]


def test_repository_rag_program_includes_source_paths_in_generation_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    program = build_repository_rag_program(
        tmp_path,
        top_k=2,
        require_configured_lm=False,
    )
    captured: dict[str, object] = {}

    def fake_retrieve_repository_context(
        root: Path,
        question: str,
        *,
        top_k: int = 4,
        retrieval_mode: str | None = None,
    ) -> tuple[list[str], list[str]]:
        del root, question, top_k, retrieval_mode
        return (
            ["README summary", "Package API notes"],
            ["README.md", "docs/architecture/package-api.md"],
        )

    def fake_respond(*, question: str, context: list[str]) -> object:
        captured["question"] = question
        captured["context"] = context
        return type("Prediction", (), {"answer": "Repository answer"})()

    monkeypatch.setattr(
        "repo_rag_lab.dspy_training.retrieve_repository_context",
        fake_retrieve_repository_context,
    )
    cast(Any, program).respond = fake_respond

    prediction = program(question="What does this repository research?")
    prediction_payload = cast(Any, prediction)

    assert captured["question"] == "What does this repository research?"
    assert captured["context"] == [
        "Source: README.md\n\nREADME summary",
        "Source: docs/architecture/package-api.md\n\nPackage API notes",
    ]
    assert prediction_payload.context == ["README summary", "Package API notes"]
    assert prediction_payload.context_sources == [
        "README.md",
        "docs/architecture/package-api.md",
    ]


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

    def fake_repository_program(
        root: Path,
        top_k: int = 4,
        *,
        retrieval_mode: str | None = None,
    ) -> FakeProgram:
        del root, top_k, retrieval_mode
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
            bundle_version="sample-version-001",
            run_family="trainer-auto",
            lineage_metadata={
                "imported_trace_record_paths": ["artifacts/traces/imported/demo.json"],
                "new_candidate_count": 1,
            },
        ),
        lm_config=DSPyLMConfig(model="openai/test-model"),
    )

    assert result.run_name == "sample-run"
    assert result.run_family == "trainer-auto"
    assert (tmp_path / result.program_path).exists()
    metadata_path = tmp_path / result.metadata_path
    assert metadata_path.exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert isinstance(metadata, dict)
    assert metadata["run_name"] == "sample-run"
    assert metadata["bundle_version"] == "sample-version-001"
    assert metadata["run_family"] == "trainer-auto"
    lineage = metadata["lineage"]
    assert isinstance(lineage, dict)
    assert lineage["new_candidate_count"] == 1
    assert metadata["training_example_count"] == 1
    assert metadata["benchmark_example_count"] == 1
    assert metadata["benchmark_path"] == "samples/training/sample-training.yaml"
    assert metadata["program_path"] == "artifacts/dspy/sample-run/program.json"
    assert result.benchmark_path == "samples/training/sample-training.yaml"
    assert result.benchmark_example_count == 1
    assert result.bundle_version == "sample-version-001"
    assert result.bundle_path == "artifacts/dspy/sample-run/bundle.json"
    bundle_path = tmp_path / result.bundle_path
    assert bundle_path.exists()
    bundle = load_bundle_manifest(bundle_path)
    assert isinstance(bundle, dict)
    assert bundle["bundle_kind"] == "global"
    assert bundle["bundle_version"] == "sample-version-001"
    assert bundle["run_family"] == "trainer-auto"
    bundle_lineage = bundle["lineage"]
    assert isinstance(bundle_lineage, dict)
    assert bundle_lineage["new_candidate_count"] == 1
    assert bundle["retrieval_mode"] is None
    assert bundle["program_path"] == "artifacts/dspy/sample-run/program.json"


def test_train_repository_program_uses_distinct_benchmark_path(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# sample\n", encoding="utf-8")
    samples_dir = tmp_path / "samples" / "training"
    samples_dir.mkdir(parents=True)
    training_path = samples_dir / "generated-training.yaml"
    training_path.write_text(
        "\n".join(
            [
                '- question: "Worker candidate question?"',
                '  expected_answer: "Worker candidate answer."',
                '  tags: ["trainer-candidate", "candidate"]',
                '- question: "What does this repository research?"',
                '  expected_answer: "Repository answer"',
                "  expected_sources:",
                '    - "README.md"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    benchmark_path = samples_dir / "repository-benchmark.yaml"
    benchmark_path.write_text(
        "\n".join(
            [
                '- question: "What does this repository research?"',
                '  expected_answer: "Repository answer"',
                "  expected_sources:",
                '    - "README.md"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    class FakeProgram:
        def __init__(
            self,
            root: Path | None = None,
            top_k: int = 4,
            *,
            retrieval_mode: str | None = None,
        ) -> None:
            del root, top_k, retrieval_mode

        def save(
            self,
            path: str | Path,
            save_program: bool = False,
            modules_to_serialize: object | None = None,
        ) -> object:
            del save_program, modules_to_serialize
            Path(path).write_text("{}", encoding="utf-8")
            return None

        def load(self, path: str | Path, allow_pickle: bool = False) -> object:
            del path, allow_pickle
            return None

        def dump_state(self) -> dict[str, object]:
            return {}

        def get_lm(self) -> object:
            return object()

        def set_lm(self, lm: object) -> object:
            return lm

        def __call__(self, *, question: str) -> object:
            return type(
                "Prediction",
                (),
                {
                    "answer": f"Repository answer for {question}",
                    "context_sources": ["README.md"],
                },
            )()

    class FakeOptimizer:
        def compile(self, program: object, **_: object) -> FakeProgram:
            return cast(FakeProgram, program)

    def fake_configure_dspy_lm(lm_config: object) -> object:
        del lm_config
        return object()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("repo_rag_lab.dspy_training.configure_dspy_lm", fake_configure_dspy_lm)
    monkeypatch.setattr("repo_rag_lab.dspy_training.RepositoryRAGProgram", FakeProgram)
    monkeypatch.setattr(
        "repo_rag_lab.dspy_training._build_optimizer",
        lambda training_config: FakeOptimizer(),
    )
    try:
        result = train_repository_program(
            tmp_path,
            training_config=DSPyTrainingConfig(
                training_path=Path("samples/training/generated-training.yaml"),
                benchmark_path=Path("samples/training/repository-benchmark.yaml"),
                run_name="sample run",
            ),
            lm_config=DSPyLMConfig(model="openai/test-model"),
        )
    finally:
        monkeypatch.undo()

    metadata = json.loads((tmp_path / result.metadata_path).read_text(encoding="utf-8"))
    assert metadata["training_example_count"] == 2
    assert metadata["benchmark_example_count"] == 1
    assert metadata["training_path"] == "samples/training/generated-training.yaml"
    assert metadata["benchmark_path"] == "samples/training/repository-benchmark.yaml"
    assert metadata["benchmark_summary"]["case_count"] == 1


def test_train_repository_program_raises_for_invalid_training_examples(tmp_path: Path) -> None:
    samples_dir = tmp_path / "samples" / "training"
    samples_dir.mkdir(parents=True)
    training_path = samples_dir / "invalid-training.yaml"
    training_path.write_text(
        '- question: ""\n  expected_answer: "Repository answer"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Training samples are invalid"):
        train_repository_program(
            tmp_path,
            training_config=DSPyTrainingConfig(
                training_path=Path("samples/training/invalid-training.yaml"),
            ),
            lm_config=DSPyLMConfig(model="openai/test-model"),
        )


def test_train_repository_program_raises_for_unsupported_optimizer(
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
                "  expected_sources:",
                '    - "README.md"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_configure_dspy_lm(lm_config: object) -> object:
        del lm_config
        return object()

    monkeypatch.setattr("repo_rag_lab.dspy_training.configure_dspy_lm", fake_configure_dspy_lm)

    with pytest.raises(ValueError, match="Unsupported DSPy optimizer"):
        train_repository_program(
            tmp_path,
            training_config=DSPyTrainingConfig(
                training_path=Path("samples/training/sample-training.yaml"),
                optimizer="unknown",
            ),
            lm_config=DSPyLMConfig(model="openai/test-model"),
        )
