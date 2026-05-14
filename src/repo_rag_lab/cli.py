"""Command-line entrypoints for the shared repository RAG workflows."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from .azure import write_deployment_manifest
from .benchmarks import DEFAULT_RETRIEVAL_EVAL_TOP_K
from .codex_proxy import serve_codex_proxy
from .dspy_training import (
    DEFAULT_DSPY_RUN_NAME,
    DEFAULT_TRAINING_PATH,
    DSPyLMConfig,
    DSPyTrainingConfig,
    resolve_dspy_helper_lm_config,
    resolve_dspy_lm_config,
    resolve_dspy_trainer_lm_config,
    train_repository_program,
)
from .dspy_workflow import RepositoryRAG
from .mcp import discover_mcp_servers, dump_candidates
from .mcp_server import serve_repo_rag_mcp
from .retrieval_profile import SUPPORTED_RETRIEVAL_MODES
from .runtime_artifacts import (
    DEFAULT_TRAINER_GENERATED_TRAINING_PATH,
    DEFAULT_TRAINER_GENERATED_TRAINING_SUMMARY_PATH,
    DEFAULT_TRAINER_SERVICE_HISTORY_DIR,
    DEFAULT_TRAINER_SERVICE_STATE_PATH,
    DEFAULT_TRAINER_TRAINING_CANDIDATES_PATH,
    DEFAULT_TRAINER_TRAINING_CANDIDATES_SUMMARY_PATH,
    RuntimeTraceContext,
    build_runtime_trace,
    fetch_remote_bundle,
    resolve_bundle_manifest,
    resolve_bundle_version_for_program,
)
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
)
from .utilities import (
    run_azure_inference_probe,
    run_azure_openai_probe,
    run_bundle_fetch,
    run_bundle_inspection,
    run_bundle_promote,
    run_bundle_publish,
    run_bundle_rollback,
    run_dspy_artifacts,
    run_exploratorium_translation_sync,
    run_file_summary_sync,
    run_github_pr_gate_sync,
    run_notebook_report,
    run_overlay_init,
    run_pages_site_sync,
    run_retrieval_evaluation,
    run_smoke_test,
    run_surface_verification,
    run_todo_backlog_sync,
    run_trace_drain,
    run_trace_enqueue,
    run_trace_export,
    run_trace_import,
    run_trainer_candidates,
    run_trainer_cycle,
    run_trainer_k8s_manifest_generation,
    run_trainer_recompile,
    run_trainer_service,
    utility_summary,
)
from .workflow import ask_repository, ask_repository_live

RETRIEVAL_MODE_CHOICES = sorted(SUPPORTED_RETRIEVAL_MODES)


def add_output_argument(
    parser: argparse.ArgumentParser,
    *,
    default: str = "text",
) -> None:
    """Attach the shared CLI output-format selector to ``parser``."""

    parser.add_argument("--output", choices=["text", "json"], default=default)


def _print_json(payload: dict[str, object]) -> None:
    """Print ``payload`` as pretty JSON."""

    print(json.dumps(payload, indent=2))


def _command_payload(
    command: str,
    *,
    root: Path,
    result: dict[str, object],
    command_status: str = "success",
    warnings: list[str] | None = None,
    artifact_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the shared machine-readable command envelope."""

    return {
        "command": command,
        "command_status": command_status,
        "root": str(root),
        "warnings": warnings or [],
        "artifact_metadata": artifact_metadata
        or {"input_paths": [], "generated_paths": [], "related_paths": []},
        **result,
    }


def _command_error_payload(command: str, *, root: Path, exc: Exception) -> dict[str, object]:
    """Build the shared machine-readable error envelope."""

    return {
        "command": command,
        "command_status": "error",
        "root": str(root),
        "warnings": [],
        "artifact_metadata": {"input_paths": [], "generated_paths": [], "related_paths": []},
        "error": {
            "type": type(exc).__name__,
            "message": str(exc),
        },
    }


def _string_list_field(payload: dict[str, object], key: str) -> list[str]:
    """Return ``payload[key]`` as a list of strings when it is sequence-like."""

    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _list_length_field(payload: dict[str, object], key: str) -> int:
    """Return the length of ``payload[key]`` when it is list-like."""

    value = payload.get(key)
    if not isinstance(value, list):
        return 0
    return len(value)


def _optional_string_field(payload: dict[str, object], key: str) -> str | None:
    """Return ``payload[key]`` when it is a non-empty string."""

    value = payload.get(key)
    if not isinstance(value, str):
        return None
    return value


def _run_json_command(command: str, *, root: Path, producer: Callable[[], str]) -> int:
    """Run a JSON-returning command and map its envelope status to an exit code."""

    try:
        payload_text = producer()
        print(payload_text)
        payload = json.loads(payload_text)
        return 0 if payload.get("command_status", "success") == "success" else 1
    except Exception as exc:
        _print_json(_command_error_payload(command, root=root, exc=exc))
        return 1


def add_dspy_lm_arguments(parser: argparse.ArgumentParser) -> None:
    """Attach shared DSPy LM configuration flags to ``parser``."""

    parser.add_argument("--dspy-model")
    parser.add_argument("--dspy-api-key")
    parser.add_argument("--dspy-api-base")
    parser.add_argument("--dspy-api-version")
    parser.add_argument("--dspy-model-type", default="chat")
    parser.add_argument("--dspy-temperature", type=float)
    parser.add_argument("--dspy-max-tokens", type=int)


def add_trainer_recompile_arguments(parser: argparse.ArgumentParser) -> None:
    """Attach shared trainer-side recompilation arguments to ``parser``."""

    parser.add_argument("--recompile-run-name")
    parser.add_argument("--recompile-base-training-path", default=str(DEFAULT_TRAINING_PATH))
    parser.add_argument("--recompile-candidates-path")
    parser.add_argument("--recompile-generated-training-path")
    parser.add_argument("--recompile-generated-training-summary-path")
    parser.add_argument(
        "--recompile-optimizer",
        choices=["bootstrapfewshot", "miprov2"],
        default="bootstrapfewshot",
    )
    parser.add_argument("--recompile-top-k", type=int, default=4)
    parser.add_argument("--recompile-max-bootstrapped-demos", type=int, default=2)
    parser.add_argument("--recompile-max-labeled-demos", type=int, default=2)
    parser.add_argument(
        "--recompile-mipro-auto",
        choices=["light", "medium", "heavy"],
        default="light",
    )
    parser.add_argument("--recompile-num-threads", type=int, default=4)
    parser.add_argument("--recompile-mipro-num-trials", type=int)
    add_dspy_lm_arguments(parser)


