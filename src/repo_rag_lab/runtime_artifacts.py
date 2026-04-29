"""Versioned bundle, overlay, and runtime-trace helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from .retrieval import RetrievalMode, resolve_retrieval_mode
from .retrieval_profile import DEFAULT_RETRIEVAL_PROFILE_PATH, load_retrieval_profile
from .rust_lookup import DEFAULT_DB_PATH

BUNDLE_SCHEMA_VERSION = 1
PUBLISHED_BUNDLE_SCHEMA_VERSION = 1
BUNDLE_CHANNEL_SCHEMA_VERSION = 1
OVERLAY_SCHEMA_VERSION = 1
TRACE_SCHEMA_VERSION = 1
TRACE_RECORD_SCHEMA_VERSION = 1
TRACE_QUEUE_ITEM_SCHEMA_VERSION = 1
OUTCOME_SCHEMA_VERSION = 1
BUNDLE_FILENAME = "bundle.json"
DEFAULT_PUBLISHED_BUNDLES_DIR = Path("artifacts/dspy/published")
DEFAULT_BUNDLE_CHANNELS_DIR = Path("artifacts/dspy/channels")
DEFAULT_OVERLAYS_DIR = Path("artifacts/overlays")
DEFAULT_OVERLAY_FILENAME = "overlay.json"
DEFAULT_TRACES_DIR = Path("artifacts/traces")
DEFAULT_IMPORTED_TRACES_DIR = DEFAULT_TRACES_DIR / "imported"
DEFAULT_QUEUED_TRACES_DIR = DEFAULT_TRACES_DIR / "queued"
DEFAULT_PROCESSED_TRACE_QUEUE_DIR = DEFAULT_TRACES_DIR / "queued_processed"
DEFAULT_TRAINER_SERVICE_DIR = Path("artifacts/trainer")
DEFAULT_TRAINER_SERVICE_STATE_PATH = DEFAULT_TRAINER_SERVICE_DIR / "service-state.json"
DEFAULT_TRAINER_SERVICE_HISTORY_DIR = DEFAULT_TRAINER_SERVICE_DIR / "history"
DEFAULT_TRAINER_TRAINING_CANDIDATES_PATH = DEFAULT_TRAINER_SERVICE_DIR / "training-candidates.yaml"
DEFAULT_TRAINER_TRAINING_CANDIDATES_SUMMARY_PATH = (
    DEFAULT_TRAINER_SERVICE_DIR / "training-candidates-summary.json"
)
DEFAULT_TRAINER_GENERATED_TRAINING_PATH = DEFAULT_TRAINER_SERVICE_DIR / "generated-training.yaml"
DEFAULT_TRAINER_GENERATED_TRAINING_SUMMARY_PATH = (
    DEFAULT_TRAINER_SERVICE_DIR / "generated-training-summary.json"
)
TRACE_RECORD_KIND = "repo-rag-trace-record"
TRACE_QUEUE_ITEM_KIND = "repo-rag-trace-queue-item"
OUTCOME_KIND = "repo-rag-outcome"
TRAINER_SERVICE_STATE_KIND = "repo-rag-trainer-service-state"
TRAINER_SERVICE_CYCLE_KIND = "repo-rag-trainer-service-cycle"
BundleChannelName = Literal["stable", "canary"]
BUNDLE_CHANNEL_NAMES: tuple[BundleChannelName, ...] = ("stable", "canary")


@dataclass(frozen=True)
class RuntimeTraceContext:
    """Structured runtime-trace input shared by the CLI surfaces."""

    question: str
    mode: str
    retrieval_mode: str
    sources: Sequence[str]
    context_count: int
    top_k: int | None = None
    provider: str | None = None
    program_loaded: bool | None = None
    program_path: str | None = None
    bundle_version: str | None = None
    overlay_path: str | None = None
    mcp_candidate_count: int = 0
    answer_length: int | None = None
    context_field: str = "context"


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _sanitize_name(name: str, *, default: str) -> str:
    parts = [part for part in re.split(r"[^A-Za-z0-9._-]+", name.strip()) if part]
    if parts:
        return "-".join(parts)
    return default


def _mapping_or_none(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return {str(key): item for key, item in value.items()}


def _mapping_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, object]] = []
    for item in value:
        normalized = _mapping_or_none(item)
        if normalized is not None:
            rows.append(normalized)
    return rows


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _list_or_empty(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return list(value)


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _int_or_none(value: object) -> int | None:
    if not isinstance(value, int):
        return None
    return int(value)


def _utc_now_isoformat() -> str:
    return datetime.now(UTC).isoformat()


def bundle_manifest_path(metadata_path: Path) -> Path:
    """Return the bundle-manifest path that belongs to ``metadata_path``."""

    return metadata_path.parent / BUNDLE_FILENAME


def build_bundle_manifest(
    root: Path, metadata: Mapping[str, object], metadata_path: Path
) -> dict[str, object]:
    """Build a versioned bundle manifest from one DSPy metadata payload."""

    resolved_root = root.resolve()
    resolved_metadata_path = metadata_path.resolve()
    resolved_bundle_path = bundle_manifest_path(resolved_metadata_path)

    run_name = str(metadata.get("run_name") or resolved_metadata_path.parent.name)
    artifact_dir = str(
        metadata.get("artifact_dir")
        or _relative_to_root(resolved_metadata_path.parent, resolved_root)
    )
    program_path_text = str(
        metadata.get("program_path")
        or _relative_to_root(resolved_metadata_path.parent / "program.json", resolved_root)
    )
    resolved_program_path = Path(program_path_text)
    if not resolved_program_path.is_absolute():
        resolved_program_path = resolved_root / resolved_program_path

    benchmark_summary = _mapping_or_none(metadata.get("benchmark_summary"))
    compiled_program_summary = _mapping_or_none(metadata.get("compiled_program_summary"))
    lm = _mapping_or_none(metadata.get("lm"))
    retrieval_profile_path = (
        str(DEFAULT_RETRIEVAL_PROFILE_PATH)
        if (resolved_root / DEFAULT_RETRIEVAL_PROFILE_PATH).is_file()
        else None
    )
    benchmark_pass_rate = None
    benchmark_status = "not-recorded"
    if benchmark_summary is not None:
        benchmark_pass_rate = benchmark_summary.get("pass_rate")
        if isinstance(benchmark_pass_rate, int | float):
            benchmark_status = "pass" if float(benchmark_pass_rate) >= 1.0 else "needs-review"
        else:
            benchmark_status = "recorded"

    bundle_status = "ready" if resolved_program_path.exists() else "missing-program"
    top_k = metadata.get("top_k")
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_kind": "global",
        "run_name": run_name,
        "bundle_version": run_name,
        "bundle_status": bundle_status,
        "created_at": metadata.get("recorded_at"),
        "artifact_dir": artifact_dir,
        "bundle_path": _relative_to_root(resolved_bundle_path, resolved_root),
        "program_path": _relative_to_root(resolved_program_path, resolved_root),
        "metadata_path": _relative_to_root(resolved_metadata_path, resolved_root),
        "training_path": metadata.get("training_path"),
        "top_k": int(top_k) if isinstance(top_k, int) else None,
        "retrieval_mode": metadata.get("retrieval_mode"),
        "benchmark_status": benchmark_status,
        "benchmark_summary": benchmark_summary,
        "compiled_program_summary": compiled_program_summary,
        "lm": lm,
        "provenance": {
            "source": "repo-rag",
            "retrieval_profile_path": retrieval_profile_path,
            "question_bank_path": "data/questions/repository.yaml",
        },
    }


def write_bundle_manifest(root: Path, metadata_path: Path) -> dict[str, object]:
    """Write and return the normalized bundle manifest for ``metadata_path``."""

    resolved_root = root.resolve()
    resolved_metadata_path = metadata_path.resolve()
    metadata = json.loads(resolved_metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError(f"DSPy artifact metadata must be a JSON object: {resolved_metadata_path}")
    payload = build_bundle_manifest(resolved_root, metadata, resolved_metadata_path)
    bundle_manifest_path(resolved_metadata_path).write_text(
        f"{json.dumps(payload, indent=2)}\n",
        encoding="utf-8",
    )
    return payload


def load_bundle_manifest(bundle_path: Path) -> dict[str, object]:
    """Load one bundle manifest from disk."""

    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Bundle manifest must be a JSON object: {bundle_path}")
    return payload


def _bundle_manifest_candidates(root: Path) -> list[tuple[Path, dict[str, object]]]:
    artifact_root = root / "artifacts" / "dspy"
    if not artifact_root.exists():
        return []
    candidates: list[tuple[Path, dict[str, object]]] = []
    for bundle_path in artifact_root.glob(f"*/{BUNDLE_FILENAME}"):
        payload = load_bundle_manifest(bundle_path)
        candidates.append((bundle_path.resolve(), payload))
    return sorted(
        candidates,
        key=lambda item: (
            str(item[1].get("created_at") or ""),
            str(_relative_to_root(item[0], root)),
        ),
        reverse=True,
    )


def resolve_bundle_manifest(
    root: Path,
    *,
    run_name: str | None = None,
    bundle_version: str | None = None,
) -> tuple[Path, dict[str, object]]:
    """Resolve a bundle manifest by run name or bundle version."""

    resolved_root = root.resolve()
    candidates = _bundle_manifest_candidates(resolved_root)
    if not candidates:
        raise ValueError("No saved DSPy bundle manifests are available yet.")

    for bundle_path, payload in candidates:
        candidate_run_name = _string_or_none(payload.get("run_name")) or bundle_path.parent.name
        candidate_bundle_version = (
            _string_or_none(payload.get("bundle_version")) or candidate_run_name
        )
        if run_name is not None and candidate_run_name != run_name:
            continue
        if bundle_version is not None and candidate_bundle_version != bundle_version:
            continue
        return bundle_path, payload

    if run_name is not None and bundle_version is not None:
        raise ValueError(
            f"No DSPy bundle matches run `{run_name}` and bundle version `{bundle_version}`."
        )
    if run_name is not None:
        raise ValueError(f"No DSPy bundle named `{run_name}` is available yet.")
    raise ValueError(f"No DSPy bundle version `{bundle_version}` is available yet.")


def _validate_bundle_channel(channel: str) -> BundleChannelName:
    cleaned = channel.strip().casefold()
    if cleaned not in BUNDLE_CHANNEL_NAMES:
        expected = ", ".join(BUNDLE_CHANNEL_NAMES)
        raise ValueError(f"Bundle channel must be one of: {expected}.")
    return cleaned  # type: ignore[return-value]


def published_bundle_record_path(root: Path, bundle_version: str) -> Path:
    """Return the publish-record path for one bundle version."""

    safe_version = _sanitize_name(bundle_version, default="bundle")
    return root / DEFAULT_PUBLISHED_BUNDLES_DIR / f"{safe_version}.json"


def load_published_bundle_record(path: Path) -> dict[str, object]:
    """Load one published-bundle record from disk."""

    payload = load_json_object(path)
    if _string_or_none(payload.get("published_bundle_kind")) != "published":
        raise ValueError(f"Published bundle record is invalid: {path}")
    return payload


def publish_bundle(
    root: Path,
    *,
    run_name: str | None = None,
    bundle_version: str | None = None,
    note: str | None = None,
) -> dict[str, object]:
    """Publish one compiled bundle manifest into the local published-bundle registry."""

    resolved_root = root.resolve()
    bundle_path, bundle = resolve_bundle_manifest(
        resolved_root,
        run_name=run_name,
        bundle_version=bundle_version,
    )
    resolved_bundle_version = _string_or_none(bundle.get("bundle_version"))
    if resolved_bundle_version is None:
        raise ValueError(f"Bundle manifest is missing `bundle_version`: {bundle_path}")
    published_path = published_bundle_record_path(resolved_root, resolved_bundle_version)
    published_path.parent.mkdir(parents=True, exist_ok=True)
    existed = published_path.exists()
    record: dict[str, object] = {
        "schema_version": PUBLISHED_BUNDLE_SCHEMA_VERSION,
        "published_bundle_kind": "published",
        "publish_status": "published",
        "publish_action": "refresh" if existed else "created",
        "published_at": _utc_now_isoformat(),
        "published_bundle_path": _relative_to_root(published_path, resolved_root),
        "bundle_version": resolved_bundle_version,
        "run_name": _string_or_none(bundle.get("run_name")) or bundle_path.parent.name,
        "bundle_path": _relative_to_root(bundle_path, resolved_root),
        "artifact_dir": _string_or_none(bundle.get("artifact_dir")),
        "program_path": _string_or_none(bundle.get("program_path")),
        "metadata_path": _string_or_none(bundle.get("metadata_path")),
        "bundle_status": _string_or_none(bundle.get("bundle_status")),
        "benchmark_status": _string_or_none(bundle.get("benchmark_status")),
        "retrieval_mode": _string_or_none(bundle.get("retrieval_mode")),
        "top_k": _int_or_none(bundle.get("top_k")),
        "note": _string_or_none(note),
        "bundle_summary": bundle,
    }
    published_path.write_text(f"{json.dumps(record, indent=2)}\n", encoding="utf-8")
    return record


def resolve_published_bundle_record(
    root: Path, *, bundle_version: str
) -> tuple[Path, dict[str, object]]:
    """Resolve one published-bundle record by bundle version."""

    resolved_root = root.resolve()
    published_path = published_bundle_record_path(resolved_root, bundle_version)
    if not published_path.is_file():
        raise ValueError(f"No published bundle version `{bundle_version}` is available yet.")
    return published_path, load_published_bundle_record(published_path)


def bundle_channel_state_path(root: Path, channel: str) -> Path:
    """Return the persisted channel-state path for ``channel``."""

    normalized_channel = _validate_bundle_channel(channel)
    return root / DEFAULT_BUNDLE_CHANNELS_DIR / f"{normalized_channel}.json"


def load_bundle_channel_state(path: Path) -> dict[str, object]:
    """Load one bundle-channel state file from disk."""

    payload = load_json_object(path)
    if _string_or_none(payload.get("channel_kind")) != "bundle-channel":
        raise ValueError(f"Bundle channel state is invalid: {path}")
    return payload


def inspect_bundle_channel(root: Path, *, channel: str) -> dict[str, object]:
    """Return the current state for one persisted bundle channel."""

    resolved_root = root.resolve()
    normalized_channel = _validate_bundle_channel(channel)
    channel_path = bundle_channel_state_path(resolved_root, normalized_channel)
    if not channel_path.is_file():
        return {
            "channel_found": False,
            "requested_channel": normalized_channel,
            "channel_path": _relative_to_root(channel_path, resolved_root),
        }
    payload = load_bundle_channel_state(channel_path)
    return {
        "channel_found": True,
        "requested_channel": normalized_channel,
        **payload,
    }


def _bundle_channel_history_entry(
    *,
    action: str,
    channel_name: str,
    bundle_version: str,
    published_bundle_path: str,
    note: str | None,
    previous_bundle_version: str | None = None,
) -> dict[str, object]:
    return {
        "recorded_at": _utc_now_isoformat(),
        "action": action,
        "channel_name": channel_name,
        "bundle_version": bundle_version,
        "previous_bundle_version": previous_bundle_version,
        "published_bundle_path": published_bundle_path,
        "note": _string_or_none(note),
    }


def _build_bundle_channel_state(
    *,
    root: Path,
    channel_name: str,
    published_record: Mapping[str, object],
    history: Sequence[Mapping[str, object]],
    channel_action: str,
) -> dict[str, object]:
    resolved_root = root.resolve()
    bundle_summary = _mapping_or_none(published_record.get("bundle_summary")) or {}
    published_bundle_path = _string_or_none(published_record.get("published_bundle_path"))
    return {
        "schema_version": BUNDLE_CHANNEL_SCHEMA_VERSION,
        "channel_kind": "bundle-channel",
        "channel_name": channel_name,
        "channel_status": "active",
        "channel_action": channel_action,
        "updated_at": _utc_now_isoformat(),
        "channel_path": _relative_to_root(
            bundle_channel_state_path(resolved_root, channel_name),
            resolved_root,
        ),
        "current_bundle_version": _string_or_none(published_record.get("bundle_version")),
        "current_run_name": _string_or_none(published_record.get("run_name")),
        "current_published_bundle_path": published_bundle_path,
        "current_bundle_path": _string_or_none(published_record.get("bundle_path")),
        "current_program_path": _string_or_none(published_record.get("program_path")),
        "current_metadata_path": _string_or_none(published_record.get("metadata_path")),
        "current_bundle_status": _string_or_none(published_record.get("bundle_status")),
        "current_benchmark_status": _string_or_none(published_record.get("benchmark_status")),
        "current_publish_status": _string_or_none(published_record.get("publish_status")),
        "current_bundle": bundle_summary,
        "history": list(history),
    }


def promote_bundle(
    root: Path,
    *,
    channel: str,
    run_name: str | None = None,
    bundle_version: str | None = None,
    note: str | None = None,
) -> dict[str, object]:
    """Promote one published bundle version into a named channel."""

    resolved_root = root.resolve()
    normalized_channel = _validate_bundle_channel(channel)
    published_record = publish_bundle(
        resolved_root,
        run_name=run_name,
        bundle_version=bundle_version,
        note=note,
    )
    channel_path = bundle_channel_state_path(resolved_root, normalized_channel)
    previous_state = load_bundle_channel_state(channel_path) if channel_path.is_file() else {}
    previous_bundle_version = _string_or_none(previous_state.get("current_bundle_version"))
    next_bundle_version = _string_or_none(published_record.get("bundle_version"))
    if next_bundle_version is None:
        raise ValueError("Published bundle record is missing `bundle_version`.")
    history = _mapping_list(previous_state.get("history"))
    channel_action = "noop" if previous_bundle_version == next_bundle_version else "promote"
    if channel_action != "noop":
        history.append(
            _bundle_channel_history_entry(
                action="promote",
                channel_name=normalized_channel,
                bundle_version=next_bundle_version,
                previous_bundle_version=previous_bundle_version,
                published_bundle_path=str(published_record.get("published_bundle_path") or ""),
                note=note,
            )
        )
    channel_path.parent.mkdir(parents=True, exist_ok=True)
    state = _build_bundle_channel_state(
        root=resolved_root,
        channel_name=normalized_channel,
        published_record=published_record,
        history=history,
        channel_action=channel_action,
    )
    channel_path.write_text(f"{json.dumps(state, indent=2)}\n", encoding="utf-8")
    return state


def _find_previous_channel_bundle_version(
    history: Sequence[Mapping[str, object]],
    *,
    current_bundle_version: str,
) -> str | None:
    for entry in reversed(history):
        candidate_version = _string_or_none(entry.get("bundle_version"))
        if candidate_version is None or candidate_version == current_bundle_version:
            continue
        return candidate_version
    return None


def rollback_bundle(
    root: Path,
    *,
    channel: str,
    bundle_version: str | None = None,
    note: str | None = None,
) -> dict[str, object]:
    """Rollback one bundle channel to its previous or explicit published version."""

    resolved_root = root.resolve()
    normalized_channel = _validate_bundle_channel(channel)
    channel_path = bundle_channel_state_path(resolved_root, normalized_channel)
    if not channel_path.is_file():
        raise ValueError(f"Bundle channel `{normalized_channel}` is not initialized yet.")
    previous_state = load_bundle_channel_state(channel_path)
    current_bundle_version = _string_or_none(previous_state.get("current_bundle_version"))
    if current_bundle_version is None:
        raise ValueError(f"Bundle channel `{normalized_channel}` has no current bundle version.")
    history = _mapping_list(previous_state.get("history"))
    target_bundle_version = bundle_version or _find_previous_channel_bundle_version(
        history,
        current_bundle_version=current_bundle_version,
    )
    if target_bundle_version is None:
        raise ValueError(
            "Bundle channel "
            f"`{normalized_channel}` does not have a previous version to roll back to."
        )
    _, published_record = resolve_published_bundle_record(
        resolved_root,
        bundle_version=target_bundle_version,
    )
    history.append(
        _bundle_channel_history_entry(
            action="rollback",
            channel_name=normalized_channel,
            bundle_version=target_bundle_version,
            previous_bundle_version=current_bundle_version,
            published_bundle_path=str(published_record.get("published_bundle_path") or ""),
            note=note,
        )
    )
    state = _build_bundle_channel_state(
        root=resolved_root,
        channel_name=normalized_channel,
        published_record=published_record,
        history=history,
        channel_action="rollback",
    )
    channel_path.write_text(f"{json.dumps(state, indent=2)}\n", encoding="utf-8")
    return state


def resolve_bundle_version_for_program(root: Path, program_path: Path | None) -> str | None:
    """Resolve the bundle version associated with ``program_path`` when possible."""

    if program_path is None:
        return None
    resolved_root = root.resolve()
    resolved_program_path = program_path.resolve()
    candidate_bundle_path = resolved_program_path.parent / BUNDLE_FILENAME
    if candidate_bundle_path.is_file():
        bundle = load_bundle_manifest(candidate_bundle_path)
        bundle_version = bundle.get("bundle_version")
        if isinstance(bundle_version, str) and bundle_version.strip():
            return bundle_version
    try:
        relative_program_path = resolved_program_path.relative_to(resolved_root)
    except ValueError:
        return None
    parts = relative_program_path.parts
    if len(parts) >= 4 and parts[:2] == ("artifacts", "dspy") and parts[-1] == "program.json":
        return parts[2]
    return None


def initialize_local_overlay(
    root: Path,
    *,
    overlay_name: str = "default",
    bundle_version: str | None = None,
    retrieval_mode: RetrievalMode | None = None,
) -> dict[str, object]:
    """Create or refresh a worker-local overlay manifest under ``artifacts/overlays``."""

    resolved_root = root.resolve()
    safe_name = _sanitize_name(overlay_name, default="default")
    overlay_dir = resolved_root / DEFAULT_OVERLAYS_DIR / safe_name
    overlay_dir.mkdir(parents=True, exist_ok=True)
    overlay_path = overlay_dir / DEFAULT_OVERLAY_FILENAME
    resolved_mode = resolve_retrieval_mode(load_retrieval_profile(resolved_root), retrieval_mode)
    profile_path = resolved_root / DEFAULT_RETRIEVAL_PROFILE_PATH
    lookup_index_path = resolved_root / DEFAULT_DB_PATH
    trace_dir = resolved_root / DEFAULT_TRACES_DIR

    payload: dict[str, object] = {
        "schema_version": OVERLAY_SCHEMA_VERSION,
        "overlay_kind": "local",
        "overlay_name": safe_name,
        "overlay_status": "ready",
        "created_at": datetime.now(UTC).isoformat(),
        "overlay_dir": _relative_to_root(overlay_dir, resolved_root),
        "overlay_path": _relative_to_root(overlay_path, resolved_root),
        "repo_root": str(resolved_root),
        "bundle_version": bundle_version,
        "retrieval_mode": resolved_mode,
        "retrieval_profile_path": (
            _relative_to_root(profile_path, resolved_root) if profile_path.is_file() else None
        ),
        "lookup_index_path": _relative_to_root(lookup_index_path, resolved_root),
        "lookup_index_exists": lookup_index_path.is_file(),
        "trace_dir": _relative_to_root(trace_dir, resolved_root),
        "worker_adaptation_scope": {
            "retrieval": True,
            "local_examples": True,
            "trace_capture": True,
            "model_weights": False,
        },
        "notes": (
            "Local overlays currently track repo-local retrieval configuration, lookup-index "
            "state, and future trace directories; they do not store model weights."
        ),
    }
    overlay_path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")
    return payload


def build_runtime_trace(trace: RuntimeTraceContext) -> dict[str, object]:
    """Return a stable runtime-trace payload for worker-side persistence."""

    payload: dict[str, object] = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "trace_kind": "repo-rag-runtime",
        "recorded_at": datetime.now(UTC).isoformat(),
        "question": trace.question,
        "mode": trace.mode,
        "provider": trace.provider,
        "retrieval_mode": trace.retrieval_mode,
        "top_k": trace.top_k,
        "bundle_version": trace.bundle_version,
        "overlay_path": trace.overlay_path,
        "program_loaded": trace.program_loaded,
        "program_path": trace.program_path,
        "sources": list(trace.sources),
        "source_count": len(trace.sources),
        "context_count": trace.context_count,
        "context_field": trace.context_field,
        "mcp_candidate_count": trace.mcp_candidate_count,
        "answer_length": trace.answer_length,
    }
    return payload


def load_json_object(path: Path) -> dict[str, object]:
    """Load one JSON object from disk."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON payload must be an object: {path}")
    return payload


