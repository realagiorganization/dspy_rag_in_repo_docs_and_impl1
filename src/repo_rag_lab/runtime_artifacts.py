"""Versioned bundle, overlay, and runtime-trace helpers."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from .azure_artifacts import (
    AzureArtifactConfig,
    AzureArtifactStore,
    batched_trace_blob_name,
    bundle_blob_names,
    bundle_channel_blob_name,
    bundle_version_blob_prefix,
    decode_queue_message,
    failed_trace_blob_name,
    family_state_blob_names,
    family_state_current_blob_name,
    processed_trace_blob_name,
    queued_trace_blob_name,
    repo_rag_bundle_container,
    repo_rag_family_state_container,
    repo_rag_trace_container,
    repo_rag_trace_queue_name,
)
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
DEFAULT_TRAINER_FAMILY_STATE_PATH = DEFAULT_TRAINER_SERVICE_DIR / "family-state.json"
DEFAULT_TRAINER_FAMILY_CACHE_DIR = DEFAULT_TRAINER_SERVICE_DIR / "families"
DEFAULT_REMOTE_FAMILY_STATE_CACHE_DIR = DEFAULT_TRAINER_SERVICE_DIR / "remote-family-state"
DEFAULT_TRAINER_RECOVERED_TRACES_DIR = DEFAULT_TRAINER_SERVICE_DIR / "recovered-imported-traces"
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
    evidence_items: Sequence[Mapping[str, object]] = ()
    command_trace: Sequence[Mapping[str, object]] = ()
    original_prompt: str | None = None
    reformulated_prompt: str | None = None
    prompt_family_id: str | None = None
    prompt_family_similarity: float | None = None
    prompt_family_band: str | None = None
    family_runtime_hit_rate: float | None = None
    family_artifact_hit_rate: float | None = None
    family_artifact_selected: bool | None = None
    mediation_metric_hits: int | None = None
    mediation_metric_total: int | None = None


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


def _dedupe_string_list(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(cleaned)
    return ordered


def _normalize_evidence_preview(value: object) -> str:
    return " ".join(str(value or "").strip().split())[:240]


def _trace_evidence_fingerprints(rows: Sequence[Mapping[str, object]]) -> list[str]:
    fingerprints: list[str] = []
    seen: set[str] = set()
    for row in rows:
        source = " ".join(str(row.get("source") or "").strip().split())
        preview = _normalize_evidence_preview(row.get("preview") or row.get("text"))
        if not source and not preview:
            continue
        payload = json.dumps(
            [source.casefold(), preview.casefold()],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        token = f"ev-{hashlib.sha256(payload).hexdigest()[:16]}"
        if token in seen:
            continue
        seen.add(token)
        fingerprints.append(token)
    return fingerprints


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


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _utc_now_isoformat() -> str:
    return datetime.now(UTC).isoformat()


def _family_runtime_metric_payload(record: Mapping[str, object]) -> dict[str, object]:
    """Return the normalized metric payload for one family runtime record."""

    hits = _int_or_none(record.get("metric_hits"))
    total = _int_or_none(record.get("metric_total"))
    ratio = _float_or_none(record.get("metric_ratio"))
    if ratio is None and hits is not None and total is not None and total > 0:
        ratio = round(max(0, min(hits, total)) / total, 6)
    return {
        "metric_hits": hits,
        "metric_total": total,
        "hit_rate": ratio,
    }


def _bundle_family_entry(family_payload: Mapping[str, object]) -> dict[str, object] | None:
    """Return the bundle-registry entry for one persisted prompt family."""

    prompt_family_id = _string_or_none(family_payload.get("prompt_family_id"))
    if prompt_family_id is None:
        return None
    father_record = _mapping_or_none(family_payload.get("family_father_record"))
    runtime_record = _mapping_or_none(
        family_payload.get("family_runtime_record")
    ) or _mapping_or_none(family_payload.get("family_champion_record"))
    father_question = _string_or_none(family_payload.get("family_father_question"))
    if father_question is None and father_record is not None:
        father_question = _string_or_none(father_record.get("question"))
    question_variants = _string_list(family_payload.get("question_variants"))
    runtime_metric = (
        _family_runtime_metric_payload(runtime_record) if runtime_record is not None else {}
    )
    persisted_runtime_artifact = _mapping_or_none(family_payload.get("family_runtime_artifact"))
    runtime_artifact: dict[str, object]
    if persisted_runtime_artifact is not None:
        runtime_artifact = persisted_runtime_artifact
    else:
        runtime_artifact = {
            "artifact_kind": (
                "family-runtime-record-placeholder"
                if runtime_record is not None
                else "family-runtime-artifact-missing"
            ),
            "artifact_ready": False,
            "artifact_source": ("family_runtime_record" if runtime_record is not None else None),
            **runtime_metric,
        }
    return {
        "prompt_family_id": prompt_family_id,
        "question": _string_or_none(family_payload.get("question")),
        "normalized_question": _string_or_none(family_payload.get("normalized_question")),
        "question_variants": question_variants,
        "question_variant_count": _int_or_none(family_payload.get("question_variant_count")),
        "family_father_question": father_question,
        "family_father_similarity_mean": _float_or_none(
            family_payload.get("family_father_similarity_mean")
        ),
        "family_father_record": father_record,
        "family_runtime_record": runtime_record,
        "family_runtime_score": _float_or_none(family_payload.get("family_runtime_score")),
        "family_runtime_metric": runtime_metric or None,
        "runtime_artifact": runtime_artifact,
    }


def build_bundle_family_registry(
    root: Path,
    *,
    family_state_path: Path,
    family_artifact_registry: Mapping[str, object] | None = None,
) -> dict[str, object] | None:
    """Build the monolithic bundle's internal family registry from one family-state file."""

    resolved_root = root.resolve()
    resolved_family_state_path = family_state_path.resolve()
    if not resolved_family_state_path.is_file():
        return None
    payload = load_json_object(resolved_family_state_path)
    raw_families = payload.get("prompt_families")
    if not isinstance(raw_families, list):
        return None
    families: list[dict[str, object]] = []
    for family in raw_families:
        normalized = _mapping_or_none(family)
        if normalized is None:
            continue
        resolved_family_payload = _resolved_family_state_family_payload(
            resolved_family_state_path,
            normalized,
        )
        entry = _bundle_family_entry(resolved_family_payload)
        if entry is not None:
            if isinstance(family_artifact_registry, Mapping):
                family_id = _string_or_none(entry.get("prompt_family_id"))
                family_artifact_payload = (
                    _mapping_or_none(family_artifact_registry.get(family_id))
                    if family_id is not None
                    else None
                )
                if family_artifact_payload is not None:
                    runtime_artifact = _mapping_or_none(entry.get("runtime_artifact")) or {}
                    benchmark_summary = _mapping_or_none(
                        family_artifact_payload.get("benchmark_summary")
                    )
                    runtime_artifact.update(
                        {
                            "artifact_kind": "compiled-family-program",
                            "artifact_ready": bool(
                                family_artifact_payload.get("artifact_ready", True)
                            ),
                            "artifact_source": _string_or_none(
                                family_artifact_payload.get("artifact_source")
                            )
                            or "family_artifact_registry",
                            "program_path": _string_or_none(
                                family_artifact_payload.get("program_path")
                            ),
                            "metadata_path": _string_or_none(
                                family_artifact_payload.get("metadata_path")
                            ),
                            "optimizer": _string_or_none(family_artifact_payload.get("optimizer")),
                            "training_example_count": _int_or_none(
                                family_artifact_payload.get("training_example_count")
                            ),
                            "benchmark_example_count": _int_or_none(
                                family_artifact_payload.get("benchmark_example_count")
                            ),
                            "benchmark_summary": benchmark_summary,
                            "hit_rate": (
                                _float_or_none(benchmark_summary.get("pass_rate"))
                                if benchmark_summary is not None
                                else _float_or_none(runtime_artifact.get("hit_rate"))
                            ),
                        }
                    )
                    entry["runtime_artifact"] = runtime_artifact
            families.append(entry)
    return {
        "schema_version": 1,
        "registry_kind": "repo-rag-family-registry",
        "family_state_path": _relative_to_root(resolved_family_state_path, resolved_root),
        "family_count": len(families),
        "prompt_family_count": len(families),
        "families": families,
    }


def _family_artifact_blob_names(bundle_version: str, prompt_family_id: str) -> dict[str, str]:
    """Return the remote blob names for one family runtime artifact."""

    prefix = bundle_version_blob_prefix(bundle_version)
    safe_family_id = _sanitize_name(prompt_family_id, default="family")
    family_prefix = f"{prefix}/families/{safe_family_id}"
    return {
        "program": f"{family_prefix}/program.json",
        "metadata": f"{family_prefix}/metadata.json",
    }