def resolve_dspy_lm_config_from_args(args: argparse.Namespace) -> DSPyLMConfig | None:
    """Resolve optional DSPy LM configuration from parsed CLI args."""

    model = getattr(args, "dspy_model", None)
    api_key = getattr(args, "dspy_api_key", None)
    api_base = getattr(args, "dspy_api_base", None)
    api_version = getattr(args, "dspy_api_version", None)
    model_type = getattr(args, "dspy_model_type", "chat")
    temperature = getattr(args, "dspy_temperature", None)
    max_tokens = getattr(args, "dspy_max_tokens", None)
    command = str(getattr(args, "command", "") or "")
    if command in {"dspy-train", "trainer-recompile", "trainer-cycle", "trainer-service"}:
        return resolve_dspy_trainer_lm_config(
            model=model,
            api_key=api_key,
            api_base=api_base,
            api_version=api_version,
            model_type=model_type,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if command == "ask" and bool(getattr(args, "use_dspy", False)):
        return resolve_dspy_helper_lm_config(
            model=model,
            api_key=api_key,
            api_base=api_base,
            api_version=api_version,
            model_type=model_type,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    return resolve_dspy_lm_config(
        model=model,
        api_key=api_key,
        api_base=api_base,
        api_version=api_version,
        model_type=model_type,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level ``repo-rag`` argument parser."""

    parser = argparse.ArgumentParser(prog="repo-rag")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser(
        "ask",
        help="Answer a repository question with lookup-first retrieval.",
    )
    ask_parser.add_argument("--question", required=True)
    ask_parser.add_argument("--root", default=".")
    ask_parser.add_argument(
        "--use-dspy",
        action="store_true",
        help=(
            "After lookup-first narrowing, use the DSPy answer path "
            "instead of the baseline retriever."
        ),
    )
    ask_parser.add_argument("--dspy-program-path")
    ask_parser.add_argument("--dspy-top-k", type=int, default=4)
    ask_parser.add_argument("--retrieval-mode", choices=RETRIEVAL_MODE_CHOICES)
    ask_parser.add_argument("--bundle-version")
    ask_parser.add_argument("--overlay-path")
    add_output_argument(ask_parser, default="text")
    add_dspy_lm_arguments(ask_parser)

    ask_live_parser = subparsers.add_parser("ask-live")
    ask_live_parser.add_argument("--question", required=True)
    ask_live_parser.add_argument("--root", default=".")
    ask_live_parser.add_argument(
        "--provider",
        choices=["azure-openai", "azure-inference"],
        default="azure-openai",
    )
    ask_live_parser.add_argument("--load-env-file", action="store_true")
    ask_live_parser.add_argument("--retrieval-mode", choices=RETRIEVAL_MODE_CHOICES)
    ask_live_parser.add_argument("--bundle-version")
    ask_live_parser.add_argument("--overlay-path")
    add_output_argument(ask_live_parser, default="text")

    mcp_parser = subparsers.add_parser("discover-mcp")
    mcp_parser.add_argument("--root", default=".")

    serve_mcp_parser = subparsers.add_parser("serve-mcp")
    serve_mcp_parser.add_argument("--root", default=".")

    serve_codex_proxy_parser = subparsers.add_parser("serve-codex-proxy")
    serve_codex_proxy_parser.add_argument("--root", default=".")
    serve_codex_proxy_parser.add_argument("--bundle-root", default=".")
    serve_codex_proxy_parser.add_argument("--artifact-dir", required=True)
    serve_codex_proxy_parser.add_argument("--host", default="127.0.0.1")
    serve_codex_proxy_parser.add_argument("--port", type=int, default=0)
    serve_codex_proxy_parser.add_argument("--dspy-top-k", type=int, default=4)
    serve_codex_proxy_parser.add_argument("--bundle-channel", default="stable")
    serve_codex_proxy_parser.add_argument("--bundle-version")
    serve_codex_proxy_parser.add_argument("--token-budget", type=int, default=700)
    serve_codex_proxy_parser.add_argument("--trivial-token-budget", type=int, default=280)
    serve_codex_proxy_parser.add_argument("--essentials-count", type=int, default=3)
    serve_codex_proxy_parser.add_argument("--low-signal-min-sources", type=int, default=1)
    serve_codex_proxy_parser.add_argument("--retrieval-mode", choices=RETRIEVAL_MODE_CHOICES)
    serve_codex_proxy_parser.add_argument("--cache-dir")
    serve_codex_proxy_parser.add_argument("--cache-ttl-seconds", type=int, default=3600)
    serve_codex_proxy_parser.add_argument("--no-dspy", action="store_true")
    serve_codex_proxy_parser.add_argument("--ready-file")

    azure_parser = subparsers.add_parser("azure-manifest")
    azure_parser.add_argument("--root", default=".")
    azure_parser.add_argument("--model-id", required=True)
    azure_parser.add_argument("--deployment-name", required=True)
    azure_parser.add_argument("--endpoint", required=True)

    utility_parser = subparsers.add_parser("utility-summary")
    utility_parser.add_argument("--root", default=".")

    file_summary_parser = subparsers.add_parser("sync-file-summaries")
    file_summary_parser.add_argument("--root", default=".")

    todo_parser = subparsers.add_parser("sync-todo-backlog")
    todo_parser.add_argument("--root", default=".")

    exploratorium_parser = subparsers.add_parser("sync-exploratorium-translation")
    exploratorium_parser.add_argument("--root", default=".")

    github_pr_gates_parser = subparsers.add_parser("sync-github-pr-gates")
    github_pr_gates_parser.add_argument("--root", default=".")
    github_pr_gates_parser.add_argument("--branch", default="master")
    github_pr_gates_parser.add_argument("--repo")
    github_pr_gates_parser.add_argument("--apply", action="store_true")

    pages_site_parser = subparsers.add_parser("sync-pages-site")
    pages_site_parser.add_argument("--root", default=".")
    pages_site_parser.add_argument("--output-dir", default="artifacts/pages_docs")
    pages_site_parser.add_argument("--branch", default="master")
    pages_site_parser.add_argument("--repo-url")

    smoke_parser = subparsers.add_parser("smoke-test")
    smoke_parser.add_argument("--root", default=".")

    azure_openai_probe_parser = subparsers.add_parser("azure-openai-probe")
    azure_openai_probe_parser.add_argument("--root", default=".")
    azure_openai_probe_parser.add_argument("--load-env-file", action="store_true")

    azure_inference_probe_parser = subparsers.add_parser("azure-inference-probe")
    azure_inference_probe_parser.add_argument("--root", default=".")
    azure_inference_probe_parser.add_argument("--load-env-file", action="store_true")

    retrieval_eval_parser = subparsers.add_parser("retrieval-eval")
    retrieval_eval_parser.add_argument("--root", default=".")
    retrieval_eval_parser.add_argument("--training-path", default=str(DEFAULT_TRAINING_PATH))
    retrieval_eval_parser.add_argument("--top-k", type=int, default=DEFAULT_RETRIEVAL_EVAL_TOP_K)
    retrieval_eval_parser.add_argument("--top-k-sweep", default="1,2,4,8")
    retrieval_eval_parser.add_argument("--retrieval-mode", choices=RETRIEVAL_MODE_CHOICES)
    retrieval_eval_parser.add_argument("--minimum-pass-rate", type=float)
    retrieval_eval_parser.add_argument("--minimum-source-recall", type=float)
    add_output_argument(retrieval_eval_parser, default="json")

    verify_parser = subparsers.add_parser("verify-surfaces")
    verify_parser.add_argument("--root", default=".")

    notebook_parser = subparsers.add_parser("run-notebooks")
    notebook_parser.add_argument("--root", default=".")
    notebook_parser.add_argument("--timeout-seconds", type=int, default=600)
    notebook_parser.add_argument("--load-env-file", action="store_true")
    notebook_parser.add_argument("--fail-fast", action="store_true")

    dspy_train_parser = subparsers.add_parser("dspy-train")
    dspy_train_parser.add_argument("--root", default=".")
    dspy_train_parser.add_argument("--training-path", default=str(DEFAULT_TRAINING_PATH))
    dspy_train_parser.add_argument("--run-name", default=DEFAULT_DSPY_RUN_NAME)
    dspy_train_parser.add_argument(
        "--optimizer",
        choices=["bootstrapfewshot", "miprov2"],
        default="bootstrapfewshot",
    )
    dspy_train_parser.add_argument("--dspy-top-k", type=int, default=4)
    dspy_train_parser.add_argument("--retrieval-mode", choices=RETRIEVAL_MODE_CHOICES)
    dspy_train_parser.add_argument("--max-bootstrapped-demos", type=int, default=2)
    dspy_train_parser.add_argument("--max-labeled-demos", type=int, default=2)
    dspy_train_parser.add_argument(
        "--mipro-auto",
        choices=["light", "medium", "heavy"],
        default="light",
    )
    dspy_train_parser.add_argument("--num-threads", type=int, default=4)
    dspy_train_parser.add_argument("--mipro-num-trials", type=int)
    add_dspy_lm_arguments(dspy_train_parser)

    dspy_artifacts_parser = subparsers.add_parser("dspy-artifacts")
    dspy_artifacts_parser.add_argument("--root", default=".")
    add_output_argument(dspy_artifacts_parser, default="json")

    bundle_inspect_parser = subparsers.add_parser("bundle-inspect")
    bundle_inspect_parser.add_argument("--root", default=".")
    bundle_inspect_parser.add_argument("--run-name")
    bundle_inspect_parser.add_argument("--bundle-version")
    bundle_inspect_parser.add_argument("--channel", choices=["stable", "canary"])
    add_output_argument(bundle_inspect_parser, default="json")

    bundle_fetch_parser = subparsers.add_parser("bundle-fetch")
    bundle_fetch_parser.add_argument("--root", default=".")
    bundle_fetch_parser.add_argument("--bundle-version")
    bundle_fetch_parser.add_argument("--channel", choices=["stable", "canary"])
    add_output_argument(bundle_fetch_parser, default="json")

    bundle_publish_parser = subparsers.add_parser("bundle-publish")
    bundle_publish_parser.add_argument("--root", default=".")
    bundle_publish_parser.add_argument("--run-name")
    bundle_publish_parser.add_argument("--bundle-version")
    bundle_publish_parser.add_argument("--note")
    add_output_argument(bundle_publish_parser, default="json")

    bundle_promote_parser = subparsers.add_parser("bundle-promote")
    bundle_promote_parser.add_argument("--root", default=".")
    bundle_promote_parser.add_argument("--channel", choices=["stable", "canary"], required=True)
    bundle_promote_parser.add_argument("--run-name")
    bundle_promote_parser.add_argument("--bundle-version")
    bundle_promote_parser.add_argument("--note")
    add_output_argument(bundle_promote_parser, default="json")

    bundle_rollback_parser = subparsers.add_parser("bundle-rollback")
    bundle_rollback_parser.add_argument("--root", default=".")
    bundle_rollback_parser.add_argument("--channel", choices=["stable", "canary"], required=True)
    bundle_rollback_parser.add_argument("--bundle-version")
    bundle_rollback_parser.add_argument("--note")
    add_output_argument(bundle_rollback_parser, default="json")

    overlay_init_parser = subparsers.add_parser("overlay-init")
    overlay_init_parser.add_argument("--root", default=".")
    overlay_init_parser.add_argument("--overlay-name", default="default")
    overlay_init_parser.add_argument("--bundle-version")
    overlay_init_parser.add_argument("--retrieval-mode", choices=RETRIEVAL_MODE_CHOICES)
    add_output_argument(overlay_init_parser, default="json")

    trace_export_parser = subparsers.add_parser("trace-export")
    trace_export_parser.add_argument("--root", default=".")
    trace_export_parser.add_argument("--payload-path")
    trace_export_parser.add_argument("--stdin", action="store_true")
    trace_export_parser.add_argument("--trace-name")
    add_output_argument(trace_export_parser, default="json")

    trace_import_parser = subparsers.add_parser("trace-import")
    trace_import_parser.add_argument("--root", default=".")
    trace_import_parser.add_argument("--trace-path", required=True)
    trace_import_parser.add_argument("--trace-name")
    trace_import_parser.add_argument("--outcome-path")
    add_output_argument(trace_import_parser, default="json")

    trace_enqueue_parser = subparsers.add_parser("trace-enqueue")
    trace_enqueue_parser.add_argument("--root", default=".")
    trace_enqueue_parser.add_argument("--trace-path", required=True)
    trace_enqueue_parser.add_argument("--trace-name")
    trace_enqueue_parser.add_argument("--batch-name")
    trace_enqueue_parser.add_argument("--queue-name", default="default")
    trace_enqueue_parser.add_argument("--outcome-path")
    add_output_argument(trace_enqueue_parser, default="json")

    trace_drain_parser = subparsers.add_parser("trace-drain")
    trace_drain_parser.add_argument("--root", default=".")
    trace_drain_parser.add_argument("--queue-name", default="default")
    trace_drain_parser.add_argument("--limit", type=int)
    trace_drain_parser.add_argument("--keep-queued", action="store_true")
    add_output_argument(trace_drain_parser, default="json")

    trainer_cycle_parser = subparsers.add_parser("trainer-cycle")
    trainer_cycle_parser.add_argument("--root", default=".")
    trainer_cycle_parser.add_argument("--queue-name", default="default")
    trainer_cycle_parser.add_argument("--limit", type=int)
    trainer_cycle_parser.add_argument("--keep-queued", action="store_true")
    trainer_cycle_parser.add_argument("--run-name")
    trainer_cycle_parser.add_argument("--bundle-version")
    trainer_cycle_parser.add_argument("--promote-channel", choices=["stable", "canary"])
    trainer_cycle_parser.add_argument("--note")
    trainer_cycle_parser.add_argument("--training-path", default=str(DEFAULT_TRAINING_PATH))
    trainer_cycle_parser.add_argument("--top-k", type=int, default=DEFAULT_RETRIEVAL_EVAL_TOP_K)
    trainer_cycle_parser.add_argument("--top-k-sweep")
    trainer_cycle_parser.add_argument("--retrieval-mode", choices=RETRIEVAL_MODE_CHOICES)
    trainer_cycle_parser.add_argument("--minimum-pass-rate", type=float)
    trainer_cycle_parser.add_argument("--minimum-source-recall", type=float)
    trainer_cycle_parser.add_argument("--minimum-bundle-pass-rate", type=float)
    trainer_cycle_parser.add_argument("--min-new-candidates-for-recompile", type=int, default=1)
    add_trainer_recompile_arguments(trainer_cycle_parser)
    add_output_argument(trainer_cycle_parser, default="json")

    trainer_service_parser = subparsers.add_parser("trainer-service")
    trainer_service_parser.add_argument("--root", default=".")
    trainer_service_parser.add_argument("--queue-name", default="default")
    trainer_service_parser.add_argument("--limit", type=int)
    trainer_service_parser.add_argument("--keep-queued", action="store_true")
    trainer_service_parser.add_argument("--run-name")
    trainer_service_parser.add_argument("--bundle-version")
    trainer_service_parser.add_argument("--promote-channel", choices=["stable", "canary"])
    trainer_service_parser.add_argument("--note")
    trainer_service_parser.add_argument("--training-path", default=str(DEFAULT_TRAINING_PATH))
    trainer_service_parser.add_argument("--top-k", type=int, default=DEFAULT_RETRIEVAL_EVAL_TOP_K)
    trainer_service_parser.add_argument("--top-k-sweep")
    trainer_service_parser.add_argument("--retrieval-mode", choices=RETRIEVAL_MODE_CHOICES)
    trainer_service_parser.add_argument("--minimum-pass-rate", type=float)
    trainer_service_parser.add_argument("--minimum-source-recall", type=float)
    trainer_service_parser.add_argument("--minimum-bundle-pass-rate", type=float)
    trainer_service_parser.add_argument("--min-new-candidates-for-recompile", type=int, default=1)
    trainer_service_parser.add_argument("--poll-interval-seconds", type=float, default=60.0)
    trainer_service_parser.add_argument("--max-cycles", type=int)
    trainer_service_parser.add_argument("--max-idle-cycles", type=int)
    trainer_service_parser.add_argument("--state-path")
    trainer_service_parser.add_argument("--history-dir")
    add_trainer_recompile_arguments(trainer_service_parser)
    add_output_argument(trainer_service_parser, default="json")

    trainer_k8s_parser = subparsers.add_parser("trainer-k8s-manifests")
    trainer_k8s_parser.add_argument("--root", default=".")
    trainer_k8s_parser.add_argument("--image", default=DEFAULT_TRAINER_K8S_IMAGE)
    trainer_k8s_parser.add_argument("--namespace", default=DEFAULT_TRAINER_K8S_NAMESPACE)
    trainer_k8s_parser.add_argument("--service-account-name", default="repo-rag-trainer")
    trainer_k8s_parser.add_argument("--config-map-name", default="repo-rag-trainer-config")
    trainer_k8s_parser.add_argument("--secret-name", default="repo-rag-trainer-secrets")
    trainer_k8s_parser.add_argument("--pvc-name", default=DEFAULT_TRAINER_K8S_PVC_NAME)
    trainer_k8s_parser.add_argument(
        "--pvc-storage-class", default=DEFAULT_TRAINER_K8S_PVC_STORAGE_CLASS
    )
    trainer_k8s_parser.add_argument("--pvc-size", default=DEFAULT_TRAINER_K8S_PVC_SIZE)
    trainer_k8s_parser.add_argument(
        "--pvc-access-modes",
        default=",".join(DEFAULT_TRAINER_K8S_PVC_ACCESS_MODES),
    )
    trainer_k8s_parser.add_argument(
        "--image-pull-secret", default=DEFAULT_TRAINER_K8S_IMAGE_PULL_SECRET_NAME
    )
    trainer_k8s_parser.add_argument("--output-dir", default=str(DEFAULT_TRAINER_K8S_OUTPUT_DIR))
    trainer_k8s_parser.add_argument("--queue-name", default=DEFAULT_TRAINER_K8S_QUEUE_NAME)
    trainer_k8s_parser.add_argument("--cycle-schedule", default=DEFAULT_TRAINER_K8S_CYCLE_SCHEDULE)
    trainer_k8s_parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=DEFAULT_TRAINER_K8S_SERVICE_POLL_INTERVAL_SECONDS,
    )
    trainer_k8s_parser.add_argument(
        "--service-max-idle-cycles",
        type=int,
        default=DEFAULT_TRAINER_K8S_SERVICE_MAX_IDLE_CYCLES,
    )
    trainer_k8s_parser.add_argument(
        "--promote-channel",
        choices=["stable", "canary"],
        default=DEFAULT_TRAINER_K8S_PROMOTE_CHANNEL,
    )
    trainer_k8s_parser.add_argument("--training-path", default=str(DEFAULT_TRAINING_PATH))
    trainer_k8s_parser.add_argument("--top-k", type=int, default=DEFAULT_RETRIEVAL_EVAL_TOP_K)
    trainer_k8s_parser.add_argument("--top-k-sweep", default="1,2,4,8")
    trainer_k8s_parser.add_argument("--retrieval-mode", choices=RETRIEVAL_MODE_CHOICES)
    trainer_k8s_parser.add_argument(
        "--minimum-pass-rate", type=float, default=DEFAULT_TRAINER_K8S_MINIMUM_PASS_RATE
    )
    trainer_k8s_parser.add_argument(
        "--minimum-source-recall",
        type=float,
        default=DEFAULT_TRAINER_K8S_MINIMUM_SOURCE_RECALL,
    )
    trainer_k8s_parser.add_argument(
        "--minimum-bundle-pass-rate",
        type=float,
        default=DEFAULT_TRAINER_K8S_MINIMUM_BUNDLE_PASS_RATE,
    )
    trainer_k8s_parser.add_argument(
        "--recompile-run-name", default=DEFAULT_TRAINER_K8S_RECOMPILE_RUN_NAME
    )
    trainer_k8s_parser.add_argument(
        "--min-new-candidates-for-recompile",
        type=int,
        default=DEFAULT_TRAINER_K8S_MIN_NEW_CANDIDATES_FOR_RECOMPILE,
    )
    trainer_k8s_parser.add_argument(
        "--recompile-base-training-path", default=str(DEFAULT_TRAINING_PATH)
    )
    add_output_argument(trainer_k8s_parser, default="json")

    trainer_candidates_parser = subparsers.add_parser("trainer-candidates")
    trainer_candidates_parser.add_argument("--root", default=".")
    trainer_candidates_parser.add_argument("--trace-path", action="append", dest="trace_paths")
    trainer_candidates_parser.add_argument("--output-path")
    trainer_candidates_parser.add_argument("--summary-path")
    trainer_candidates_parser.add_argument("--include-statuses", default="accepted,candidate")
    add_output_argument(trainer_candidates_parser, default="json")

    trainer_recompile_parser = subparsers.add_parser("trainer-recompile")
    trainer_recompile_parser.add_argument("--root", default=".")
    trainer_recompile_parser.add_argument("--run-name", default=DEFAULT_DSPY_RUN_NAME)
    trainer_recompile_parser.add_argument(
        "--base-training-path", default=str(DEFAULT_TRAINING_PATH)
    )
    trainer_recompile_parser.add_argument("--candidates-path")
    trainer_recompile_parser.add_argument("--generated-training-path")
    trainer_recompile_parser.add_argument("--generated-training-summary-path")
    trainer_recompile_parser.add_argument(
        "--optimizer",
        choices=["bootstrapfewshot", "miprov2"],
        default="bootstrapfewshot",
    )
    trainer_recompile_parser.add_argument("--dspy-top-k", type=int, default=4)
    trainer_recompile_parser.add_argument("--retrieval-mode", choices=RETRIEVAL_MODE_CHOICES)
    trainer_recompile_parser.add_argument("--max-bootstrapped-demos", type=int, default=2)
    trainer_recompile_parser.add_argument("--max-labeled-demos", type=int, default=2)
    trainer_recompile_parser.add_argument(
        "--mipro-auto",
        choices=["light", "medium", "heavy"],
        default="light",
    )
    trainer_recompile_parser.add_argument("--num-threads", type=int, default=4)
    trainer_recompile_parser.add_argument("--mipro-num-trials", type=int)
    add_dspy_lm_arguments(trainer_recompile_parser)
    add_output_argument(trainer_recompile_parser, default="json")
    return parser


def main() -> int:
    """Run the requested CLI command and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root).resolve()

    if args.command == "ask":
        output_mode = getattr(args, "output", "text")
        try:
            if args.use_dspy:
                resolved_program_path = (
                    Path(args.dspy_program_path) if args.dspy_program_path else None
                )
                bundle_version = args.bundle_version if hasattr(args, "bundle_version") else None
                if resolved_program_path is None and bundle_version is not None:
                    requested_bundle_version = str(bundle_version)
                    remote_bundle = fetch_remote_bundle(
                        root,
                        bundle_version=requested_bundle_version,
                    )
                    remote_program_path = (
                        remote_bundle.get("program_path")
                        if isinstance(remote_bundle, dict)
                        else None
                    )
                    if isinstance(remote_program_path, str) and remote_program_path.strip():
                        resolved_program_path = (root / remote_program_path).resolve()
                    else:
                        try:
                            _, local_bundle = resolve_bundle_manifest(
                                root,
                                bundle_version=requested_bundle_version,
                            )
                        except ValueError:
                            local_bundle = None
                        local_program_path = (
                            local_bundle.get("program_path")
                            if isinstance(local_bundle, dict)
                            else None
                        )
                        if isinstance(local_program_path, str) and local_program_path.strip():
                            local_program_path_obj = Path(local_program_path)
                            if not local_program_path_obj.is_absolute():
                                local_program_path_obj = (root / local_program_path_obj).resolve()
                            resolved_program_path = local_program_path_obj
                        else:
                            raise FileNotFoundError(
                                "Requested DSPy bundle version "
                                f"`{requested_bundle_version}` could not be resolved locally or "
                                "through the configured Azure bundle store."
                            )
                runner = RepositoryRAG(
                    root=root,
                    top_k=args.dspy_top_k,
                    program_path=resolved_program_path,
                    lm_config=resolve_dspy_lm_config_from_args(args),
                    require_configured_lm=True,
                    retrieval_mode=getattr(args, "retrieval_mode", None),
                )
                dspy_result = runner(args.question)
                if output_mode == "json":
                    result = dspy_result.to_payload(root=root)
                    result["mode"] = "dspy"
                    result["top_k"] = args.dspy_top_k
                    result["program_path"] = (
                        str(runner.program_path.relative_to(root))
                        if runner.program_path is not None
                        and runner.program_path.is_relative_to(root)
                        else (str(runner.program_path) if runner.program_path is not None else None)
                    )
                    bundle_version = getattr(
                        args, "bundle_version", None
                    ) or resolve_bundle_version_for_program(
                        root,
                        runner.program_path,
                    )
                    overlay_path = getattr(args, "overlay_path", None)
                    retrieved_context = result.get("retrieved_context")
                    evidence_items = (
                        [item for item in retrieved_context if isinstance(item, dict)]
                        if isinstance(retrieved_context, list)
                        else []
                    )
                    result["bundle_version"] = bundle_version
                    result["overlay_path"] = overlay_path
                    result["trace"] = build_runtime_trace(
                        RuntimeTraceContext(
                            question=args.question,
                            mode="dspy",
                            retrieval_mode=str(result.get("retrieval_mode") or "lexical"),
                            sources=_string_list_field(result, "sources"),
                            context_count=_list_length_field(result, "retrieved_context"),
                            top_k=args.dspy_top_k,
                            program_loaded=bool(result.get("program_loaded")),
                            program_path=_optional_string_field(result, "program_path"),
                            bundle_version=bundle_version,
                            overlay_path=overlay_path,
                            mcp_candidate_count=0,
                            answer_length=len(str(result.get("answer") or "")),
                            context_field="retrieved_context",
                            evidence_items=evidence_items,
                        )
                    )
                    _print_json(_command_payload("ask", root=root, result=result))
                    return 0
                print(dspy_result.answer)
                return 0
            rag_result = ask_repository(
                question=args.question,
                root=root,
                retrieval_mode=getattr(args, "retrieval_mode", None),
            )
            if output_mode == "json":
                result = rag_result.to_payload(root=root)
                result["mode"] = "baseline"
                result["top_k"] = 4
                bundle_version = getattr(args, "bundle_version", None)
                overlay_path = getattr(args, "overlay_path", None)
                context_items = result.get("context")
                evidence_items = (
                    [item for item in context_items if isinstance(item, dict)]
                    if isinstance(context_items, list)
                    else []
                )
                result["bundle_version"] = bundle_version
                result["overlay_path"] = overlay_path
                result["trace"] = build_runtime_trace(
                    RuntimeTraceContext(
                        question=args.question,
                        mode="baseline",
                        retrieval_mode=str(result.get("retrieval_mode") or "lexical"),
                        sources=_string_list_field(result, "sources"),
                        context_count=_list_length_field(result, "context"),
                        top_k=4,
                        bundle_version=bundle_version,
                        overlay_path=overlay_path,
                        mcp_candidate_count=_list_length_field(result, "mcp_candidates"),
                        answer_length=len(str(result.get("answer") or "")),
                        context_field="context",
                        evidence_items=evidence_items,
                    )
                )
                _print_json(_command_payload("ask", root=root, result=result))
                return 0
            print(rag_result.answer)
            return 0
        except Exception as exc:
            if output_mode == "json":
                _print_json(_command_error_payload("ask", root=root, exc=exc))
                return 1
            raise

    if args.command == "ask-live":
        output_mode = getattr(args, "output", "text")
        try:
            live_result = ask_repository_live(
                question=args.question,
                root=root,
                provider=args.provider,
                load_env_file=args.load_env_file,
                retrieval_mode=getattr(args, "retrieval_mode", None),
            )
            if output_mode == "json":
                result = live_result.to_payload(root=root)
                result["mode"] = "live"
                result["provider"] = args.provider
                result["load_env_file"] = args.load_env_file
                bundle_version = getattr(args, "bundle_version", None)
                overlay_path = getattr(args, "overlay_path", None)
                context_items = result.get("context")
                evidence_items = (
                    [item for item in context_items if isinstance(item, dict)]
                    if isinstance(context_items, list)
                    else []
                )
                result["bundle_version"] = bundle_version
                result["overlay_path"] = overlay_path
                result["trace"] = build_runtime_trace(
                    RuntimeTraceContext(
                        question=args.question,
                        mode="live",
                        retrieval_mode=str(result.get("retrieval_mode") or "lexical"),
                        sources=_string_list_field(result, "sources"),
                        context_count=_list_length_field(result, "context"),
                        top_k=4,
                        provider=args.provider,
                        bundle_version=bundle_version,
                        overlay_path=overlay_path,
                        mcp_candidate_count=_list_length_field(result, "mcp_candidates"),
                        answer_length=len(str(result.get("answer") or "")),
                        context_field="context",
                        evidence_items=evidence_items,
                    )
                )
                _print_json(_command_payload("ask-live", root=root, result=result))
                return 0
            print(live_result.answer)
            return 0
        except Exception as exc:
            if output_mode == "json":
                _print_json(_command_error_payload("ask-live", root=root, exc=exc))
                return 1
            raise

    if args.command == "discover-mcp":
        candidates = discover_mcp_servers(root)
        print(dump_candidates(candidates))
        return 0

    if args.command == "serve-mcp":
        return serve_repo_rag_mcp(
            root,
            input_stream=sys.stdin.buffer,
            output_stream=sys.stdout.buffer,
        )

    if args.command == "serve-codex-proxy":
        return serve_codex_proxy(
            repository_root=root,
            bundle_root=Path(args.bundle_root).expanduser().resolve(),
            artifact_dir=Path(args.artifact_dir).expanduser().resolve(),
            host=args.host,
            port=args.port,
            prefer_dspy=not args.no_dspy,
            dspy_top_k=args.dspy_top_k,
            bundle_channel=args.bundle_channel,
            bundle_version=args.bundle_version,
            token_budget=args.token_budget,
            trivial_token_budget=args.trivial_token_budget,
            essentials_count=args.essentials_count,
            low_signal_min_sources=args.low_signal_min_sources,
            retrieval_mode=getattr(args, "retrieval_mode", None),
            cache_dir=(Path(args.cache_dir).expanduser().resolve() if args.cache_dir else None),
            cache_ttl_seconds=args.cache_ttl_seconds,
            ready_file=(Path(args.ready_file).expanduser().resolve() if args.ready_file else None),
        )

    if args.command == "azure-manifest":
        output_path = write_deployment_manifest(
            root=root,
            model_id=args.model_id,
            deployment_name=args.deployment_name,
            endpoint=args.endpoint,
        )
        print(output_path)
        return 0

    if args.command == "utility-summary":
        print(utility_summary(root))
        return 0

    if args.command == "sync-file-summaries":
        return _run_json_command(
            "sync-file-summaries",
            root=root,
            producer=lambda: run_file_summary_sync(root),
        )

    if args.command == "sync-todo-backlog":
        return _run_json_command(
            "sync-todo-backlog",
            root=root,
            producer=lambda: run_todo_backlog_sync(root),
        )

    if args.command == "sync-exploratorium-translation":
        return _run_json_command(
            "sync-exploratorium-translation",
            root=root,
            producer=lambda: run_exploratorium_translation_sync(root),
        )

    if args.command == "sync-github-pr-gates":
        return _run_json_command(
            "sync-github-pr-gates",
            root=root,
            producer=lambda: run_github_pr_gate_sync(
                root,
                branch=args.branch,
                repo=args.repo,
                apply=args.apply,
            ),
        )

    if args.command == "sync-pages-site":
        return _run_json_command(
            "sync-pages-site",
            root=root,
            producer=lambda: run_pages_site_sync(
                root,
                output_dir=Path(args.output_dir),
                branch=args.branch,
                repo_url=args.repo_url,
            ),
        )

    if args.command == "smoke-test":
        return _run_json_command("smoke-test", root=root, producer=lambda: run_smoke_test(root))

    if args.command == "azure-openai-probe":
        return _run_json_command(
            "azure-openai-probe",
            root=root,
            producer=lambda: run_azure_openai_probe(root, load_env_file=args.load_env_file),
        )

    if args.command == "azure-inference-probe":
        return _run_json_command(
            "azure-inference-probe",
            root=root,
            producer=lambda: run_azure_inference_probe(root, load_env_file=args.load_env_file),
        )

    if args.command == "retrieval-eval":
        return _run_json_command(
            "retrieval-eval",
            root=root,
            producer=lambda: run_retrieval_evaluation(
                root,
                training_path=Path(args.training_path),
                top_k=args.top_k,
                top_k_sweep=args.top_k_sweep,
                retrieval_mode=getattr(args, "retrieval_mode", None),
                minimum_pass_rate=args.minimum_pass_rate,
                minimum_source_recall=args.minimum_source_recall,
            ),
        )

    if args.command == "verify-surfaces":
        return _run_json_command(
            "verify-surfaces",
            root=root,
            producer=lambda: run_surface_verification(root),
        )

    if args.command == "run-notebooks":
        return _run_json_command(
            "run-notebooks",
            root=root,
            producer=lambda: run_notebook_report(
                root,
                timeout_seconds=args.timeout_seconds,
                load_env_file=args.load_env_file,
                fail_fast=args.fail_fast,
                stream=sys.stderr,
            ),
        )

    if args.command == "dspy-train":
        lm_config = resolve_dspy_lm_config_from_args(args)
        if lm_config is None:
            parser.error(
                "DSPy training requires LM configuration. Pass --dspy-model / --dspy-api-* "
                "flags, export DSPY_* env vars, or source the repository env first."
            )
        try:
            training_result = train_repository_program(
                root,
                training_config=DSPyTrainingConfig(
                    training_path=Path(args.training_path),
                    run_name=args.run_name,
                    optimizer=args.optimizer,
                    top_k=args.dspy_top_k,
                    retrieval_mode=getattr(args, "retrieval_mode", None),
                    max_bootstrapped_demos=args.max_bootstrapped_demos,
                    max_labeled_demos=args.max_labeled_demos,
                    mipro_auto=args.mipro_auto,
                    num_threads=args.num_threads,
                    mipro_num_trials=args.mipro_num_trials,
                ),
                lm_config=lm_config,
            )
            _print_json(
                _command_payload(
                    "dspy-train",
                    root=root,
                    result=training_result.to_payload(),
                )
            )
            return 0
        except Exception as exc:
            _print_json(_command_error_payload("dspy-train", root=root, exc=exc))
            return 1

    if args.command == "dspy-artifacts":
        return _run_json_command(
            "dspy-artifacts",
            root=root,
            producer=lambda: run_dspy_artifacts(root),
        )

    if args.command == "bundle-inspect":
        return _run_json_command(
            "bundle-inspect",
            root=root,
            producer=lambda: run_bundle_inspection(
                root,
                run_name=args.run_name,
                bundle_version=args.bundle_version,
                channel=args.channel,
            ),
        )

    if args.command == "bundle-fetch":
        return _run_json_command(
            "bundle-fetch",
            root=root,
            producer=lambda: run_bundle_fetch(
                root,
                bundle_version=args.bundle_version,
                channel=args.channel,
            ),
        )

    if args.command == "bundle-publish":
        return _run_json_command(
            "bundle-publish",
            root=root,
            producer=lambda: run_bundle_publish(
                root,
                run_name=args.run_name,
                bundle_version=args.bundle_version,
                note=args.note,
            ),
        )

    if args.command == "bundle-promote":
        return _run_json_command(
            "bundle-promote",
            root=root,
            producer=lambda: run_bundle_promote(
                root,
                channel=args.channel,
                run_name=args.run_name,
                bundle_version=args.bundle_version,
                note=args.note,
            ),
        )

    if args.command == "bundle-rollback":
        return _run_json_command(
            "bundle-rollback",
            root=root,
            producer=lambda: run_bundle_rollback(
                root,
                channel=args.channel,
                bundle_version=args.bundle_version,
                note=args.note,
            ),
        )

    if args.command == "overlay-init":
        return _run_json_command(
            "overlay-init",
            root=root,
            producer=lambda: run_overlay_init(
                root,
                overlay_name=args.overlay_name,
                bundle_version=args.bundle_version,
                retrieval_mode=getattr(args, "retrieval_mode", None),
            ),
        )

    if args.command == "trace-export":
        payload_text = sys.stdin.read() if args.stdin else None
        return _run_json_command(
            "trace-export",
            root=root,
            producer=lambda: run_trace_export(
                root,
                payload_path=Path(args.payload_path) if args.payload_path else None,
                payload_text=payload_text,
                trace_name=args.trace_name,
            ),
        )

    if args.command == "trace-import":
        return _run_json_command(
            "trace-import",
            root=root,
            producer=lambda: run_trace_import(
                root,
                trace_path=Path(args.trace_path),
                trace_name=args.trace_name,
                outcome_path=Path(args.outcome_path) if args.outcome_path else None,
            ),
        )

    if args.command == "trace-enqueue":
        return _run_json_command(
            "trace-enqueue",
            root=root,
            producer=lambda: run_trace_enqueue(
                root,
                trace_path=Path(args.trace_path),
                trace_name=args.trace_name,
                batch_name=args.batch_name,
                queue_name=args.queue_name,
                outcome_path=Path(args.outcome_path) if args.outcome_path else None,
            ),
        )

    if args.command == "trace-drain":
        return _run_json_command(
            "trace-drain",
            root=root,
            producer=lambda: run_trace_drain(
                root,
                queue_name=args.queue_name,
                limit=args.limit,
                keep_queued=args.keep_queued,
            ),
        )

    if args.command == "trainer-cycle":
        return _run_json_command(
            "trainer-cycle",
            root=root,
            producer=lambda: run_trainer_cycle(
                root,
                queue_name=args.queue_name,
                limit=args.limit,
                keep_queued=args.keep_queued,
                run_name=args.run_name,
                bundle_version=args.bundle_version,
                recompile_run_name=args.recompile_run_name,
                recompile_base_training_path=Path(args.recompile_base_training_path),
                recompile_candidates_path=Path(args.recompile_candidates_path)
                if getattr(args, "recompile_candidates_path", None)
                else DEFAULT_TRAINER_TRAINING_CANDIDATES_PATH,
                recompile_generated_training_path=Path(args.recompile_generated_training_path)
                if getattr(args, "recompile_generated_training_path", None)
                else DEFAULT_TRAINER_GENERATED_TRAINING_PATH,
                recompile_generated_training_summary_path=Path(
                    args.recompile_generated_training_summary_path
                )
                if getattr(args, "recompile_generated_training_summary_path", None)
                else DEFAULT_TRAINER_GENERATED_TRAINING_SUMMARY_PATH,
                recompile_optimizer=args.recompile_optimizer,
                recompile_top_k=args.recompile_top_k,
                recompile_max_bootstrapped_demos=args.recompile_max_bootstrapped_demos,
                recompile_max_labeled_demos=args.recompile_max_labeled_demos,
                recompile_mipro_auto=args.recompile_mipro_auto,
                recompile_num_threads=args.recompile_num_threads,
                recompile_mipro_num_trials=args.recompile_mipro_num_trials,
                recompile_lm_config=resolve_dspy_lm_config_from_args(args),
                promote_channel=args.promote_channel,
                note=args.note,
                training_path=Path(args.training_path),
                top_k=args.top_k,
                top_k_sweep=args.top_k_sweep,
                retrieval_mode=getattr(args, "retrieval_mode", None),
                minimum_pass_rate=args.minimum_pass_rate,
                minimum_source_recall=args.minimum_source_recall,
                minimum_bundle_pass_rate=args.minimum_bundle_pass_rate,
                min_new_candidates_for_recompile=args.min_new_candidates_for_recompile,
            ),
        )

    if args.command == "trainer-service":
        return _run_json_command(
            "trainer-service",
            root=root,
            producer=lambda: run_trainer_service(
                root,
                queue_name=args.queue_name,
                limit=args.limit,
                keep_queued=args.keep_queued,
                run_name=args.run_name,
                bundle_version=args.bundle_version,
                recompile_run_name=args.recompile_run_name,
                recompile_base_training_path=Path(args.recompile_base_training_path),
                recompile_candidates_path=Path(args.recompile_candidates_path)
                if getattr(args, "recompile_candidates_path", None)
                else DEFAULT_TRAINER_TRAINING_CANDIDATES_PATH,
                recompile_generated_training_path=Path(args.recompile_generated_training_path)
                if getattr(args, "recompile_generated_training_path", None)
                else DEFAULT_TRAINER_GENERATED_TRAINING_PATH,
                recompile_generated_training_summary_path=Path(
                    args.recompile_generated_training_summary_path
                )
                if getattr(args, "recompile_generated_training_summary_path", None)
                else DEFAULT_TRAINER_GENERATED_TRAINING_SUMMARY_PATH,
                recompile_optimizer=args.recompile_optimizer,
                recompile_top_k=args.recompile_top_k,
                recompile_max_bootstrapped_demos=args.recompile_max_bootstrapped_demos,
                recompile_max_labeled_demos=args.recompile_max_labeled_demos,
                recompile_mipro_auto=args.recompile_mipro_auto,
                recompile_num_threads=args.recompile_num_threads,
                recompile_mipro_num_trials=args.recompile_mipro_num_trials,
                recompile_lm_config=resolve_dspy_lm_config_from_args(args),
                promote_channel=args.promote_channel,
                note=args.note,
                training_path=Path(args.training_path),
                top_k=args.top_k,
                top_k_sweep=args.top_k_sweep,
                retrieval_mode=args.retrieval_mode,
                minimum_pass_rate=args.minimum_pass_rate,
                minimum_source_recall=args.minimum_source_recall,
                minimum_bundle_pass_rate=args.minimum_bundle_pass_rate,
                min_new_candidates_for_recompile=args.min_new_candidates_for_recompile,
                poll_interval_seconds=args.poll_interval_seconds,
                max_cycles=args.max_cycles,
                max_idle_cycles=args.max_idle_cycles,
                state_path=Path(args.state_path)
                if getattr(args, "state_path", None)
                else DEFAULT_TRAINER_SERVICE_STATE_PATH,
                history_dir=Path(args.history_dir)
                if getattr(args, "history_dir", None)
                else DEFAULT_TRAINER_SERVICE_HISTORY_DIR,
            ),
        )

    if args.command == "trainer-k8s-manifests":
        return _run_json_command(
            "trainer-k8s-manifests",
            root=root,
            producer=lambda: run_trainer_k8s_manifest_generation(
                root,
                image=args.image,
                namespace=args.namespace,
                service_account_name=args.service_account_name,
                config_map_name=args.config_map_name,
                secret_name=args.secret_name,
                pvc_name=args.pvc_name,
                pvc_storage_class_name=args.pvc_storage_class,
                pvc_size=args.pvc_size,
                pvc_access_modes=tuple(
                    mode.strip()
                    for mode in str(args.pvc_access_modes or "").split(",")
                    if mode.strip()
                ),
                image_pull_secret_name=args.image_pull_secret,
                output_dir=Path(args.output_dir),
                queue_name=args.queue_name,
                cycle_schedule=args.cycle_schedule,
                poll_interval_seconds=args.poll_interval_seconds,
                service_max_idle_cycles=args.service_max_idle_cycles,
                promote_channel=args.promote_channel,
                retrieval_training_path=Path(args.training_path),
                retrieval_top_k=args.top_k,
                retrieval_top_k_sweep=args.top_k_sweep,
                retrieval_mode=args.retrieval_mode,
                minimum_pass_rate=args.minimum_pass_rate,
                minimum_source_recall=args.minimum_source_recall,
                minimum_bundle_pass_rate=args.minimum_bundle_pass_rate,
                recompile_run_name=args.recompile_run_name,
                min_new_candidates_for_recompile=args.min_new_candidates_for_recompile,
                recompile_base_training_path=Path(args.recompile_base_training_path),
            ),
        )

    if args.command == "trainer-candidates":
        include_statuses = [
            status.strip()
            for status in str(args.include_statuses or "").split(",")
            if status.strip()
        ]
        return _run_json_command(
            "trainer-candidates",
            root=root,
            producer=lambda: run_trainer_candidates(
                root,
                trace_paths=[Path(path) for path in (args.trace_paths or [])],
                output_path=Path(args.output_path)
                if getattr(args, "output_path", None)
                else DEFAULT_TRAINER_TRAINING_CANDIDATES_PATH,
                summary_path=Path(args.summary_path)
                if getattr(args, "summary_path", None)
                else DEFAULT_TRAINER_TRAINING_CANDIDATES_SUMMARY_PATH,
                include_statuses=include_statuses,
            ),
        )

    if args.command == "trainer-recompile":
        lm_config = resolve_dspy_lm_config_from_args(args)
        if lm_config is None:
            _print_json(
                _command_error_payload(
                    "trainer-recompile",
                    root=root,
                    exc=RuntimeError(
                        "DSPy LM configuration is required. Pass CLI flags, export DSPY_* "
                        "variables, or source the repository Azure/OpenAI environment before "
                        "using trainer-side recompilation."
                    ),
                )
            )
            return 1
        return _run_json_command(
            "trainer-recompile",
            root=root,
            producer=lambda: run_trainer_recompile(
                root,
                run_name=args.run_name,
                base_training_path=Path(args.base_training_path),
                candidates_path=Path(args.candidates_path)
                if getattr(args, "candidates_path", None)
                else DEFAULT_TRAINER_TRAINING_CANDIDATES_PATH,
                generated_training_path=Path(args.generated_training_path)
                if getattr(args, "generated_training_path", None)
                else DEFAULT_TRAINER_GENERATED_TRAINING_PATH,
                generated_training_summary_path=Path(args.generated_training_summary_path)
                if getattr(args, "generated_training_summary_path", None)
                else DEFAULT_TRAINER_GENERATED_TRAINING_SUMMARY_PATH,
                lm_config=lm_config,
                optimizer=args.optimizer,
                top_k=args.dspy_top_k,
                retrieval_mode=args.retrieval_mode,
                max_bootstrapped_demos=args.max_bootstrapped_demos,
                max_labeled_demos=args.max_labeled_demos,
                mipro_auto=args.mipro_auto,
                num_threads=args.num_threads,
                mipro_num_trials=args.mipro_num_trials,
            ),
        )

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
