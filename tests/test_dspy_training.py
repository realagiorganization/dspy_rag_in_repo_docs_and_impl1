from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from repo_rag_lab.dspy_training import (
    DEFAULT_DSPY_MODEL,
    DSPyLMConfig,
    DSPyTrainingConfig,
    _training_examples_signature,
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
from repo_rag_lab.training_samples import TrainingExample, load_training_examples


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


def test_resolve_dspy_lm_config_prefers_dspy_model_with_shared_azure_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPY_MODEL", "azure/dspy-helper")
    monkeypatch.delenv("DSPY_API_KEY", raising=False)
    monkeypatch.delenv("DSPY_API_BASE", raising=False)
    monkeypatch.delenv("DSPY_API_VERSION", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "repo-rag-ft")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-10-21")

    config = resolve_dspy_lm_config()

    assert config is not None
    assert config.model == "azure/dspy-helper"
    assert config.api_key == "secret"
    assert config.api_base == "https://example.openai.azure.com"
    assert config.api_version == "2024-10-21"


def test_resolve_dspy_lm_config_prefers_full_dspy_env_over_repo_azure_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPY_MODEL", "azure/dspy-helper")
    monkeypatch.setenv("DSPY_API_KEY", "dspy-secret")
    monkeypatch.setenv("DSPY_API_BASE", "https://dspy-helper.openai.azure.com/")
    monkeypatch.setenv("DSPY_API_VERSION", "2025-03-01-preview")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "repo-rag-ft")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-10-21")

    config = resolve_dspy_lm_config()

    assert config is not None
    assert config.model == "azure/dspy-helper"
    assert config.api_key == "dspy-secret"
    assert config.api_base == "https://dspy-helper.openai.azure.com"
    assert config.api_version == "2025-03-01-preview"


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


def test_build_dspy_trainset_embeds_prompt_lineage_into_question() -> None:
    trainset = build_dspy_trainset(
        [
            TrainingExample(
                question="Inspect whether the README already embeds a demo GIF.",
                expected_answer="The README already embeds the demo GIF.",
                tags=("trainer-candidate",),
                original_prompt="Add a demo GIF to README",
                reformulated_prompt="Inspect whether the README already embeds a demo GIF.",
                command_trace=(
                    {"type": "message", "role": "assistant", "text": "inspect README"},
                    {"type": "message", "role": "assistant", "text": "check docs/assets"},
                ),
            )
        ]
    )

    assert len(trainset) == 1
    assert trainset[0].inputs().question == (
        "Question: Inspect whether the README already embeds a demo GIF.\n\n"
        "Original prompt: Add a demo GIF to README\n\n"
        "Command trace:\n"
        "assistant: inspect README\n"
        "assistant: check docs/assets"
    )
    assert trainset[0].labels().answer == "The README already embeds the demo GIF."


def test_repository_answer_metric_requires_answer_and_source_match() -> None:
    class Example:
        answer = "The files are stored under docs/architecture/inspired."
        expected_sources = ("README.md",)
        benchmark_context = ()

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
        benchmark_context = ()

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
        benchmark_context = ()

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


def test_repository_answer_metric_accepts_benchmark_context_grounded_summary() -> None:
    class Example:
        answer = (
            "The requested deliverable is already present in the repository, with a demo GIF "
            "embedded in the README and stored under docs/assets."
        )
        expected_sources = ()
        benchmark_context = (
            "# national-debt-relief\n## Demo\n"
            "![Automated demo walkthrough](docs/assets/national-debt-relief-demo.gif)\n"
            "Automated walkthrough of the wireframe.",
        )

    class Prediction:
        answer = (
            "This appears to already be done in the repository because the README embeds the demo "
            "GIF at docs/assets/national-debt-relief-demo.gif."
        )
        context_sources = ("README.md",)

    assert repository_answer_metric(Example(), Prediction()) is True