def _family_state_member_blob_names(
    family_state_version: str,
    prompt_family_id: str,
) -> dict[str, str]:
    """Return the remote blob names for one persisted family-state member."""

    safe_family_id = _sanitize_name(prompt_family_id, default="family")
    family_prefix = f"versions/{family_state_version}/families/{safe_family_id}"
    return {
        "family": f"{family_prefix}/family.json",
        "father": f"{family_prefix}/father.json",
        "records_prefix": f"{family_prefix}/records",
        "runtime_program": f"{family_prefix}/runtime-artifact/program.json",
        "runtime_metadata": f"{family_prefix}/runtime-artifact/metadata.json",
    }


def _resolve_family_state_family_path(
    family_state_path: Path,
    family_payload: Mapping[str, object],
) -> Path | None:
    """Resolve one persisted local/remote family payload path from a thin family-state entry."""

    family_path_text = _string_or_none(family_payload.get("family_path"))
    if family_path_text is None:
        return None
    candidate = Path(family_path_text)
    if candidate.is_absolute():
        return candidate
    return family_state_path.resolve().parent / candidate


def _resolved_family_state_family_payload(
    family_state_path: Path,
    family_payload: Mapping[str, object],
) -> dict[str, object]:
    """Return the full family payload for one thin-index family-state entry when available."""

    resolved_family_path = _resolve_family_state_family_path(family_state_path, family_payload)
    if resolved_family_path is not None and resolved_family_path.is_file():
        try:
            payload = json.loads(resolved_family_path.read_text(encoding="utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, dict):
            merged_payload = {str(key): value for key, value in payload.items()}
            for field_name in (
                "prompt_family_id",
                "family_needs_recompile",
                "question",
                "normalized_question",
                "question_variants",
                "question_variant_count",
                "family_father_question",
                "family_father_similarity_mean",
                "family_father_record",
                "family_runtime_record",
                "family_runtime_artifact",
                "family_runtime_score",
                "family_champion_record",
                "family_champion_score",
            ):
                if field_name in family_payload and field_name not in merged_payload:
                    merged_payload[field_name] = family_payload[field_name]
            return merged_payload
    return {str(key): value for key, value in family_payload.items()}


def _family_state_record_token(record: Mapping[str, object]) -> str:
    """Return a stable file token for one persisted family replay-set record."""

    exact_snapshot_id = _string_or_none(record.get("exact_snapshot_id"))
    if exact_snapshot_id is not None:
        return _sanitize_name(exact_snapshot_id, default="record")
    record_token = json.dumps(
        {str(key): value for key, value in record.items()},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha1(record_token.encode("utf-8")).hexdigest()[:16]


def _family_state_records_from_payload(
    family_payload: Mapping[str, object],
) -> list[dict[str, object]]:
    """Return stable deduplicated replay-set records known for one persisted family."""

    records: list[dict[str, object]] = []
    seen: set[str] = set()

    def _append_record(value: object) -> None:
        record = _mapping_or_none(value)
        if record is None:
            return
        token = _family_state_record_token(record)
        if token in seen:
            return
        seen.add(token)
        records.append(record)

    raw_family_records = family_payload.get("family_records")
    if isinstance(raw_family_records, list):
        for value in raw_family_records:
            _append_record(value)
    raw_context_groups = family_payload.get("context_groups")
    if isinstance(raw_context_groups, list):
        for group in raw_context_groups:
            group_mapping = _mapping_or_none(group)
            if group_mapping is None:
                continue
            _append_record(group_mapping.get("champion_record"))
    _append_record(family_payload.get("family_runtime_record"))
    _append_record(family_payload.get("family_champion_record"))
    _append_record(family_payload.get("family_father_record"))
    return records


def _bundle_family_runtime_artifacts(
    bundle_payload: Mapping[str, object],
) -> list[tuple[str, dict[str, object]]]:
    """Return bundle family runtime-artifact payloads keyed by family id."""

    family_registry = bundle_payload.get("family_registry")
    registry_mapping = family_registry if isinstance(family_registry, Mapping) else {}
    raw_families = registry_mapping.get("families")
    if not isinstance(raw_families, list):
        return []
    artifacts: list[tuple[str, dict[str, object]]] = []
    for family in raw_families:
        if not isinstance(family, Mapping):
            continue
        prompt_family_id = _string_or_none(family.get("prompt_family_id"))
        runtime_artifact_value = family.get("runtime_artifact")
        if prompt_family_id is None or not isinstance(runtime_artifact_value, Mapping):
            continue
        if isinstance(runtime_artifact_value, dict):
            artifacts.append((prompt_family_id, runtime_artifact_value))
            continue
        runtime_artifact = _mapping_or_none(runtime_artifact_value)
        if runtime_artifact is None:
            continue
        if isinstance(family, dict):
            family["runtime_artifact"] = runtime_artifact
        artifacts.append((prompt_family_id, runtime_artifact))
    return artifacts


def bundle_manifest_path(metadata_path: Path) -> Path:
    """Return the bundle-manifest path that belongs to ``metadata_path``."""

    return metadata_path.parent / BUNDLE_FILENAME


def _bundle_store_is_mirror_layout(root: Path) -> bool:
    """Return whether ``root`` looks like the staged worker bundle mirror."""

    resolved_root = root.resolve()
    return (resolved_root / "channels").is_dir() or (resolved_root / "versions").is_dir()


def _bundle_channels_dir(root: Path) -> Path:
    """Return the bundle-channel directory for either repo or mirror layout."""

    resolved_root = root.resolve()
    if _bundle_store_is_mirror_layout(resolved_root):
        return resolved_root / "channels"
    return resolved_root / DEFAULT_BUNDLE_CHANNELS_DIR


def build_bundle_manifest(
    root: Path, metadata: Mapping[str, object], metadata_path: Path
) -> dict[str, object]:
    """Build a versioned bundle manifest from one DSPy metadata payload."""

    resolved_root = root.resolve()
    resolved_metadata_path = metadata_path.resolve()
    resolved_bundle_path = bundle_manifest_path(resolved_metadata_path)

    run_name = str(metadata.get("run_name") or resolved_metadata_path.parent.name)
    bundle_version = str(metadata.get("bundle_version") or run_name)
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
    lineage = _mapping_or_none(metadata.get("lineage"))
    family_artifact_registry = _mapping_or_none(metadata.get("family_artifact_registry"))
    family_state_path = (
        _string_or_none(lineage.get("family_state_path")) if isinstance(lineage, Mapping) else None
    ) or (
        _string_or_none(lineage.get("champion_index_path"))
        if isinstance(lineage, Mapping)
        else None
    )
    family_count = None
    if isinstance(lineage, Mapping):
        raw_family_count = lineage.get("family_count")
        if not isinstance(raw_family_count, int):
            raw_family_count = lineage.get("prompt_family_count")
        if isinstance(raw_family_count, int):
            family_count = raw_family_count
    family_registry = None
    if family_state_path is not None:
        resolved_family_state_path = Path(family_state_path)
        if not resolved_family_state_path.is_absolute():
            resolved_family_state_path = resolved_root / resolved_family_state_path
        family_registry = build_bundle_family_registry(
            resolved_root,
            family_state_path=resolved_family_state_path,
            family_artifact_registry=family_artifact_registry,
        )
        if family_registry is not None and family_count is None:
            raw_registry_count = family_registry.get("family_count")
            if isinstance(raw_registry_count, int):
                family_count = raw_registry_count
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
        "bundle_version": bundle_version,
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
        "family_artifact_registry": family_artifact_registry,
        "lm": lm,
        "run_family": _string_or_none(metadata.get("run_family")),
        "lineage": lineage,
        "family_state_path": family_state_path,
        "family_count": family_count,
        "family_registry": family_registry,
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
    resolved_root = root.resolve()
    if _bundle_store_is_mirror_layout(resolved_root):
        versions_root = resolved_root / "versions"
        if not versions_root.exists():
            return []
        candidate_paths = versions_root.glob(f"*/{BUNDLE_FILENAME}")
    else:
        artifact_root = resolved_root / "artifacts" / "dspy"
        if not artifact_root.exists():
            return []
        candidate_paths = artifact_root.glob(f"*/{BUNDLE_FILENAME}")
    candidates: list[tuple[Path, dict[str, object]]] = []
    for bundle_path in candidate_paths:
        payload = load_bundle_manifest(bundle_path)
        candidates.append((bundle_path.resolve(), payload))
    return sorted(
        candidates,
        key=lambda item: (
            str(item[1].get("created_at") or ""),
            str(_relative_to_root(item[0], resolved_root)),
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


def resolve_azure_artifact_config(*, queue_name: str | None = None) -> AzureArtifactConfig | None:
    """Resolve Azure Blob + Queue configuration from the current environment."""

    config = AzureArtifactConfig.from_env(queue_name=queue_name)
    if not config.configured:
        return None
    return config


def published_bundle_record_from_state(
    state: Mapping[str, object],
    *,
    root: Path,
) -> dict[str, object]:
    """Reconstruct one published-bundle-like payload from a channel state."""

    bundle_summary = _mapping_or_none(state.get("current_bundle")) or {}
    return {
        "schema_version": PUBLISHED_BUNDLE_SCHEMA_VERSION,
        "published_bundle_kind": "published",
        "publish_status": _string_or_none(state.get("current_publish_status")) or "published",
        "published_at": _string_or_none(state.get("updated_at")),
        "published_bundle_path": _string_or_none(state.get("current_published_bundle_path")),
        "bundle_version": _string_or_none(state.get("current_bundle_version")),
        "run_name": _string_or_none(state.get("current_run_name")),
        "bundle_path": _string_or_none(state.get("current_bundle_path")),
        "artifact_dir": _string_or_none(bundle_summary.get("artifact_dir")),
        "program_path": _string_or_none(state.get("current_program_path")),
        "metadata_path": _string_or_none(state.get("current_metadata_path")),
        "bundle_status": _string_or_none(state.get("current_bundle_status")),
        "benchmark_status": _string_or_none(state.get("current_benchmark_status")),
        "retrieval_mode": _string_or_none(bundle_summary.get("retrieval_mode")),
        "top_k": _int_or_none(bundle_summary.get("top_k")),
        "note": None,
        "bundle_summary": bundle_summary,
        "remote_root": str(root),
    }


def upload_remote_bundle(
    root: Path,
    *,
    published_record: Mapping[str, object],
    config: AzureArtifactConfig,
) -> dict[str, object]:
    """Publish one bundle version plus metadata/program assets into Azure Blob storage."""

    resolved_root = root.resolve()
    store = AzureArtifactStore(config)
    container = repo_rag_bundle_container(config)
    bundle_version = _string_or_none(published_record.get("bundle_version"))
    bundle_path_text = _string_or_none(published_record.get("bundle_path"))
    metadata_path_text = _string_or_none(published_record.get("metadata_path"))
    program_path_text = _string_or_none(published_record.get("program_path"))
    if bundle_version is None or bundle_path_text is None or metadata_path_text is None:
        raise ValueError("Published bundle record is missing one or more required bundle paths.")

    bundle_blob_map = bundle_blob_names(bundle_version)
    bundle_path = resolved_root / bundle_path_text
    metadata_path = resolved_root / metadata_path_text
    program_path = resolved_root / program_path_text if program_path_text is not None else None
    bundle_payload = load_bundle_manifest(bundle_path)

    store.upload_text(container, bundle_blob_map["bundle"], bundle_path.read_text(encoding="utf-8"))
    store.upload_text(
        container,
        bundle_blob_map["metadata"],
        metadata_path.read_text(encoding="utf-8"),
    )
    if program_path is not None and program_path.is_file():
        store.upload_text(
            container,
            bundle_blob_map["program"],
            program_path.read_text(encoding="utf-8"),
        )
    remote_family_artifact_blobs: dict[str, dict[str, str]] = {}
    for prompt_family_id, runtime_artifact in _bundle_family_runtime_artifacts(bundle_payload):
        if not bool(runtime_artifact.get("artifact_ready")):
            continue
        artifact_program_path_text = _string_or_none(runtime_artifact.get("program_path"))
        if artifact_program_path_text is None:
            continue
        artifact_program_path = resolved_root / artifact_program_path_text
        if not artifact_program_path.is_file():
            continue
        family_blob_map = _family_artifact_blob_names(bundle_version, prompt_family_id)
        store.upload_text(
            container,
            family_blob_map["program"],
            artifact_program_path.read_text(encoding="utf-8"),
        )
        artifact_metadata_path_text = _string_or_none(runtime_artifact.get("metadata_path"))
        if artifact_metadata_path_text is not None:
            artifact_metadata_path = resolved_root / artifact_metadata_path_text
            if artifact_metadata_path.is_file():
                store.upload_text(
                    container,
                    family_blob_map["metadata"],
                    artifact_metadata_path.read_text(encoding="utf-8"),
                )
        remote_family_artifact_blobs[prompt_family_id] = family_blob_map
    store.upload_json(container, bundle_blob_map["published"], published_record)
    payload: dict[str, object] = {
        "storage_backend": "azure-blob",
        "bundle_container": container,
        "remote_bundle_blobs": bundle_blob_map,
    }
    if remote_family_artifact_blobs:
        payload["remote_family_artifact_blobs"] = remote_family_artifact_blobs
    return payload


def upload_remote_bundle_channel(
    channel_state: Mapping[str, object],
    *,
    channel: str,
    config: AzureArtifactConfig,
) -> dict[str, object]:
    """Upload one bundle-channel state into Azure Blob storage."""

    store = AzureArtifactStore(config)
    container = repo_rag_bundle_container(config)
    blob_name = bundle_channel_blob_name(channel)
    store.upload_json(container, blob_name, channel_state)
    return {
        "storage_backend": "azure-blob",
        "bundle_container": container,
        "remote_channel_blob": blob_name,
    }


def inspect_remote_bundle_channel(channel: str) -> dict[str, object] | None:
    """Inspect one remote bundle channel when Azure bundle storage is configured."""

    config = resolve_azure_artifact_config()
    if config is None or not config.bundles_enabled:
        return None
    normalized_channel = _validate_bundle_channel(channel)
    store = AzureArtifactStore(config)
    container = repo_rag_bundle_container(config)
    blob_name = bundle_channel_blob_name(normalized_channel)
    if not store.blob_exists(container, blob_name):
        return {
            "channel_found": False,
            "requested_channel": normalized_channel,
            "channel_path": blob_name,
            "storage_backend": "azure-blob",
            "bundle_container": container,
        }
    payload = store.download_json(container, blob_name)
    return {
        "channel_found": True,
        "requested_channel": normalized_channel,
        "storage_backend": "azure-blob",
        "bundle_container": container,
        **payload,
    }


def inspect_remote_bundle_version(bundle_version: str) -> dict[str, object] | None:
    """Inspect one remote bundle version when Azure bundle storage is configured."""

    config = resolve_azure_artifact_config()
    if config is None or not config.bundles_enabled:
        return None
    store = AzureArtifactStore(config)
    container = repo_rag_bundle_container(config)
    blob_map = bundle_blob_names(bundle_version)
    if not store.blob_exists(container, blob_map["bundle"]):
        return None
    bundle_payload = store.download_json(container, blob_map["bundle"])
    bundle_payload["storage_backend"] = "azure-blob"
    bundle_payload["bundle_container"] = container
    bundle_payload["remote_bundle_blobs"] = blob_map
    return bundle_payload


def _latest_remote_bundle_version(
    *,
    store: AzureArtifactStore,
    container: str,
) -> str | None:
    """Return the newest remotely published bundle version visible in blob storage."""

    bundle_blob_names = sorted(store.list_blobs(container, prefix="versions/"), reverse=True)
    versions: set[str] = set()
    for blob_name in bundle_blob_names:
        if not blob_name.endswith("/bundle.json"):
            continue
        parts = blob_name.split("/", 2)
        if len(parts) < 3:
            continue
        version = parts[1].strip()
        if version:
            versions.add(version)
    if not versions:
        return None
    return sorted(versions, reverse=True)[0]


def fetch_remote_bundle(
    root: Path,
    *,
    bundle_version: str | None = None,
    channel: str | None = None,
) -> dict[str, object] | None:
    """Download one remote bundle version into the local worker cache."""

    resolved_root = root.resolve()
    config = resolve_azure_artifact_config()
    if config is None or not config.bundles_enabled:
        return None
    requested_channel: str | None = None
    resolved_bundle_version = bundle_version
    store = AzureArtifactStore(config)
    container = repo_rag_bundle_container(config)
    resolved_from = "bundle-version" if bundle_version is not None else "channel"
    if resolved_bundle_version is None:
        requested_channel = channel or "stable"
        channel_state = inspect_remote_bundle_channel(requested_channel)
        if channel_state is not None and channel_state.get("channel_found"):
            resolved_bundle_version = _string_or_none(channel_state.get("current_bundle_version"))
        if resolved_bundle_version is None:
            resolved_bundle_version = _latest_remote_bundle_version(
                store=store,
                container=container,
            )
            resolved_from = "latest-remote-version"
        if resolved_bundle_version is None:
            return None

    blob_map = bundle_blob_names(resolved_bundle_version)
    cache_dir = resolved_root / "artifacts" / "dspy" / "remote" / resolved_bundle_version
    cache_dir.mkdir(parents=True, exist_ok=True)
    local_paths = {
        "bundle_path": cache_dir / BUNDLE_FILENAME,
        "metadata_path": cache_dir / "metadata.json",
        "program_path": cache_dir / "program.json",
        "published_bundle_path": cache_dir / "published.json",
    }
    for key in ("bundle_path", "metadata_path", "program_path"):
        local_path = local_paths[key]
        blob_key = {
            "bundle_path": "bundle",
            "metadata_path": "metadata",
            "program_path": "program",
        }[key]
        local_path.write_text(
            store.download_text(container, blob_map[blob_key]),
            encoding="utf-8",
        )
    published_payload: dict[str, object] = {}
    published_blob_name = blob_map["published"]
    if store.blob_exists(container, published_blob_name):
        local_paths["published_bundle_path"].write_text(
            store.download_text(container, published_blob_name),
            encoding="utf-8",
        )
        published_payload = load_json_object(local_paths["published_bundle_path"])
    bundle_payload = load_bundle_manifest(local_paths["bundle_path"])
    remote_family_artifact_blobs: dict[str, dict[str, str]] = {}
    for prompt_family_id, runtime_artifact in _bundle_family_runtime_artifacts(bundle_payload):
        if not bool(runtime_artifact.get("artifact_ready")):
            continue
        family_blob_map = _family_artifact_blob_names(resolved_bundle_version, prompt_family_id)
        local_family_dir = (
            cache_dir
            / "families"
            / _sanitize_name(
                prompt_family_id,
                default="family",
            )
        )
        local_family_dir.mkdir(parents=True, exist_ok=True)
        downloaded_any = False
        if store.blob_exists(container, family_blob_map["program"]):
            local_program_path = local_family_dir / "program.json"
            local_program_path.write_text(
                store.download_text(container, family_blob_map["program"]),
                encoding="utf-8",
            )
            runtime_artifact["program_path"] = _relative_to_root(local_program_path, resolved_root)
            downloaded_any = True
        if store.blob_exists(container, family_blob_map["metadata"]):
            local_metadata_path = local_family_dir / "metadata.json"
            local_metadata_path.write_text(
                store.download_text(container, family_blob_map["metadata"]),
                encoding="utf-8",
            )
            runtime_artifact["metadata_path"] = _relative_to_root(
                local_metadata_path,
                resolved_root,
            )
            downloaded_any = True
        runtime_artifact["artifact_ready"] = downloaded_any and bool(
            _string_or_none(runtime_artifact.get("program_path"))
        )
        if downloaded_any:
            remote_family_artifact_blobs[prompt_family_id] = family_blob_map
    local_paths["bundle_path"].write_text(
        f"{json.dumps(bundle_payload, indent=2)}\n",
        encoding="utf-8",
    )
    payload: dict[str, object] = {
        "bundle_found": True,
        "storage_backend": "azure-blob",
        "bundle_container": container,
        "bundle_version": resolved_bundle_version,
        "requested_channel": requested_channel,
        "resolved_from": resolved_from,
        "remote_bundle_blobs": blob_map,
        "cache_dir": _relative_to_root(cache_dir, resolved_root),
        "bundle_path": _relative_to_root(local_paths["bundle_path"], resolved_root),
        "metadata_path": _relative_to_root(local_paths["metadata_path"], resolved_root),
        "program_path": _relative_to_root(local_paths["program_path"], resolved_root),
        "bundle_status": _string_or_none(bundle_payload.get("bundle_status")),
        "benchmark_status": _string_or_none(bundle_payload.get("benchmark_status")),
        "run_name": _string_or_none(bundle_payload.get("run_name")),
        "publish_status": _string_or_none(published_payload.get("publish_status")),
    }
    if local_paths["published_bundle_path"].is_file():
        payload["published_bundle_path"] = _relative_to_root(
            local_paths["published_bundle_path"],
            resolved_root,
        )
    if remote_family_artifact_blobs:
        payload["remote_family_artifact_blobs"] = remote_family_artifact_blobs
    return payload


def _utc_timestamp_token() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def upload_remote_family_state(
    root: Path,
    *,
    family_state_path: Path,
) -> dict[str, object] | None:
    """Upload one family-state index into the remote family-state container when configured."""

    config = resolve_azure_artifact_config()
    if config is None or not config.family_state_enabled:
        return None
    payload = load_json_object(family_state_path)
    resolved_root = root.resolve()
    resolved_family_state_path = family_state_path.resolve()
    store = AzureArtifactStore(config)
    container = repo_rag_family_state_container(config)
    for legacy_blob_name in store.list_blobs(container, prefix="families/"):
        store.delete_blob(container, legacy_blob_name)
    if store.blob_exists(container, "family-state.json"):
        store.delete_blob(container, "family-state.json")
    family_state_version = _utc_timestamp_token()
    blob_map = family_state_blob_names(family_state_version)
    prompt_families = payload.get("prompt_families")
    prompt_family_count = len(prompt_families) if isinstance(prompt_families, list) else 0
    current_payload = {
        "schema_version": 1,
        "family_state_kind": "repo-rag-family-state",
        "updated_at": _utc_now_isoformat(),
        "current_version": family_state_version,
        "current_family_state_blob": blob_map["family_state"],
        "current_family_count": prompt_family_count,
        "current_prompt_family_count": prompt_family_count,
    }
    family_state_text = resolved_family_state_path.read_text(encoding="utf-8")
    remote_family_member_blobs: dict[str, dict[str, object]] = {}
    for family_entry in _mapping_list(payload.get("prompt_families")):
        prompt_family_id = _string_or_none(family_entry.get("prompt_family_id"))
        if prompt_family_id is None:
            continue
        family_payload = _resolved_family_state_family_payload(
            resolved_family_state_path,
            family_entry,
        )
        family_blob_map = _family_state_member_blob_names(family_state_version, prompt_family_id)
        store.upload_json(container, family_blob_map["family"], family_payload)
        father_record = _mapping_or_none(family_payload.get("family_father_record"))
        if father_record is not None:
            store.upload_json(container, family_blob_map["father"], father_record)
        record_blob_map: dict[str, str] = {}
        for record in _family_state_records_from_payload(family_payload):
            record_token = _family_state_record_token(record)
            record_blob_name = f"{family_blob_map['records_prefix']}/{record_token}.json"
            store.upload_json(container, record_blob_name, record)
            record_blob_map[record_token] = record_blob_name
        runtime_artifact_blob_map: dict[str, str] = {}
        runtime_artifact = _mapping_or_none(family_payload.get("family_runtime_artifact"))
        if runtime_artifact is not None:
            runtime_program_path_text = _string_or_none(runtime_artifact.get("program_path"))
            if runtime_program_path_text is not None:
                runtime_program_path = Path(runtime_program_path_text)
                if not runtime_program_path.is_absolute():
                    runtime_program_path = resolved_root / runtime_program_path
                if runtime_program_path.is_file():
                    store.upload_text(
                        container,
                        family_blob_map["runtime_program"],
                        runtime_program_path.read_text(encoding="utf-8"),
                    )
                    runtime_artifact_blob_map["program"] = family_blob_map["runtime_program"]
            runtime_metadata_path_text = _string_or_none(runtime_artifact.get("metadata_path"))
            if runtime_metadata_path_text is not None:
                runtime_metadata_path = Path(runtime_metadata_path_text)
                if not runtime_metadata_path.is_absolute():
                    runtime_metadata_path = resolved_root / runtime_metadata_path
                if runtime_metadata_path.is_file():
                    store.upload_text(
                        container,
                        family_blob_map["runtime_metadata"],
                        runtime_metadata_path.read_text(encoding="utf-8"),
                    )
                    runtime_artifact_blob_map["metadata"] = family_blob_map["runtime_metadata"]
        remote_family_member_blobs[prompt_family_id] = {
            "family": family_blob_map["family"],
            "father": family_blob_map["father"],
            "record_blobs": record_blob_map,
            "runtime_artifact_blobs": runtime_artifact_blob_map,
        }
    store.upload_text(
        container,
        blob_map["family_state"],
        family_state_text,
    )
    store.upload_json(container, blob_map["current"], current_payload)
    return {
        "storage_backend": "azure-blob",
        "family_state_container": container,
        "family_state_version": family_state_version,
        "remote_family_state_blobs": blob_map,
        "remote_family_member_blobs": remote_family_member_blobs,
        "family_state_path": _relative_to_root(resolved_family_state_path, resolved_root),
    }


def fetch_remote_family_state(root: Path) -> dict[str, object] | None:
    """Download the current remote family-state index into a local cache when configured."""

    resolved_root = root.resolve()
    config = resolve_azure_artifact_config()
    if config is None or not config.family_state_enabled:
        return None
    store = AzureArtifactStore(config)
    container = repo_rag_family_state_container(config)
    current_blob = family_state_current_blob_name()
    if not store.blob_exists(container, current_blob):
        return None
    current_payload = store.download_json(container, current_blob)
    family_state_version = _string_or_none(current_payload.get("current_version"))
    family_state_blob = _string_or_none(current_payload.get("current_family_state_blob")) or (
        _string_or_none(current_payload.get("current_champion_index_blob"))
    )
    if family_state_version is None or family_state_blob is None:
        return None
    cache_dir = resolved_root / DEFAULT_REMOTE_FAMILY_STATE_CACHE_DIR / family_state_version
    cache_dir.mkdir(parents=True, exist_ok=True)
    family_state_path = cache_dir / "family-state.json"
    current_path = cache_dir / "current.json"
    family_state_text = store.download_text(container, family_state_blob)
    current_path.write_text(
        json.dumps(current_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    cached_family_paths: dict[str, str] = {}
    cached_family_member_paths: dict[str, dict[str, object]] = {}
    remote_family_member_blobs: dict[str, dict[str, object]] = {}
    family_state_payload = json.loads(family_state_text)
    raw_prompt_families = (
        family_state_payload.get("prompt_families")
        if isinstance(family_state_payload, Mapping)
        else []
    )
    for family_index, family_value in enumerate(
        raw_prompt_families if isinstance(raw_prompt_families, list) else []
    ):
        family_entry = _mapping_or_none(family_value)
        if family_entry is None:
            continue
        prompt_family_id = _string_or_none(family_entry.get("prompt_family_id"))
        if prompt_family_id is None:
            continue
        family_blob_map = _family_state_member_blob_names(family_state_version, prompt_family_id)
        family_dir = cache_dir / "families" / _sanitize_name(prompt_family_id, default="family")
        family_dir.mkdir(parents=True, exist_ok=True)
        local_family_path = family_dir / "family.json"
        if store.blob_exists(container, family_blob_map["family"]):
            family_text = store.download_text(container, family_blob_map["family"])
        else:
            family_text = f"{json.dumps(family_entry, indent=2)}\n"
        local_family_path.write_text(family_text, encoding="utf-8")
        full_family_payload = json.loads(family_text)
        if not isinstance(full_family_payload, dict):
            full_family_payload = {str(key): value for key, value in family_entry.items()}
        cached_family_paths[prompt_family_id] = _relative_to_root(local_family_path, resolved_root)
        local_member_paths: dict[str, object] = {
            "family": _relative_to_root(local_family_path, resolved_root)
        }
        remote_member_blobs: dict[str, object] = {
            "family": family_blob_map["family"],
            "father": family_blob_map["father"],
            "record_blobs": {},
            "runtime_artifact_blobs": {},
        }
        father_record = _mapping_or_none(full_family_payload.get("family_father_record")) or _mapping_or_none(
            family_entry.get("family_father_record")
        )
        local_father_path = family_dir / "father.json"
        if store.blob_exists(container, family_blob_map["father"]):
            father_text = store.download_text(container, family_blob_map["father"])
            local_father_path.write_text(father_text, encoding="utf-8")
            local_member_paths["father"] = _relative_to_root(local_father_path, resolved_root)
        elif father_record is not None:
            local_father_path.write_text(
                f"{json.dumps(father_record, indent=2)}\n",
                encoding="utf-8",
            )
            local_member_paths["father"] = _relative_to_root(local_father_path, resolved_root)
        record_paths: list[str] = []
        record_blob_map: dict[str, str] = {}
        for record in _family_state_records_from_payload(full_family_payload):
            record_token = _family_state_record_token(record)
            record_blob_name = f"{family_blob_map['records_prefix']}/{record_token}.json"
            local_record_path = family_dir / "records" / f"{record_token}.json"
            local_record_path.parent.mkdir(parents=True, exist_ok=True)
            if store.blob_exists(container, record_blob_name):
                record_text = store.download_text(container, record_blob_name)
            else:
                record_text = f"{json.dumps(record, indent=2)}\n"
            local_record_path.write_text(record_text, encoding="utf-8")
            record_paths.append(_relative_to_root(local_record_path, resolved_root))
            record_blob_map[record_token] = record_blob_name
        local_member_paths["record_paths"] = record_paths
        remote_member_blobs["record_blobs"] = record_blob_map
        runtime_artifact = _mapping_or_none(full_family_payload.get("family_runtime_artifact")) or _mapping_or_none(
            family_entry.get("family_runtime_artifact")
        )
        runtime_artifact_blob_map: dict[str, str] = {}
        local_runtime_paths: dict[str, str] = {}
        if runtime_artifact is not None:
            normalized_runtime_artifact = {
                str(key): value for key, value in runtime_artifact.items()
            }
            if store.blob_exists(container, family_blob_map["runtime_program"]):
                local_runtime_dir = family_dir / "runtime-artifact"
                local_runtime_dir.mkdir(parents=True, exist_ok=True)
                local_runtime_program_path = local_runtime_dir / "program.json"
                local_runtime_program_path.write_text(
                    store.download_text(container, family_blob_map["runtime_program"]),
                    encoding="utf-8",
                )
                normalized_runtime_artifact["program_path"] = _relative_to_root(
                    local_runtime_program_path,
                    resolved_root,
                )
                local_runtime_paths["program"] = _relative_to_root(
                    local_runtime_program_path,
                    resolved_root,
                )
                runtime_artifact_blob_map["program"] = family_blob_map["runtime_program"]
            if store.blob_exists(container, family_blob_map["runtime_metadata"]):
                local_runtime_dir = family_dir / "runtime-artifact"
                local_runtime_dir.mkdir(parents=True, exist_ok=True)
                local_runtime_metadata_path = local_runtime_dir / "metadata.json"
                local_runtime_metadata_path.write_text(
                    store.download_text(container, family_blob_map["runtime_metadata"]),
                    encoding="utf-8",
                )
                normalized_runtime_artifact["metadata_path"] = _relative_to_root(
                    local_runtime_metadata_path,
                    resolved_root,
                )
                local_runtime_paths["metadata"] = _relative_to_root(
                    local_runtime_metadata_path,
                    resolved_root,
                )
                runtime_artifact_blob_map["metadata"] = family_blob_map["runtime_metadata"]
            if runtime_artifact_blob_map:
                full_family_payload["family_runtime_artifact"] = normalized_runtime_artifact
                if isinstance(raw_prompt_families, list):
                    updated_entry = dict(family_entry)
                    updated_entry["family_runtime_artifact"] = normalized_runtime_artifact
                    raw_prompt_families[family_index] = updated_entry
                    family_entry = updated_entry
                family_text = f"{json.dumps(full_family_payload, indent=2)}\n"
                local_family_path.write_text(family_text, encoding="utf-8")
                local_member_paths["runtime_artifact"] = local_runtime_paths
                remote_member_blobs["runtime_artifact_blobs"] = runtime_artifact_blob_map
        family_entry["family_path"] = str(Path("families") / _sanitize_name(prompt_family_id, default="family") / "family.json")
        if "father" in local_member_paths:
            family_entry["father_path"] = str(
                Path("families")
                / _sanitize_name(prompt_family_id, default="family")
                / "father.json"
            )
        family_entry["family_record_count"] = len(record_paths)
        family_entry["context_group_count"] = len(
            full_family_payload.get("context_groups")
            if isinstance(full_family_payload.get("context_groups"), list)
            else []
        )
        if isinstance(raw_prompt_families, list):
            raw_prompt_families[family_index] = family_entry
        cached_family_member_paths[prompt_family_id] = local_member_paths
        remote_family_member_blobs[prompt_family_id] = remote_member_blobs
    family_state_path.write_text(
        f"{json.dumps(family_state_payload, indent=2)}\n",
        encoding="utf-8",
    )
    return {
        "family_state_found": True,
        "storage_backend": "azure-blob",
        "family_state_container": container,
        "family_state_version": family_state_version,
        "current_blob": current_blob,
        "family_state_blob": family_state_blob,
        "cache_dir": _relative_to_root(cache_dir, resolved_root),
        "family_state_path": _relative_to_root(family_state_path, resolved_root),
        "current_state_path": _relative_to_root(current_path, resolved_root),
        "cached_family_paths": cached_family_paths,
        "cached_family_member_paths": cached_family_member_paths,
        "remote_family_member_blobs": remote_family_member_blobs,
    }


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
    return _bundle_channels_dir(root) / f"{normalized_channel}.json"


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
        "channel_path": _relative_to_root(channel_path, resolved_root),
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

    evidence_fingerprints = _dedupe_string_list(_trace_evidence_fingerprints(trace.evidence_items))
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
        "evidence_fingerprints": evidence_fingerprints,
        "evidence_count": len(evidence_fingerprints),
        "mcp_candidate_count": trace.mcp_candidate_count,
        "answer_length": trace.answer_length,
        "command_trace": _mapping_list(trace.command_trace),
        "original_prompt": trace.original_prompt,
        "reformulated_prompt": trace.reformulated_prompt,
        "prompt_family_id": trace.prompt_family_id,
        "prompt_family_similarity": trace.prompt_family_similarity,
        "prompt_family_band": trace.prompt_family_band,
        "family_runtime_hit_rate": trace.family_runtime_hit_rate,
        "family_artifact_hit_rate": trace.family_artifact_hit_rate,
        "family_artifact_selected": trace.family_artifact_selected,
        "mediation_metric_hits": trace.mediation_metric_hits,
        "mediation_metric_total": trace.mediation_metric_total,
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
    evidence_count = _int_or_none(payload.get("evidence_count"))
    mcp_candidate_count = _int_or_none(payload.get("mcp_candidate_count"))
    answer_length = _int_or_none(payload.get("answer_length"))
    prompt_family_similarity = _float_or_none(payload.get("prompt_family_similarity"))
    family_runtime_hit_rate = _float_or_none(payload.get("family_runtime_hit_rate"))
    family_artifact_hit_rate = _float_or_none(payload.get("family_artifact_hit_rate"))
    mediation_metric_hits = _int_or_none(payload.get("mediation_metric_hits"))
    mediation_metric_total = _int_or_none(payload.get("mediation_metric_total"))
    sources = _string_list(payload.get("sources"))
    evidence_fingerprints = _dedupe_string_list(_string_list(payload.get("evidence_fingerprints")))
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
        "evidence_fingerprints": evidence_fingerprints,
        "evidence_count": evidence_count
        if evidence_count is not None
        else len(evidence_fingerprints),
        "mcp_candidate_count": mcp_candidate_count if mcp_candidate_count is not None else 0,
        "answer_length": answer_length,
        "command_trace": _mapping_list(payload.get("command_trace")),
        "original_prompt": _string_or_none(payload.get("original_prompt")),
        "reformulated_prompt": _string_or_none(payload.get("reformulated_prompt")),
        "prompt_family_id": _string_or_none(payload.get("prompt_family_id")),
        "prompt_family_similarity": prompt_family_similarity,
        "prompt_family_band": _string_or_none(payload.get("prompt_family_band")),
        "family_runtime_hit_rate": family_runtime_hit_rate,
        "family_artifact_hit_rate": family_artifact_hit_rate,
        "family_artifact_selected": (
            payload.get("family_artifact_selected")
            if isinstance(payload.get("family_artifact_selected"), bool)
            else None
        ),
        "mediation_metric_hits": mediation_metric_hits,
        "mediation_metric_total": mediation_metric_total,
    }


def _trace_record_snapshot(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        "question": _string_or_none(payload.get("question")),
        "original_prompt": _string_or_none(payload.get("original_prompt")),
        "reformulated_prompt": _string_or_none(payload.get("reformulated_prompt")),
        "answer": _string_or_none(payload.get("answer")),
        "response_text": _string_or_none(payload.get("response_text")),
        "sources": _string_list(payload.get("sources")),
        "context": _list_or_empty(payload.get("context")),
        "retrieved_context": _list_or_empty(payload.get("retrieved_context")),
        "command_trace": _list_or_empty(payload.get("command_trace")),
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


def _backfill_runtime_trace_evidence(
    trace_payload: Mapping[str, object],
    snapshot: Mapping[str, object],
) -> dict[str, object]:
    """Backfill evidence fingerprints from stored context rows when the trace lacks them."""

    normalized = {str(key): value for key, value in trace_payload.items()}
    evidence_fingerprints = _dedupe_string_list(
        _string_list(normalized.get("evidence_fingerprints"))
    )
    if not evidence_fingerprints:
        evidence_rows = [
            row
            for row in _list_or_empty(snapshot.get("retrieved_context"))
            if isinstance(row, Mapping)
        ]
        evidence_rows.extend(
            row for row in _list_or_empty(snapshot.get("context")) if isinstance(row, Mapping)
        )
        evidence_fingerprints = _trace_evidence_fingerprints(evidence_rows)
    normalized["evidence_fingerprints"] = evidence_fingerprints
    evidence_count = _int_or_none(normalized.get("evidence_count"))
    normalized["evidence_count"] = (
        evidence_count if evidence_count is not None else len(evidence_fingerprints)
    )
    return normalized


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
        snapshot = {
            "question": _string_or_none(payload.get("question")),
            "original_prompt": _string_or_none(payload.get("original_prompt")),
            "reformulated_prompt": _string_or_none(payload.get("reformulated_prompt")),
            "answer": _string_or_none(payload.get("answer")),
            "response_text": _string_or_none(payload.get("response_text")),
            "sources": _string_list(payload.get("sources")),
            "context": _list_or_empty(payload.get("context")),
            "retrieved_context": _list_or_empty(payload.get("retrieved_context")),
            "command_trace": _list_or_empty(payload.get("command_trace")),
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
        normalized_trace = _normalize_runtime_trace(
            _backfill_runtime_trace_evidence(runtime_trace_payload, snapshot)
        )
        outcome_payload = _mapping_or_none(payload.get("outcome"))
        return {
            "source_command": _string_or_none(payload.get("source_command")) or "trace-record",
            "source_command_status": _string_or_none(payload.get("source_command_status"))
            or "success",
            "source_root": _string_or_none(payload.get("source_root")),
            "snapshot": {
                **snapshot,
                "question": snapshot["question"] or normalized_trace["question"],
                "original_prompt": (
                    snapshot["original_prompt"]
                    or _string_or_none(normalized_trace.get("original_prompt"))
                ),
                "reformulated_prompt": (
                    snapshot["reformulated_prompt"]
                    or _string_or_none(normalized_trace.get("reformulated_prompt"))
                ),
                "sources": snapshot["sources"] or normalized_trace["sources"],
            },
            "trace": normalized_trace,
            "outcome": _normalize_outcome_payload(outcome_payload)
            if outcome_payload is not None
            else None,
        }

    embedded_trace = _mapping_or_none(payload.get("trace"))
    if embedded_trace is not None:
        outcome_payload = _mapping_or_none(payload.get("outcome"))
        embedded_snapshot: dict[str, object] = _trace_record_snapshot(payload)
        return {
            "source_command": _string_or_none(payload.get("command")) or "unknown-command",
            "source_command_status": _string_or_none(payload.get("command_status")) or "success",
            "source_root": _string_or_none(payload.get("root")),
            "snapshot": embedded_snapshot,
            "trace": _normalize_runtime_trace(
                _backfill_runtime_trace_evidence(embedded_trace, embedded_snapshot)
            ),
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
                "original_prompt": _string_or_none(normalized_trace.get("original_prompt")),
                "reformulated_prompt": _string_or_none(normalized_trace.get("reformulated_prompt")),
                "answer": None,
                "response_text": None,
                "sources": _string_list(normalized_trace.get("sources")),
                "context": [],
                "retrieved_context": [],
                "command_trace": [],
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


def _trace_batch_dir(root: Path, batch_name: str) -> Path:
    safe_batch_name = _sanitize_name(batch_name, default="batch")
    return root / DEFAULT_TRACES_DIR / "batches" / safe_batch_name


def _build_trace_record(
    root: Path,
    normalized_payload: Mapping[str, object],
    *,
    trace_path: Path,
    imported: bool,
    outcome: Mapping[str, object] | None,
) -> dict[str, object]:
    """Build one normalized stored trace record for a concrete path."""

    resolved_root = root.resolve()
    snapshot = _mapping_or_none(normalized_payload.get("snapshot")) or {}
    trace = _mapping_or_none(normalized_payload.get("trace")) or {}
    normalized_outcome = _mapping_or_none(normalized_payload.get("outcome"))
    if outcome is not None:
        normalized_outcome = _normalize_outcome_payload(outcome)
    return {
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
        "original_prompt": _string_or_none(snapshot.get("original_prompt"))
        or _string_or_none(trace.get("original_prompt")),
        "reformulated_prompt": _string_or_none(snapshot.get("reformulated_prompt"))
        or _string_or_none(trace.get("reformulated_prompt")),
        "bundle_version": _string_or_none(trace.get("bundle_version")),
        "program_path": _string_or_none(trace.get("program_path")),
        "prompt_family_id": _string_or_none(trace.get("prompt_family_id")),
        "prompt_family_similarity": _float_or_none(trace.get("prompt_family_similarity")),
        "prompt_family_band": _string_or_none(trace.get("prompt_family_band")),
        "family_runtime_hit_rate": _float_or_none(trace.get("family_runtime_hit_rate")),
        "family_artifact_hit_rate": _float_or_none(trace.get("family_artifact_hit_rate")),
        "family_artifact_selected": (
            trace.get("family_artifact_selected")
            if isinstance(trace.get("family_artifact_selected"), bool)
            else None
        ),
        "mediation_metric_hits": _int_or_none(trace.get("mediation_metric_hits")),
        "mediation_metric_total": _int_or_none(trace.get("mediation_metric_total")),
        "answer": _string_or_none(snapshot.get("answer")),
        "response_text": _string_or_none(snapshot.get("response_text")),
        "sources": _string_list(snapshot.get("sources")) or _string_list(trace.get("sources")),
        "context": _list_or_empty(snapshot.get("context")),
        "retrieved_context": _list_or_empty(snapshot.get("retrieved_context")),
        "command_trace": _list_or_empty(snapshot.get("command_trace")),
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
    record = _build_trace_record(
        resolved_root,
        normalized_payload,
        trace_path=trace_path,
        imported=imported,
        outcome=normalized_outcome,
    )
    trace_path.write_text(f"{json.dumps(record, indent=2)}\n", encoding="utf-8")
    return record


def inspect_pending_trainer_inputs(
    root: Path,
    *,
    queue_name: str = "default",
    output_dir: Path = DEFAULT_TRAINER_RECOVERED_TRACES_DIR,
) -> dict[str, object]:
    """Inspect whether a trainer cycle has any new queued trace input."""

    resolved_root = root.resolve()
    resolved_output_dir = output_dir if output_dir.is_absolute() else resolved_root / output_dir
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    normalized_queue_name = _sanitize_name(queue_name, default="default")
    config = resolve_azure_artifact_config(queue_name=queue_name)

    if config is not None and config.queue_enabled:
        store = AzureArtifactStore(config)
        container = repo_rag_trace_container(config)
        queue_name_remote = repo_rag_trace_queue_name(config, fallback=normalized_queue_name)
        queued_prefix = queued_trace_blob_name(queue_name_remote, "")
        queued_blob_names = sorted(store.list_blobs(container, prefix=queued_prefix))
        queue_visible_count = len(queued_blob_names)
        queue_message_count = store.approximate_queue_message_count(queue_name_remote)
        recoverable_processed_count = 0
        processed_count = 0
        if queue_visible_count == 0:
            prefix = processed_trace_blob_name(queue_name_remote, "")
            blob_names = sorted(store.list_blobs(container, prefix=prefix))
            processed_count = len(blob_names)
            recoverable_processed_count = sum(
                1
                for blob_name in blob_names
                if not (resolved_output_dir / Path(blob_name).name).is_file()
            )
        return {
            "queue_name": queue_name_remote,
            "queue_visible_count": queue_visible_count,
            "queue_message_count": queue_message_count,
            "processed_count": processed_count,
            "recoverable_processed_count": recoverable_processed_count,
            "current_cycle_input_detected": queue_visible_count > 0,
            "storage_backend": "azure-blob-queue",
            "trace_container": container,
            "processed_queue_dir": f"azure://{container}/processed/{queue_name_remote}",
        }

    queue_dir = _trace_queue_dir(resolved_root, queue_name, processed=False)
    processed_dir = _trace_queue_dir(resolved_root, queue_name, processed=True)
    queued_paths = sorted(queue_dir.glob("*.json")) if queue_dir.is_dir() else []
    queue_visible_count = len(queued_paths)
    processed_paths = sorted(processed_dir.glob("*.json")) if processed_dir.is_dir() else []
    recoverable_processed_count = 0
    if queue_visible_count == 0:
        recoverable_processed_count = sum(
            1
            for processed_path in processed_paths
            if not (resolved_output_dir / processed_path.name).is_file()
        )
    return {
        "queue_name": normalized_queue_name,
        "queue_visible_count": queue_visible_count,
        "processed_count": len(processed_paths),
        "recoverable_processed_count": recoverable_processed_count,
        "current_cycle_input_detected": queue_visible_count > 0,
        "storage_backend": "filesystem",
        "queue_dir": _relative_to_root(queue_dir, resolved_root),
        "processed_queue_dir": _relative_to_root(processed_dir, resolved_root),
    }


def restore_processed_trace_records(
    root: Path,
    *,
    queue_name: str = "default",
    output_dir: Path = DEFAULT_TRAINER_RECOVERED_TRACES_DIR,
) -> dict[str, object]:
    """Restore a durable local trace ledger from processed queue items."""

    resolved_root = root.resolve()
    resolved_output_dir = output_dir if output_dir.is_absolute() else resolved_root / output_dir
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    normalized_queue_name = _sanitize_name(queue_name, default="default")
    config = resolve_azure_artifact_config(queue_name=queue_name)

    if config is not None and config.queue_enabled:
        store = AzureArtifactStore(config)
        container = repo_rag_trace_container(config)
        queue_name_remote = repo_rag_trace_queue_name(config, fallback=normalized_queue_name)
        prefix = processed_trace_blob_name(queue_name_remote, "")
        blob_names = sorted(store.list_blobs(container, prefix=prefix))
        restored_paths: list[str] = []
        failures: list[dict[str, str]] = []
        for blob_name in blob_names:
            try:
                queued_item = store.download_json(container, blob_name)
                if _string_or_none(queued_item.get("queue_item_kind")) != TRACE_QUEUE_ITEM_KIND:
                    raise ValueError("Processed trace blob is missing `queue_item_kind`.")
                trace_payload = _mapping_or_none(queued_item.get("trace_payload"))
                if trace_payload is None:
                    raise ValueError("Processed trace blob is missing `trace_payload`.")
                trace_path = resolved_output_dir / Path(blob_name).name
                if trace_path.is_file():
                    continue
                normalized_payload = normalize_trace_record_payload(trace_payload)
                record = _build_trace_record(
                    resolved_root,
                    normalized_payload,
                    trace_path=trace_path,
                    imported=True,
                    outcome=_mapping_or_none(queued_item.get("outcome")),
                )
                trace_path.write_text(f"{json.dumps(record, indent=2)}\n", encoding="utf-8")
                restored_paths.append(_relative_to_root(trace_path, resolved_root))
            except Exception as exc:
                failures.append(
                    {
                        "queue_item_path": blob_name,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )
        return {
            "queue_name": queue_name_remote,
            "processed_queue_dir": f"azure://{container}/processed/{queue_name_remote}",
            "output_dir": _relative_to_root(resolved_output_dir, resolved_root),
            "queue_found": bool(blob_names),
            "processed_count": len(blob_names),
            "restored_count": len(restored_paths),
            "failed_count": len(failures),
            "storage_backend": "azure-blob-queue",
            "trace_container": container,
            "trace_paths": restored_paths,
            "failures": failures,
        }

    processed_dir = _trace_queue_dir(resolved_root, queue_name, processed=True)
    processed_paths = sorted(processed_dir.glob("*.json")) if processed_dir.is_dir() else []
    restored_paths_local: list[str] = []
    local_failures: list[dict[str, str]] = []
    for processed_path in processed_paths:
        try:
            queued_item = _load_trace_queue_item(processed_path)
            trace_payload = _mapping_or_none(queued_item.get("trace_payload"))
            if trace_payload is None:
                raise ValueError("Processed trace item is missing `trace_payload`.")
            trace_path = resolved_output_dir / processed_path.name
            if trace_path.is_file():
                continue
            normalized_payload = normalize_trace_record_payload(trace_payload)
            record = _build_trace_record(
                resolved_root,
                normalized_payload,
                trace_path=trace_path,
                imported=True,
                outcome=_mapping_or_none(queued_item.get("outcome")),
            )
            trace_path.write_text(f"{json.dumps(record, indent=2)}\n", encoding="utf-8")
            restored_paths_local.append(_relative_to_root(trace_path, resolved_root))
        except Exception as exc:
            local_failures.append(
                {
                    "queue_item_path": _relative_to_root(processed_path, resolved_root),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
    return {
        "queue_name": normalized_queue_name,
        "processed_queue_dir": _relative_to_root(processed_dir, resolved_root),
        "output_dir": _relative_to_root(resolved_output_dir, resolved_root),
        "queue_found": processed_dir.is_dir(),
        "processed_count": len(processed_paths),
        "restored_count": len(restored_paths_local),
        "failed_count": len(local_failures),
        "storage_backend": "filesystem",
        "trace_paths": restored_paths_local,
        "failures": local_failures,
    }


def queue_trace_record(
    root: Path,
    payload: Mapping[str, object],
    *,
    queue_name: str = "default",
    trace_name: str | None = None,
    batch_name: str | None = None,
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
    safe_batch_name = (
        _sanitize_name(batch_name, default="batch")
        if isinstance(batch_name, str) and batch_name
        else None
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
        "batch_name": safe_batch_name,
        "batch_trace_path": None,
        "trace_payload": payload,
        "outcome": normalized_outcome,
    }
    config = resolve_azure_artifact_config(queue_name=queue_name)
    if config is not None and config.queue_enabled:
        store = AzureArtifactStore(config)
        container = repo_rag_trace_container(config)
        normalized_queue_name = repo_rag_trace_queue_name(config, fallback=normalized_queue_name)
        file_name = queue_item_path.name
        if safe_batch_name:
            batch_blob_name = batched_trace_blob_name(safe_batch_name, file_name)
            queue_item["batch_trace_path"] = batch_blob_name
            store.upload_json(container, batch_blob_name, queue_item)
        blob_name = queued_trace_blob_name(normalized_queue_name, file_name)
        store.upload_json(container, blob_name, queue_item)
        queue_message = {
            "schema_version": TRACE_QUEUE_ITEM_SCHEMA_VERSION,
            "queue_item_kind": TRACE_QUEUE_ITEM_KIND,
            "queue_name": normalized_queue_name,
            "bundle_version": queue_item.get("bundle_version"),
            "queued_at": queued_at,
            "blob_name": blob_name,
            "trace_container": container,
            "trace_name": safe_trace_name,
        }
        message_info = store.send_queue_message(normalized_queue_name, queue_message)
        return {
            **queue_item,
            "storage_backend": "azure-blob-queue",
            "queue_name": normalized_queue_name,
            "trace_container": container,
            "queue_item_path": blob_name,
            "queue_message": message_info,
        }

    if safe_batch_name:
        batch_dir = _trace_batch_dir(resolved_root, safe_batch_name)
        batch_dir.mkdir(parents=True, exist_ok=True)
        batch_trace_path = batch_dir / queue_item_path.name
        queue_item["batch_trace_path"] = _relative_to_root(batch_trace_path, resolved_root)
        batch_trace_path.write_text(f"{json.dumps(queue_item, indent=2)}\n", encoding="utf-8")
    queue_item_path.write_text(f"{json.dumps(queue_item, indent=2)}\n", encoding="utf-8")
    return {
        **queue_item,
        "storage_backend": "filesystem",
    }


def _load_trace_queue_item(path: Path) -> dict[str, object]:
    payload = load_json_object(path)
    if _string_or_none(payload.get("queue_item_kind")) != TRACE_QUEUE_ITEM_KIND:
        raise ValueError(f"Queued trace item is invalid: {path}")
    return payload


def _is_stale_queue_blob_pointer(blob_name: str | None, exc: Exception) -> bool:
    """Return whether one Azure queue pointer refers to an already-missing trace blob."""

    if not blob_name:
        return False
    error_text = str(exc)
    return (
        type(exc).__name__ in {"ResourceNotFoundError", "KeyError"} or "BlobNotFound" in error_text
    )


def drain_trace_queue(
    root: Path,
    *,
    queue_name: str = "default",
    limit: int | None = None,
    keep_queued: bool = False,
) -> dict[str, object]:
    """Import queued trace items into the trainer-side imported-trace store."""

    resolved_root = root.resolve()
    config = resolve_azure_artifact_config(queue_name=queue_name)
    normalized_queue_name = _sanitize_name(queue_name, default="default")
    if config is not None and config.queue_enabled:
        store = AzureArtifactStore(config)
        container = repo_rag_trace_container(config)
        queue_name_remote = repo_rag_trace_queue_name(config, fallback=normalized_queue_name)
        received_messages = store.receive_queue_messages(queue_name_remote, limit=limit)
        imported_items: list[dict[str, object]] = []
        failures: list[dict[str, object]] = []
        skipped_items: list[dict[str, object]] = []
        for message in received_messages:
            message_payload = None
            blob_name = None
            try:
                message_payload = decode_queue_message(message.content)
                blob_name = _string_or_none(message_payload.get("blob_name"))
                if blob_name is None:
                    raise ValueError("Azure queue message is missing `blob_name`.")
                queued_item = store.download_json(container, blob_name)
                if _string_or_none(queued_item.get("queue_item_kind")) != TRACE_QUEUE_ITEM_KIND:
                    raise ValueError("Queued trace blob is missing `queue_item_kind`.")
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
                file_name = Path(blob_name).name
                processed_blob = processed_trace_blob_name(queue_name_remote, file_name)
                processed_item = {
                    **queued_item,
                    "queue_status": "imported",
                    "drained_at": _utc_now_isoformat(),
                    "imported_trace_record_path": imported_record.get("trace_record_path"),
                    "processed_queue_item_path": processed_blob,
                }
                store.upload_json(container, processed_blob, processed_item)
                if not keep_queued:
                    store.delete_blob(container, blob_name)
                store.delete_queue_message(queue_name_remote, message)
                imported_items.append(
                    {
                        "queue_item_path": blob_name,
                        "processed_queue_item_path": processed_blob,
                        "trace_name": trace_name,
                        "question": processed_item.get("question"),
                        "imported_trace_record_path": imported_record.get("trace_record_path"),
                        "acceptance_status": (
                            outcome.get("acceptance_status") if outcome is not None else None
                        ),
                    }
                )
            except Exception as exc:
                if _is_stale_queue_blob_pointer(blob_name, exc):
                    skip_reason = (
                        "stale-failed-blob"
                        if str(blob_name).startswith("failed/")
                        else "stale-queue-blob"
                    )
                    store.delete_queue_message(queue_name_remote, message)
                    skipped_items.append(
                        {
                            "queue_item_path": blob_name,
                            "skip_reason": skip_reason,
                            "error_type": type(exc).__name__,
                            "error_message": str(exc),
                        }
                    )
                    continue
                failure_blob = None
                try:
                    payload = message_payload or decode_queue_message(message.content)
                    blob_name = _string_or_none(payload.get("blob_name"))
                    if blob_name is not None:
                        failure_blob = failed_trace_blob_name(
                            queue_name_remote, Path(blob_name).name
                        )
                        store.upload_json(
                            container,
                            failure_blob,
                            {
                                "message_id": message.message_id,
                                "dequeue_count": message.dequeue_count,
                                "failed_at": _utc_now_isoformat(),
                                "error_type": type(exc).__name__,
                                "error_message": str(exc),
                                "queue_message": payload,
                            },
                        )
                except Exception:
                    failure_blob = failure_blob
                failures.append(
                    {
                        "queue_item_path": failure_blob or "azure-queue-message",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )

        return {
            "queue_name": queue_name_remote,
            "queue_dir": f"azure://{container}/queued/{queue_name_remote}",
            "processed_queue_dir": f"azure://{container}/processed/{queue_name_remote}",
            "queue_found": True,
            "queued_count_before": len(received_messages),
            "selected_count": len(received_messages),
            "drained_count": len(imported_items),
            "failed_count": len(failures),
            "skipped_count": len(skipped_items),
            "remaining_count": None,
            "keep_queued": keep_queued,
            "status": "success" if not failures else "partial",
            "storage_backend": "azure-blob-queue",
            "trace_container": container,
            "items": imported_items,
            "failures": failures,
            "skipped_items": skipped_items,
        }

    queue_dir = _trace_queue_dir(resolved_root, queue_name, processed=False)
    processed_dir = _trace_queue_dir(resolved_root, queue_name, processed=True)
    queued_paths = sorted(queue_dir.glob("*.json")) if queue_dir.is_dir() else []
    selected_paths = queued_paths[:limit] if isinstance(limit, int) and limit > 0 else queued_paths
    local_imported_items: list[dict[str, object]] = []
    local_failures: list[dict[str, object]] = []

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
            local_imported_items.append(
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
            local_failures.append(
                {
                    "queue_item_path": _relative_to_root(queued_path, resolved_root),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )

    queued_count_after = len(list(queue_dir.glob("*.json"))) if queue_dir.is_dir() else 0
    return {
        "queue_name": normalized_queue_name,
        "queue_dir": _relative_to_root(queue_dir, resolved_root),
        "processed_queue_dir": _relative_to_root(processed_dir, resolved_root),
        "queue_found": queue_dir.is_dir(),
        "queued_count_before": len(queued_paths),
        "selected_count": len(selected_paths),
        "drained_count": len(local_imported_items),
        "failed_count": len(local_failures),
        "remaining_count": queued_count_after,
        "keep_queued": keep_queued,
        "status": "success" if not local_failures else "partial",
        "storage_backend": "filesystem",
        "items": local_imported_items,
        "failures": local_failures,
    }
