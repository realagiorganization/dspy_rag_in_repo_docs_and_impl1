"""User-facing utility helpers shared by the CLI, tests, and notebooks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TextIO

from .azure import write_deployment_manifest
from .azure_runtime import probe_azure_inference, probe_azure_openai
from .mcp import discover_mcp_servers
from .notebook_runner import run_notebooks
from .todo_backlog import sync_todo_backlog
from .verification import verify_repository_surfaces
from .workflow import ask_repository


def utility_summary(root: Path) -> str:
    """Describe the supported command surfaces for the repository workflow."""

    lines = [
        "Repository utility surfaces:",
        "- make utility-summary / uv run repo-rag utility-summary: list the supported entrypoints",
        "- make ask / uv run repo-rag ask: answer repository-grounded questions",
        "- make ask-dspy / uv run repo-rag ask --use-dspy: answer with the DSPy runtime path",
        (
            "- make ask-live / uv run repo-rag ask-live: answer with retrieved repo evidence "
            "plus a live Azure-backed synthesis step"
        ),
        "- make dspy-train / uv run repo-rag dspy-train: compile and persist a DSPy RAG program",
        "- make discover-mcp / uv run repo-rag discover-mcp: inspect repo-local MCP candidates",
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
            "- make todo-sync / uv run repo-rag sync-todo-backlog: "
            "regenerate the linkified TODO tables for Markdown and the publication PDF"
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
    payload = {
        "answer_contains_repository": "repository" in answer.answer.lower(),
        "mcp_candidate_count": len(mcp_candidates),
        "manifest_path": str(manifest_path.relative_to(root)),
    }
    return json.dumps(payload, indent=2)


def run_surface_verification(root: Path) -> str:
    """Serialize the current repository-surface verification result as JSON."""

    return json.dumps(verify_repository_surfaces(root), indent=2)


def run_azure_openai_probe(root: Path, *, load_env_file: bool = False) -> str:
    """Serialize the Azure OpenAI runtime probe as JSON."""

    return json.dumps(probe_azure_openai(root, load_env_file=load_env_file), indent=2)


def run_azure_inference_probe(root: Path, *, load_env_file: bool = False) -> str:
    """Serialize the Azure AI Inference runtime probe as JSON."""

    return json.dumps(probe_azure_inference(root, load_env_file=load_env_file), indent=2)


def run_todo_backlog_sync(root: Path) -> str:
    """Regenerate the backlog tables and serialize the result as JSON."""

    return json.dumps(sync_todo_backlog(root), indent=2)


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
    return json.dumps(payload, indent=2)
