from __future__ import annotations

import argparse
from pathlib import Path

from .app import RepositoryApp
from .azure import write_deployment_manifest
from .dspy_workflow import RepositoryRAG
from .mcp import discover_mcp_servers, dump_candidates
from .server import serve_ui
from .utilities import run_smoke_test, run_surface_verification, utility_summary
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

    render_ui_parser = subparsers.add_parser("render-ui")
    render_ui_parser.add_argument("--question", required=True)
    render_ui_parser.add_argument("--root", default=".")
    render_ui_parser.add_argument("--output")

    serve_ui_parser = subparsers.add_parser("serve-ui")
    serve_ui_parser.add_argument("--question", required=True)
    serve_ui_parser.add_argument("--root", default=".")
    serve_ui_parser.add_argument("--host", default="127.0.0.1")
    serve_ui_parser.add_argument("--port", type=int, default=8000)
    serve_ui_parser.add_argument("--once", action="store_true")

    smoke_parser = subparsers.add_parser("smoke-test")
    smoke_parser.add_argument("--root", default=".")

    verify_parser = subparsers.add_parser("verify-surfaces")
    verify_parser.add_argument("--root", default=".")
    return parser


def main() -> int:
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

    if args.command == "render-ui":
        html = RepositoryApp().render_question_page(args.question, root)
        if args.output:
            output_path = Path(args.output).resolve()
            output_path.write_text(html, encoding="utf-8")
            print(output_path)
            return 0
        print(html)
        return 0

    if args.command == "serve-ui":
        return serve_ui(
            root=root,
            question=args.question,
            host=args.host,
            port=args.port,
            once=args.once,
        )

    if args.command == "smoke-test":
        print(run_smoke_test(root))
        return 0

    if args.command == "verify-surfaces":
        payload = run_surface_verification(root)
        print(payload)
        return 0 if '"issue_count": 0' in payload else 1

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
