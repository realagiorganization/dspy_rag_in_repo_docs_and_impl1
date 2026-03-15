from __future__ import annotations

import argparse
from pathlib import Path

from .azure import write_deployment_manifest
from .dspy_workflow import RepositoryRAG
from .mcp import discover_mcp_servers, dump_candidates
from .utilities import run_smoke_test, utility_summary
from .workflow import ask_repository


def build_parser() -> argparse.ArgumentParser:
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
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root).resolve()

    if args.command == "ask":
        if args.use_dspy:
            result = RepositoryRAG(root=root)(args.question)
            print(result.answer)
            return 0
        result = ask_repository(question=args.question, root=root)
        print(result.answer)
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

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
