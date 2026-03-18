"""Command-line entrypoints for the shared repository RAG workflows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .azure import write_deployment_manifest
from .benchmarks import DEFAULT_RETRIEVAL_EVAL_TOP_K
from .dspy_training import (
    DEFAULT_DSPY_RUN_NAME,
    DEFAULT_TRAINING_PATH,
    DSPyLMConfig,
    DSPyTrainingConfig,
    resolve_dspy_lm_config,
    train_repository_program,
)
from .dspy_workflow import RepositoryRAG
from .mcp import discover_mcp_servers, dump_candidates
from .utilities import (
    run_azure_inference_probe,
    run_azure_openai_probe,
    run_dspy_artifacts,
    run_exploratorium_translation_sync,
    run_file_summary_sync,
    run_notebook_report,
    run_retrieval_evaluation,
    run_smoke_test,
    run_surface_verification,
    run_todo_backlog_sync,
    utility_summary,
)
from .workflow import ask_repository, ask_repository_live


def add_dspy_lm_arguments(parser: argparse.ArgumentParser) -> None:
    """Attach shared DSPy LM configuration flags to ``parser``."""

    parser.add_argument("--dspy-model")
    parser.add_argument("--dspy-api-key")
    parser.add_argument("--dspy-api-base")
    parser.add_argument("--dspy-api-version")
    parser.add_argument("--dspy-model-type", default="chat")
    parser.add_argument("--dspy-temperature", type=float)
    parser.add_argument("--dspy-max-tokens", type=int)


def resolve_dspy_lm_config_from_args(args: argparse.Namespace) -> DSPyLMConfig | None:
    """Resolve optional DSPy LM configuration from parsed CLI args."""

    return resolve_dspy_lm_config(
        model=getattr(args, "dspy_model", None),
        api_key=getattr(args, "dspy_api_key", None),
        api_base=getattr(args, "dspy_api_base", None),
        api_version=getattr(args, "dspy_api_version", None),
        model_type=getattr(args, "dspy_model_type", "chat"),
        temperature=getattr(args, "dspy_temperature", None),
        max_tokens=getattr(args, "dspy_max_tokens", None),
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level ``repo-rag`` argument parser."""

    parser = argparse.ArgumentParser(prog="repo-rag")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("--question", required=True)
    ask_parser.add_argument("--root", default=".")
    ask_parser.add_argument("--use-dspy", action="store_true")
    ask_parser.add_argument("--dspy-program-path")
    ask_parser.add_argument("--dspy-top-k", type=int, default=4)
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

    mcp_parser = subparsers.add_parser("discover-mcp")
    mcp_parser.add_argument("--root", default=".")

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
    return parser


def main() -> int:
    """Run the requested CLI command and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root).resolve()

    if args.command == "ask":
        if args.use_dspy:
            dspy_result = RepositoryRAG(
                root=root,
                top_k=args.dspy_top_k,
                program_path=Path(args.dspy_program_path) if args.dspy_program_path else None,
                lm_config=resolve_dspy_lm_config_from_args(args),
                require_configured_lm=True,
            )(args.question)
            print(dspy_result.answer)
            return 0
        rag_result = ask_repository(question=args.question, root=root)
        print(rag_result.answer)
        return 0

    if args.command == "ask-live":
        live_result = ask_repository_live(
            question=args.question,
            root=root,
            provider=args.provider,
            load_env_file=args.load_env_file,
        )
        print(live_result.answer)
        return 0

    if args.command == "discover-mcp":
        candidates = discover_mcp_servers(root)
        print(dump_candidates(candidates))
        return 0

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
        print(run_file_summary_sync(root))
        return 0

    if args.command == "sync-todo-backlog":
        print(run_todo_backlog_sync(root))
        return 0

    if args.command == "sync-exploratorium-translation":
        print(run_exploratorium_translation_sync(root))
        return 0

    if args.command == "smoke-test":
        print(run_smoke_test(root))
        return 0

    if args.command == "azure-openai-probe":
        print(run_azure_openai_probe(root, load_env_file=args.load_env_file))
        return 0

    if args.command == "azure-inference-probe":
        print(run_azure_inference_probe(root, load_env_file=args.load_env_file))
        return 0

    if args.command == "retrieval-eval":
        print(
            run_retrieval_evaluation(
                root,
                training_path=Path(args.training_path),
                top_k=args.top_k,
                top_k_sweep=args.top_k_sweep,
            )
        )
        return 0

    if args.command == "verify-surfaces":
        payload = run_surface_verification(root)
        print(payload)
        return 0 if '"issue_count": 0' in payload else 1

    if args.command == "run-notebooks":
        payload = run_notebook_report(
            root,
            timeout_seconds=args.timeout_seconds,
            load_env_file=args.load_env_file,
            fail_fast=args.fail_fast,
            stream=sys.stderr,
        )
        print(payload)
        return 0 if '"failure_count": 0' in payload else 1

    if args.command == "dspy-train":
        lm_config = resolve_dspy_lm_config_from_args(args)
        if lm_config is None:
            parser.error(
                "DSPy training requires LM configuration. Pass --dspy-model / --dspy-api-* "
                "flags, export DSPY_* env vars, or source the repository env first."
            )
        result = train_repository_program(
            root,
            training_config=DSPyTrainingConfig(
                training_path=Path(args.training_path),
                run_name=args.run_name,
                optimizer=args.optimizer,
                top_k=args.dspy_top_k,
                max_bootstrapped_demos=args.max_bootstrapped_demos,
                max_labeled_demos=args.max_labeled_demos,
                mipro_auto=args.mipro_auto,
                num_threads=args.num_threads,
                mipro_num_trials=args.mipro_num_trials,
            ),
            lm_config=lm_config,
        )
        print(result.to_json())
        return 0

    if args.command == "dspy-artifacts":
        print(run_dspy_artifacts(root))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
