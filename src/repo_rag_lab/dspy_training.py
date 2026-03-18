"""DSPy training and artifact helpers for repository-grounded RAG."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast
from urllib.parse import urlparse

from .corpus import load_documents
from .retrieval import chunk_documents, retrieve
from .training_samples import TrainingExample, load_training_examples, validate_training_examples

try:
    import dspy as _dspy
except ImportError:  # pragma: no cover - optional dependency at import time
    _dspy = None

DEFAULT_DSPY_RUN_NAME = "repository-rag-default"
DEFAULT_OPENAI_MODEL = "openai/gpt-4o-mini"
DEFAULT_DSPY_MODEL = DEFAULT_OPENAI_MODEL
DEFAULT_TRAINING_PATH = Path("samples/training/repository_training_examples.yaml")
PROGRAM_FILENAME = "program.json"
METADATA_FILENAME = "metadata.json"


class ExampleLike(Protocol):
    """Minimal interface needed by the repository metric."""

    @property
    def answer(self) -> str: ...

    @property
    def expected_sources(self) -> Sequence[str]: ...


class PredictionLike(Protocol):
    """Minimal interface needed by the repository metric."""

    @property
    def answer(self) -> str: ...

    @property
    def context_sources(self) -> Sequence[str]: ...


class TrainsetExampleLike(Protocol):
    """Minimal DSPy example surface exercised by the tests."""

    def inputs(self) -> QuestionInputLike: ...

    def labels(self) -> AnswerLabelLike: ...


class QuestionInputLike(Protocol):
    """Minimal input view returned by ``dspy.Example.inputs()``."""

    question: str


class AnswerLabelLike(Protocol):
    """Minimal label view returned by ``dspy.Example.labels()``."""

    answer: str


class QuestionAnsweringProgram(Protocol):
    """Minimal callable program surface used by evaluation helpers."""

    def __call__(self, *, question: str) -> object: ...


class RepositoryProgram(QuestionAnsweringProgram, Protocol):
    """Minimal compiled-program surface used by the runtime and tests."""

    def save(
        self,
        path: str | Path,
        save_program: bool = False,
        modules_to_serialize: object | None = None,
    ) -> object: ...

    def load(self, path: str | Path, allow_pickle: bool = False) -> object: ...

    def dump_state(self) -> dict[str, object]: ...

    def get_lm(self) -> object: ...

    def set_lm(self, lm: object) -> object: ...


class OptimizerLike(Protocol):
    """Minimal optimizer surface shared by the supported DSPy optimizers."""

    def compile(
        self,
        program: RepositoryProgram,
        trainset: Sequence[TrainsetExampleLike],
        **kwargs: object,
    ) -> RepositoryProgram: ...


@dataclass(frozen=True)
class DSPyLMConfig:
    """Explicit LM configuration for DSPy runtime and training flows."""

    model: str
    api_key: str | None = None
    api_base: str | None = None
    api_version: str | None = None
    model_type: str = "chat"
    temperature: float | None = None
    max_tokens: int | None = None

    def as_metadata(self) -> dict[str, object]:
        """Return a JSON-safe, secret-free metadata view of the LM settings."""

        payload = asdict(self)
        payload.pop("api_key", None)
        return payload


@dataclass(frozen=True)
class DSPyTrainingConfig:
    """Configuration for compiling a repository-grounded DSPy program."""

    training_path: Path = DEFAULT_TRAINING_PATH
    run_name: str = DEFAULT_DSPY_RUN_NAME
    optimizer: str = "bootstrapfewshot"
    top_k: int = 4
    max_bootstrapped_demos: int = 2
    max_labeled_demos: int = 2
    mipro_auto: str = "light"
    num_threads: int = 4
    mipro_num_trials: int | None = None


@dataclass(frozen=True)
class DSPyArtifactPaths:
    """Resolved output paths for one compiled DSPy run."""

    artifact_dir: Path
    program_path: Path
    metadata_path: Path


@dataclass(frozen=True)
class DSPyTrainingResult:
    """Serializable summary of one DSPy training run."""

    run_name: str
    artifact_dir: str
    program_path: str
    metadata_path: str
    training_path: str
    optimizer: str
    training_example_count: int
    benchmark_summary: dict[str, object]
    lm_model: str

    def to_json(self) -> str:
        """Return the training result as indented JSON."""

        return json.dumps(asdict(self), indent=2)


@dataclass(frozen=True)
class _EvaluationCase:
    """Simple metric input used outside DSPy's trainset objects."""

    answer: str
    expected_sources: tuple[str, ...] = ()


