"""DSPy training and artifact helpers for repository-grounded RAG."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast
from urllib.parse import urlparse

from .corpus import load_documents
from .retrieval import RetrievalMode, chunk_documents, resolve_retrieval_mode, retrieve
from .retrieval_profile import load_retrieval_profile
from .runtime_artifacts import write_bundle_manifest
from .training_samples import (
    TrainingExample,
    load_family_state_payload,
    load_training_examples,
    normalize_training_examples,
    validate_training_examples,
)

try:
    import dspy as _dspy
except ImportError:  # pragma: no cover - optional dependency at import time
    _dspy = None

DEFAULT_DSPY_RUN_NAME = "repository-rag-default"
DEFAULT_OPENAI_MODEL = "openai/gpt-4o-mini"
DEFAULT_DSPY_MODEL = DEFAULT_OPENAI_MODEL
DSPY_HELPER_SCOPE = "helper"
DSPY_TRAINER_SCOPE = "trainer"
DEFAULT_DSPY_HELPER_MODEL = "azure/gpt-5.4-nano"
DEFAULT_DSPY_TRAINER_MODEL = "azure/gpt-5.4-mini"
DEFAULT_TRAINING_PATH = Path("samples/training/repository_training_examples.yaml")
PROGRAM_FILENAME = "program.json"
METADATA_FILENAME = "metadata.json"
DSPY_ARTIFACTS_DIR = Path("artifacts/dspy")


class ExampleLike(Protocol):
    """Minimal interface needed by the repository metric."""

    @property
    def answer(self) -> str: ...

    @property
    def expected_sources(self) -> Sequence[str]: ...

    @property
    def benchmark_context(self) -> Sequence[str]: ...


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

    def __call__(self, *, question: str, **kwargs: object) -> object: ...


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

    def answer_from_context(
        self,
        *,
        question: str,
        context: Sequence[str],
        context_sources: Sequence[str],
        original_prompt: str | None = None,
        reformulated_prompt: str | None = None,
        command_trace: Sequence[Mapping[str, object]] = (),
    ) -> object: ...


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
    benchmark_path: Path | None = None
    run_name: str = DEFAULT_DSPY_RUN_NAME
    bundle_version: str | None = None
    run_family: str | None = None
    lineage_metadata: Mapping[str, object] | None = None
    optimizer: str = "bootstrapfewshot"
    top_k: int = 4
    retrieval_mode: RetrievalMode | None = None
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
class DSPyFamilyArtifactResult:
    """Serializable summary of one family-scoped DSPy runtime artifact."""

    prompt_family_id: str
    artifact_dir: str
    program_path: str
    metadata_path: str
    optimizer: str
    training_example_count: int
    benchmark_example_count: int
    benchmark_summary: dict[str, object]
    hit_rate: float | None = None
    artifact_ready: bool = True
    artifact_source: str = "recompiled"

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DSPyTrainingResult:
    """Serializable summary of one DSPy training run."""

    run_name: str
    run_family: str | None
    artifact_dir: str
    program_path: str
    metadata_path: str
    training_path: str
    benchmark_path: str
    optimizer: str
    training_example_count: int
    benchmark_example_count: int
    benchmark_summary: dict[str, object]
    lm_model: str
    bundle_path: str | None = None
    bundle_version: str | None = None
    lineage_metadata: dict[str, object] | None = None

    def to_payload(self) -> dict[str, object]:
        """Return the training result as a machine-readable payload."""

        payload = asdict(self)
        input_paths = [self.training_path]
        if self.benchmark_path and self.benchmark_path not in input_paths:
            input_paths.append(self.benchmark_path)
        payload["artifact_metadata"] = {
            "input_paths": input_paths,
            "generated_paths": [
                self.artifact_dir,
                self.program_path,
                self.metadata_path,
                *([self.bundle_path] if self.bundle_path else []),
            ],
            "related_paths": ["samples/training/repository_training_examples.yaml"],
        }
        return payload

    def to_json(self) -> str:
        """Return the training result as indented JSON."""

        return json.dumps(self.to_payload(), indent=2)


@dataclass(frozen=True)
class _EvaluationCase:
    """Simple metric input used outside DSPy's trainset objects."""

    answer: str
    expected_sources: tuple[str, ...] = ()
    benchmark_context: tuple[str, ...] = ()


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


def _scoped_env_name(scope: str, suffix: str) -> str:
    return f"DSPY_{scope.upper()}_{suffix}"


def _first_non_empty_env(*names: str) -> str | None:
    return _first_non_empty(*(os.getenv(name) for name in names))


def _float_from_env_names(*names: str) -> float | None:
    for name in names:
        raw_value = os.getenv(name)
        if raw_value is None or not raw_value.strip():
            continue
        return float(raw_value)
    return None


def _int_from_env_names(*names: str) -> int | None:
    for name in names:
        raw_value = os.getenv(name)
        if raw_value is None or not raw_value.strip():
            continue
        return int(raw_value)
    return None


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


def _normalize_context_rows(values: Sequence[str]) -> tuple[str, ...]:
    """Return stable ordered non-empty benchmark-context rows."""

    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value).strip()
        if not cleaned:
            continue
        folded = cleaned.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        ordered.append(cleaned)
    return tuple(ordered)