def test_evaluate_repository_program_reports_pass_rate() -> None:
    class FakeProgram:
        def __call__(self, *, question: str, **kwargs: object) -> object:
            del kwargs
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
        def __call__(self, *, question: str, **kwargs: object) -> object:
            del kwargs
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
    assert summary["skipped_count"] == 0
    results = cast(list[dict[str, object]], summary["results"])
    assert results[0]["benchmark_context_sources"] == ["README.md"]


def test_evaluate_repository_program_passes_prompt_lineage_when_supported() -> None:
    captured: dict[str, object] = {}

    class FakeProgram:
        def __call__(
            self,
            *,
            question: str,
            **kwargs: object,
        ) -> object:
            captured["question"] = question
            captured["original_prompt"] = kwargs.get("original_prompt")
            captured["reformulated_prompt"] = kwargs.get("reformulated_prompt")
            captured["command_trace"] = kwargs.get("command_trace")
            return type(
                "Prediction",
                (),
                {
                    "answer": "Prepared the README inspection plan.",
                    "context_sources": ["README.md"],
                },
            )()

    summary = evaluate_repository_program(
        FakeProgram(),
        Path("."),
        [
            TrainingExample(
                question="Inspect whether the README already embeds a demo GIF.",
                expected_answer="Prepared the README inspection plan.",
                tags=("trainer-candidate", "candidate"),
                expected_sources=("README.md",),
                original_prompt="Add a demo GIF to README",
                reformulated_prompt="Inspect whether the README already embeds a demo GIF.",
                command_trace=({"type": "message", "role": "assistant", "text": "inspect README"},),
            )
        ],
    )

    assert summary["case_count"] == 1
    assert summary["pass_count"] == 1
    assert captured["original_prompt"] == "Add a demo GIF to README"
    assert captured["reformulated_prompt"] == (
        "Inspect whether the README already embeds a demo GIF."
    )
    assert captured["command_trace"] == (
        {"type": "message", "role": "assistant", "text": "inspect README"},
    )


