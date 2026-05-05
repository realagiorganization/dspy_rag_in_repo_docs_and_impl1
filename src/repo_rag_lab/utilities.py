"""User-facing utility helpers shared by the CLI, tests, and notebooks."""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from .azure import write_deployment_manifest
from .azure_runtime import probe_azure_inference, probe_azure_openai
from .benchmarks import (
    DEFAULT_RETRIEVAL_EVAL_TOP_K,
    build_retrieval_benchmarks,
    check_retrieval_quality_thresholds,
    evaluate_retrieval_quality_suite,
    normalize_retrieval_top_k_values,
)
from .dspy_training import (
    DEFAULT_DSPY_RUN_NAME,
    DEFAULT_TRAINING_PATH,
    DSPyLMConfig,
    DSPyTrainingConfig,
    describe_dspy_artifacts,
    resolve_dspy_lm_config,
    train_repository_program,
)
from .exploratorium_translation import sync_exploratorium_translation
from .file_summaries import sync_file_summaries
from .github_pr_gates import sync_github_pr_gates
from .mcp import discover_mcp_servers
from .notebook_runner import run_notebooks
from .pages_site import sync_pages_site
from .retrieval import RetrievalMode
from .runtime_artifacts import (
    DEFAULT_TRAINER_GENERATED_TRAINING_PATH,
    DEFAULT_TRAINER_GENERATED_TRAINING_SUMMARY_PATH,
    DEFAULT_TRAINER_RECOVERED_TRACES_DIR,
    DEFAULT_TRAINER_SERVICE_HISTORY_DIR,
    DEFAULT_TRAINER_SERVICE_STATE_PATH,
    DEFAULT_TRAINER_TRAINING_CANDIDATES_PATH,
    DEFAULT_TRAINER_TRAINING_CANDIDATES_SUMMARY_PATH,
    TRAINER_SERVICE_CYCLE_KIND,
    TRAINER_SERVICE_STATE_KIND,
    drain_trace_queue,
    fetch_remote_bundle,
    initialize_local_overlay,
    inspect_bundle_channel,
    inspect_remote_bundle_channel,
    inspect_remote_bundle_version,
    load_json_object,
    promote_bundle,
    publish_bundle,
    published_bundle_record_from_state,
    queue_trace_record,
    resolve_azure_artifact_config,
    resolve_bundle_manifest,
    restore_processed_trace_records,
    rollback_bundle,
    upload_remote_bundle,
    upload_remote_bundle_channel,
    write_trace_record,
)
from .todo_backlog import sync_todo_backlog
from .trainer_deployment import (
    DEFAULT_TRAINER_K8S_CYCLE_SCHEDULE,
    DEFAULT_TRAINER_K8S_IMAGE,
    DEFAULT_TRAINER_K8S_IMAGE_PULL_SECRET_NAME,
    DEFAULT_TRAINER_K8S_MIN_NEW_CANDIDATES_FOR_RECOMPILE,
    DEFAULT_TRAINER_K8S_MINIMUM_BUNDLE_PASS_RATE,
    DEFAULT_TRAINER_K8S_MINIMUM_PASS_RATE,
    DEFAULT_TRAINER_K8S_MINIMUM_SOURCE_RECALL,
    DEFAULT_TRAINER_K8S_NAMESPACE,
    DEFAULT_TRAINER_K8S_OUTPUT_DIR,
    DEFAULT_TRAINER_K8S_PROMOTE_CHANNEL,
    DEFAULT_TRAINER_K8S_PVC_ACCESS_MODES,
    DEFAULT_TRAINER_K8S_PVC_NAME,
    DEFAULT_TRAINER_K8S_PVC_SIZE,
    DEFAULT_TRAINER_K8S_PVC_STORAGE_CLASS,
    DEFAULT_TRAINER_K8S_QUEUE_NAME,
    DEFAULT_TRAINER_K8S_RECOMPILE_RUN_NAME,
    DEFAULT_TRAINER_K8S_SERVICE_MAX_IDLE_CYCLES,
    DEFAULT_TRAINER_K8S_SERVICE_POLL_INTERVAL_SECONDS,
    TrainerK8sConfig,
    write_trainer_k8s_manifests,
)
from .training_samples import (
    load_training_examples,
    materialize_combined_training_examples,
    materialize_training_candidates,
)
from .verification import verify_repository_surfaces
from .workflow import ask_repository


def _json_command_payload(
    command: str,
    *,
    root: Path,
    payload: Mapping[str, object],
    command_status: str = "success",
    warnings: Sequence[str] | None = None,
    artifact_metadata: Mapping[str, object] | None = None,
) -> str:
    """Attach shared command metadata to a machine-readable payload."""

    return json.dumps(
        {
            "command": command,
            "command_status": command_status,
            "root": str(root),
            "warnings": list(warnings or ()),
            "artifact_metadata": artifact_metadata or _artifact_metadata(),
            **payload,
        },
        indent=2,
    )


def _artifact_metadata(
    *,
    input_paths: Sequence[str | Path] = (),
    generated_paths: Sequence[str | Path] = (),
    related_paths: Sequence[str | Path] = (),
) -> dict[str, list[str]]:
    """Return a normalized artifact metadata payload."""

    def _normalize(entries: Sequence[str | Path]) -> list[str]:
        normalized: list[str] = []
        for entry in entries:
            text = str(entry).strip()
            if text:
                normalized.append(text)
        return normalized

    return {
        "input_paths": _normalize(input_paths),
        "generated_paths": _normalize(generated_paths),
        "related_paths": _normalize(related_paths),
    }