def _answer_overlap_score(expected_answer: str, predicted_answer: str) -> float:
    """Return a simple token-overlap score for repository answer paraphrases."""

    expected_tokens = set(re.findall(r"[a-z0-9]+", _normalize_text(expected_answer)))
    predicted_tokens = set(re.findall(r"[a-z0-9]+", _normalize_text(predicted_answer)))
    if not expected_tokens or not predicted_tokens:
        return 0.0
    return len(expected_tokens.intersection(predicted_tokens)) / min(
        len(expected_tokens),
        len(predicted_tokens),
    )


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
    azure_api_base = _derive_azure_api_base(
        os.getenv("AZURE_OPENAI_ENDPOINT"),
        os.getenv("AZURE_OPENAI_CHAT_COMPLETIONS_URI"),
    )
    azure_api_key = _first_non_empty(resolved_api_key, os.getenv("AZURE_OPENAI_API_KEY"))
    azure_api_version = _first_non_empty(
        resolved_api_version, os.getenv("AZURE_OPENAI_API_VERSION")
    )
    openai_api_key = _first_non_empty(resolved_api_key, os.getenv("OPENAI_API_KEY"))
    if resolved_model is not None:
        normalized_model = resolved_model.strip()
        lowered_model = normalized_model.casefold()
        effective_api_key = resolved_api_key
        effective_api_base = resolved_api_base
        effective_api_version = resolved_api_version
        if lowered_model.startswith("azure/"):
            effective_api_key = azure_api_key
            effective_api_base = _normalize_api_base(
                _first_non_empty(resolved_api_base, azure_api_base)
            )
            effective_api_version = azure_api_version
        elif lowered_model.startswith("openai/"):
            effective_api_key = openai_api_key
        return DSPyLMConfig(
            model=normalized_model,
            api_key=effective_api_key,
            api_base=effective_api_base,
            api_version=effective_api_version,
            model_type=resolved_model_type or "chat",
            temperature=resolved_temperature,
            max_tokens=resolved_max_tokens,
        )
    azure_deployment = _first_non_empty(os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"))
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


def _resolve_scoped_dspy_lm_config(
    scope: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    api_version: str | None = None,
    model_type: str | None = "chat",
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> DSPyLMConfig | None:
    scoped_model = _scoped_env_name(scope, "MODEL")
    scoped_api_key = _scoped_env_name(scope, "API_KEY")
    scoped_api_base = _scoped_env_name(scope, "API_BASE")
    scoped_api_version = _scoped_env_name(scope, "API_VERSION")
    scoped_model_type = _scoped_env_name(scope, "MODEL_TYPE")
    scoped_temperature = _scoped_env_name(scope, "TEMPERATURE")
    scoped_max_tokens = _scoped_env_name(scope, "MAX_TOKENS")

    default_model_by_scope = {
        DSPY_HELPER_SCOPE: DEFAULT_DSPY_HELPER_MODEL,
        DSPY_TRAINER_SCOPE: DEFAULT_DSPY_TRAINER_MODEL,
    }
    resolved_model_type = _first_non_empty(
        model_type,
        _first_non_empty_env(scoped_model_type, "DSPY_MODEL_TYPE"),
        "chat",
    )
    resolved_temperature = (
        temperature
        if temperature is not None
        else _float_from_env_names(scoped_temperature, "DSPY_TEMPERATURE")
    )
    resolved_max_tokens = (
        max_tokens
        if max_tokens is not None
        else _int_from_env_names(scoped_max_tokens, "DSPY_MAX_TOKENS")
    )
    resolved_api_key = _first_non_empty(
        api_key,
        _first_non_empty_env(scoped_api_key, "DSPY_API_KEY"),
    )
    resolved_api_base = _normalize_api_base(
        _first_non_empty(
            api_base,
            _first_non_empty_env(scoped_api_base, "DSPY_API_BASE"),
        )
    )
    resolved_api_version = _first_non_empty(
        api_version,
        _first_non_empty_env(scoped_api_version, "DSPY_API_VERSION"),
    )
    resolved_model = _first_non_empty(
        model,
        _first_non_empty_env(scoped_model, "DSPY_MODEL"),
        default_model_by_scope.get(scope),
    )
    if resolved_model is None:
        return None

    azure_api_base = _derive_azure_api_base(
        os.getenv("AZURE_OPENAI_ENDPOINT"),
        os.getenv("AZURE_OPENAI_CHAT_COMPLETIONS_URI"),
    )
    azure_api_key = _first_non_empty(resolved_api_key, os.getenv("AZURE_OPENAI_API_KEY"))
    azure_api_version = _first_non_empty(
        resolved_api_version, os.getenv("AZURE_OPENAI_API_VERSION")
    )
    openai_api_key = _first_non_empty(resolved_api_key, os.getenv("OPENAI_API_KEY"))

    normalized_model = resolved_model.strip()
    lowered_model = normalized_model.casefold()
    effective_api_key = resolved_api_key
    effective_api_base = resolved_api_base
    effective_api_version = resolved_api_version
    if lowered_model.startswith("azure/"):
        effective_api_key = azure_api_key
        effective_api_base = _normalize_api_base(
            _first_non_empty(resolved_api_base, azure_api_base)
        )
        effective_api_version = azure_api_version
    elif lowered_model.startswith("openai/"):
        effective_api_key = openai_api_key

    return DSPyLMConfig(
        model=normalized_model,
        api_key=effective_api_key,
        api_base=effective_api_base,
        api_version=effective_api_version,
        model_type=resolved_model_type or "chat",
        temperature=resolved_temperature,
        max_tokens=resolved_max_tokens,
    )


def resolve_dspy_helper_lm_config(
    *,
    model: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    api_version: str | None = None,
    model_type: str | None = "chat",
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> DSPyLMConfig | None:
    """Resolve the DSPy LM configuration for helper/runtime mediation calls."""

    return _resolve_scoped_dspy_lm_config(
        DSPY_HELPER_SCOPE,
        model=model,
        api_key=api_key,
        api_base=api_base,
        api_version=api_version,
        model_type=model_type,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def resolve_dspy_trainer_lm_config(
    *,
    model: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    api_version: str | None = None,
    model_type: str | None = "chat",
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> DSPyLMConfig | None:
    """Resolve the DSPy LM configuration for trainer-side compile/recompile work."""

    return _resolve_scoped_dspy_lm_config(
        DSPY_TRAINER_SCOPE,
        model=model,
        api_key=api_key,
        api_base=api_base,
        api_version=api_version,
        model_type=model_type,
        temperature=temperature,
        max_tokens=max_tokens,
    )


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
    artifact_dir = root / DSPY_ARTIFACTS_DIR / safe_run_name
    return DSPyArtifactPaths(
        artifact_dir=artifact_dir,
        program_path=artifact_dir / PROGRAM_FILENAME,
        metadata_path=artifact_dir / METADATA_FILENAME,
    )


def resolve_family_dspy_artifact_paths(
    root: Path,
    *,
    run_name: str,
    prompt_family_id: str,
) -> DSPyArtifactPaths:
    """Resolve the artifact directory and file paths for one family-scoped DSPy artifact."""

    safe_run_name = _sanitize_run_name(run_name)
    safe_family_id = _sanitize_run_name(prompt_family_id)
    artifact_dir = root / DSPY_ARTIFACTS_DIR / safe_run_name / "families" / safe_family_id
    return DSPyArtifactPaths(
        artifact_dir=artifact_dir,
        program_path=artifact_dir / PROGRAM_FILENAME,
        metadata_path=artifact_dir / METADATA_FILENAME,
    )


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _training_examples_signature(examples: Sequence[TrainingExample]) -> str:
    """Return a stable compile-facing signature for one ordered example set."""

    payload = json.dumps(
        [asdict(example) for example in examples],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def load_dspy_artifact_metadata(metadata_path: Path) -> dict[str, object]:
    """Load one DSPy artifact metadata payload from disk."""

    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"DSPy artifact metadata must be a JSON object: {metadata_path}")
    return payload


def list_dspy_artifacts(root: Path) -> list[dict[str, object]]:
    """Return compiled DSPy run summaries ordered newest-first."""

    resolved_root = root.resolve()
    artifact_root = resolved_root / DSPY_ARTIFACTS_DIR
    if not artifact_root.exists():
        return []

    runs: list[dict[str, object]] = []
    for metadata_path in artifact_root.glob(f"*/{METADATA_FILENAME}"):
        metadata = load_dspy_artifact_metadata(metadata_path)
        bundle_summary = write_bundle_manifest(resolved_root, metadata_path)
        program_path_value = metadata.get("program_path")
        if isinstance(program_path_value, str) and program_path_value.strip():
            resolved_program_path = Path(program_path_value)
            if not resolved_program_path.is_absolute():
                resolved_program_path = resolved_root / resolved_program_path
        else:
            resolved_program_path = metadata_path.parent / PROGRAM_FILENAME
        benchmark_summary = metadata.get("benchmark_summary")
        compiled_program_summary = metadata.get("compiled_program_summary")
        benchmark_pass_rate = None
        benchmark_case_count = None
        if isinstance(benchmark_summary, dict):
            benchmark_pass_rate = benchmark_summary.get("pass_rate")
            benchmark_case_count = benchmark_summary.get("case_count")
        runs.append(
            {
                "run_name": metadata.get("run_name", metadata_path.parent.name),
                "recorded_at": metadata.get("recorded_at"),
                "artifact_dir": _relative_to_root(metadata_path.parent, resolved_root),
                "metadata_path": _relative_to_root(metadata_path, resolved_root),
                "program_path": _relative_to_root(resolved_program_path, resolved_root),
                "program_exists": resolved_program_path.exists(),
                "training_path": metadata.get("training_path"),
                "optimizer": metadata.get("optimizer"),
                "training_example_count": metadata.get("training_example_count"),
                "benchmark_pass_rate": benchmark_pass_rate,
                "benchmark_case_count": benchmark_case_count,
                "benchmark_summary": benchmark_summary
                if isinstance(benchmark_summary, dict)
                else None,
                "compiled_program_summary": (
                    compiled_program_summary if isinstance(compiled_program_summary, dict) else None
                ),
                "lm": metadata.get("lm") if isinstance(metadata.get("lm"), dict) else None,
                "bundle_path": bundle_summary.get("bundle_path"),
                "bundle_version": bundle_summary.get("bundle_version"),
                "bundle_status": bundle_summary.get("bundle_status"),
                "bundle_benchmark_status": bundle_summary.get("benchmark_status"),
                "bundle_summary": bundle_summary,
            }
        )

    return sorted(
        runs,
        key=lambda run: (
            str(run.get("recorded_at") or ""),
            str(run.get("metadata_path") or ""),
        ),
        reverse=True,
    )


def latest_dspy_artifact_summary(root: Path) -> dict[str, object] | None:
    """Return the newest compiled DSPy run summary."""

    runs = list_dspy_artifacts(root.resolve())
    if not runs:
        return None
    return runs[0]


def latest_dspy_artifact_metadata(root: Path) -> Path | None:
    """Return the newest compiled-program metadata file under ``artifacts/dspy``."""

    latest_run = latest_dspy_artifact_summary(root.resolve())
    if latest_run is None:
        return None
    metadata_path_value = latest_run.get("metadata_path")
    if not isinstance(metadata_path_value, str) or not metadata_path_value.strip():
        return None
    resolved_metadata_path = Path(metadata_path_value)
    if not resolved_metadata_path.is_absolute():
        resolved_metadata_path = root.resolve() / resolved_metadata_path
    return resolved_metadata_path


def resolve_dspy_program_path(root: Path, program_path: Path | None = None) -> Path | None:
    """Resolve an explicit or latest compiled DSPy program path."""

    if program_path is not None:
        return program_path.resolve()
    latest_run = latest_dspy_artifact_summary(root.resolve())
    if latest_run is None:
        return None
    program_path_value = latest_run.get("program_path")
    if not isinstance(program_path_value, str) or not program_path_value.strip():
        return None
    resolved_program_path = Path(program_path_value)
    if not resolved_program_path.is_absolute():
        resolved_program_path = root.resolve() / resolved_program_path
    return resolved_program_path


def describe_dspy_artifacts(root: Path) -> dict[str, object]:
    """Summarize all compiled DSPy artifacts under ``artifacts/dspy``."""

    runs = list_dspy_artifacts(root.resolve())
    latest_run = runs[0] if runs else None
    return {
        "artifact_root": str(DSPY_ARTIFACTS_DIR),
        "run_count": len(runs),
        "latest_run_name": latest_run.get("run_name") if latest_run is not None else None,
        "latest_metadata_path": latest_run.get("metadata_path") if latest_run is not None else None,
        "latest_program_path": latest_run.get("program_path") if latest_run is not None else None,
        "latest_bundle_path": latest_run.get("bundle_path") if latest_run is not None else None,
        "latest_bundle_version": latest_run.get("bundle_version")
        if latest_run is not None
        else None,
        "runs": runs,
    }


def retrieve_repository_context(
    root: Path,
    question: str,
    *,
    top_k: int = 4,
    retrieval_mode: RetrievalMode | None = None,
) -> tuple[list[str], list[str]]:
    """Return retrieved repository snippets plus their relative source paths."""

    documents = load_documents(root)
    chunks = chunk_documents(documents)
    profile = load_retrieval_profile(root)
    retrieved_chunks = retrieve(
        question,
        chunks,
        top_k=top_k,
        profile=profile,
        retrieval_mode=retrieval_mode,
        root=root,
    )
    context = [chunk.text for chunk in retrieved_chunks]
    context_sources = [str(chunk.source) for chunk in retrieved_chunks]
    return context, context_sources


def _format_generation_context(context: Sequence[str], context_sources: Sequence[str]) -> list[str]:
    """Attach source paths to DSPy generation context so file/path answers stay grounded."""

    formatted: list[str] = []
    for text, source in zip(context, context_sources, strict=False):
        normalized_text = str(text).strip()
        normalized_source = str(source).strip()
        if normalized_source and normalized_text:
            formatted.append(f"Source: {normalized_source}\n\n{normalized_text}")
        elif normalized_source:
            formatted.append(f"Source: {normalized_source}")
        elif normalized_text:
            formatted.append(normalized_text)
    if len(context) > len(formatted):
        formatted.extend(
            str(text).strip() for text in context[len(formatted) :] if str(text).strip()
        )
    return formatted


def _command_trace_prompt_text(command_trace: Sequence[Mapping[str, object]]) -> str:
    """Return a stable readable command-trace block for DSPy prompt composition."""

    rows: list[str] = []
    for step in command_trace:
        role = " ".join(str(step.get("role") or "").strip().split())
        step_type = " ".join(str(step.get("type") or "").strip().split())
        text = " ".join(
            str(
                step.get("text")
                or step.get("command")
                or step.get("summary")
                or step.get("output")
                or ""
            )
            .strip()
            .split()
        )
        if role and text:
            rows.append(f"{role}: {text}")
        elif step_type and text:
            rows.append(f"{step_type}: {text}")
        elif text:
            rows.append(text)
    return "\n".join(rows).strip()


def _compose_repository_question(
    question: str,
    *,
    original_prompt: str = "",
    reformulated_prompt: str = "",
    command_trace: Sequence[Mapping[str, object]] = (),
) -> str:
    """Return the DSPy-facing question text with prompt-lineage context when available."""

    normalized_question = " ".join(str(question or "").strip().split())
    normalized_original = " ".join(str(original_prompt or "").strip().split())
    normalized_reformulated = " ".join(str(reformulated_prompt or "").strip().split())
    trace_text = _command_trace_prompt_text(command_trace)
    if (
        not trace_text
        and (
            not normalized_original
            or normalized_original.casefold() == normalized_question.casefold()
        )
        and (
            not normalized_reformulated
            or normalized_reformulated.casefold() == normalized_question.casefold()
        )
    ):
        return normalized_question or normalized_reformulated or normalized_original
    primary_question = normalized_question or normalized_reformulated or normalized_original
    sections = [f"Question: {primary_question}"]
    if normalized_original and normalized_original.casefold() != normalized_question.casefold():
        sections.append(f"Original prompt: {normalized_original}")
    if (
        normalized_reformulated
        and normalized_reformulated.casefold() != normalized_question.casefold()
    ):
        sections.append(f"Reformulated prompt: {normalized_reformulated}")
    if trace_text:
        sections.append(f"Command trace:\n{trace_text}")
    return "\n\n".join(section for section in sections if section.strip())


def repository_answer_metric(
    example: ExampleLike, pred: PredictionLike, trace: object | None = None
) -> bool:
    """Score a repository RAG prediction against the expected answer and sources."""

    del trace
    expected_answer = _normalize_text(example.answer)
    predicted_answer = _normalize_text(pred.answer)
    answer_match = bool(predicted_answer) and (
        expected_answer in predicted_answer
        or predicted_answer in expected_answer
        or _answer_overlap_score(expected_answer, predicted_answer) >= 0.6
    )
    expected_sources = set(_normalize_sources(example.expected_sources))
    benchmark_context = _normalize_context_rows(getattr(example, "benchmark_context", ()))
    context_grounded_match = False
    if benchmark_context and predicted_answer:
        context_reference = _normalize_text("\n".join(benchmark_context))
        context_grounded_match = (
            predicted_answer in context_reference
            or _answer_overlap_score(context_reference, predicted_answer) >= 0.55
        )
    if not expected_sources:
        if benchmark_context:
            return answer_match or context_grounded_match
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

        def __init__(
            self,
            root: Path,
            top_k: int = 4,
            *,
            retrieval_mode: RetrievalMode | None = None,
        ) -> None:
            super().__init__()
            self.root = root.resolve()
            self.top_k = top_k
            self.retrieval_mode: RetrievalMode = resolve_retrieval_mode(
                load_retrieval_profile(self.root),
                retrieval_mode,
            )
            dspy_module = _dspy
            assert dspy_module is not None
            self.respond = dspy_module.ChainOfThought(RepositoryAnswerSignature)

        def forward(
            self,
            question: str,
            *,
            original_prompt: str | None = None,
            reformulated_prompt: str | None = None,
            command_trace: Sequence[Mapping[str, object]] = (),
        ) -> object:
            retrieval_question = " ".join(
                str(reformulated_prompt or question or original_prompt or "").strip().split()
            )
            context, context_sources = retrieve_repository_context(
                self.root,
                retrieval_question or question,
                top_k=self.top_k,
                retrieval_mode=self.retrieval_mode,
            )
            return self.answer_from_context(
                question=question,
                context=context,
                context_sources=context_sources,
                original_prompt=original_prompt,
                reformulated_prompt=reformulated_prompt,
                command_trace=command_trace,
            )

        def answer_from_context(
            self,
            *,
            question: str,
            context: Sequence[str],
            context_sources: Sequence[str],
            original_prompt: str | None = None,
            reformulated_prompt: str | None = None,
            command_trace: Sequence[Mapping[str, object]] = (),
        ) -> object:
            generation_context = _format_generation_context(context, context_sources)
            dspy_module = _dspy
            assert dspy_module is not None
            generation_question = _compose_repository_question(
                question,
                original_prompt=original_prompt or "",
                reformulated_prompt=reformulated_prompt or "",
                command_trace=command_trace,
            )
            prediction = self.respond(question=generation_question, context=generation_context)
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
    retrieval_mode: RetrievalMode | None = None,
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
            retrieval_mode=retrieval_mode,
        )
    if lm_config is None and require_configured_lm:
        raise RuntimeError(
            "DSPy LM configuration is required. Pass CLI flags, export DSPY_* variables, "
            "or source the repository Azure/OpenAI environment before using DSPy."
        )
    if lm_config is not None:
        configure_dspy_lm(lm_config)
    return cast(
        RepositoryProgram,
        RepositoryRAGProgram(resolved_root, top_k=top_k, retrieval_mode=retrieval_mode),
    )


def load_compiled_repository_rag(
    *,
    program_path: Path,
    root: Path,
    top_k: int = 4,
    lm_config: DSPyLMConfig | None = None,
    retrieval_mode: RetrievalMode | None = None,
) -> RepositoryProgram:
    """Load a previously compiled repository DSPy program from disk."""

    _require_dspy()
    resolved_program_path = program_path.resolve()
    if not resolved_program_path.exists():
        raise FileNotFoundError(f"Compiled DSPy program does not exist: {resolved_program_path}")
    if lm_config is not None:
        configure_dspy_lm(lm_config)
    program = RepositoryRAGProgram(root.resolve(), top_k=top_k, retrieval_mode=retrieval_mode)
    program.load(str(resolved_program_path), allow_pickle=False)
    return cast(RepositoryProgram, program)


def build_dspy_trainset(examples: Sequence[TrainingExample]) -> list[TrainsetExampleLike]:
    """Convert repository training examples into DSPy ``Example`` objects."""

    dspy_module = _require_dspy()
    trainset: list[TrainsetExampleLike] = []
    for example in examples:
        dspy_example = dspy_module.Example(
            question=_compose_repository_question(
                example.question,
                original_prompt=example.original_prompt,
                reformulated_prompt=example.reformulated_prompt,
                command_trace=example.command_trace,
            ),
            answer=example.expected_answer,
            expected_sources=list(example.expected_sources),
            benchmark_context=list(example.benchmark_context),
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
    skipped_count = 0
    for example in examples:
        if (
            "trainer-candidate" in example.tags
            and not example.expected_sources
            and not example.benchmark_context
        ):
            skipped_count += 1
            results.append(
                {
                    "question": example.question,
                    "expected_sources": list(example.expected_sources),
                    "benchmark_context_sources": list(example.benchmark_context_sources),
                    "retrieved_sources": [],
                    "matched_sources": [],
                    "answer_preview": "",
                    "passed": None,
                    "skipped": True,
                    "skip_reason": "missing-benchmark-context",
                    "tags": list(example.tags),
                }
            )
            continue
        if example.benchmark_context and hasattr(program, "answer_from_context"):
            repository_program = cast(RepositoryProgram, program)
            try:
                prediction = cast(
                    PredictionLike,
                    repository_program.answer_from_context(
                        question=example.question,
                        context=example.benchmark_context,
                        context_sources=example.benchmark_context_sources,
                        original_prompt=example.original_prompt or None,
                        reformulated_prompt=example.reformulated_prompt or None,
                        command_trace=example.command_trace,
                    ),
                )
            except TypeError:
                prediction = cast(
                    PredictionLike,
                    repository_program.answer_from_context(
                        question=example.question,
                        context=example.benchmark_context,
                        context_sources=example.benchmark_context_sources,
                    ),
                )
        else:
            try:
                prediction = cast(
                    PredictionLike,
                    program(
                        question=example.question,
                        original_prompt=example.original_prompt or None,
                        reformulated_prompt=example.reformulated_prompt or None,
                        command_trace=example.command_trace,
                    ),
                )
            except TypeError:
                prediction = cast(PredictionLike, program(question=example.question))
        retrieved_sources = _normalize_sources(prediction.context_sources)
        matched_sources = tuple(
            source for source in retrieved_sources if source in set(example.expected_sources)
        )
        passed = repository_answer_metric(
            _EvaluationCase(
                answer=example.expected_answer,
                expected_sources=example.expected_sources,
                benchmark_context=example.benchmark_context,
            ),
            prediction,
        )
        if passed:
            pass_count += 1
        results.append(
            {
                "question": example.question,
                "expected_sources": list(example.expected_sources),
                "benchmark_context_sources": list(example.benchmark_context_sources),
                "retrieved_sources": list(retrieved_sources),
                "matched_sources": list(matched_sources),
                "answer_preview": prediction.answer[:240],
                "passed": passed,
                "skipped": False,
                "skip_reason": None,
                "tags": list(example.tags),
            }
        )
    case_count = len(results) - skipped_count
    return {
        "case_count": case_count,
        "pass_count": pass_count,
        "pass_rate": (pass_count / case_count) if case_count else 0.0,
        "skipped_count": skipped_count,
        "results": results,
        "root": str(root),
    }


def _family_candidate_records(payload: Mapping[str, object]) -> list[dict[str, object]]:
    """Return stable unique candidate records for one persisted prompt family."""

    records: list[dict[str, object]] = []
    seen: set[str] = set()

    def _append_record(record: object) -> None:
        if not isinstance(record, Mapping):
            return
        normalized = {str(key): value for key, value in record.items()}
        identity = str(normalized.get("exact_snapshot_id") or "").strip()
        if not identity:
            identity = json.dumps(
                normalized,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        if identity in seen:
            return
        seen.add(identity)
        records.append(normalized)

    raw_family_records = payload.get("family_records")
    if isinstance(raw_family_records, list):
        for record in raw_family_records:
            _append_record(record)
    raw_context_groups = payload.get("context_groups")
    if isinstance(raw_context_groups, list):
        for group in raw_context_groups:
            if not isinstance(group, Mapping):
                continue
            _append_record(group.get("champion_record"))
    _append_record(payload.get("family_runtime_record"))
    _append_record(payload.get("family_father_record"))
    _append_record(payload.get("family_champion_record"))
    return records


def _family_examples_from_payload(payload: Mapping[str, object]) -> list[TrainingExample]:
    """Return normalized DSPy training examples for one persisted prompt family."""

    candidate_records = _family_candidate_records(payload)
    if not candidate_records:
        return []
    return normalize_training_examples(candidate_records)


def _compile_repository_program_artifact(
    root: Path,
    *,
    artifact_paths: DSPyArtifactPaths,
    examples: Sequence[TrainingExample],
    benchmark_examples: Sequence[TrainingExample],
    training_config: DSPyTrainingConfig,
    lm_config: DSPyLMConfig,
) -> dict[str, object]:
    """Compile one DSPy repository program artifact and write its metadata."""

    resolved_root = root.resolve()
    artifact_paths.artifact_dir.mkdir(parents=True, exist_ok=True)
    program = RepositoryRAGProgram(
        resolved_root,
        top_k=training_config.top_k,
        retrieval_mode=training_config.retrieval_mode,
    )
    optimizer = _build_optimizer(training_config)
    trainset = build_dspy_trainset(examples)
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
    benchmark_summary = evaluate_repository_program(
        compiled_program,
        resolved_root,
        benchmark_examples,
    )
    return {
        "compiled_program": compiled_program,
        "benchmark_summary": benchmark_summary,
        "trainset_size": len(trainset),
    }


def _load_previous_family_artifact_registry(root: Path) -> dict[str, dict[str, object]]:
    """Return the latest persisted family-artifact registry when one is available."""

    latest_metadata_path = latest_dspy_artifact_metadata(root)
    if latest_metadata_path is None or not latest_metadata_path.is_file():
        return {}
    metadata = load_dspy_artifact_metadata(latest_metadata_path)
    registry = metadata.get("family_artifact_registry")
    if not isinstance(registry, Mapping):
        return {}
    normalized_registry: dict[str, dict[str, object]] = {}
    for family_id, payload in registry.items():
        if not isinstance(payload, Mapping):
            continue
        normalized_registry[str(family_id)] = {str(key): value for key, value in payload.items()}
    return normalized_registry


def _artifact_path_exists(root: Path, path_text: object) -> bool:
    """Return whether one artifact path resolves to an existing local file."""

    cleaned = str(path_text or "").strip()
    if not cleaned:
        return False
    resolved_path = Path(cleaned)
    if not resolved_path.is_absolute():
        resolved_path = root / resolved_path
    return resolved_path.is_file()


def _lineage_has_dirty_families(lineage_metadata: Mapping[str, object] | None) -> bool:
    """Return whether one lineage payload reports any dirty prompt families."""

    if not isinstance(lineage_metadata, Mapping):
        return False
    dirty_family_count = lineage_metadata.get("dirty_family_count")
    if isinstance(dirty_family_count, int) and dirty_family_count > 0:
        return True
    dirty_family_ids = lineage_metadata.get("dirty_family_ids")
    return isinstance(dirty_family_ids, list) and bool(dirty_family_ids)


def _family_artifact_payload_is_usable(root: Path, payload: Mapping[str, object]) -> bool:
    """Return whether one carried-forward family artifact still has a runnable local program."""

    if not bool(payload.get("artifact_ready", True)):
        return False
    return _artifact_path_exists(root, payload.get("program_path"))


def _update_family_artifact_state(
    family_payload: dict[str, object],
    artifact_payload: Mapping[str, object],
) -> None:
    """Persist the current family runtime artifact summary back into family state."""

    family_payload["family_runtime_artifact"] = {
        str(key): value for key, value in artifact_payload.items()
    }
    family_payload["family_needs_recompile"] = False


def _family_runtime_hit_rate(family_payload: Mapping[str, object]) -> float | None:
    """Return the family runtime hit-rate baseline aligned to trace metric-1."""

    runtime_record = family_payload.get("family_runtime_record")
    if not isinstance(runtime_record, Mapping):
        return None
    metric_ratio = runtime_record.get("metric_ratio")
    if isinstance(metric_ratio, (int, float)) and not isinstance(metric_ratio, bool):
        return float(metric_ratio)
    metric_hits = runtime_record.get("metric_hits")
    metric_total = runtime_record.get("metric_total")
    if (
        isinstance(metric_hits, int)
        and isinstance(metric_total, int)
        and not isinstance(metric_hits, bool)
        and not isinstance(metric_total, bool)
        and metric_total > 0
    ):
        return round(max(0, min(metric_hits, metric_total)) / metric_total, 6)
    return None


def _compile_family_artifacts(
    root: Path,
    *,
    training_config: DSPyTrainingConfig,
    lineage_metadata: Mapping[str, object] | None,
    lm_config: DSPyLMConfig,
) -> dict[str, dict[str, object]]:
    """Compile one family-scoped DSPy artifact for each persisted prompt family."""

    if not isinstance(lineage_metadata, Mapping):
        return {}
    family_state_path_text = str(
        lineage_metadata.get("family_state_path")
        or lineage_metadata.get("champion_index_path")
        or ""
    ).strip()
    if not family_state_path_text:
        return {}
    resolved_root = root.resolve()
    resolved_family_state_path = Path(family_state_path_text)
    if not resolved_family_state_path.is_absolute():
        resolved_family_state_path = resolved_root / resolved_family_state_path
    if not resolved_family_state_path.is_file():
        return {}
    payload = load_family_state_payload(resolved_family_state_path)
    raw_families = payload.get("prompt_families")
    if not isinstance(raw_families, list):
        return {}
    previous_registry = _load_previous_family_artifact_registry(resolved_root)
    family_results: dict[str, dict[str, object]] = {}
    family_state_changed = False
    for family in raw_families:
        if not isinstance(family, Mapping):
            continue
        prompt_family_id = str(family.get("prompt_family_id") or "").strip()
        if not prompt_family_id:
            continue
        carried_artifact = previous_registry.get(prompt_family_id)
        needs_recompile = bool(family.get("family_needs_recompile"))
        if (
            not needs_recompile
            and isinstance(carried_artifact, Mapping)
            and _family_artifact_payload_is_usable(resolved_root, carried_artifact)
        ):
            normalized_carried_artifact = {
                str(key): value for key, value in carried_artifact.items()
            }
            normalized_carried_artifact["artifact_source"] = "carried-forward"
            family_results[prompt_family_id] = normalized_carried_artifact
            if isinstance(family, dict):
                _update_family_artifact_state(family, normalized_carried_artifact)
                family_state_changed = True
            continue
        examples = _family_examples_from_payload(family)
        if not examples:
            continue
        artifact_paths = resolve_family_dspy_artifact_paths(
            resolved_root,
            run_name=training_config.run_name,
            prompt_family_id=prompt_family_id,
        )
        artifact_payload = _compile_repository_program_artifact(
            resolved_root,
            artifact_paths=artifact_paths,
            examples=examples,
            benchmark_examples=examples,
            training_config=training_config,
            lm_config=lm_config,
        )
        relative_program_path = str(artifact_paths.program_path.relative_to(resolved_root))
        relative_metadata_path = str(artifact_paths.metadata_path.relative_to(resolved_root))
        benchmark_summary = artifact_payload["benchmark_summary"]
        family_metadata = {
            "recorded_at": datetime.now(UTC).isoformat(),
            "run_name": _sanitize_run_name(training_config.run_name),
            "prompt_family_id": prompt_family_id,
            "artifact_kind": "repo-rag-family-runtime-artifact",
            "artifact_dir": str(artifact_paths.artifact_dir.relative_to(resolved_root)),
            "program_path": relative_program_path,
            "metadata_path": relative_metadata_path,
            "optimizer": training_config.optimizer,
            "top_k": training_config.top_k,
            "retrieval_mode": training_config.retrieval_mode,
            "lm": lm_config.as_metadata(),
            "training_example_count": len(examples),
            "benchmark_example_count": len(examples),
            "benchmark_summary": benchmark_summary,
            "family_state_path": str(resolved_family_state_path.relative_to(resolved_root)),
        }
        artifact_paths.metadata_path.write_text(
            f"{json.dumps(family_metadata, indent=2)}\n",
            encoding="utf-8",
        )
        family_results[prompt_family_id] = DSPyFamilyArtifactResult(
            prompt_family_id=prompt_family_id,
            artifact_dir=str(artifact_paths.artifact_dir.relative_to(resolved_root)),
            program_path=relative_program_path,
            metadata_path=relative_metadata_path,
            optimizer=training_config.optimizer,
            training_example_count=len(examples),
            benchmark_example_count=len(examples),
            benchmark_summary=cast(dict[str, object], benchmark_summary),
            hit_rate=_family_runtime_hit_rate(family),
            artifact_ready=artifact_paths.program_path.is_file(),
            artifact_source="recompiled",
        ).to_payload()
        if isinstance(family, dict):
            _update_family_artifact_state(family, family_results[prompt_family_id])
            family_state_changed = True
    if family_state_changed:
        resolved_family_state_path.write_text(
            f"{json.dumps(payload, indent=2)}\n",
            encoding="utf-8",
        )
    return family_results


def _global_artifact_payload_is_usable(
    root: Path,
    payload: Mapping[str, object],
    *,
    training_config: DSPyTrainingConfig,
    lm_config: DSPyLMConfig,
    training_path: Path,
    benchmark_path: Path,
    training_examples_signature: str,
    benchmark_examples_signature: str,
    lineage_metadata: Mapping[str, object] | None,
) -> bool:
    """Return whether one latest global DSPy artifact can be carried forward safely."""

    previous_training_examples_signature = _string_or_none(
        payload.get("training_examples_signature")
    )
    previous_benchmark_examples_signature = _string_or_none(
        payload.get("benchmark_examples_signature")
    )
    signatures_compatible = (
        previous_training_examples_signature is not None
        and previous_benchmark_examples_signature is not None
        and previous_training_examples_signature == training_examples_signature
        and previous_benchmark_examples_signature == benchmark_examples_signature
    )
    if _lineage_has_dirty_families(lineage_metadata) and not signatures_compatible:
        return False
    if not _artifact_path_exists(root, payload.get("program_path")):
        return False
    expected_training_path = _relative_to_root(training_path, root)
    expected_benchmark_path = _relative_to_root(benchmark_path, root)
    if _string_or_none(payload.get("training_path")) != expected_training_path:
        return False
    if _string_or_none(payload.get("benchmark_path")) != expected_benchmark_path:
        return False
    if (
        previous_training_examples_signature is not None
        and previous_training_examples_signature != training_examples_signature
    ):
        return False
    if (
        previous_benchmark_examples_signature is not None
        and previous_benchmark_examples_signature != benchmark_examples_signature
    ):
        return False
    if _string_or_none(payload.get("optimizer")) != training_config.optimizer:
        return False
    previous_top_k = payload.get("top_k")
    if isinstance(previous_top_k, int) and previous_top_k != training_config.top_k:
        return False
    previous_retrieval_mode = payload.get("retrieval_mode")
    current_retrieval_mode = training_config.retrieval_mode
    if isinstance(previous_retrieval_mode, str):
        if str(current_retrieval_mode) != previous_retrieval_mode:
            return False
    elif current_retrieval_mode is not None and previous_retrieval_mode is not None:
        return False
    previous_lm = payload.get("lm")
    if isinstance(previous_lm, Mapping):
        previous_lm_model = _string_or_none(previous_lm.get("model"))
        if previous_lm_model is not None and previous_lm_model != lm_config.model:
            return False
    return True


def _carry_forward_global_artifact(
    root: Path,
    *,
    artifact_paths: DSPyArtifactPaths,
    training_config: DSPyTrainingConfig,
    lm_config: DSPyLMConfig,
    training_path: Path,
    benchmark_path: Path,
    training_examples_signature: str,
    benchmark_examples_signature: str,
    lineage_metadata: Mapping[str, object] | None,
) -> dict[str, object] | None:
    """Copy the latest compatible global DSPy program into the new run directory."""

    latest_metadata_path = latest_dspy_artifact_metadata(root)
    if latest_metadata_path is None or not latest_metadata_path.is_file():
        return None
    latest_metadata = load_dspy_artifact_metadata(latest_metadata_path)
    if not _global_artifact_payload_is_usable(
        root,
        latest_metadata,
        training_config=training_config,
        lm_config=lm_config,
        training_path=training_path,
        benchmark_path=benchmark_path,
        training_examples_signature=training_examples_signature,
        benchmark_examples_signature=benchmark_examples_signature,
        lineage_metadata=lineage_metadata,
    ):
        return None
    program_path_text = _string_or_none(latest_metadata.get("program_path"))
    if program_path_text is None:
        return None
    previous_program_path = Path(program_path_text)
    if not previous_program_path.is_absolute():
        previous_program_path = root / previous_program_path
    if not previous_program_path.is_file():
        return None
    artifact_paths.artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_paths.program_path.write_bytes(previous_program_path.read_bytes())
    benchmark_summary = latest_metadata.get("benchmark_summary")
    compiled_program_summary = latest_metadata.get("compiled_program_summary")
    if not isinstance(benchmark_summary, dict):
        return None
    normalized_program_summary: dict[str, object]
    if isinstance(compiled_program_summary, dict):
        normalized_program_summary = dict(compiled_program_summary)
    else:
        normalized_program_summary = {}
    normalized_program_summary["artifact_source"] = "carried-forward"
    normalized_program_summary.setdefault("top_k", training_config.top_k)
    normalized_program_summary.setdefault("program_type", "RepositoryRAGProgram")
    return {
        "compiled_program": None,
        "benchmark_summary": benchmark_summary,
        "trainset_size": normalized_program_summary.get("trainset_size") or 0,
        "compiled_program_summary": normalized_program_summary,
        "artifact_source": "carried-forward",
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
    benchmark_path = training_config.benchmark_path or training_config.training_path
    if not benchmark_path.is_absolute():
        benchmark_path = resolved_root / benchmark_path
    if benchmark_path == training_path:
        benchmark_examples = examples
    else:
        benchmark_examples = load_training_examples(benchmark_path)
        benchmark_validation_issues = validate_training_examples(
            benchmark_examples,
            root=resolved_root,
        )
        if benchmark_validation_issues:
            issues_text = "\n".join(f"- {issue}" for issue in benchmark_validation_issues)
            raise ValueError(f"Benchmark samples are invalid:\n{issues_text}")
    training_examples_signature = _training_examples_signature(examples)
    benchmark_examples_signature = _training_examples_signature(benchmark_examples)

    configure_dspy_lm(lm_config)
    artifact_paths = resolve_dspy_artifact_paths(resolved_root, training_config.run_name)
    compiled_artifact = _carry_forward_global_artifact(
        resolved_root,
        artifact_paths=artifact_paths,
        training_config=training_config,
        lm_config=lm_config,
        training_path=training_path,
        benchmark_path=benchmark_path,
        training_examples_signature=training_examples_signature,
        benchmark_examples_signature=benchmark_examples_signature,
        lineage_metadata=training_config.lineage_metadata,
    )
    if compiled_artifact is None:
        compiled_artifact = _compile_repository_program_artifact(
            resolved_root,
            artifact_paths=artifact_paths,
            examples=examples,
            benchmark_examples=benchmark_examples,
            training_config=training_config,
            lm_config=lm_config,
        )
    benchmark_summary = cast(dict[str, object], compiled_artifact["benchmark_summary"])
    family_artifact_registry = _compile_family_artifacts(
        resolved_root,
        training_config=training_config,
        lineage_metadata=training_config.lineage_metadata,
        lm_config=lm_config,
    )
    compiled_program_summary_value = compiled_artifact.get("compiled_program_summary")
    if not isinstance(compiled_program_summary_value, dict):
        compiled_program = compiled_artifact["compiled_program"]
        trainset_size_value = compiled_artifact.get("trainset_size")
        trainset_size = (
            int(trainset_size_value) if isinstance(trainset_size_value, (int, str)) else 0
        )
        compiled_program_summary = {
            "program_type": compiled_program.__class__.__name__,
            "trainset_size": trainset_size,
            "top_k": training_config.top_k,
            "artifact_source": str(compiled_artifact.get("artifact_source") or "recompiled"),
        }
    else:
        compiled_program_summary = cast(dict[str, object], compiled_program_summary_value)
    relative_program_path = str(artifact_paths.program_path.relative_to(resolved_root))
    relative_metadata_path = str(artifact_paths.metadata_path.relative_to(resolved_root))
    metadata = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "run_name": _sanitize_run_name(training_config.run_name),
        "bundle_version": _sanitize_run_name(
            training_config.bundle_version or training_config.run_name
        ),
        "run_family": (
            _sanitize_run_name(training_config.run_family)
            if isinstance(training_config.run_family, str) and training_config.run_family.strip()
            else None
        ),
        "artifact_dir": str(artifact_paths.artifact_dir.relative_to(resolved_root)),
        "program_path": relative_program_path,
        "metadata_path": relative_metadata_path,
        "training_path": str(training_path.relative_to(resolved_root)),
        "benchmark_path": str(benchmark_path.relative_to(resolved_root)),
        "training_examples_signature": training_examples_signature,
        "benchmark_examples_signature": benchmark_examples_signature,
        "training_example_count": len(examples),
        "benchmark_example_count": len(benchmark_examples),
        "optimizer": training_config.optimizer,
        "top_k": training_config.top_k,
        "retrieval_mode": training_config.retrieval_mode,
        "lm": lm_config.as_metadata(),
        "benchmark_summary": benchmark_summary,
        "compiled_program_summary": compiled_program_summary,
        "family_artifact_registry": family_artifact_registry or None,
        "lineage": (
            dict(training_config.lineage_metadata)
            if isinstance(training_config.lineage_metadata, Mapping)
            else None
        ),
    }
    artifact_paths.metadata_path.write_text(
        f"{json.dumps(metadata, indent=2)}\n",
        encoding="utf-8",
    )
    bundle_manifest = write_bundle_manifest(resolved_root, artifact_paths.metadata_path)
    return DSPyTrainingResult(
        run_name=_sanitize_run_name(training_config.run_name),
        run_family=(
            _sanitize_run_name(training_config.run_family)
            if isinstance(training_config.run_family, str) and training_config.run_family.strip()
            else None
        ),
        artifact_dir=str(artifact_paths.artifact_dir.relative_to(resolved_root)),
        program_path=relative_program_path,
        metadata_path=relative_metadata_path,
        training_path=str(training_path.relative_to(resolved_root)),
        benchmark_path=str(benchmark_path.relative_to(resolved_root)),
        optimizer=training_config.optimizer,
        training_example_count=len(examples),
        benchmark_example_count=len(benchmark_examples),
        benchmark_summary=benchmark_summary,
        lm_model=lm_config.model,
        bundle_path=str(bundle_manifest.get("bundle_path") or ""),
        bundle_version=str(bundle_manifest.get("bundle_version") or ""),
        lineage_metadata=(
            dict(training_config.lineage_metadata)
            if isinstance(training_config.lineage_metadata, Mapping)
            else None
        ),
    )
