"""Command-line entrypoints for the shared repository RAG workflows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .azure import write_deployment_manifest
from .dspy_workflow import RepositoryRAG
from .mcp import discover_mcp_servers, dump_candidates
from .utilities import (
    run_notebook_report,
    run_smoke_test,
    run_surface_verification,
    utility_summary,
)
from .workflow import ask_repository


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level ``repo-rag`` argument parser."""

    parser = argparse.ArgumentParser(prog="repo-rag")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("--question", required=True)
    ask_parser.add_argument("--root", default=".")
    ask_parser.add_argument("--use-dspy", action="store_true")

    mcp_parser = subparsers.add_parser("discover-mcp")
    mcp_parser.add_argument("--root", default=".")

    azure_parser = subparsers.add_parser("azure-manifest")
    azure_parser.add_argument("--root", default=".")
    azure_parser.add_argument("--model-id", required=True)
    azure_parser.add_argument("--deployment-name", required=True)
    azure_parser.add_argument("--endpoint", required=True)

    utility_parser = subparsers.add_parser("utility-summary")
    utility_parser.add_argument("--root", default=".")

    smoke_parser = subparsers.add_parser("smoke-test")
    smoke_parser.add_argument("--root", default=".")

    verify_parser = subparsers.add_parser("verify-surfaces")
    verify_parser.add_argument("--root", default=".")

    notebook_parser = subparsers.add_parser("run-notebooks")
    notebook_parser.add_argument("--root", default=".")
    notebook_parser.add_argument("--timeout-seconds", type=int, default=600)
    notebook_parser.add_argument("--load-env-file", action="store_true")
    notebook_parser.add_argument("--fail-fast", action="store_true")
    return parser


def main() -> int:
    """Run the requested CLI command and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root).resolve()

    if args.command == "ask":
        if args.use_dspy:
            dspy_result = RepositoryRAG(root=root)(args.question)
            print(dspy_result.answer)
            return 0
        rag_result = ask_repository(question=args.question, root=root)
        print(rag_result.answer)
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

    if args.command == "smoke-test":
        print(run_smoke_test(root))
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

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