def _path_text_for_root(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` when possible."""

    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _write_json_artifact(path: Path, payload: Mapping[str, object]) -> None:
    """Write one formatted JSON artifact to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(dict(payload), indent=2)}\n", encoding="utf-8")


def _sanitize_training_run_name(name: str, *, default: str = DEFAULT_DSPY_RUN_NAME) -> str:
    """Normalize one trainer family/run label into the artifact-safe DSPy naming surface."""

    parts = [part for part in re.split(r"[^A-Za-z0-9._-]+", name.strip()) if part]
    if parts:
        return "-".join(parts)
    return default


def _versioned_training_run_name(run_family: str, *, recorded_at: datetime | None = None) -> str:
    """Return one timestamp-only immutable bundle version for trainer publish cycles."""

    _sanitize_training_run_name(run_family, default=DEFAULT_DSPY_RUN_NAME)
    return (recorded_at or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S%fZ")


def _summarize_imported_trace_records(
    root: Path,
    imported_trace_paths: Sequence[str | Path],
) -> dict[str, object]:
    """Summarize imported trace records for trainer-side ingestion reporting."""

    acceptance_status_counts: Counter[str] = Counter()
    execution_status_counts: Counter[str] = Counter()
    retrieval_mode_counts: Counter[str] = Counter()
    bundle_version_counts: Counter[str] = Counter()
    source_error_count = 0
    missing_source_count = 0
    missing_context_count = 0
    used_baseline_fallback_count = 0
    invalid_record_count = 0
    processed_paths: list[str] = []

    for candidate in imported_trace_paths:
        candidate_path = Path(str(candidate))
        resolved_path = (
            candidate_path if candidate_path.is_absolute() else root / candidate_path
        ).resolve()
        if not resolved_path.is_file():
            invalid_record_count += 1
            continue
        payload = load_json_object(resolved_path)
        trace = payload.get("trace")
        trace_mapping = trace if isinstance(trace, Mapping) else {}
        outcome = payload.get("outcome")
        outcome_mapping = outcome if isinstance(outcome, Mapping) else {}

        acceptance_status = str(outcome_mapping.get("acceptance_status") or "").strip()
        if acceptance_status:
            acceptance_status_counts[acceptance_status] += 1

        execution_status = str(outcome_mapping.get("execution_status") or "").strip()
        if execution_status:
            execution_status_counts[execution_status] += 1

        retrieval_mode = str(trace_mapping.get("retrieval_mode") or "").strip()
        if retrieval_mode:
            retrieval_mode_counts[retrieval_mode] += 1

        bundle_version = str(trace_mapping.get("bundle_version") or "").strip()
        if bundle_version:
            bundle_version_counts[bundle_version] += 1

        source_count = trace_mapping.get("source_count")
        if isinstance(source_count, int) and source_count == 0:
            missing_source_count += 1
        context_count = trace_mapping.get("context_count")
        if isinstance(context_count, int) and context_count == 0:
            missing_context_count += 1
        if payload.get("source_error") is not None:
            source_error_count += 1
        if outcome_mapping.get("used_baseline_fallback") is True:
            used_baseline_fallback_count += 1

        processed_paths.append(_path_text_for_root(resolved_path, root))

    return {
        "record_count": len(processed_paths),
        "processed_paths": processed_paths,
        "acceptance_status_counts": dict(sorted(acceptance_status_counts.items())),
        "execution_status_counts": dict(sorted(execution_status_counts.items())),
        "retrieval_mode_counts": dict(sorted(retrieval_mode_counts.items())),
        "bundle_version_counts": dict(sorted(bundle_version_counts.items())),
        "missing_source_count": missing_source_count,
        "missing_context_count": missing_context_count,
        "source_error_count": source_error_count,
        "used_baseline_fallback_count": used_baseline_fallback_count,
        "invalid_record_count": invalid_record_count,
    }


def utility_summary(root: Path) -> str:
    """Describe the supported command surfaces for the repository workflow."""

    lines = [
        "Repository utility surfaces:",
        "- make utility-summary / uv run repo-rag utility-summary: list the supported entrypoints",
        (
            "- make ask / uv run repo-rag ask: answer repository-grounded questions with a "
            "Rust lookup-first pass before the baseline retrieval fallback; "
            "pass --output json for a machine-readable envelope"
        ),
        (
            "- make ask-dspy / uv run repo-rag ask --use-dspy: answer with the explicit DSPy "
            "runtime path after the same lookup-first narrowing; "
            "pass --output json for a machine-readable envelope"
        ),
        (
            "- make rust-lookup-index / cargo run --manifest-path rust-cli/Cargo.toml -- index: "
            "build the local SQLite FTS index of tracked UTF-8 repository files"
        ),
        (
            "- make rust-lookup / cargo run --manifest-path rust-cli/Cargo.toml -- lookup: "
            "search the local SQLite index before escalating to DSPy synthesis"
        ),
        (
            "- make ask-live / uv run repo-rag ask-live: answer with retrieved repo evidence "
            "plus a live Azure-backed synthesis step; pass --output json for a "
            "machine-readable envelope"
        ),
        "- make dspy-train / uv run repo-rag dspy-train: compile and persist a DSPy RAG program",
        (
            "- make dspy-artifacts / uv run repo-rag dspy-artifacts: inspect saved DSPy "
            "programs as JSON with shared command metadata"
        ),
        (
            "- make bundle-inspect / uv run repo-rag bundle-inspect: inspect one named immutable "
            "DSPy bundle version or, when needed, a promoted channel alias for worker-side startup"
        ),
        (
            "- make bundle-publish / uv run repo-rag bundle-publish: publish a compiled DSPy "
            "bundle version into the local bundle registry without mutating a prior immutable "
            "version"
        ),
        (
            "- make bundle-promote / uv run repo-rag bundle-promote: optionally point the stable "
            "or canary channel at a published DSPy bundle version; channel aliases are a fallback "
            "to the primary DSPY_BUNDLE_VERSION pinning contract"
        ),
        (
            "- make bundle-rollback / uv run repo-rag bundle-rollback: move a stable or canary "
            "channel back to an earlier published bundle version when channel aliases are in use"
        ),
        (
            "- make bundle-fetch / uv run repo-rag bundle-fetch: download one remote bundle "
            "version or channel-selected bundle into the local worker cache when Azure bundle "
            "storage is configured"
        ),
        (
            "- make overlay-init / uv run repo-rag overlay-init: initialize a worker-local "
            "overlay manifest that records retrieval mode, lookup-index location, and trace dir"
        ),
        (
            "- make trace-export / uv run repo-rag trace-export: persist a normalized runtime "
            "trace record from an ask-family JSON payload for asynchronous optimization"
        ),
        (
            "- make trace-import / uv run repo-rag trace-import: validate and ingest an external "
            "runtime trace record plus optional outcome metadata into the local trace store"
        ),
        (
            "- make trace-enqueue / uv run repo-rag trace-enqueue: stage a normalized runtime "
            "trace record plus optional outcome metadata into a trainer-side queue for later "
            "asynchronous import"
        ),
        (
            "- make trace-drain / uv run repo-rag trace-drain: import queued trainer-side trace "
            "handoff items into the local imported-trace store"
        ),
        (
            "- make trainer-cycle / uv run repo-rag trainer-cycle: run one background-compatible "
            "trainer pass that drains queued traces, evaluates retrieval gates, and optionally "
            "publishes/promotes a bundle"
        ),
        (
            "- make trainer-service / uv run repo-rag trainer-service: run a long-lived "
            "background trainer loop that polls the queue, records cycle history, and writes "
            "service state under artifacts/trainer/"
        ),
        (
            "- make trainer-k8s-manifests / uv run repo-rag trainer-k8s-manifests: "
            "materialize Kubernetes manifests for trainer-service and trainer-cycle roles"
        ),
        (
            "- make trainer-candidates / uv run repo-rag trainer-candidates: materialize "
            "trainer-side YAML candidate examples from imported trace records for later "
            "DSPy review or compilation"
        ),
        (
            "- make trainer-recompile / uv run repo-rag trainer-recompile: merge the base "
            "training set with trainer-side candidate examples and compile a new DSPy run when "
            "LM configuration is available"
        ),
        "- make discover-mcp / uv run repo-rag discover-mcp: inspect repo-local MCP candidates",
        (
            "- make serve-mcp / uv run repo-rag serve-mcp: expose only the bounded MCP "
            "tool surface for lightweight ask, bundle status, artifact listing, and queued "
            "trace publish"
        ),
        (
            "- make serve-codex-proxy / uv run repo-rag serve-codex-proxy: expose a local "
            "Responses-compatible mediation proxy for downstream Codex workers, attempting "
            "repo-RAG retrieval plus DSPy shaping before heuristic fallback or pass-through"
        ),
        "- make azure-manifest / uv run repo-rag azure-manifest: write Azure deployment metadata",
        (
            "- make azure-openai-probe / uv run repo-rag azure-openai-probe: "
            "validate the Azure OpenAI runtime contract"
        ),
        (
            "- make azure-inference-probe / uv run repo-rag azure-inference-probe: "
            "validate the Azure AI Inference runtime contract"
        ),
        (
            "- make files-sync / uv run repo-rag sync-file-summaries: "
            "regenerate FILES.md and FILES.csv from the tracked repository files"
        ),
        (
            "- make todo-sync / uv run repo-rag sync-todo-backlog: "
            "regenerate the linkified TODO tables for Markdown and the publication PDF"
        ),
        (
            "- make exploratorium-sync / uv run repo-rag sync-exploratorium-translation: "
            "regenerate the bilingual publication inventory of files, links, and fetch state"
        ),
        (
            "- make github-pr-gates / uv run repo-rag sync-github-pr-gates --apply: "
            "sync the required GitHub pull-request status checks through gh branch protection"
        ),
        (
            "- make pages-build / uv run repo-rag sync-pages-site: "
            "generate the MkDocs GitHub Pages catalog of tracked Markdown files"
        ),
        (
            "- make retrieval-eval / uv run repo-rag retrieval-eval: "
            "measure retrieval quality across a top-k sweep, richer source metrics, "
            "per-tag summaries, threshold enforcement, and shared JSON command metadata"
        ),
        "- make smoke-test / uv run repo-rag smoke-test: validate the core workflow surfaces",
        (
            "- make verify-surfaces / uv run repo-rag verify-surfaces: "
            "validate notebooks and Makefile verification surfaces"
        ),
        (
            "- make notebook-report / uv run repo-rag run-notebooks: "
            "execute all tracked notebooks with monitored progress and report artifacts"
        ),
        f"- root: {root}",
    ]
    return "\n".join(lines)


def run_smoke_test(root: Path) -> str:
    """Run the repository's lightweight end-to-end utility smoke test."""

    answer = ask_repository("What does this repository research?", root=root)
    mcp_candidates = discover_mcp_servers(root)
    manifest_path = write_deployment_manifest(
        root=root,
        model_id="sample-ft-model",
        deployment_name="repo-rag-smoke",
        endpoint="https://example.services.ai.azure.com/models",
    )
    manifest_path_text = str(manifest_path.relative_to(root))
    payload = {
        "answer_contains_repository": "repository" in answer.answer.lower(),
        "mcp_candidate_count": len(mcp_candidates),
        "manifest_path": manifest_path_text,
    }
    warnings: list[str] = []
    if payload["mcp_candidate_count"] == 0:
        warnings.append("No MCP candidates were discovered during the smoke test.")
    return _json_command_payload(
        "smoke-test",
        root=root,
        payload=payload,
        command_status="success" if payload["answer_contains_repository"] else "fail",
        warnings=warnings,
        artifact_metadata=_artifact_metadata(
            generated_paths=[manifest_path_text],
            related_paths=["README.md", "Makefile"],
        ),
    )


def run_trainer_k8s_manifest_generation(
    root: Path,
    *,
    image: str = DEFAULT_TRAINER_K8S_IMAGE,
    namespace: str = DEFAULT_TRAINER_K8S_NAMESPACE,
    service_account_name: str = "repo-rag-trainer",
    config_map_name: str = "repo-rag-trainer-config",
    secret_name: str = "repo-rag-trainer-secrets",
    pvc_name: str = DEFAULT_TRAINER_K8S_PVC_NAME,
    pvc_storage_class_name: str | None = DEFAULT_TRAINER_K8S_PVC_STORAGE_CLASS,
    pvc_size: str = DEFAULT_TRAINER_K8S_PVC_SIZE,
    pvc_access_modes: tuple[str, ...] = DEFAULT_TRAINER_K8S_PVC_ACCESS_MODES,
    image_pull_secret_name: str | None = DEFAULT_TRAINER_K8S_IMAGE_PULL_SECRET_NAME,
    output_dir: Path = DEFAULT_TRAINER_K8S_OUTPUT_DIR,
    queue_name: str = DEFAULT_TRAINER_K8S_QUEUE_NAME,
    cycle_schedule: str = DEFAULT_TRAINER_K8S_CYCLE_SCHEDULE,
    poll_interval_seconds: float = DEFAULT_TRAINER_K8S_SERVICE_POLL_INTERVAL_SECONDS,
    service_max_idle_cycles: int | None = DEFAULT_TRAINER_K8S_SERVICE_MAX_IDLE_CYCLES,
    promote_channel: str | None = DEFAULT_TRAINER_K8S_PROMOTE_CHANNEL,
    retrieval_training_path: Path = DEFAULT_TRAINING_PATH,
    retrieval_top_k: int = DEFAULT_RETRIEVAL_EVAL_TOP_K,
    retrieval_top_k_sweep: str = "1,2,4,8",
    retrieval_mode: RetrievalMode | None = None,
    minimum_pass_rate: float | None = DEFAULT_TRAINER_K8S_MINIMUM_PASS_RATE,
    minimum_source_recall: float | None = DEFAULT_TRAINER_K8S_MINIMUM_SOURCE_RECALL,
    minimum_bundle_pass_rate: float | None = DEFAULT_TRAINER_K8S_MINIMUM_BUNDLE_PASS_RATE,
    recompile_run_name: str | None = DEFAULT_TRAINER_K8S_RECOMPILE_RUN_NAME,
    min_new_candidates_for_recompile: int = (DEFAULT_TRAINER_K8S_MIN_NEW_CANDIDATES_FOR_RECOMPILE),
    recompile_base_training_path: Path = DEFAULT_TRAINING_PATH,
) -> str:
    """Materialize Kubernetes manifests for trainer-service and trainer-cycle roles."""

    payload = write_trainer_k8s_manifests(
        root,
        config=TrainerK8sConfig(
            image=image,
            namespace=namespace,
            service_account_name=service_account_name,
            config_map_name=config_map_name,
            secret_name=secret_name,
            pvc_name=pvc_name,
            pvc_storage_class_name=pvc_storage_class_name,
            pvc_size=pvc_size,
            pvc_access_modes=pvc_access_modes,
            image_pull_secret_name=image_pull_secret_name,
            output_dir=output_dir,
            queue_name=queue_name,
            cycle_schedule=cycle_schedule,
            poll_interval_seconds=poll_interval_seconds,
            service_max_idle_cycles=service_max_idle_cycles,
            promote_channel=promote_channel,
            retrieval_training_path=str(retrieval_training_path),
            retrieval_top_k=retrieval_top_k,
            retrieval_top_k_sweep=retrieval_top_k_sweep,
            retrieval_mode=retrieval_mode,
            minimum_pass_rate=minimum_pass_rate,
            minimum_source_recall=minimum_source_recall,
            minimum_bundle_pass_rate=minimum_bundle_pass_rate,
            recompile_run_name=recompile_run_name,
            min_new_candidates_for_recompile=min_new_candidates_for_recompile,
            recompile_base_training_path=str(recompile_base_training_path),
        ),
    )
    manifest_paths = payload.get("manifest_paths")
    generated_manifest_paths = manifest_paths if isinstance(manifest_paths, list) else []
    return _json_command_payload(
        "trainer-k8s-manifests",
        root=root,
        payload=payload,
        artifact_metadata=_artifact_metadata(
            input_paths=[str(retrieval_training_path), str(recompile_base_training_path)],
            generated_paths=[str(path) for path in generated_manifest_paths],
            related_paths=["Makefile", "docs/operations/azure-deployment.md", "artifacts/trainer"],
        ),
    )


def _parse_retrieval_top_k_sweep(raw_values: str | None, *, top_k: int) -> tuple[int, ...]:
    if raw_values is None or not raw_values.strip():
        return normalize_retrieval_top_k_values(default_top_k=top_k)
    parsed_values: list[int] = []
    for raw_value in raw_values.split(","):
        cleaned = raw_value.strip()
        if not cleaned:
            continue
        parsed_values.append(int(cleaned))
    return normalize_retrieval_top_k_values(parsed_values, default_top_k=top_k)


def _build_retrieval_evaluation_payload(
    root: Path,
    *,
    training_path: Path = DEFAULT_TRAINING_PATH,
    top_k: int = DEFAULT_RETRIEVAL_EVAL_TOP_K,
    top_k_sweep: str | None = None,
    retrieval_mode: RetrievalMode | None = None,
    minimum_pass_rate: float | None = None,
    minimum_source_recall: float | None = None,
) -> dict[str, object]:
    """Build the shared retrieval-evaluation payload without the outer command envelope."""

    resolved_training_path = training_path if training_path.is_absolute() else root / training_path
    examples = load_training_examples(resolved_training_path)
    benchmarks = build_retrieval_benchmarks(examples)
    suite = evaluate_retrieval_quality_suite(
        root,
        benchmarks,
        top_k=top_k,
        top_k_values=_parse_retrieval_top_k_sweep(top_k_sweep, top_k=top_k),
        retrieval_mode=retrieval_mode,
    )
    try:
        training_path_text = str(resolved_training_path.relative_to(root))
    except ValueError:
        training_path_text = str(resolved_training_path)
    threshold_failures = check_retrieval_quality_thresholds(
        suite["default_summary"],
        minimum_pass_rate=minimum_pass_rate,
        minimum_source_recall=minimum_source_recall,
    )
    payload: dict[str, object] = {
        "training_path": training_path_text,
        "benchmark_count": len(benchmarks),
        **suite,
        "thresholds_enabled": any(
            threshold is not None for threshold in (minimum_pass_rate, minimum_source_recall)
        ),
        "thresholds": {
            "minimum_pass_rate": minimum_pass_rate,
            "minimum_source_recall": minimum_source_recall,
        },
        "threshold_failures": threshold_failures,
        "status": "pass" if not threshold_failures else "fail",
    }
    return payload


def run_retrieval_evaluation(
    root: Path,
    *,
    training_path: Path = DEFAULT_TRAINING_PATH,
    top_k: int = DEFAULT_RETRIEVAL_EVAL_TOP_K,
    top_k_sweep: str | None = None,
    retrieval_mode: RetrievalMode | None = None,
    minimum_pass_rate: float | None = None,
    minimum_source_recall: float | None = None,
) -> str:
    """Serialize a retrieval-quality evaluation suite as JSON."""

    payload = _build_retrieval_evaluation_payload(
        root,
        training_path=training_path,
        top_k=top_k,
        top_k_sweep=top_k_sweep,
        retrieval_mode=retrieval_mode,
        minimum_pass_rate=minimum_pass_rate,
        minimum_source_recall=minimum_source_recall,
    )
    return _json_command_payload(
        "retrieval-eval",
        root=root,
        payload=payload,
        command_status="success" if not payload["threshold_failures"] else "fail",
        artifact_metadata=_artifact_metadata(
            input_paths=[str(payload.get("training_path") or "")],
            related_paths=["data/questions/repository.yaml"],
        ),
    )


def run_dspy_artifacts(root: Path) -> str:
    """Serialize the current DSPy artifact inventory as JSON."""

    payload = describe_dspy_artifacts(root)
    artifact_root = str(payload.get("artifact_root") or "")
    latest_metadata_path = payload.get("latest_metadata_path")
    latest_program_path = payload.get("latest_program_path")
    warnings: list[str] = []
    if payload["run_count"] == 0:
        warnings.append("No saved DSPy runs are available yet.")
    return _json_command_payload(
        "dspy-artifacts",
        root=root,
        payload=payload,
        warnings=warnings,
        artifact_metadata=_artifact_metadata(
            generated_paths=[artifact_root],
            related_paths=[
                str(latest_metadata_path or ""),
                str(latest_program_path or ""),
            ],
        ),
    )


def run_bundle_inspection(
    root: Path,
    *,
    run_name: str | None = None,
    bundle_version: str | None = None,
    channel: str | None = None,
) -> str:
    """Serialize the latest, named, or promoted-channel DSPy bundle state as JSON."""

    if channel is not None:
        channel_state = inspect_remote_bundle_channel(channel) or inspect_bundle_channel(
            root,
            channel=channel,
        )
        if not channel_state.get("channel_found", False):
            warnings = [f"Bundle channel `{channel}` is not initialized yet."]
            return _json_command_payload(
                "bundle-inspect",
                root=root,
                payload={
                    "bundle_found": False,
                    **channel_state,
                },
                warnings=warnings,
                artifact_metadata=_artifact_metadata(
                    generated_paths=[str(channel_state.get("channel_path") or "")]
                ),
            )
        return _json_command_payload(
            "bundle-inspect",
            root=root,
            payload={
                "bundle_found": bool(channel_state.get("current_bundle_version")),
                **channel_state,
            },
            artifact_metadata=_artifact_metadata(
                generated_paths=[
                    str(channel_state.get("channel_path") or ""),
                    str(channel_state.get("current_published_bundle_path") or ""),
                ],
                related_paths=[
                    str(channel_state.get("current_bundle_path") or ""),
                    str(channel_state.get("current_metadata_path") or ""),
                    str(channel_state.get("current_program_path") or ""),
                ],
            ),
        )

    try:
        selected_bundle: dict[str, object] | None = None
        if bundle_version is not None:
            selected_bundle = inspect_remote_bundle_version(bundle_version)
        if selected_bundle is None:
            _, selected_bundle = resolve_bundle_manifest(
                root,
                run_name=run_name,
                bundle_version=bundle_version,
            )
    except ValueError:
        payload = describe_dspy_artifacts(root)
        warnings = [
            (
                f"No DSPy bundle named `{run_name}` is available yet."
                if run_name
                else (
                    f"No DSPy bundle version `{bundle_version}` is available yet."
                    if bundle_version
                    else "No saved DSPy bundles are available yet."
                )
            )
        ]
        return _json_command_payload(
            "bundle-inspect",
            root=root,
            payload={
                "bundle_found": False,
                "requested_run_name": run_name,
                "requested_bundle_version": bundle_version,
            },
            warnings=warnings,
            artifact_metadata=_artifact_metadata(
                generated_paths=[str(payload.get("artifact_root") or "")]
            ),
        )

    return _json_command_payload(
        "bundle-inspect",
        root=root,
        payload={
            "bundle_found": True,
            **selected_bundle,
        },
        artifact_metadata=_artifact_metadata(
            generated_paths=[str(selected_bundle.get("bundle_path") or "")],
            related_paths=[
                str(selected_bundle.get("metadata_path") or ""),
                str(selected_bundle.get("program_path") or ""),
            ],
        ),
    )


def run_bundle_publish(
    root: Path,
    *,
    run_name: str | None = None,
    bundle_version: str | None = None,
    note: str | None = None,
) -> str:
    """Publish one compiled bundle into the local published-bundle registry."""

    record = publish_bundle(root, run_name=run_name, bundle_version=bundle_version, note=note)
    remote_publish = None
    config = resolve_azure_artifact_config()
    if config is not None and config.bundles_enabled:
        remote_publish = upload_remote_bundle(root, published_record=record, config=config)
    return _json_command_payload(
        "bundle-publish",
        root=root,
        payload={
            **record,
            "remote_publish": remote_publish,
        },
        artifact_metadata=_artifact_metadata(
            generated_paths=[str(record.get("published_bundle_path") or "")],
            related_paths=[
                str(record.get("bundle_path") or ""),
                str(record.get("metadata_path") or ""),
                str(record.get("program_path") or ""),
            ],
        ),
    )


def run_bundle_promote(
    root: Path,
    *,
    channel: str,
    run_name: str | None = None,
    bundle_version: str | None = None,
    note: str | None = None,
) -> str:
    """Promote a published bundle into one persisted channel."""

    state = promote_bundle(
        root,
        channel=channel,
        run_name=run_name,
        bundle_version=bundle_version,
        note=note,
    )
    remote_publish = None
    config = resolve_azure_artifact_config()
    if config is not None and config.bundles_enabled:
        published_record = published_bundle_record_from_state(state, root=root)
        remote_publish = upload_remote_bundle(
            root, published_record=published_record, config=config
        )
        remote_channel = upload_remote_bundle_channel(
            state,
            channel=channel,
            config=config,
        )
    else:
        remote_channel = None
    return _json_command_payload(
        "bundle-promote",
        root=root,
        payload={
            **state,
            "remote_publish": remote_publish,
            "remote_channel": remote_channel,
        },
        artifact_metadata=_artifact_metadata(
            generated_paths=[
                str(state.get("channel_path") or ""),
                str(state.get("current_published_bundle_path") or ""),
            ],
            related_paths=[
                str(state.get("current_bundle_path") or ""),
                str(state.get("current_metadata_path") or ""),
                str(state.get("current_program_path") or ""),
            ],
        ),
    )


def run_bundle_rollback(
    root: Path,
    *,
    channel: str,
    bundle_version: str | None = None,
    note: str | None = None,
) -> str:
    """Rollback one persisted bundle channel."""

    state = rollback_bundle(root, channel=channel, bundle_version=bundle_version, note=note)
    config = resolve_azure_artifact_config()
    remote_publish = None
    remote_channel = None
    if config is not None and config.bundles_enabled:
        published_record = published_bundle_record_from_state(state, root=root)
        remote_publish = upload_remote_bundle(
            root, published_record=published_record, config=config
        )
        remote_channel = upload_remote_bundle_channel(
            state,
            channel=channel,
            config=config,
        )
    return _json_command_payload(
        "bundle-rollback",
        root=root,
        payload={
            **state,
            "remote_publish": remote_publish,
            "remote_channel": remote_channel,
        },
        artifact_metadata=_artifact_metadata(
            generated_paths=[
                str(state.get("channel_path") or ""),
                str(state.get("current_published_bundle_path") or ""),
            ],
            related_paths=[
                str(state.get("current_bundle_path") or ""),
                str(state.get("current_metadata_path") or ""),
                str(state.get("current_program_path") or ""),
            ],
        ),
    )


def run_bundle_fetch(
    root: Path,
    *,
    bundle_version: str | None = None,
    channel: str | None = None,
) -> str:
    """Download one Azure-hosted bundle version into the local worker cache."""

    payload = fetch_remote_bundle(root, bundle_version=bundle_version, channel=channel)
    if payload is None:
        warnings = ["Azure bundle storage is not configured or the requested bundle was not found."]
        return _json_command_payload(
            "bundle-fetch",
            root=root,
            payload={
                "bundle_found": False,
                "requested_bundle_version": bundle_version,
                "requested_channel": channel,
            },
            warnings=warnings,
        )
    return _json_command_payload(
        "bundle-fetch",
        root=root,
        payload=payload,
        artifact_metadata=_artifact_metadata(
            generated_paths=[
                str(payload.get("cache_dir") or ""),
                str(payload.get("bundle_path") or ""),
                str(payload.get("metadata_path") or ""),
                str(payload.get("program_path") or ""),
                str(payload.get("published_bundle_path") or ""),
            ],
        ),
    )


def run_overlay_init(
    root: Path,
    *,
    overlay_name: str = "default",
    bundle_version: str | None = None,
    retrieval_mode: RetrievalMode | None = None,
) -> str:
    """Create or refresh a worker-local overlay manifest and serialize it as JSON."""

    payload = initialize_local_overlay(
        root,
        overlay_name=overlay_name,
        bundle_version=bundle_version,
        retrieval_mode=retrieval_mode,
    )
    return _json_command_payload(
        "overlay-init",
        root=root,
        payload=payload,
        artifact_metadata=_artifact_metadata(
            generated_paths=[
                str(payload.get("overlay_dir") or ""),
                str(payload.get("overlay_path") or ""),
            ],
            related_paths=[
                str(payload.get("retrieval_profile_path") or ""),
                str(payload.get("lookup_index_path") or ""),
                str(payload.get("trace_dir") or ""),
            ],
        ),
    )


def _load_trace_payload(
    *,
    payload_path: Path | None = None,
    payload_text: str | None = None,
) -> dict[str, object]:
    if payload_path is None and payload_text is None:
        raise ValueError("Pass either a payload path or inline payload text for trace export.")
    if payload_path is not None:
        return load_json_object(payload_path)
    assert payload_text is not None
    payload = json.loads(payload_text)
    if not isinstance(payload, dict):
        raise ValueError("Trace payload must be a JSON object.")
    return payload


def _load_outcome_payload(
    *,
    outcome_path: Path | None = None,
    outcome_text: str | None = None,
) -> dict[str, object] | None:
    if outcome_path is None and outcome_text is None:
        return None
    if outcome_path is not None:
        return load_json_object(outcome_path)
    assert outcome_text is not None
    payload = json.loads(outcome_text)
    if not isinstance(payload, dict):
        raise ValueError("Outcome payload must be a JSON object.")
    return payload


def run_trace_export(
    root: Path,
    *,
    payload_path: Path | None = None,
    payload_text: str | None = None,
    trace_name: str | None = None,
) -> str:
    """Persist a normalized runtime-trace record and serialize the result as JSON."""

    payload = _load_trace_payload(payload_path=payload_path, payload_text=payload_text)
    record = write_trace_record(root, payload, trace_name=trace_name, imported=False)
    trace_record_path = str(record.get("trace_record_path") or "")
    source_payload_path = str(payload_path) if payload_path is not None else ""
    return _json_command_payload(
        "trace-export",
        root=root,
        payload=record,
        artifact_metadata=_artifact_metadata(
            input_paths=[source_payload_path],
            generated_paths=[trace_record_path],
            related_paths=["artifacts/traces"],
        ),
    )


def run_trace_import(
    root: Path,
    *,
    trace_path: Path,
    trace_name: str | None = None,
    outcome_path: Path | None = None,
    outcome_text: str | None = None,
) -> str:
    """Validate and ingest an external runtime-trace record into the local trace store."""

    payload = load_json_object(trace_path)
    outcome = _load_outcome_payload(outcome_path=outcome_path, outcome_text=outcome_text)
    record = write_trace_record(
        root,
        payload,
        trace_name=trace_name,
        imported=True,
        outcome=outcome,
    )
    trace_record_path = str(record.get("trace_record_path") or "")
    input_paths: list[str | Path] = [trace_path]
    if outcome_path is not None:
        input_paths.append(outcome_path)
    return _json_command_payload(
        "trace-import",
        root=root,
        payload=record,
        artifact_metadata=_artifact_metadata(
            input_paths=input_paths,
            generated_paths=[trace_record_path],
            related_paths=["artifacts/traces/imported"],
        ),
    )


def run_trace_enqueue(
    root: Path,
    *,
    trace_path: Path,
    queue_name: str = "default",
    trace_name: str | None = None,
    outcome_path: Path | None = None,
    outcome_text: str | None = None,
) -> str:
    """Queue an external runtime-trace record for asynchronous trainer-side import."""

    payload = load_json_object(trace_path)
    outcome = _load_outcome_payload(outcome_path=outcome_path, outcome_text=outcome_text)
    queue_item = queue_trace_record(
        root,
        payload,
        queue_name=queue_name,
        trace_name=trace_name,
        outcome=outcome,
        source_trace_path=trace_path,
        source_outcome_path=outcome_path,
    )
    queue_item_path = str(queue_item.get("queue_item_path") or "")
    return _json_command_payload(
        "trace-enqueue",
        root=root,
        payload=queue_item,
        artifact_metadata=_artifact_metadata(
            input_paths=[trace_path, outcome_path] if outcome_path is not None else [trace_path],
            generated_paths=[queue_item_path],
            related_paths=["artifacts/traces/queued"],
        ),
    )


def run_trace_drain(
    root: Path,
    *,
    queue_name: str = "default",
    limit: int | None = None,
    keep_queued: bool = False,
) -> str:
    """Drain queued trainer-side trace handoff items into the imported-trace store."""

    payload = drain_trace_queue(
        root,
        queue_name=queue_name,
        limit=limit,
        keep_queued=keep_queued,
    )
    warnings: list[str] = []
    drained_items = payload.get("items")
    normalized_items = drained_items if isinstance(drained_items, list) else []
    if not payload.get("queue_found"):
        warnings.append("No queued trace items were available for the requested queue.")
    if payload.get("failed_count"):
        warnings.append("One or more queued trace items failed during drain.")
    return _json_command_payload(
        "trace-drain",
        root=root,
        payload=payload,
        command_status="success" if payload.get("failed_count", 0) == 0 else "fail",
        warnings=warnings,
        artifact_metadata=_artifact_metadata(
            generated_paths=[
                str(item.get("imported_trace_record_path") or "")
                for item in normalized_items
                if isinstance(item, Mapping)
            ],
            related_paths=["artifacts/traces/queued", "artifacts/traces/imported"],
        ),
    )


def _coerce_pass_rate(value: object) -> float | None:
    """Return one numeric pass-rate value when available."""

    if isinstance(value, int | float):
        return float(value)
    return None


def _build_bundle_benchmark_gate(
    root: Path,
    *,
    run_name: str | None,
    bundle_version: str | None,
    recompile_payload: Mapping[str, object] | None,
    minimum_pass_rate: float | None,
) -> dict[str, object]:
    """Summarize whether one bundle candidate clears the trainer-side benchmark gate."""

    payload: dict[str, object] = {
        "status": "not-requested",
        "minimum_pass_rate": minimum_pass_rate,
        "source": None,
        "run_name": run_name,
        "bundle_version": bundle_version,
        "benchmark_pass_rate": None,
        "benchmark_status": None,
        "bundle_path": None,
        "metadata_path": None,
        "error": None,
    }
    if minimum_pass_rate is None:
        return payload

    if recompile_payload is not None:
        payload["source"] = "recompile-training-result"
        training_result = recompile_payload.get("training_result")
        if not isinstance(training_result, Mapping):
            payload["status"] = "fail"
            payload["error"] = {
                "type": "MissingTrainingResult",
                "message": "Trainer-side recompilation did not produce a compiled training result.",
            }
            return payload
        payload["run_name"] = str(training_result.get("run_name") or run_name or "")
        payload["bundle_version"] = str(
            training_result.get("bundle_version") or bundle_version or ""
        )
        payload["bundle_path"] = str(training_result.get("bundle_path") or "")
        payload["metadata_path"] = str(training_result.get("metadata_path") or "")
        benchmark_summary = training_result.get("benchmark_summary")
        if not isinstance(benchmark_summary, Mapping):
            payload["status"] = "fail"
            payload["error"] = {
                "type": "MissingBenchmarkSummary",
                "message": "The compiled DSPy training result did not record a benchmark summary.",
            }
            return payload
        benchmark_pass_rate = _coerce_pass_rate(benchmark_summary.get("pass_rate"))
        payload["benchmark_pass_rate"] = benchmark_pass_rate
        payload["benchmark_status"] = (
            "pass"
            if benchmark_pass_rate is not None and benchmark_pass_rate >= minimum_pass_rate
            else "fail"
        )
        payload["status"] = "pass" if payload["benchmark_status"] == "pass" else "fail"
        return payload

    try:
        bundle_path, bundle_manifest = resolve_bundle_manifest(
            root.resolve(),
            run_name=run_name,
            bundle_version=bundle_version,
        )
    except Exception as exc:
        payload["status"] = "error"
        payload["source"] = "bundle-manifest"
        payload["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        return payload

    benchmark_summary = bundle_manifest.get("benchmark_summary")
    benchmark_pass_rate = (
        _coerce_pass_rate(benchmark_summary.get("pass_rate"))
        if isinstance(benchmark_summary, Mapping)
        else None
    )
    payload.update(
        {
            "source": "bundle-manifest",
            "run_name": str(bundle_manifest.get("run_name") or run_name or ""),
            "bundle_version": str(bundle_manifest.get("bundle_version") or bundle_version or ""),
            "bundle_path": str(bundle_manifest.get("bundle_path") or ""),
            "metadata_path": str(bundle_manifest.get("metadata_path") or ""),
            "benchmark_pass_rate": benchmark_pass_rate,
            "benchmark_status": str(bundle_manifest.get("benchmark_status") or ""),
            "resolved_bundle_manifest_path": str(bundle_path.relative_to(root.resolve())),
        }
    )
    payload["status"] = (
        "pass"
        if benchmark_pass_rate is not None and benchmark_pass_rate >= minimum_pass_rate
        else "fail"
    )
    return payload


def run_trainer_cycle(
    root: Path,
    *,
    queue_name: str = "default",
    limit: int | None = None,
    keep_queued: bool = False,
    run_name: str | None = None,
    bundle_version: str | None = None,
    recompile_run_name: str | None = None,
    recompile_base_training_path: Path = DEFAULT_TRAINING_PATH,
    recompile_candidates_path: Path = DEFAULT_TRAINER_TRAINING_CANDIDATES_PATH,
    recompile_generated_training_path: Path = DEFAULT_TRAINER_GENERATED_TRAINING_PATH,
    recompile_generated_training_summary_path: Path = (
        DEFAULT_TRAINER_GENERATED_TRAINING_SUMMARY_PATH
    ),
    recompile_optimizer: str = "bootstrapfewshot",
    recompile_top_k: int = 4,
    recompile_max_bootstrapped_demos: int = 2,
    recompile_max_labeled_demos: int = 2,
    recompile_mipro_auto: str = "light",
    recompile_num_threads: int = 4,
    recompile_mipro_num_trials: int | None = None,
    recompile_lm_config: DSPyLMConfig | None = None,
    promote_channel: str | None = None,
    note: str | None = None,
    training_path: Path = DEFAULT_TRAINING_PATH,
    top_k: int = DEFAULT_RETRIEVAL_EVAL_TOP_K,
    top_k_sweep: str | None = None,
    retrieval_mode: RetrievalMode | None = None,
    minimum_pass_rate: float | None = None,
    minimum_source_recall: float | None = None,
    minimum_bundle_pass_rate: float | None = None,
    min_new_candidates_for_recompile: int = 1,
) -> str:
    """Run one background-compatible trainer pass for queue drain, gating, and promotion."""

    effective_minimum_pass_rate = minimum_pass_rate
    effective_minimum_source_recall = minimum_source_recall
    effective_minimum_bundle_pass_rate = minimum_bundle_pass_rate
    if promote_channel is not None:
        if effective_minimum_pass_rate is None:
            effective_minimum_pass_rate = 1.0
        if effective_minimum_source_recall is None:
            effective_minimum_source_recall = 1.0

    queue_payload = drain_trace_queue(
        root,
        queue_name=queue_name,
        limit=limit,
        keep_queued=keep_queued,
    )
    queue_items = queue_payload.get("items")
    normalized_queue_items = queue_items if isinstance(queue_items, list) else []
    imported_trace_paths = [
        str(item.get("imported_trace_record_path") or "")
        for item in normalized_queue_items
        if isinstance(item, Mapping) and item.get("imported_trace_record_path")
    ]
    durable_trace_recovery = restore_processed_trace_records(
        root,
        queue_name=queue_name,
        output_dir=DEFAULT_TRAINER_RECOVERED_TRACES_DIR,
    )
    raw_trace_paths = durable_trace_recovery.get("trace_paths")
    recovered_trace_paths = (
        [str(path) for path in raw_trace_paths if isinstance(path, str) and path.strip()]
        if isinstance(raw_trace_paths, list)
        else []
    )
    trainer_trace_paths = recovered_trace_paths or imported_trace_paths
    ingestion_summary = _summarize_imported_trace_records(root, trainer_trace_paths)
    training_candidates = materialize_training_candidates(
        root,
        trace_paths=[Path(path) for path in trainer_trace_paths],
        output_path=DEFAULT_TRAINER_TRAINING_CANDIDATES_PATH,
        summary_path=DEFAULT_TRAINER_TRAINING_CANDIDATES_SUMMARY_PATH,
        seed_existing_output=True,
    )
    new_candidate_count_raw = training_candidates.get("new_candidate_count")
    try:
        new_candidate_count = max(0, int(new_candidate_count_raw or 0))
    except (TypeError, ValueError):
        new_candidate_count = 0
    effective_min_new_candidates = max(1, int(min_new_candidates_for_recompile))
    recompile_requested = recompile_run_name is not None
    recompile_threshold_met = new_candidate_count >= effective_min_new_candidates
    recompile_triggered = recompile_requested and recompile_threshold_met
    explicit_publish_requested = run_name is not None or bundle_version is not None
    if effective_minimum_bundle_pass_rate is None and (
        explicit_publish_requested or recompile_triggered
    ):
        effective_minimum_bundle_pass_rate = 1.0
    retrieval_payload = _build_retrieval_evaluation_payload(
        root,
        training_path=training_path,
        top_k=top_k,
        top_k_sweep=top_k_sweep,
        retrieval_mode=retrieval_mode,
        minimum_pass_rate=effective_minimum_pass_rate,
        minimum_source_recall=effective_minimum_source_recall,
    )
    gate_passed = retrieval_payload.get("status") == "pass"

    publish_payload: dict[str, object] | None = None
    promote_payload: dict[str, object] | None = None
    recompile_payload: dict[str, object] | None = None
    bundle_gate_payload: dict[str, object] | None = None
    cycle_warnings: list[str] = []
    publish_requested = explicit_publish_requested
    promotion_requested = False
    promotion_status = "not-requested" if promote_channel is None else "blocked"
    publish_error: dict[str, str] | None = None
    promote_error: dict[str, str] | None = None
    recompile_error: dict[str, str] | None = None

    if not queue_payload.get("queue_found"):
        cycle_warnings.append("No queued trace items were available for this trainer cycle.")
    if queue_payload.get("failed_count"):
        cycle_warnings.append("One or more queued trace items failed during trainer drain.")
    if ingestion_summary.get("invalid_record_count"):
        cycle_warnings.append(
            "One or more imported trace records could not be summarized during trainer ingestion."
        )

    if recompile_requested:
        if not recompile_triggered:
            recompile_status = (
                "skipped-no-new-candidates"
                if new_candidate_count == 0
                else "skipped-below-new-candidate-threshold"
            )
            recompile_payload = {
                "recompile_status": recompile_status,
                "generated_training": None,
                "training_result": None,
                "new_candidate_count": new_candidate_count,
                "min_new_candidates_for_recompile": effective_min_new_candidates,
            }
            if new_candidate_count == 0:
                cycle_warnings.append(
                    "Trainer-side bundle recompilation was skipped because no new training "
                    "candidates were imported during this cycle."
                )
            else:
                cycle_warnings.append(
                    "Trainer-side bundle recompilation was skipped because the number of new "
                    "training candidates did not reach the configured minimum threshold."
                )
        else:
            assert recompile_run_name is not None
            resolved_recompile_run_name = _versioned_training_run_name(recompile_run_name)
            recompile_lineage = {
                "run_family": recompile_run_name,
                "resolved_run_name": resolved_recompile_run_name,
                "imported_trace_record_paths": trainer_trace_paths,
                "imported_trace_count": len(trainer_trace_paths),
                "durable_trace_recovery": durable_trace_recovery,
                "training_candidates_path": training_candidates.get("output_path"),
                "training_candidates_summary_path": training_candidates.get("summary_path"),
                "champion_index_path": training_candidates.get("champion_index_path"),
                "candidate_count": training_candidates.get("candidate_count"),
                "new_candidate_count": new_candidate_count,
                "min_new_candidates_for_recompile": effective_min_new_candidates,
                "duplicate_count": training_candidates.get("duplicate_count"),
                "replaced_count": training_candidates.get("replaced_count"),
                "prompt_family_count": training_candidates.get("prompt_family_count"),
                "context_group_count": training_candidates.get("context_group_count"),
            }
            try:
                recompile_payload = _trainer_recompile_payload(
                    root,
                    run_name=resolved_recompile_run_name,
                    bundle_version=resolved_recompile_run_name,
                    run_family=recompile_run_name,
                    lineage_metadata=recompile_lineage,
                    base_training_path=recompile_base_training_path,
                    candidates_path=recompile_candidates_path,
                    generated_training_path=recompile_generated_training_path,
                    generated_training_summary_path=recompile_generated_training_summary_path,
                    lm_config=recompile_lm_config,
                    optimizer=recompile_optimizer,
                    top_k=recompile_top_k,
                    retrieval_mode=retrieval_mode,
                    max_bootstrapped_demos=recompile_max_bootstrapped_demos,
                    max_labeled_demos=recompile_max_labeled_demos,
                    mipro_auto=recompile_mipro_auto,
                    num_threads=recompile_num_threads,
                    mipro_num_trials=recompile_mipro_num_trials,
                    skip_without_lm=True,
                )
                recompile_payload["requested_run_name"] = recompile_run_name
                recompile_payload["resolved_run_name"] = resolved_recompile_run_name
                recompile_payload["lineage_metadata"] = recompile_lineage
                if recompile_payload.get("recompile_status") != "compiled":
                    cycle_warnings.append(
                        "Trainer-side bundle recompilation was skipped because DSPy LM "
                        "configuration is unavailable."
                    )
            except Exception as exc:
                recompile_error = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
                cycle_warnings.append(
                    "Trainer-side bundle recompilation failed during trainer cycle."
                )

    effective_publish_run_name = run_name
    if effective_publish_run_name is None and isinstance(recompile_payload, Mapping):
        training_result = recompile_payload.get("training_result")
        if isinstance(training_result, Mapping):
            training_run_name = training_result.get("run_name")
            if isinstance(training_run_name, str) and training_run_name.strip():
                effective_publish_run_name = training_run_name.strip()
                publish_requested = True
    promotion_requested = promote_channel is not None and publish_requested
    if promote_channel is not None and not promotion_requested:
        promotion_status = "not-requested"

    bundle_gate_payload = _build_bundle_benchmark_gate(
        root,
        run_name=effective_publish_run_name,
        bundle_version=bundle_version,
        recompile_payload=(
            recompile_payload
            if recompile_triggered and isinstance(recompile_payload, Mapping)
            else None
        ),
        minimum_pass_rate=effective_minimum_bundle_pass_rate,
    )
    bundle_gate_passed = bundle_gate_payload.get("status") in {"pass", "not-requested"}
    if publish_requested and not bundle_gate_passed:
        cycle_warnings.append("Bundle publish was blocked by trainer-side DSPy benchmark gates.")

    if publish_requested and bundle_gate_passed:
        try:
            publish_record = publish_bundle(
                root,
                run_name=effective_publish_run_name,
                bundle_version=bundle_version,
                note=note,
            )
            remote_publish = None
            config = resolve_azure_artifact_config()
            if config is not None and config.bundles_enabled:
                remote_publish = upload_remote_bundle(
                    root,
                    published_record=publish_record,
                    config=config,
                )
            publish_payload = {
                **publish_record,
                "remote_publish": remote_publish,
            }
        except Exception as exc:
            publish_error = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            cycle_warnings.append("Bundle publish failed during trainer cycle.")

    if promotion_requested:
        if not gate_passed:
            cycle_warnings.append(
                f"Promotion to `{promote_channel}` was blocked by retrieval gate failures."
            )
        elif not bundle_gate_passed:
            cycle_warnings.append(
                f"Promotion to `{promote_channel}` was blocked by trainer-side DSPy "
                "benchmark gates."
            )
        elif publish_error is not None:
            cycle_warnings.append(
                f"Promotion to `{promote_channel}` was skipped because bundle publish failed."
            )
        else:
            assert promote_channel is not None
            try:
                promote_state = promote_bundle(
                    root,
                    channel=promote_channel,
                    run_name=effective_publish_run_name,
                    bundle_version=bundle_version,
                    note=note,
                )
                remote_publish = None
                remote_channel = None
                config = resolve_azure_artifact_config()
                if config is not None and config.bundles_enabled:
                    published_record = published_bundle_record_from_state(
                        promote_state,
                        root=root,
                    )
                    remote_publish = upload_remote_bundle(
                        root,
                        published_record=published_record,
                        config=config,
                    )
                    remote_channel = upload_remote_bundle_channel(
                        promote_state,
                        channel=promote_channel,
                        config=config,
                    )
                promote_payload = {
                    **promote_state,
                    "remote_publish": remote_publish,
                    "remote_channel": remote_channel,
                }
                promotion_status = "promoted"
            except Exception as exc:
                promote_error = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
                promotion_status = "failed"
                cycle_warnings.append("Bundle promotion failed during trainer cycle.")

    if promotion_requested and gate_passed and publish_error is None and promote_payload is None:
        promotion_status = "failed"

    cycle_payload: dict[str, object] = {
        "queue_name": queue_name,
        "queue_drain": queue_payload,
        "durable_trace_recovery": durable_trace_recovery,
        "ingestion_summary": ingestion_summary,
        "training_candidates": training_candidates,
        "min_new_candidates_for_recompile": effective_min_new_candidates,
        "recompile_threshold_met": recompile_threshold_met,
        "recompile": recompile_payload,
        "recompile_error": recompile_error,
        "retrieval_gate": retrieval_payload,
        "gate_passed": gate_passed,
        "bundle_gate": bundle_gate_payload,
        "bundle_gate_passed": bundle_gate_passed,
        "publish_requested": publish_requested,
        "promotion_requested": promotion_requested,
        "publish": publish_payload,
        "publish_error": publish_error,
        "promote_channel": promote_channel,
        "promotion_status": promotion_status,
        "promotion": promote_payload,
        "promotion_error": promote_error,
        "note": note,
    }
    final_recompile_status: str | None = (
        str(recompile_payload.get("recompile_status"))
        if isinstance(recompile_payload, Mapping)
        and recompile_payload.get("recompile_status") is not None
        else None
    )
    recompile_failed = recompile_error is not None or (
        recompile_triggered and final_recompile_status != "compiled"
    )
    bundle_gate_required = effective_minimum_bundle_pass_rate is not None and (
        publish_requested or recompile_triggered
    )
    cycle_failed = (
        bool(queue_payload.get("failed_count"))
        or (promotion_requested and not gate_passed)
        or (bundle_gate_required and not bundle_gate_passed)
        or publish_error is not None
        or promote_error is not None
        or recompile_failed
    )
    generated_training_mapping: Mapping[str, object] = {}
    training_result_mapping: Mapping[str, object] = {}
    if isinstance(recompile_payload, Mapping):
        raw_generated_training = recompile_payload.get("generated_training")
        if isinstance(raw_generated_training, Mapping):
            generated_training_mapping = raw_generated_training
        raw_training_result = recompile_payload.get("training_result")
        if isinstance(raw_training_result, Mapping):
            training_result_mapping = raw_training_result
    return _json_command_payload(
        "trainer-cycle",
        root=root,
        payload=cycle_payload,
        command_status="success" if not cycle_failed else "fail",
        warnings=cycle_warnings,
        artifact_metadata=_artifact_metadata(
            input_paths=[str(retrieval_payload.get("training_path") or "")],
            generated_paths=[
                *trainer_trace_paths,
                str(training_candidates.get("output_path") or ""),
                str(training_candidates.get("summary_path") or ""),
                str(generated_training_mapping.get("output_path") or ""),
                str(generated_training_mapping.get("summary_path") or ""),
                str(training_result_mapping.get("program_path") or ""),
                str(training_result_mapping.get("metadata_path") or ""),
                str(training_result_mapping.get("bundle_path") or ""),
                str(bundle_gate_payload.get("resolved_bundle_manifest_path") or ""),
            ]
            + (
                [str(publish_payload.get("published_bundle_path") or "")]
                if isinstance(publish_payload, Mapping)
                else []
            )
            + (
                [str(promote_payload.get("channel_path") or "")]
                if isinstance(promote_payload, Mapping)
                else []
            ),
            related_paths=[
                "artifacts/traces/queued",
                "artifacts/traces/imported",
                "artifacts/trainer/recovered-imported-traces",
                "artifacts/dspy/published",
                "artifacts/dspy/channels",
            ],
        ),
    )


def run_trainer_candidates(
    root: Path,
    *,
    trace_paths: Sequence[Path] = (),
    output_path: Path = DEFAULT_TRAINER_TRAINING_CANDIDATES_PATH,
    summary_path: Path = DEFAULT_TRAINER_TRAINING_CANDIDATES_SUMMARY_PATH,
    include_statuses: Sequence[str] = ("accepted", "candidate"),
) -> str:
    """Materialize trainer-side DSPy training candidates from imported trace records."""

    payload = materialize_training_candidates(
        root,
        trace_paths=trace_paths,
        output_path=output_path,
        summary_path=summary_path,
        include_statuses=include_statuses,
    )
    return _json_command_payload(
        "trainer-candidates",
        root=root,
        payload=payload,
        command_status="success",
        artifact_metadata=_artifact_metadata(
            input_paths=[str(path) for path in trace_paths],
            generated_paths=[
                str(payload.get("output_path") or ""),
                str(payload.get("summary_path") or ""),
                str(payload.get("champion_index_path") or ""),
            ],
            related_paths=["artifacts/traces/imported"],
        ),
    )


def _trainer_recompile_payload(
    root: Path,
    *,
    run_name: str,
    bundle_version: str | None = None,
    run_family: str | None = None,
    lineage_metadata: Mapping[str, object] | None = None,
    base_training_path: Path = DEFAULT_TRAINING_PATH,
    candidates_path: Path = DEFAULT_TRAINER_TRAINING_CANDIDATES_PATH,
    generated_training_path: Path = DEFAULT_TRAINER_GENERATED_TRAINING_PATH,
    generated_training_summary_path: Path = DEFAULT_TRAINER_GENERATED_TRAINING_SUMMARY_PATH,
    lm_config: DSPyLMConfig | None = None,
    optimizer: str = "bootstrapfewshot",
    top_k: int = 4,
    retrieval_mode: RetrievalMode | None = None,
    max_bootstrapped_demos: int = 2,
    max_labeled_demos: int = 2,
    mipro_auto: str = "light",
    num_threads: int = 4,
    mipro_num_trials: int | None = None,
    skip_without_lm: bool = False,
) -> dict[str, object]:
    """Build one trainer-side recompilation payload from base+candidate examples."""

    generated_training = materialize_combined_training_examples(
        root,
        base_training_path=base_training_path,
        candidates_path=candidates_path,
        output_path=generated_training_path,
        summary_path=generated_training_summary_path,
    )
    resolved_lm_config = lm_config or resolve_dspy_lm_config()
    if resolved_lm_config is None:
        if skip_without_lm:
            return {
                "recompile_status": "skipped-no-lm-config",
                "generated_training": generated_training,
                "training_result": None,
            }
        raise RuntimeError(
            "DSPy LM configuration is required for trainer-side recompilation. "
            "Pass CLI flags, export DSPY_* variables, or configure the repository Azure/OpenAI env."
        )

    training_result = train_repository_program(
        root,
        training_config=DSPyTrainingConfig(
            training_path=generated_training_path,
            run_name=run_name,
            bundle_version=bundle_version,
            run_family=run_family,
            lineage_metadata=lineage_metadata,
            optimizer=optimizer,
            top_k=top_k,
            retrieval_mode=retrieval_mode,
            max_bootstrapped_demos=max_bootstrapped_demos,
            max_labeled_demos=max_labeled_demos,
            mipro_auto=mipro_auto,
            num_threads=num_threads,
            mipro_num_trials=mipro_num_trials,
        ),
        lm_config=resolved_lm_config,
    )
    return {
        "recompile_status": "compiled",
        "generated_training": generated_training,
        "training_result": training_result.to_payload(),
    }


def run_trainer_recompile(
    root: Path,
    *,
    run_name: str = DEFAULT_DSPY_RUN_NAME,
    base_training_path: Path = DEFAULT_TRAINING_PATH,
    candidates_path: Path = DEFAULT_TRAINER_TRAINING_CANDIDATES_PATH,
    generated_training_path: Path = DEFAULT_TRAINER_GENERATED_TRAINING_PATH,
    generated_training_summary_path: Path = DEFAULT_TRAINER_GENERATED_TRAINING_SUMMARY_PATH,
    lm_config: DSPyLMConfig | None = None,
    optimizer: str = "bootstrapfewshot",
    top_k: int = 4,
    retrieval_mode: RetrievalMode | None = None,
    max_bootstrapped_demos: int = 2,
    max_labeled_demos: int = 2,
    mipro_auto: str = "light",
    num_threads: int = 4,
    mipro_num_trials: int | None = None,
) -> str:
    """Recompile a DSPy bundle from base training samples plus trainer-side candidates."""

    payload = _trainer_recompile_payload(
        root,
        run_name=run_name,
        base_training_path=base_training_path,
        candidates_path=candidates_path,
        generated_training_path=generated_training_path,
        generated_training_summary_path=generated_training_summary_path,
        lm_config=lm_config,
        optimizer=optimizer,
        top_k=top_k,
        retrieval_mode=retrieval_mode,
        max_bootstrapped_demos=max_bootstrapped_demos,
        max_labeled_demos=max_labeled_demos,
        mipro_auto=mipro_auto,
        num_threads=num_threads,
        mipro_num_trials=mipro_num_trials,
    )
    generated_training = payload.get("generated_training")
    training_result = payload.get("training_result")
    return _json_command_payload(
        "trainer-recompile",
        root=root,
        payload=payload,
        command_status="success",
        artifact_metadata=_artifact_metadata(
            input_paths=[
                str(base_training_path),
                str(candidates_path),
            ],
            generated_paths=[
                str(generated_training.get("output_path") or "")
                if isinstance(generated_training, Mapping)
                else "",
                str(generated_training.get("summary_path") or "")
                if isinstance(generated_training, Mapping)
                else "",
                str(training_result.get("program_path") or "")
                if isinstance(training_result, Mapping)
                else "",
                str(training_result.get("metadata_path") or "")
                if isinstance(training_result, Mapping)
                else "",
                str(training_result.get("bundle_path") or "")
                if isinstance(training_result, Mapping)
                else "",
            ],
            related_paths=["artifacts/dspy", "artifacts/trainer"],
        ),
    )


def run_trainer_service(
    root: Path,
    *,
    queue_name: str = "default",
    limit: int | None = None,
    keep_queued: bool = False,
    run_name: str | None = None,
    bundle_version: str | None = None,
    recompile_run_name: str | None = None,
    recompile_base_training_path: Path = DEFAULT_TRAINING_PATH,
    recompile_candidates_path: Path = DEFAULT_TRAINER_TRAINING_CANDIDATES_PATH,
    recompile_generated_training_path: Path = DEFAULT_TRAINER_GENERATED_TRAINING_PATH,
    recompile_generated_training_summary_path: Path = (
        DEFAULT_TRAINER_GENERATED_TRAINING_SUMMARY_PATH
    ),
    recompile_optimizer: str = "bootstrapfewshot",
    recompile_top_k: int = 4,
    recompile_max_bootstrapped_demos: int = 2,
    recompile_max_labeled_demos: int = 2,
    recompile_mipro_auto: str = "light",
    recompile_num_threads: int = 4,
    recompile_mipro_num_trials: int | None = None,
    recompile_lm_config: DSPyLMConfig | None = None,
    promote_channel: str | None = None,
    note: str | None = None,
    training_path: Path = DEFAULT_TRAINING_PATH,
    top_k: int = DEFAULT_RETRIEVAL_EVAL_TOP_K,
    top_k_sweep: str | None = None,
    retrieval_mode: RetrievalMode | None = None,
    minimum_pass_rate: float | None = None,
    minimum_source_recall: float | None = None,
    minimum_bundle_pass_rate: float | None = None,
    min_new_candidates_for_recompile: int = 1,
    poll_interval_seconds: float = 60.0,
    max_cycles: int | None = None,
    max_idle_cycles: int | None = None,
    state_path: Path = DEFAULT_TRAINER_SERVICE_STATE_PATH,
    history_dir: Path = DEFAULT_TRAINER_SERVICE_HISTORY_DIR,
) -> str:
    """Run a long-lived background trainer loop around ``trainer-cycle``."""

    resolved_root = root.resolve()
    resolved_state_path = state_path if state_path.is_absolute() else resolved_root / state_path
    resolved_history_dir = history_dir if history_dir.is_absolute() else resolved_root / history_dir
    started_at = datetime.now(UTC)
    cycles_executed = 0
    successful_cycle_count = 0
    failed_cycle_count = 0
    total_drained_count = 0
    total_queue_failures = 0
    total_publish_count = 0
    total_promotion_count = 0
    total_training_candidate_count = 0
    total_new_training_candidate_count = 0
    total_prompt_family_count = 0
    total_context_group_count = 0
    total_recompiled_run_count = 0
    total_skipped_recompile_count = 0
    gate_failure_count = 0
    bundle_gate_failure_count = 0
    idle_cycles = 0
    consecutive_idle_cycles = 0
    acceptance_status_totals: Counter[str] = Counter()
    execution_status_totals: Counter[str] = Counter()
    retrieval_mode_totals: Counter[str] = Counter()
    bundle_version_totals: Counter[str] = Counter()
    missing_source_count = 0
    missing_context_count = 0
    source_error_count = 0
    used_baseline_fallback_count = 0
    invalid_record_count = 0
    latest_cycle_record_path: Path | None = None
    last_cycle_payload: dict[str, object] | None = None
    latest_warnings: list[str] = []
    stop_reason = "completed"

    try:
        while True:
            cycle_started_at = datetime.now(UTC)
            cycle_payload = json.loads(
                run_trainer_cycle(
                    resolved_root,
                    queue_name=queue_name,
                    limit=limit,
                    keep_queued=keep_queued,
                    run_name=run_name,
                    bundle_version=bundle_version,
                    recompile_run_name=recompile_run_name,
                    recompile_base_training_path=recompile_base_training_path,
                    recompile_candidates_path=recompile_candidates_path,
                    recompile_generated_training_path=recompile_generated_training_path,
                    recompile_generated_training_summary_path=(
                        recompile_generated_training_summary_path
                    ),
                    recompile_optimizer=recompile_optimizer,
                    recompile_top_k=recompile_top_k,
                    recompile_max_bootstrapped_demos=recompile_max_bootstrapped_demos,
                    recompile_max_labeled_demos=recompile_max_labeled_demos,
                    recompile_mipro_auto=recompile_mipro_auto,
                    recompile_num_threads=recompile_num_threads,
                    recompile_mipro_num_trials=recompile_mipro_num_trials,
                    recompile_lm_config=recompile_lm_config,
                    promote_channel=promote_channel,
                    note=note,
                    training_path=training_path,
                    top_k=top_k,
                    top_k_sweep=top_k_sweep,
                    retrieval_mode=retrieval_mode,
                    minimum_pass_rate=minimum_pass_rate,
                    minimum_source_recall=minimum_source_recall,
                    minimum_bundle_pass_rate=minimum_bundle_pass_rate,
                    min_new_candidates_for_recompile=min_new_candidates_for_recompile,
                )
            )
            cycles_executed += 1
            last_cycle_payload = cycle_payload
            latest_warnings = [
                str(item)
                for item in cycle_payload.get("warnings", [])
                if isinstance(item, str) and item.strip()
            ]

            queue_drain = cycle_payload.get("queue_drain")
            if not isinstance(queue_drain, Mapping):
                queue_drain = {}
            drained_count = int(queue_drain.get("drained_count") or 0)
            queue_failed_count = int(queue_drain.get("failed_count") or 0)
            total_drained_count += drained_count
            total_queue_failures += queue_failed_count

            if drained_count == 0 and queue_failed_count == 0:
                idle_cycles += 1
                consecutive_idle_cycles += 1
            else:
                consecutive_idle_cycles = 0

            cycle_status = str(cycle_payload.get("command_status") or "success")
            if cycle_status == "success":
                successful_cycle_count += 1
            else:
                failed_cycle_count += 1

            if cycle_payload.get("gate_passed") is False:
                gate_failure_count += 1
            if cycle_payload.get("bundle_gate_passed") is False:
                bundle_gate_failure_count += 1
            if isinstance(cycle_payload.get("publish"), Mapping):
                total_publish_count += 1
            if isinstance(cycle_payload.get("promotion"), Mapping):
                total_promotion_count += 1
            recompile_payload = cycle_payload.get("recompile")
            if isinstance(recompile_payload, Mapping):
                recompile_status = str(recompile_payload.get("recompile_status") or "").strip()
                if recompile_status == "compiled":
                    total_recompiled_run_count += 1
                elif recompile_status:
                    total_skipped_recompile_count += 1
            training_candidates = cycle_payload.get("training_candidates")
            if isinstance(training_candidates, Mapping):
                total_training_candidate_count = int(
                    training_candidates.get("candidate_count") or total_training_candidate_count
                )
                total_new_training_candidate_count += int(
                    training_candidates.get("new_candidate_count") or 0
                )
                total_prompt_family_count = int(
                    training_candidates.get("prompt_family_count") or total_prompt_family_count
                )
                total_context_group_count = int(
                    training_candidates.get("context_group_count") or total_context_group_count
                )

            ingestion_summary = cycle_payload.get("ingestion_summary")
            if isinstance(ingestion_summary, Mapping):
                for name, value in (
                    ("acceptance_status_counts", acceptance_status_totals),
                    ("execution_status_counts", execution_status_totals),
                    ("retrieval_mode_counts", retrieval_mode_totals),
                    ("bundle_version_counts", bundle_version_totals),
                ):
                    mapping_value = ingestion_summary.get(name)
                    if isinstance(mapping_value, Mapping):
                        for key, count in mapping_value.items():
                            if isinstance(count, int):
                                value[str(key)] += count
                missing_source_count += int(ingestion_summary.get("missing_source_count") or 0)
                missing_context_count += int(ingestion_summary.get("missing_context_count") or 0)
                source_error_count += int(ingestion_summary.get("source_error_count") or 0)
                used_baseline_fallback_count += int(
                    ingestion_summary.get("used_baseline_fallback_count") or 0
                )
                invalid_record_count += int(ingestion_summary.get("invalid_record_count") or 0)

            cycle_timestamp = cycle_started_at.strftime("%Y%m%dT%H%M%SZ")
            latest_cycle_record_path = (
                resolved_history_dir / f"{cycle_timestamp}-cycle-{cycles_executed:04d}.json"
            )
            cycle_record = {
                "trainer_service_cycle_kind": TRAINER_SERVICE_CYCLE_KIND,
                "recorded_at": datetime.now(UTC).isoformat(),
                "service_started_at": started_at.isoformat(),
                "service_cycle_number": cycles_executed,
                "queue_name": queue_name,
                "cycle": cycle_payload,
            }
            _write_json_artifact(latest_cycle_record_path, cycle_record)

            state_payload = {
                "trainer_service_state_kind": TRAINER_SERVICE_STATE_KIND,
                "updated_at": datetime.now(UTC).isoformat(),
                "started_at": started_at.isoformat(),
                "queue_name": queue_name,
                "poll_interval_seconds": poll_interval_seconds,
                "max_cycles": max_cycles,
                "max_idle_cycles": max_idle_cycles,
                "cycles_executed": cycles_executed,
                "successful_cycle_count": successful_cycle_count,
                "failed_cycle_count": failed_cycle_count,
                "idle_cycles": idle_cycles,
                "consecutive_idle_cycles": consecutive_idle_cycles,
                "total_drained_count": total_drained_count,
                "total_queue_failures": total_queue_failures,
                "total_publish_count": total_publish_count,
                "total_promotion_count": total_promotion_count,
                "total_training_candidate_count": total_training_candidate_count,
                "total_new_training_candidate_count": total_new_training_candidate_count,
                "total_prompt_family_count": total_prompt_family_count,
                "total_context_group_count": total_context_group_count,
                "total_recompiled_run_count": total_recompiled_run_count,
                "total_skipped_recompile_count": total_skipped_recompile_count,
                "gate_failure_count": gate_failure_count,
                "bundle_gate_failure_count": bundle_gate_failure_count,
                "acceptance_status_totals": dict(sorted(acceptance_status_totals.items())),
                "execution_status_totals": dict(sorted(execution_status_totals.items())),
                "retrieval_mode_totals": dict(sorted(retrieval_mode_totals.items())),
                "bundle_version_totals": dict(sorted(bundle_version_totals.items())),
                "missing_source_count": missing_source_count,
                "missing_context_count": missing_context_count,
                "source_error_count": source_error_count,
                "used_baseline_fallback_count": used_baseline_fallback_count,
                "invalid_record_count": invalid_record_count,
                "latest_cycle_record_path": _path_text_for_root(
                    latest_cycle_record_path, resolved_root
                ),
                "last_cycle_command_status": cycle_status,
                "last_cycle_warnings": latest_warnings,
                "last_cycle": last_cycle_payload,
            }
            _write_json_artifact(resolved_state_path, state_payload)

            if max_cycles is not None and cycles_executed >= max_cycles:
                stop_reason = "max-cycles"
                break
            if max_idle_cycles is not None and consecutive_idle_cycles >= max_idle_cycles:
                stop_reason = "max-idle-cycles"
                break
            if poll_interval_seconds > 0:
                time.sleep(poll_interval_seconds)
    except KeyboardInterrupt:
        stop_reason = "keyboard-interrupt"

    service_warnings: list[str] = []
    if failed_cycle_count:
        service_warnings.append("One or more trainer cycles failed during service execution.")
    if stop_reason == "max-idle-cycles":
        service_warnings.append("Trainer service stopped after the configured idle-cycle limit.")
    if invalid_record_count:
        service_warnings.append(
            "One or more imported trace records were unavailable during trainer-side ingestion."
        )
    if bundle_gate_failure_count:
        service_warnings.append(
            "One or more trainer cycles were blocked by trainer-side DSPy benchmark gates."
        )
    service_warnings.extend(latest_warnings)

    service_payload: dict[str, object] = {
        "service_status": "success" if failed_cycle_count == 0 else "fail",
        "started_at": started_at.isoformat(),
        "stopped_at": datetime.now(UTC).isoformat(),
        "stop_reason": stop_reason,
        "queue_name": queue_name,
        "poll_interval_seconds": poll_interval_seconds,
        "max_cycles": max_cycles,
        "max_idle_cycles": max_idle_cycles,
        "cycles_executed": cycles_executed,
        "successful_cycle_count": successful_cycle_count,
        "failed_cycle_count": failed_cycle_count,
        "idle_cycles": idle_cycles,
        "consecutive_idle_cycles": consecutive_idle_cycles,
        "total_drained_count": total_drained_count,
        "total_queue_failures": total_queue_failures,
        "gate_failure_count": gate_failure_count,
        "acceptance_status_totals": dict(sorted(acceptance_status_totals.items())),
        "execution_status_totals": dict(sorted(execution_status_totals.items())),
        "retrieval_mode_totals": dict(sorted(retrieval_mode_totals.items())),
        "bundle_version_totals": dict(sorted(bundle_version_totals.items())),
        "missing_source_count": missing_source_count,
        "missing_context_count": missing_context_count,
        "source_error_count": source_error_count,
        "used_baseline_fallback_count": used_baseline_fallback_count,
        "invalid_record_count": invalid_record_count,
        "total_publish_count": total_publish_count,
        "total_promotion_count": total_promotion_count,
        "total_training_candidate_count": total_training_candidate_count,
        "total_new_training_candidate_count": total_new_training_candidate_count,
        "min_new_candidates_for_recompile": max(1, int(min_new_candidates_for_recompile)),
        "total_prompt_family_count": total_prompt_family_count,
        "total_context_group_count": total_context_group_count,
        "total_recompiled_run_count": total_recompiled_run_count,
        "total_skipped_recompile_count": total_skipped_recompile_count,
        "bundle_gate_failure_count": bundle_gate_failure_count,
        "state_path": _path_text_for_root(resolved_state_path, resolved_root),
        "history_dir": _path_text_for_root(resolved_history_dir, resolved_root),
        "latest_cycle_record_path": _path_text_for_root(latest_cycle_record_path, resolved_root)
        if latest_cycle_record_path is not None
        else None,
        "last_cycle": last_cycle_payload,
    }
    return _json_command_payload(
        "trainer-service",
        root=resolved_root,
        payload=service_payload,
        command_status="success" if failed_cycle_count == 0 else "fail",
        warnings=service_warnings,
        artifact_metadata=_artifact_metadata(
            input_paths=[str(training_path)],
            generated_paths=[
                _path_text_for_root(resolved_state_path, resolved_root),
                _path_text_for_root(resolved_history_dir, resolved_root),
                _path_text_for_root(latest_cycle_record_path, resolved_root)
                if latest_cycle_record_path is not None
                else "",
            ],
            related_paths=[
                "artifacts/traces/queued",
                "artifacts/traces/imported",
                "artifacts/dspy/published",
                "artifacts/dspy/channels",
            ],
        ),
    )


def run_surface_verification(root: Path) -> str:
    """Serialize the current repository-surface verification result as JSON."""

    payload = verify_repository_surfaces(root)
    return _json_command_payload(
        "verify-surfaces",
        root=root,
        payload=payload,
        command_status="success" if payload["issue_count"] == 0 else "fail",
        artifact_metadata=_artifact_metadata(
            input_paths=["Makefile"],
            related_paths=["notebooks/"],
        ),
    )


def run_azure_openai_probe(root: Path, *, load_env_file: bool = False) -> str:
    """Serialize the Azure OpenAI runtime probe as JSON."""

    payload = probe_azure_openai(root, load_env_file=load_env_file)
    status = str(payload.get("status") or "success").lower()
    return _json_command_payload(
        "azure-openai-probe",
        root=root,
        payload=payload,
        command_status="success" if status == "success" else "fail",
        artifact_metadata=_artifact_metadata(
            input_paths=[".env.sample"],
            related_paths=["docs/operations/environment.md", "docs/operations/azure-deployment.md"],
        ),
    )


def run_azure_inference_probe(root: Path, *, load_env_file: bool = False) -> str:
    """Serialize the Azure AI Inference runtime probe as JSON."""

    payload = probe_azure_inference(root, load_env_file=load_env_file)
    status = str(payload.get("status") or "success").lower()
    return _json_command_payload(
        "azure-inference-probe",
        root=root,
        payload=payload,
        command_status="success" if status == "success" else "fail",
        artifact_metadata=_artifact_metadata(
            input_paths=[".env.sample"],
            related_paths=["docs/operations/environment.md", "docs/operations/azure-deployment.md"],
        ),
    )


def run_todo_backlog_sync(root: Path) -> str:
    """Regenerate the backlog tables and serialize the result as JSON."""

    payload = sync_todo_backlog(root)
    source_path = str(payload.get("source_path") or "")
    markdown_path = str(payload.get("markdown_path") or "")
    latex_path = str(payload.get("latex_path") or "")
    return _json_command_payload(
        "sync-todo-backlog",
        root=root,
        payload=payload,
        artifact_metadata=_artifact_metadata(
            input_paths=[source_path],
            generated_paths=[markdown_path, latex_path],
            related_paths=[
                "docs/planning/repo-hardening-plan.md",
                "docs/planning/dataset-integration-plan.md",
            ],
        ),
    )


def run_file_summary_sync(root: Path) -> str:
    """Regenerate FILES.md and FILES.csv and serialize the result as JSON."""

    payload = sync_file_summaries(root)
    markdown_path = str(payload.get("markdown_path") or "")
    csv_path = str(payload.get("csv_path") or "")
    guide_path = str(payload.get("guide_path") or "")
    return _json_command_payload(
        "sync-file-summaries",
        root=root,
        payload=payload,
        artifact_metadata=_artifact_metadata(
            generated_paths=[markdown_path, csv_path, guide_path],
            related_paths=["AGENTS.md"],
        ),
    )


def run_exploratorium_translation_sync(root: Path) -> str:
    """Regenerate the exploratorium translation surfaces and serialize the result as JSON."""

    payload = sync_exploratorium_translation(root)
    tex_path = str(payload.get("tex_path") or "")
    manifest_path = str(payload.get("manifest_path") or "")
    main_tex_path = str(payload.get("main_tex_path") or "")
    pdf_path = str(payload.get("pdf_path") or "")
    return _json_command_payload(
        "sync-exploratorium-translation",
        root=root,
        payload=payload,
        artifact_metadata=_artifact_metadata(
            generated_paths=[
                tex_path,
                manifest_path,
                main_tex_path,
                pdf_path,
            ],
            related_paths=["publication/repository-rag-lab-article.tex"],
        ),
    )


def run_github_pr_gate_sync(
    root: Path,
    *,
    branch: str = "master",
    repo: str | None = None,
    apply: bool = False,
) -> str:
    """Serialize the GitHub pull-request gate sync result as JSON."""

    payload = sync_github_pr_gates(root, branch=branch, repo=repo, apply=apply)
    return _json_command_payload(
        "sync-github-pr-gates",
        root=root,
        payload=payload,
        artifact_metadata=_artifact_metadata(
            related_paths=[".github/workflows/ci.yml", "Makefile"],
        ),
    )


def run_pages_site_sync(
    root: Path,
    *,
    output_dir: Path,
    branch: str = "master",
    repo_url: str | None = None,
) -> str:
    """Serialize the GitHub Pages site sync result as JSON."""

    payload = sync_pages_site(root, output_dir=output_dir, branch=branch, repo_url=repo_url)
    generated_paths: list[str] = []
    output_dir_text = payload.get("output_dir")
    if isinstance(output_dir_text, str):
        generated_paths.append(output_dir_text)
    for key in ("index_path", "catalog_path", "manifest_path"):
        value = payload.get(key)
        if isinstance(value, str):
            generated_paths.append(value)
    return _json_command_payload(
        "sync-pages-site",
        root=root,
        payload=payload,
        artifact_metadata=_artifact_metadata(
            generated_paths=generated_paths,
            related_paths=["mkdocs.yml"],
        ),
    )


def run_notebook_report(
    root: Path,
    *,
    timeout_seconds: int = 600,
    load_env_file: bool = False,
    fail_fast: bool = False,
    stream: TextIO | None = None,
) -> str:
    """Execute all tracked notebooks and serialize the monitored run report as JSON."""

    payload = run_notebooks(
        root,
        timeout_seconds=timeout_seconds,
        load_env_file=load_env_file,
        fail_fast=fail_fast,
        stream=stream,
    )
    generated_paths: list[str] = []
    report_markdown_path = payload.get("report_markdown_path")
    generated_paths.append(report_markdown_path)
    notebooks = payload.get("notebooks")
    for notebook in notebooks:
        generated_paths.append(notebook["raw_log_path"])
    status = str(payload.get("status") or "").lower()
    command_status = "success" if status == "success" else "fail"
    return _json_command_payload(
        "run-notebooks",
        root=root,
        payload=payload,
        command_status=command_status,
        artifact_metadata=_artifact_metadata(
            input_paths=["notebooks/"],
            generated_paths=generated_paths,
            related_paths=["src/repo_rag_lab/notebook_runner.py"],
        ),
    )