def _normalize_runtime_trace(payload: Mapping[str, object]) -> dict[str, object]:
    trace_kind = _string_or_none(payload.get("trace_kind"))
    question = _string_or_none(payload.get("question"))
    mode = _string_or_none(payload.get("mode"))
    retrieval_mode = _string_or_none(payload.get("retrieval_mode"))
    if trace_kind != "repo-rag-runtime":
        raise ValueError("Trace payload must declare `trace_kind: repo-rag-runtime`.")
    if question is None:
        raise ValueError("Trace payload must include `question`.")
    if mode is None:
        raise ValueError("Trace payload must include `mode`.")
    if retrieval_mode is None:
        raise ValueError("Trace payload must include `retrieval_mode`.")
    schema_version = _int_or_none(payload.get("schema_version")) or TRACE_SCHEMA_VERSION
    top_k = _int_or_none(payload.get("top_k"))
    source_count = _int_or_none(payload.get("source_count"))
    context_count = _int_or_none(payload.get("context_count"))
    mcp_candidate_count = _int_or_none(payload.get("mcp_candidate_count"))
    answer_length = _int_or_none(payload.get("answer_length"))
    sources = _string_list(payload.get("sources"))
    return {
        "schema_version": schema_version,
        "trace_kind": trace_kind,
        "recorded_at": _string_or_none(payload.get("recorded_at")),
        "question": question,
        "mode": mode,
        "provider": _string_or_none(payload.get("provider")),
        "retrieval_mode": retrieval_mode,
        "top_k": top_k,
        "bundle_version": _string_or_none(payload.get("bundle_version")),
        "overlay_path": _string_or_none(payload.get("overlay_path")),
        "program_loaded": payload.get("program_loaded")
        if isinstance(payload.get("program_loaded"), bool)
        else None,
        "program_path": _string_or_none(payload.get("program_path")),
        "sources": sources,
        "source_count": source_count if source_count is not None else len(sources),
        "context_count": context_count if context_count is not None else 0,
        "context_field": _string_or_none(payload.get("context_field")) or "context",
        "mcp_candidate_count": mcp_candidate_count if mcp_candidate_count is not None else 0,
        "answer_length": answer_length,
    }