def _require_dspy() -> ModuleType:
    if _dspy is None:  # pragma: no cover - exercised only when DSPy is absent
        raise RuntimeError(
            "DSPy is not installed in the active environment. Run `uv sync --extra azure` first."
        )
    return _dspy


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None


def _float_from_env(name: str) -> float | None:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return None
    return float(raw_value)


def _int_from_env(name: str) -> int | None:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return None
    return int(raw_value)


def _normalize_api_base(api_base: str | None) -> str | None:
    if api_base is None:
        return None
    cleaned = api_base.strip()
    if not cleaned:
        return None
    return cleaned.rstrip("/")


def _derive_azure_api_base(endpoint: str | None, chat_completions_uri: str | None) -> str | None:
    if endpoint and endpoint.strip():
        return _normalize_api_base(endpoint)
    if not chat_completions_uri or not chat_completions_uri.strip():
        return None
    parsed = urlparse(chat_completions_uri)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _sanitize_run_name(run_name: str) -> str:
    parts = [part for part in re.split(r"[^A-Za-z0-9._-]+", run_name.strip()) if part]
    if parts:
        return "-".join(parts)
    return DEFAULT_DSPY_RUN_NAME


def _normalize_text(text: str) -> str:
    return " ".join(text.casefold().split())


def _normalize_sources(values: Sequence[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return tuple(ordered)


def resolve_dspy_lm_config(
    *,
    model: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    api_version: str | None = None,
    model_type: str | None = "chat",
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> DSPyLMConfig | None:
    """Resolve DSPy LM configuration from explicit arguments and environment variables."""

    resolved_model_type = _first_non_empty(model_type, os.getenv("DSPY_MODEL_TYPE"), "chat")
    resolved_temperature = (
        temperature if temperature is not None else _float_from_env("DSPY_TEMPERATURE")
    )
    resolved_max_tokens = max_tokens if max_tokens is not None else _int_from_env("DSPY_MAX_TOKENS")
    resolved_api_key = _first_non_empty(api_key, os.getenv("DSPY_API_KEY"))
    resolved_api_base = _normalize_api_base(_first_non_empty(api_base, os.getenv("DSPY_API_BASE")))
    resolved_api_version = _first_non_empty(api_version, os.getenv("DSPY_API_VERSION"))
    resolved_model = _first_non_empty(model, os.getenv("DSPY_MODEL"))
    if resolved_model is not None:
        return DSPyLMConfig(
            model=resolved_model,
            api_key=resolved_api_key,
            api_base=resolved_api_base,
            api_version=resolved_api_version,
            model_type=resolved_model_type or "chat",
            temperature=resolved_temperature,
            max_tokens=resolved_max_tokens,
        )

    azure_api_base = _derive_azure_api_base(
        os.getenv("AZURE_OPENAI_ENDPOINT"),
        os.getenv("AZURE_OPENAI_CHAT_COMPLETIONS_URI"),
    )
    azure_deployment = _first_non_empty(os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"))
    azure_api_key = _first_non_empty(resolved_api_key, os.getenv("AZURE_OPENAI_API_KEY"))
    azure_api_version = _first_non_empty(
        resolved_api_version, os.getenv("AZURE_OPENAI_API_VERSION")
    )
    if azure_deployment is not None and azure_api_base is not None:
        return DSPyLMConfig(
            model=f"azure/{azure_deployment}",
            api_key=azure_api_key,
            api_base=azure_api_base,
            api_version=azure_api_version,
            model_type=resolved_model_type or "chat",
            temperature=resolved_temperature,
            max_tokens=resolved_max_tokens,
        )

    openai_api_key = _first_non_empty(resolved_api_key, os.getenv("OPENAI_API_KEY"))
    if openai_api_key is not None:
        return DSPyLMConfig(
            model=DEFAULT_OPENAI_MODEL,
            api_key=openai_api_key,
            api_base=resolved_api_base,
            api_version=resolved_api_version,
            model_type=resolved_model_type or "chat",
            temperature=resolved_temperature,
            max_tokens=resolved_max_tokens,
        )

    return None


def configure_dspy_lm(lm_config: DSPyLMConfig) -> object:
    """Build and globally configure the DSPy LM for this process."""

    dspy_module = _require_dspy()
    lm_kwargs: dict[str, object] = {}
    if lm_config.api_key is not None:
        lm_kwargs["api_key"] = lm_config.api_key
    if lm_config.api_base is not None:
        lm_kwargs["api_base"] = lm_config.api_base
    if lm_config.api_version is not None:
        lm_kwargs["api_version"] = lm_config.api_version
    lm = dspy_module.LM(
        lm_config.model,
        model_type=lm_config.model_type,
        temperature=lm_config.temperature,
        max_tokens=lm_config.max_tokens,
        **lm_kwargs,
    )
    dspy_module.configure(lm=lm)
    return lm


def resolve_dspy_artifact_paths(root: Path, run_name: str) -> DSPyArtifactPaths:
    """Resolve the artifact directory and file paths for a DSPy training run."""

    safe_run_name = _sanitize_run_name(run_name)
    artifact_dir = root / "artifacts" / "dspy" / safe_run_name
    return DSPyArtifactPaths(
        artifact_dir=artifact_dir,
        program_path=artifact_dir / PROGRAM_FILENAME,
        metadata_path=artifact_dir / METADATA_FILENAME,
    )


def latest_dspy_artifact_metadata(root: Path) -> Path | None:
    """Return the newest compiled-program metadata file under ``artifacts/dspy``."""

    artifact_root = root / "artifacts" / "dspy"
    if not artifact_root.exists():
        return None
    metadata_paths = list(artifact_root.glob(f"*/{METADATA_FILENAME}"))
    if not metadata_paths:
        return None
    return max(metadata_paths, key=lambda path: (path.stat().st_mtime_ns, str(path)))


def retrieve_repository_context(
    root: Path, question: str, *, top_k: int = 4
) -> tuple[list[str], list[str]]:
    """Return retrieved repository snippets plus their relative source paths."""

    documents = load_documents(root)
    chunks = chunk_documents(documents)
    retrieved_chunks = retrieve(question, chunks, top_k=top_k)
    context = [chunk.text for chunk in retrieved_chunks]
    context_sources = [str(chunk.source.relative_to(root)) for chunk in retrieved_chunks]
    return context, context_sources


def repository_answer_metric(
    example: ExampleLike, pred: PredictionLike, trace: object | None = None
) -> bool:
    """Score a repository RAG prediction against the expected answer and sources."""

    del trace
    expected_answer = _normalize_text(example.answer)
    predicted_answer = _normalize_text(pred.answer)
    answer_match = bool(predicted_answer) and (
        expected_answer in predicted_answer or predicted_answer in expected_answer
    )
    expected_sources = set(_normalize_sources(example.expected_sources))
    if not expected_sources:
        return answer_match
    matched_sources = expected_sources.intersection(_normalize_sources(pred.context_sources))
    return answer_match and bool(matched_sources)


if _dspy is not None:

    class RepositoryAnswerSignature(_dspy.Signature):
        """Answer a repository question using retrieved repository context."""

        question = _dspy.InputField()
        context = _dspy.InputField()
        answer = _dspy.OutputField()

    class RepositoryRAGProgram(_dspy.Module):
        """Repository-grounded DSPy module that performs retrieval before generation."""

        def __init__(self, root: Path, top_k: int = 4) -> None:
            super().__init__()
            self.root = root.resolve()
            self.top_k = top_k
            dspy_module = _dspy
            assert dspy_module is not None
            self.respond = dspy_module.ChainOfThought(RepositoryAnswerSignature)

        def forward(self, question: str) -> object:
            context, context_sources = retrieve_repository_context(
                self.root, question, top_k=self.top_k
            )
            dspy_module = _dspy
            assert dspy_module is not None
            prediction = self.respond(question=question, context=context)
            answer = str(getattr(prediction, "answer", ""))
            return dspy_module.Prediction(
                answer=answer,
                context=context,
                context_sources=context_sources,
            )


def build_repository_rag_program(
    root: Path,
    *,
    top_k: int = 4,
    program_path: Path | None = None,
    lm_config: DSPyLMConfig | None = None,
    require_configured_lm: bool = True,
) -> RepositoryProgram:
    """Instantiate a repository DSPy program, optionally loading a saved artifact."""

    _require_dspy()
    resolved_root = root.resolve()
    if program_path is not None:
        return load_compiled_repository_rag(
            program_path=program_path,
            root=resolved_root,
            top_k=top_k,
            lm_config=lm_config,
        )
    if lm_config is None and require_configured_lm:
        raise RuntimeError(
            "DSPy LM configuration is required. Pass CLI flags, export DSPY_* variables, "
            "or source the repository Azure/OpenAI environment before using DSPy."
        )
    if lm_config is not None:
        configure_dspy_lm(lm_config)
    return cast(RepositoryProgram, RepositoryRAGProgram(resolved_root, top_k=top_k))


def load_compiled_repository_rag(
    *,
    program_path: Path,
    root: Path,
    top_k: int = 4,
    lm_config: DSPyLMConfig | None = None,
) -> RepositoryProgram:
    """Load a previously compiled repository DSPy program from disk."""

    _require_dspy()
    resolved_program_path = program_path.resolve()
    if not resolved_program_path.exists():
        raise FileNotFoundError(f"Compiled DSPy program does not exist: {resolved_program_path}")
    if lm_config is not None:
        configure_dspy_lm(lm_config)
    program = RepositoryRAGProgram(root.resolve(), top_k=top_k)
    program.load(str(resolved_program_path), allow_pickle=False)
    return cast(RepositoryProgram, program)


def build_dspy_trainset(examples: Sequence[TrainingExample]) -> list[TrainsetExampleLike]:
    """Convert repository training examples into DSPy ``Example`` objects."""

    dspy_module = _require_dspy()
    trainset: list[TrainsetExampleLike] = []
    for example in examples:
        dspy_example = dspy_module.Example(
            question=example.question,
            answer=example.expected_answer,
            expected_sources=list(example.expected_sources),
        ).with_inputs("question")
        trainset.append(dspy_example)
    return trainset


def _build_optimizer(training_config: DSPyTrainingConfig) -> OptimizerLike:
    dspy_module = _require_dspy()
    optimizer_name = training_config.optimizer.casefold()
    if optimizer_name == "bootstrapfewshot":
        return dspy_module.BootstrapFewShot(
            metric=repository_answer_metric,
            max_bootstrapped_demos=training_config.max_bootstrapped_demos,
            max_labeled_demos=training_config.max_labeled_demos,
        )
    if optimizer_name == "miprov2":
        return dspy_module.MIPROv2(
            metric=repository_answer_metric,
            max_bootstrapped_demos=training_config.max_bootstrapped_demos,
            max_labeled_demos=training_config.max_labeled_demos,
            auto=training_config.mipro_auto,
            num_threads=training_config.num_threads,
        )
    raise ValueError(f"Unsupported DSPy optimizer: {training_config.optimizer}")


def evaluate_repository_program(
    program: QuestionAnsweringProgram, root: Path, examples: Sequence[TrainingExample]
) -> dict[str, object]:
    """Evaluate a compiled repository program against the repository training set."""

    results: list[dict[str, object]] = []
    pass_count = 0
    for example in examples:
        prediction = cast(PredictionLike, program(question=example.question))
        retrieved_sources = _normalize_sources(prediction.context_sources)
        matched_sources = tuple(
            source for source in retrieved_sources if source in set(example.expected_sources)
        )
        passed = repository_answer_metric(
            _EvaluationCase(
                answer=example.expected_answer,
                expected_sources=example.expected_sources,
            ),
            prediction,
        )
        if passed:
            pass_count += 1
        results.append(
            {
                "question": example.question,
                "expected_sources": list(example.expected_sources),
                "retrieved_sources": list(retrieved_sources),
                "matched_sources": list(matched_sources),
                "answer_preview": prediction.answer[:240],
                "passed": passed,
                "tags": list(example.tags),
            }
        )
    case_count = len(results)
    return {
        "case_count": case_count,
        "pass_count": pass_count,
        "pass_rate": (pass_count / case_count) if case_count else 0.0,
        "results": results,
        "root": str(root),
    }


def train_repository_program(
    root: Path,
    *,
    training_config: DSPyTrainingConfig,
    lm_config: DSPyLMConfig,
) -> DSPyTrainingResult:
    """Compile, persist, and summarize a repository-grounded DSPy program."""

    resolved_root = root.resolve()
    training_path = training_config.training_path
    if not training_path.is_absolute():
        training_path = resolved_root / training_path
    examples = load_training_examples(training_path)
    validation_issues = validate_training_examples(examples, root=resolved_root)
    if validation_issues:
        issues_text = "\n".join(f"- {issue}" for issue in validation_issues)
        raise ValueError(f"Training samples are invalid:\n{issues_text}")

    configure_dspy_lm(lm_config)
    trainset = build_dspy_trainset(examples)
    artifact_paths = resolve_dspy_artifact_paths(resolved_root, training_config.run_name)
    artifact_paths.artifact_dir.mkdir(parents=True, exist_ok=True)
    program = RepositoryRAGProgram(resolved_root, top_k=training_config.top_k)
    optimizer = _build_optimizer(training_config)
    if training_config.optimizer.casefold() == "miprov2":
        compiled_program = optimizer.compile(
            program,
            trainset=trainset,
            valset=trainset,
            num_trials=training_config.mipro_num_trials,
            max_bootstrapped_demos=training_config.max_bootstrapped_demos,
            max_labeled_demos=training_config.max_labeled_demos,
        )
    else:
        compiled_program = optimizer.compile(program, trainset=trainset)

    compiled_program.save(str(artifact_paths.program_path), save_program=False)
    benchmark_summary = evaluate_repository_program(compiled_program, resolved_root, examples)
    relative_program_path = str(artifact_paths.program_path.relative_to(resolved_root))
    relative_metadata_path = str(artifact_paths.metadata_path.relative_to(resolved_root))
    metadata = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "run_name": _sanitize_run_name(training_config.run_name),
        "artifact_dir": str(artifact_paths.artifact_dir.relative_to(resolved_root)),
        "program_path": relative_program_path,
        "metadata_path": relative_metadata_path,
        "training_path": str(training_path.relative_to(resolved_root)),
        "training_example_count": len(examples),
        "optimizer": training_config.optimizer,
        "top_k": training_config.top_k,
        "lm": lm_config.as_metadata(),
        "benchmark_summary": benchmark_summary,
        "compiled_program_summary": {
            "program_type": compiled_program.__class__.__name__,
            "trainset_size": len(trainset),
            "top_k": training_config.top_k,
        },
    }
    artifact_paths.metadata_path.write_text(
        f"{json.dumps(metadata, indent=2)}\n",
        encoding="utf-8",
    )
    return DSPyTrainingResult(
        run_name=_sanitize_run_name(training_config.run_name),
        artifact_dir=str(artifact_paths.artifact_dir.relative_to(resolved_root)),
        program_path=relative_program_path,
        metadata_path=relative_metadata_path,
        training_path=str(training_path.relative_to(resolved_root)),
        optimizer=training_config.optimizer,
        training_example_count=len(examples),
        benchmark_summary=benchmark_summary,
        lm_model=lm_config.model,
    )