def test_evaluate_repository_program_skips_contextless_trainer_candidates() -> None:
    class FakeProgram:
        def __call__(self, *, question: str, **kwargs: object) -> object:
            del kwargs
            raise AssertionError(f"unexpected live retrieval call for {question}")

    summary = evaluate_repository_program(
        FakeProgram(),
        Path("."),
        [
            TrainingExample(
                question="External trainer row without preserved context",
                expected_answer="Some historical execution answer.",
                tags=("trainer-candidate", "candidate"),
            )
        ],
    )

    assert summary["case_count"] == 0
    assert summary["pass_count"] == 0
    assert summary["skipped_count"] == 1
    results = cast(list[dict[str, object]], summary["results"])
    assert results[0]["passed"] is None
    assert results[0]["skip_reason"] == "missing-benchmark-context"


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
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True)
    (trainer_dir / "family-state.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_kind": "repo-rag-trainer-champion-index",
                "family_state_kind": "repo-rag-trainer-family-state",
                "generated_at": "2026-05-09T19:30:00+00:00",
                "prompt_families": [
                    {
                        "prompt_family_id": "pf-sample",
                        "question": "What does this repository research?",
                        "normalized_question": "what does this repository research?",
                        "question_variants": ["What does this repository research?"],
                        "question_variant_count": 1,
                        "family_father_question": "What does this repository research?",
                        "family_father_similarity_mean": 1.0,
                        "family_father_record": {
                            "question": "What does this repository research?",
                            "expected_answer": "Repository-grounded RAG workflows.",
                            "tags": ["trainer-candidate", "candidate"],
                            "prompt_family_id": "pf-sample",
                            "exact_snapshot_id": "ts-sample",
                            "metric_hits": 1,
                            "metric_total": 1,
                            "metric_ratio": 1.0,
                        },
                        "family_runtime_score": 1.0,
                        "family_runtime_record": {
                            "question": "What does this repository research?",
                            "expected_answer": "Repository-grounded RAG workflows.",
                            "tags": ["trainer-candidate", "candidate"],
                            "prompt_family_id": "pf-sample",
                            "exact_snapshot_id": "ts-sample",
                            "metric_hits": 1,
                            "metric_total": 1,
                            "metric_ratio": 1.0,
                        },
                        "context_groups": [],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
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
        def __call__(self, *, question: str, **kwargs: object) -> object:
            del kwargs
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
                "family_state_path": "artifacts/trainer/family-state.json",
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
    family_artifact_registry = metadata["family_artifact_registry"]
    assert isinstance(family_artifact_registry, dict)
    family_artifact = family_artifact_registry["pf-sample"]
    assert family_artifact["artifact_ready"] is True
    assert family_artifact["program_path"] == (
        "artifacts/dspy/sample-run/families/pf-sample/program.json"
    )
    assert family_artifact["metadata_path"] == (
        "artifacts/dspy/sample-run/families/pf-sample/metadata.json"
    )
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
    assert bundle["family_state_path"] == "artifacts/trainer/family-state.json"
    family_registry = bundle["family_registry"]
    assert isinstance(family_registry, dict)
    assert family_registry["family_count"] == 1
    families = family_registry["families"]
    assert isinstance(families, list)
    assert families[0]["prompt_family_id"] == "pf-sample"
    assert families[0]["family_father_question"] == "What does this repository research?"
    assert families[0]["family_runtime_metric"]["hit_rate"] == 1.0
    runtime_artifact = families[0]["runtime_artifact"]
    assert runtime_artifact["artifact_ready"] is True
    assert runtime_artifact["artifact_kind"] == "compiled-family-program"
    assert runtime_artifact["program_path"] == (
        "artifacts/dspy/sample-run/families/pf-sample/program.json"
    )
    assert runtime_artifact["metadata_path"] == (
        "artifacts/dspy/sample-run/families/pf-sample/metadata.json"
    )


def test_train_repository_program_recompiles_only_dirty_families(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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

    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True)
    family_state_path = trainer_dir / "family-state.json"
    family_state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_kind": "repo-rag-trainer-champion-index",
                "family_state_kind": "repo-rag-trainer-family-state",
                "generated_at": "2026-05-09T15:00:00+00:00",
                "prompt_families": [
                    {
                        "prompt_family_id": "pf-dirty",
                        "family_needs_recompile": True,
                        "family_records": [
                            {
                                "question": "Inspect failing pytest stderr",
                                "expected_answer": "Investigate the failing pytest stderr output.",
                                "tags": ["trainer-candidate", "candidate"],
                                "prompt_family_id": "pf-dirty",
                                "exact_snapshot_id": "ts-dirty",
                                "metric_hits": 1,
                                "metric_total": 1,
                                "metric_ratio": 1.0,
                            },
                            {
                                "question": (
                                    "Inspect failing pytest stderr and summarize the stack."
                                ),
                                "expected_answer": "Summarize the failing pytest stack trace.",
                                "tags": ["trainer-candidate", "candidate"],
                                "prompt_family_id": "pf-dirty",
                                "exact_snapshot_id": "ts-dirty-2",
                                "metric_hits": 1,
                                "metric_total": 1,
                                "metric_ratio": 1.0,
                            },
                        ],
                        "family_runtime_record": {
                            "question": "Inspect failing pytest stderr",
                            "expected_answer": "Investigate the failing pytest stderr output.",
                            "tags": ["trainer-candidate", "candidate"],
                            "prompt_family_id": "pf-dirty",
                            "exact_snapshot_id": "ts-dirty",
                            "metric_hits": 1,
                            "metric_total": 1,
                            "metric_ratio": 1.0,
                        },
                        "context_groups": [
                            {
                                "context_group_id": "cg-dirty",
                                "sources": ["README.md"],
                                "evidence_fingerprints": [],
                                "evidence_count": 0,
                                "retrieval_mode": "lexical",
                                "mode": "codex-proxy",
                                "context_field": "evidence_previews",
                                "source_count": 1,
                                "context_count": 1,
                                "top_k": 4,
                                "trace_count": 1,
                                "support_by_record_key": {},
                                "champion_score": 1.0,
                                "champion_record": {
                                    "question": "Inspect failing pytest stderr",
                                    "expected_answer": (
                                        "Investigate the failing pytest stderr output."
                                    ),
                                    "tags": ["trainer-candidate", "candidate"],
                                    "prompt_family_id": "pf-dirty",
                                    "exact_snapshot_id": "ts-dirty",
                                    "metric_hits": 1,
                                    "metric_total": 1,
                                    "metric_ratio": 1.0,
                                },
                            }
                        ],
                    },
                    {
                        "prompt_family_id": "pf-clean",
                        "family_needs_recompile": False,
                        "family_runtime_record": {
                            "question": "Inspect docs assets",
                            "expected_answer": "Inspect the docs assets directory.",
                            "tags": ["trainer-candidate", "candidate"],
                            "prompt_family_id": "pf-clean",
                            "exact_snapshot_id": "ts-clean",
                            "metric_hits": 1,
                            "metric_total": 1,
                            "metric_ratio": 1.0,
                        },
                        "context_groups": [
                            {
                                "context_group_id": "cg-clean",
                                "sources": ["README.md"],
                                "evidence_fingerprints": [],
                                "evidence_count": 0,
                                "retrieval_mode": "lexical",
                                "mode": "codex-proxy",
                                "context_field": "evidence_previews",
                                "source_count": 1,
                                "context_count": 1,
                                "top_k": 4,
                                "trace_count": 1,
                                "support_by_record_key": {},
                                "champion_score": 1.0,
                                "champion_record": {
                                    "question": "Inspect docs assets",
                                    "expected_answer": "Inspect the docs assets directory.",
                                    "tags": ["trainer-candidate", "candidate"],
                                    "prompt_family_id": "pf-clean",
                                    "exact_snapshot_id": "ts-clean",
                                    "metric_hits": 1,
                                    "metric_total": 1,
                                    "metric_ratio": 1.0,
                                },
                            }
                        ],
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    previous_run_dir = tmp_path / "artifacts" / "dspy" / "previous-run"
    previous_run_dir.mkdir(parents=True)
    dirty_previous_dir = previous_run_dir / "families" / "pf-dirty"
    clean_previous_dir = previous_run_dir / "families" / "pf-clean"
    dirty_previous_dir.mkdir(parents=True)
    clean_previous_dir.mkdir(parents=True)
    (dirty_previous_dir / "program.json").write_text('{"program":"old-dirty"}\n', encoding="utf-8")
    (dirty_previous_dir / "metadata.json").write_text(
        '{"prompt_family_id":"pf-dirty"}\n',
        encoding="utf-8",
    )
    (clean_previous_dir / "program.json").write_text('{"program":"old-clean"}\n', encoding="utf-8")
    (clean_previous_dir / "metadata.json").write_text(
        '{"prompt_family_id":"pf-clean"}\n',
        encoding="utf-8",
    )
    (previous_run_dir / "metadata.json").write_text(
        json.dumps(
            {
                "run_name": "previous-run",
                "recorded_at": "2026-05-09T14:00:00+00:00",
                "program_path": "artifacts/dspy/previous-run/program.json",
                "family_artifact_registry": {
                    "pf-dirty": {
                        "prompt_family_id": "pf-dirty",
                        "artifact_dir": "artifacts/dspy/previous-run/families/pf-dirty",
                        "program_path": (
                            "artifacts/dspy/previous-run/families/pf-dirty/program.json"
                        ),
                        "metadata_path": (
                            "artifacts/dspy/previous-run/families/pf-dirty/metadata.json"
                        ),
                        "optimizer": "bootstrapfewshot",
                        "training_example_count": 1,
                        "benchmark_example_count": 1,
                        "benchmark_summary": {"case_count": 1, "pass_rate": 1.0},
                        "artifact_ready": True,
                    },
                    "pf-clean": {
                        "prompt_family_id": "pf-clean",
                        "artifact_dir": "artifacts/dspy/previous-run/families/pf-clean",
                        "program_path": (
                            "artifacts/dspy/previous-run/families/pf-clean/program.json"
                        ),
                        "metadata_path": (
                            "artifacts/dspy/previous-run/families/pf-clean/metadata.json"
                        ),
                        "optimizer": "bootstrapfewshot",
                        "training_example_count": 1,
                        "benchmark_example_count": 1,
                        "benchmark_summary": {"case_count": 1, "pass_rate": 1.0},
                        "artifact_ready": True,
                    },
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    compiled_paths: list[str] = []
    compiled_example_counts: dict[str, int] = {}

    def fake_configure_dspy_lm(lm_config: object) -> object:
        del lm_config
        return object()

    def fake_compile_repository_program_artifact(
        root: Path,
        *,
        artifact_paths: object,
        examples: object,
        benchmark_examples: object,
        training_config: object,
        lm_config: object,
    ) -> dict[str, object]:
        del benchmark_examples, training_config, lm_config
        paths = cast(Any, artifact_paths)
        artifact_dir = cast(Path, paths.artifact_dir)
        program_path = cast(Path, paths.program_path)
        relative_program_path = str(program_path.relative_to(root.resolve()))
        artifact_dir.mkdir(parents=True, exist_ok=True)
        program_path.write_text('{"compiled": true}\n', encoding="utf-8")
        compiled_paths.append(relative_program_path)
        compiled_example_counts[relative_program_path] = len(cast(list[Any], examples))
        return {
            "compiled_program": object(),
            "benchmark_summary": {"case_count": 1, "pass_rate": 1.0},
            "trainset_size": 1,
        }

    monkeypatch.setattr("repo_rag_lab.dspy_training.configure_dspy_lm", fake_configure_dspy_lm)
    monkeypatch.setattr(
        "repo_rag_lab.dspy_training._compile_repository_program_artifact",
        fake_compile_repository_program_artifact,
    )

    result = train_repository_program(
        tmp_path,
        training_config=DSPyTrainingConfig(
            training_path=Path("samples/training/sample-training.yaml"),
            run_name="family-dirty-run",
            bundle_version="family-dirty-run",
            lineage_metadata={
                "family_state_path": "artifacts/trainer/family-state.json",
            },
        ),
        lm_config=DSPyLMConfig(model="openai/test-model"),
    )

    assert sorted(compiled_paths) == [
        "artifacts/dspy/family-dirty-run/families/pf-dirty/program.json",
        "artifacts/dspy/family-dirty-run/program.json",
    ]
    assert compiled_example_counts == {
        "artifacts/dspy/family-dirty-run/families/pf-dirty/program.json": 2,
        "artifacts/dspy/family-dirty-run/program.json": 1,
    }
    metadata = json.loads((tmp_path / result.metadata_path).read_text(encoding="utf-8"))
    family_artifact_registry = metadata["family_artifact_registry"]
    assert family_artifact_registry["pf-dirty"]["artifact_source"] == "recompiled"
    assert family_artifact_registry["pf-dirty"]["program_path"] == (
        "artifacts/dspy/family-dirty-run/families/pf-dirty/program.json"
    )
    assert family_artifact_registry["pf-clean"]["artifact_source"] == "carried-forward"
    assert family_artifact_registry["pf-clean"]["program_path"] == (
        "artifacts/dspy/previous-run/families/pf-clean/program.json"
    )
    assert result.bundle_path is not None
    bundle = load_bundle_manifest(tmp_path / result.bundle_path)
    family_registry = cast(dict[str, object], bundle["family_registry"])
    bundle_families = cast(list[dict[str, object]], family_registry["families"])
    dirty_bundle_family = next(
        family for family in bundle_families if family["prompt_family_id"] == "pf-dirty"
    )
    clean_bundle_family = next(
        family for family in bundle_families if family["prompt_family_id"] == "pf-clean"
    )
    dirty_runtime_artifact = cast(dict[str, object], dirty_bundle_family["runtime_artifact"])
    clean_runtime_artifact = cast(dict[str, object], clean_bundle_family["runtime_artifact"])
    assert dirty_runtime_artifact["artifact_source"] == "recompiled"
    assert clean_runtime_artifact["artifact_source"] == "carried-forward"

    updated_family_state = json.loads(family_state_path.read_text(encoding="utf-8"))
    updated_families = {
        family["prompt_family_id"]: family for family in updated_family_state["prompt_families"]
    }
    assert updated_families["pf-dirty"]["family_needs_recompile"] is False
    assert updated_families["pf-clean"]["family_needs_recompile"] is False
    assert updated_families["pf-dirty"]["family_runtime_artifact"]["program_path"] == (
        "artifacts/dspy/family-dirty-run/families/pf-dirty/program.json"
    )
    assert updated_families["pf-clean"]["family_runtime_artifact"]["program_path"] == (
        "artifacts/dspy/previous-run/families/pf-clean/program.json"
    )


def test_train_repository_program_carries_forward_global_program_when_no_dirty_families(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "README.md").write_text("# sample\n", encoding="utf-8")
    samples_dir = tmp_path / "samples" / "training"
    samples_dir.mkdir(parents=True)
    training_path = samples_dir / "sample-training.yaml"
    training_path.write_text(
        "\n".join(
            [
                '- question: "What does this repository research?"',
                '  expected_answer: "Repository-grounded RAG workflows."',
                "  expected_sources:",
                '    - "README.md"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True)
    family_state_path = trainer_dir / "family-state.json"
    family_state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "family_state_kind": "repo-rag-trainer-family-state",
                "prompt_families": [
                    {
                        "prompt_family_id": "pf-clean",
                        "family_needs_recompile": False,
                        "family_father_record": {
                            "question": "What does this repository research?",
                            "expected_answer": "Repository-grounded RAG workflows.",
                            "expected_sources": ["README.md"],
                            "tags": ["trainer-candidate", "candidate"],
                            "prompt_family_id": "pf-clean",
                            "exact_snapshot_id": "ts-clean",
                            "metric_hits": 1,
                            "metric_total": 1,
                            "metric_ratio": 1.0,
                        },
                        "context_groups": [],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    previous_run_dir = tmp_path / "artifacts" / "dspy" / "previous-global"
    previous_run_dir.mkdir(parents=True)
    (previous_run_dir / "program.json").write_text(
        '{"program":"previous-global"}\n',
        encoding="utf-8",
    )
    family_previous_dir = previous_run_dir / "families" / "pf-clean"
    family_previous_dir.mkdir(parents=True)
    (family_previous_dir / "program.json").write_text(
        '{"program":"clean-family"}\n',
        encoding="utf-8",
    )
    (family_previous_dir / "metadata.json").write_text(
        '{"prompt_family_id":"pf-clean"}\n',
        encoding="utf-8",
    )
    (previous_run_dir / "metadata.json").write_text(
        json.dumps(
            {
                "run_name": "previous-global",
                "recorded_at": "2026-05-09T14:00:00+00:00",
                "program_path": "artifacts/dspy/previous-global/program.json",
                "training_path": "samples/training/sample-training.yaml",
                "benchmark_path": "samples/training/sample-training.yaml",
                "optimizer": "bootstrapfewshot",
                "top_k": 4,
                "retrieval_mode": None,
                "lm": {"model": "openai/test-model"},
                "benchmark_summary": {"case_count": 1, "pass_rate": 1.0},
                "compiled_program_summary": {
                    "program_type": "RepositoryRAGProgram",
                    "trainset_size": 1,
                    "top_k": 4,
                },
                "family_artifact_registry": {
                    "pf-clean": {
                        "prompt_family_id": "pf-clean",
                        "artifact_dir": "artifacts/dspy/previous-global/families/pf-clean",
                        "program_path": (
                            "artifacts/dspy/previous-global/families/pf-clean/program.json"
                        ),
                        "metadata_path": (
                            "artifacts/dspy/previous-global/families/pf-clean/metadata.json"
                        ),
                        "optimizer": "bootstrapfewshot",
                        "training_example_count": 1,
                        "benchmark_example_count": 1,
                        "benchmark_summary": {"case_count": 1, "pass_rate": 1.0},
                        "artifact_ready": True,
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_configure_dspy_lm(lm_config: object) -> object:
        del lm_config
        return object()

    def fail_compile_repository_program_artifact(
        *args: object,
        **kwargs: object,
    ) -> dict[str, object]:
        del args, kwargs
        raise AssertionError(
            "compile should not run when global and family artifacts carry forward"
        )

    monkeypatch.setattr("repo_rag_lab.dspy_training.configure_dspy_lm", fake_configure_dspy_lm)
    monkeypatch.setattr(
        "repo_rag_lab.dspy_training._compile_repository_program_artifact",
        fail_compile_repository_program_artifact,
    )

    result = train_repository_program(
        tmp_path,
        training_config=DSPyTrainingConfig(
            training_path=Path("samples/training/sample-training.yaml"),
            run_name="carry-forward-global",
            bundle_version="carry-forward-global",
            lineage_metadata={
                "family_state_path": "artifacts/trainer/family-state.json",
                "dirty_family_count": 0,
                "dirty_family_ids": [],
            },
        ),
        lm_config=DSPyLMConfig(model="openai/test-model"),
    )

    carried_program_path = tmp_path / result.program_path
    assert carried_program_path.exists()
    assert carried_program_path.read_text(encoding="utf-8") == '{"program":"previous-global"}\n'
    metadata = json.loads((tmp_path / result.metadata_path).read_text(encoding="utf-8"))
    compiled_program_summary = metadata["compiled_program_summary"]
    assert compiled_program_summary["artifact_source"] == "carried-forward"
    assert compiled_program_summary["program_type"] == "RepositoryRAGProgram"
    assert compiled_program_summary["trainset_size"] == 1
    assert metadata["benchmark_summary"]["pass_rate"] == 1.0


def test_train_repository_program_carries_forward_global_program_for_dirty_family_cycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "README.md").write_text("# sample\n", encoding="utf-8")
    samples_dir = tmp_path / "samples" / "training"
    samples_dir.mkdir(parents=True)
    training_path = samples_dir / "sample-training.yaml"
    training_path.write_text(
        "\n".join(
            [
                '- question: "What does this repository research?"',
                '  expected_answer: "Repository-grounded RAG workflows."',
                "  expected_sources:",
                '    - "README.md"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    training_signature = _training_examples_signature(load_training_examples(training_path))
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True)
    family_state_path = trainer_dir / "family-state.json"
    family_state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "family_state_kind": "repo-rag-trainer-family-state",
                "prompt_families": [
                    {
                        "prompt_family_id": "pf-dirty",
                        "family_needs_recompile": True,
                        "family_father_record": {
                            "question": "What does this repository research?",
                            "expected_answer": "Repository-grounded RAG workflows.",
                            "expected_sources": ["README.md"],
                            "tags": ["trainer-candidate", "candidate"],
                            "prompt_family_id": "pf-dirty",
                            "exact_snapshot_id": "ts-dirty-father",
                            "metric_hits": 1,
                            "metric_total": 1,
                            "metric_ratio": 1.0,
                        },
                        "family_records": [
                            {
                                "question": "What does this repository research?",
                                "expected_answer": "Repository-grounded RAG workflows.",
                                "expected_sources": ["README.md"],
                                "tags": ["trainer-candidate", "candidate"],
                                "prompt_family_id": "pf-dirty",
                                "exact_snapshot_id": "ts-dirty-record",
                                "metric_hits": 1,
                                "metric_total": 1,
                                "metric_ratio": 1.0,
                            }
                        ],
                        "context_groups": [],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    previous_run_dir = tmp_path / "artifacts" / "dspy" / "previous-global-dirty"
    previous_run_dir.mkdir(parents=True)
    (previous_run_dir / "program.json").write_text(
        '{"program":"previous-global-dirty"}\n',
        encoding="utf-8",
    )
    (previous_run_dir / "metadata.json").write_text(
        json.dumps(
            {
                "run_name": "previous-global-dirty",
                "recorded_at": "2026-05-09T15:00:00+00:00",
                "program_path": "artifacts/dspy/previous-global-dirty/program.json",
                "training_path": "samples/training/sample-training.yaml",
                "benchmark_path": "samples/training/sample-training.yaml",
                "training_examples_signature": training_signature,
                "benchmark_examples_signature": training_signature,
                "optimizer": "bootstrapfewshot",
                "top_k": 4,
                "retrieval_mode": None,
                "lm": {"model": "openai/test-model"},
                "benchmark_summary": {"case_count": 1, "pass_rate": 1.0},
                "compiled_program_summary": {
                    "program_type": "RepositoryRAGProgram",
                    "trainset_size": 1,
                    "top_k": 4,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    compiled_paths: list[str] = []

    def fake_configure_dspy_lm(lm_config: object) -> object:
        del lm_config
        return object()

    def fake_compile_repository_program_artifact(
        root: Path,
        *,
        artifact_paths: object,
        examples: object,
        benchmark_examples: object,
        training_config: object,
        lm_config: object,
    ) -> dict[str, object]:
        del training_config, lm_config, root, benchmark_examples
        resolved_artifact_paths = cast(Any, artifact_paths)
        relative_program_path = str(resolved_artifact_paths.program_path.relative_to(tmp_path))
        compiled_paths.append(relative_program_path)
        artifact_dir = resolved_artifact_paths.artifact_dir
        artifact_dir.mkdir(parents=True, exist_ok=True)
        resolved_artifact_paths.program_path.write_text(
            '{"compiled": true}\n',
            encoding="utf-8",
        )
        return {
            "compiled_program": object(),
            "benchmark_summary": {"case_count": 1, "pass_rate": 1.0},
            "trainset_size": len(cast(list[Any], examples)),
        }

    monkeypatch.setattr("repo_rag_lab.dspy_training.configure_dspy_lm", fake_configure_dspy_lm)
    monkeypatch.setattr(
        "repo_rag_lab.dspy_training._compile_repository_program_artifact",
        fake_compile_repository_program_artifact,
    )

    result = train_repository_program(
        tmp_path,
        training_config=DSPyTrainingConfig(
            training_path=Path("samples/training/sample-training.yaml"),
            run_name="carry-forward-dirty-global",
            bundle_version="carry-forward-dirty-global",
            lineage_metadata={
                "family_state_path": "artifacts/trainer/family-state.json",
                "dirty_family_count": 1,
                "dirty_family_ids": ["pf-dirty"],
            },
        ),
        lm_config=DSPyLMConfig(model="openai/test-model"),
    )

    assert compiled_paths == [
        "artifacts/dspy/carry-forward-dirty-global/families/pf-dirty/program.json"
    ]
    carried_program_path = tmp_path / result.program_path
    assert carried_program_path.exists()
    assert (
        carried_program_path.read_text(encoding="utf-8") == '{"program":"previous-global-dirty"}\n'
    )
    metadata = json.loads((tmp_path / result.metadata_path).read_text(encoding="utf-8"))
    compiled_program_summary = metadata["compiled_program_summary"]
    assert compiled_program_summary["artifact_source"] == "carried-forward"
    assert metadata["training_examples_signature"] == training_signature
    assert metadata["benchmark_examples_signature"] == training_signature


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

        def __call__(self, *, question: str, **kwargs: object) -> object:
            del kwargs
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
