from __future__ import annotations

import json
from pathlib import Path

from .azure import write_deployment_manifest
from .mcp import discover_mcp_servers
from .site import build_docs_site, verify_docs_site_sources
from .verification import verify_repository_surfaces
from .workflow import ask_repository


def utility_summary(root: Path) -> str:
    lines = [
        "Repository utility surfaces:",
        "- ask: answer repository-grounded questions",
        "- discover-mcp: inspect repo-local MCP candidates",
        "- azure-manifest: write Azure deployment metadata",
        "- docs-site: build the generated documentation site",
        "- render-ui: render a static HTML answer page for a repository question",
        "- serve-ui: serve the rendered repository answer page over HTTP",
        "- smoke-test: validate the core workflow surfaces",
        "- verify-surfaces: validate notebooks, Makefile, and docs-site sources",
        f"- root: {root}",
    ]
    return "\n".join(lines)


def run_smoke_test(root: Path) -> str:
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
    return json.dumps(verify_repository_surfaces(root), indent=2)


def run_docs_site(root: Path) -> str:
    return str(build_docs_site(root))


def run_docs_site_verification(root: Path) -> str:
    return json.dumps(verify_docs_site_sources(root), indent=2)