def _trace_record_snapshot(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        "question": _string_or_none(payload.get("question")),
        "answer": _string_or_none(payload.get("answer")),
        "response_text": _string_or_none(payload.get("response_text")),
        "sources": _string_list(payload.get("sources")),
        "context": _list_or_empty(payload.get("context")),
        "retrieved_context": _list_or_empty(payload.get("retrieved_context")),
        "warnings": _string_list(payload.get("source_warnings") or payload.get("warnings")),
        "artifact_metadata": _mapping_or_none(
            payload.get("source_artifact_metadata") or payload.get("artifact_metadata")
        )
        or {
            "input_paths": [],
            "generated_paths": [],
            "related_paths": [],
        },
        "error": _mapping_or_none(payload.get("source_error") or payload.get("error")),
    }


def _normalize_outcome_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized = {str(key): value for key, value in payload.items()}
    explicit_status = _string_or_none(normalized.get("acceptance_status"))
    explicit_accepted = _bool_or_none(normalized.get("accepted"))
    execution_status = _string_or_none(normalized.get("execution_status")) or "unknown"
    if explicit_status is None:
        if explicit_accepted is True:
            explicit_status = "accepted"
        elif explicit_accepted is False:
            explicit_status = "rejected" if execution_status == "success" else "failed"
        elif execution_status == "success":
            explicit_status = "candidate"
        else:
            explicit_status = "failed"
    if explicit_accepted is None:
        if explicit_status == "accepted":
            explicit_accepted = True
        elif explicit_status in {"rejected", "failed"}:
            explicit_accepted = False
    normalized["outcome_kind"] = OUTCOME_KIND
    normalized["outcome_schema_version"] = OUTCOME_SCHEMA_VERSION
    normalized["acceptance_status"] = explicit_status
    normalized["accepted"] = explicit_accepted
    normalized["execution_status"] = execution_status
    warnings = normalized.get("warnings")
    if isinstance(warnings, list):
        normalized["warnings"] = [str(item) for item in warnings]
    return normalized


def normalize_trace_record_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Normalize a command envelope, raw runtime trace, or existing trace record."""

    trace_record_kind = _string_or_none(payload.get("trace_record_kind"))
    if trace_record_kind == TRACE_RECORD_KIND:
        runtime_trace_payload = _mapping_or_none(payload.get("trace"))
        if runtime_trace_payload is None:
            raise ValueError("Trace record payload must include a `trace` object.")
        normalized_trace = _normalize_runtime_trace(runtime_trace_payload)
        outcome_payload = _mapping_or_none(payload.get("outcome"))
        return {
            "source_command": _string_or_none(payload.get("source_command")) or "trace-record",
            "source_command_status": _string_or_none(payload.get("source_command_status"))
            or "success",
            "source_root": _string_or_none(payload.get("source_root")),
            "snapshot": {
                "question": _string_or_none(payload.get("question"))
                or normalized_trace["question"],
                "answer": _string_or_none(payload.get("answer")),
                "response_text": _string_or_none(payload.get("response_text")),
                "sources": _string_list(payload.get("sources")) or normalized_trace["sources"],
                "context": _list_or_empty(payload.get("context")),
                "retrieved_context": _list_or_empty(payload.get("retrieved_context")),
                "warnings": _string_list(payload.get("source_warnings") or payload.get("warnings")),
                "artifact_metadata": _mapping_or_none(
                    payload.get("source_artifact_metadata") or payload.get("artifact_metadata")
                )
                or {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "error": _mapping_or_none(payload.get("source_error") or payload.get("error")),
            },
            "trace": normalized_trace,
            "outcome": _normalize_outcome_payload(outcome_payload)
            if outcome_payload is not None
            else None,
        }

    embedded_trace = _mapping_or_none(payload.get("trace"))
    if embedded_trace is not None:
        outcome_payload = _mapping_or_none(payload.get("outcome"))
        return {
            "source_command": _string_or_none(payload.get("command")) or "unknown-command",
            "source_command_status": _string_or_none(payload.get("command_status")) or "success",
            "source_root": _string_or_none(payload.get("root")),
            "snapshot": _trace_record_snapshot(payload),
            "trace": _normalize_runtime_trace(embedded_trace),
            "outcome": _normalize_outcome_payload(outcome_payload)
            if outcome_payload is not None
            else None,
        }

    if _string_or_none(payload.get("trace_kind")) == "repo-rag-runtime":
        normalized_trace = _normalize_runtime_trace(payload)
        outcome_payload = _mapping_or_none(payload.get("outcome"))
        return {
            "source_command": "raw-trace",
            "source_command_status": "success",
            "source_root": None,
            "snapshot": {
                "question": normalized_trace["question"],
                "answer": None,
                "response_text": None,
                "sources": _string_list(normalized_trace.get("sources")),
                "context": [],
                "retrieved_context": [],
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "error": None,
            },
            "trace": normalized_trace,
            "outcome": _normalize_outcome_payload(outcome_payload)
            if outcome_payload is not None
            else None,
        }

    raise ValueError(
        "Trace payload must be a command envelope with `trace`, a raw "
        "`repo-rag-runtime` trace, or an existing trace record."
    )


def _trace_storage_dir(root: Path, *, imported: bool) -> Path:
    return root / (DEFAULT_IMPORTED_TRACES_DIR if imported else DEFAULT_TRACES_DIR)


def _default_trace_name(normalized_payload: Mapping[str, object]) -> str:
    trace = _mapping_or_none(normalized_payload.get("trace")) or {}
    mode = _string_or_none(trace.get("mode")) or "trace"
    question = _string_or_none(trace.get("question")) or "record"
    return _sanitize_name(f"{mode}-{question}", default="trace-record")


def _trace_queue_dir(root: Path, queue_name: str, *, processed: bool) -> Path:
    safe_queue_name = _sanitize_name(queue_name, default="default")
    base_dir = DEFAULT_PROCESSED_TRACE_QUEUE_DIR if processed else DEFAULT_QUEUED_TRACES_DIR
    return root / base_dir / safe_queue_name


def write_trace_record(
    root: Path,
    payload: Mapping[str, object],
    *,
    trace_name: str | None = None,
    imported: bool = False,
    outcome: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Normalize and persist one runtime-trace record under ``artifacts/traces``."""

    resolved_root = root.resolve()
    normalized_payload = normalize_trace_record_payload(payload)
    normalized_outcome = _mapping_or_none(normalized_payload.get("outcome"))
    if outcome is not None:
        normalized_outcome = _normalize_outcome_payload(outcome)
    trace_dir = _trace_storage_dir(resolved_root, imported=imported)
    trace_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_name(
        trace_name or _default_trace_name(normalized_payload),
        default="trace-record",
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    trace_path = trace_dir / f"{timestamp}-{safe_name}.json"
    snapshot = _mapping_or_none(normalized_payload.get("snapshot")) or {}
    trace = _mapping_or_none(normalized_payload.get("trace")) or {}
    record: dict[str, object] = {
        "schema_version": TRACE_RECORD_SCHEMA_VERSION,
        "trace_record_kind": TRACE_RECORD_KIND,
        "stored_at": datetime.now(UTC).isoformat(),
        "trace_record_path": _relative_to_root(trace_path, resolved_root),
        "trace_storage_kind": "imported" if imported else "exported",
        "source_command": _string_or_none(normalized_payload.get("source_command"))
        or ("trace-import" if imported else "trace-export"),
        "source_command_status": _string_or_none(normalized_payload.get("source_command_status"))
        or "success",
        "source_root": _string_or_none(normalized_payload.get("source_root")),
        "question": _string_or_none(snapshot.get("question"))
        or _string_or_none(trace.get("question")),
        "answer": _string_or_none(snapshot.get("answer")),
        "response_text": _string_or_none(snapshot.get("response_text")),
        "sources": _string_list(snapshot.get("sources")) or _string_list(trace.get("sources")),
        "context": _list_or_empty(snapshot.get("context")),
        "retrieved_context": _list_or_empty(snapshot.get("retrieved_context")),
        "source_warnings": _string_list(snapshot.get("warnings")),
        "source_artifact_metadata": _mapping_or_none(snapshot.get("artifact_metadata"))
        or {
            "input_paths": [],
            "generated_paths": [],
            "related_paths": [],
        },
        "source_error": _mapping_or_none(snapshot.get("error")),
        "trace": trace,
        "outcome": normalized_outcome,
    }
    trace_path.write_text(f"{json.dumps(record, indent=2)}\n", encoding="utf-8")
    return record


def queue_trace_record(
    root: Path,
    payload: Mapping[str, object],
    *,
    queue_name: str = "default",
    trace_name: str | None = None,
    outcome: Mapping[str, object] | None = None,
    source_trace_path: Path | None = None,
    source_outcome_path: Path | None = None,
) -> dict[str, object]:
    """Persist one queued trainer-side handoff item for later asynchronous trace import."""

    resolved_root = root.resolve()
    normalized_payload = normalize_trace_record_payload(payload)
    normalized_outcome = _mapping_or_none(normalized_payload.get("outcome"))
    if outcome is not None:
        normalized_outcome = _normalize_outcome_payload(outcome)
    queue_dir = _trace_queue_dir(resolved_root, queue_name, processed=False)
    queue_dir.mkdir(parents=True, exist_ok=True)
    safe_trace_name = _sanitize_name(
        trace_name or _default_trace_name(normalized_payload),
        default="trace-record",
    )
    normalized_queue_name = queue_dir.name
    queued_at = _utc_now_isoformat()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    queue_item_path = queue_dir / f"{timestamp}-{safe_trace_name}.json"
    snapshot = _mapping_or_none(normalized_payload.get("snapshot")) or {}
    trace = _mapping_or_none(normalized_payload.get("trace")) or {}
    queue_item: dict[str, object] = {
        "schema_version": TRACE_QUEUE_ITEM_SCHEMA_VERSION,
        "queue_item_kind": TRACE_QUEUE_ITEM_KIND,
        "queue_status": "queued",
        "queue_name": normalized_queue_name,
        "queued_at": queued_at,
        "queue_item_path": _relative_to_root(queue_item_path, resolved_root),
        "trace_name": safe_trace_name,
        "question": _string_or_none(snapshot.get("question"))
        or _string_or_none(trace.get("question")),
        "bundle_version": _string_or_none(trace.get("bundle_version")),
        "source_command": _string_or_none(normalized_payload.get("source_command")),
        "source_root": _string_or_none(normalized_payload.get("source_root")),
        "source_trace_path": str(source_trace_path) if source_trace_path is not None else None,
        "source_outcome_path": (
            str(source_outcome_path) if source_outcome_path is not None else None
        ),
        "trace_payload": payload,
        "outcome": normalized_outcome,
    }
    queue_item_path.write_text(f"{json.dumps(queue_item, indent=2)}\n", encoding="utf-8")
    return queue_item


def _load_trace_queue_item(path: Path) -> dict[str, object]:
    payload = load_json_object(path)
    if _string_or_none(payload.get("queue_item_kind")) != TRACE_QUEUE_ITEM_KIND:
        raise ValueError(f"Queued trace item is invalid: {path}")
    return payload


def drain_trace_queue(
    root: Path,
    *,
    queue_name: str = "default",
    limit: int | None = None,
    keep_queued: bool = False,
) -> dict[str, object]:
    """Import queued trace items into the trainer-side imported-trace store."""

    resolved_root = root.resolve()
    queue_dir = _trace_queue_dir(resolved_root, queue_name, processed=False)
    processed_dir = _trace_queue_dir(resolved_root, queue_name, processed=True)
    queued_paths = sorted(queue_dir.glob("*.json")) if queue_dir.is_dir() else []
    selected_paths = queued_paths[:limit] if isinstance(limit, int) and limit > 0 else queued_paths
    imported_items: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    for queued_path in selected_paths:
        try:
            queued_item = _load_trace_queue_item(queued_path)
            trace_payload = _mapping_or_none(queued_item.get("trace_payload"))
            if trace_payload is None:
                raise ValueError("Queued trace item is missing `trace_payload`.")
            trace_name = _string_or_none(queued_item.get("trace_name"))
            outcome = _mapping_or_none(queued_item.get("outcome"))
            imported_record = write_trace_record(
                resolved_root,
                trace_payload,
                trace_name=trace_name,
                imported=True,
                outcome=outcome,
            )
            processed_dir.mkdir(parents=True, exist_ok=True)
            processed_path = processed_dir / queued_path.name
            processed_item = {
                **queued_item,
                "queue_status": "imported",
                "drained_at": _utc_now_isoformat(),
                "imported_trace_record_path": imported_record.get("trace_record_path"),
                "processed_queue_item_path": _relative_to_root(processed_path, resolved_root),
            }
            processed_path.write_text(
                f"{json.dumps(processed_item, indent=2)}\n",
                encoding="utf-8",
            )
            if not keep_queued and queued_path.exists():
                queued_path.unlink()
            imported_items.append(
                {
                    "queue_item_path": _relative_to_root(queued_path, resolved_root),
                    "processed_queue_item_path": _relative_to_root(processed_path, resolved_root),
                    "trace_name": trace_name,
                    "question": processed_item.get("question"),
                    "imported_trace_record_path": imported_record.get("trace_record_path"),
                    "acceptance_status": (
                        outcome.get("acceptance_status") if outcome is not None else None
                    ),
                }
            )
        except Exception as exc:
            failures.append(
                {
                    "queue_item_path": _relative_to_root(queued_path, resolved_root),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )

    queued_count_after = len(list(queue_dir.glob("*.json"))) if queue_dir.is_dir() else 0
    return {
        "queue_name": _sanitize_name(queue_name, default="default"),
        "queue_dir": _relative_to_root(queue_dir, resolved_root),
        "processed_queue_dir": _relative_to_root(processed_dir, resolved_root),
        "queue_found": queue_dir.is_dir(),
        "queued_count_before": len(queued_paths),
        "selected_count": len(selected_paths),
        "drained_count": len(imported_items),
        "failed_count": len(failures),
        "remaining_count": queued_count_after,
        "keep_queued": keep_queued,
        "status": "success" if not failures else "partial",
        "items": imported_items,
        "failures": failures,
    }
