# Repository RAG Lab

[![CI](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/workflows/ci.yml/badge.svg)](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/workflows/ci.yml)
[![Publish](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/workflows/publish.yml/badge.svg)](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/workflows/publish.yml)
[![Coverage](https://img.shields.io/badge/coverage-94.12%25-brightgreen)](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/workflows/ci.yml)

This repository is a `uv`-first research lab for repository-grounded Retrieval-Augmented
Generation. Notebooks, the packaged Python CLI, `make` targets, tests, CI, and the Rust wrapper
all share the same implementation so experiments and automation stay aligned.

## What The Repository Covers

The current scaffold focuses on three connected jobs:

1. Explore in-repo RAG over repository files with a simple baseline retriever and an optional
   DSPy-shaped flow.
2. Discover MCP-related artifacts in the repository, submodules, or package manifests.
3. Prepare Azure deployment manifests for tuned artifacts that are produced outside this repo.

## Tooling Stance

This repository is intentionally fully `uv`-managed.

- `uv` owns environment sync, locked execution, dependency resolution, builds, and publishing.
- `uv_build` is the Python build backend.
- `make` is a convenience layer over `uv run ...`.
- Pixi is not part of the current toolchain because it would duplicate responsibilities already
  covered by `uv`.

## Quick Start

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --extra azure
make hooks-install
make quality
make ask QUESTION="What does this repository research?"
```

## Preferred Workflow Surfaces

| Surface | Preferred command | Purpose |
| --- | --- | --- |
| Utility overview | `make utility-summary` | Show the supported user-facing entrypoints. |
| Direct CLI | `uv run repo-rag utility-summary` | Use the packaged CLI without going through `make`. |
| Ask a repo question | `make ask QUESTION="..."` | Run the baseline repository-grounded RAG workflow. |
| DSPy-shaped ask | `uv run repo-rag ask --question "..." --use-dspy` | Exercise the optional DSPy wrapper after configuring a DSPy LM in-process; see `README.DSPY.MD`. |
| MCP discovery | `make discover-mcp` | Inspect MCP-related repository artifacts. |
| Smoke test | `make smoke-test` | Check answer generation, MCP discovery, and Azure manifest output together. |
| Surface verification | `make verify-surfaces` | Enforce the Makefile and notebook contract. |
| Notebook research | `make notebook` | Open the main notebook playbook in JupyterLab. |
| Rust wrapper | `cargo run --manifest-path rust-cli/Cargo.toml -- ask --question "..."` | Run the same Python workflow through the Rust shim. |

## Repository Map

| Path | Role |
| --- | --- |
| `src/repo_rag_lab/` | Shared Python package for corpus loading, retrieval, MCP discovery, CLI commands, notebook scaffolds, utilities, and verification helpers. |
| `README.DSPY.MD` | Central DSPy map covering corpus planning, training samples, benchmarks, notebook scaffolds, and current DSPy runtime limitations. |
| `notebooks/` | Research playbooks that reuse package helpers for validation, assertions, and logging instead of embedding workflow logic inline. |
| `tests/` | Pytest suites, BDD-style checks, doctests, and surface verification tests. |
| `samples/training/` | Starter question-answer pairs for DSPy-oriented experiments. |
| `samples/population/` | Starter corpus-planning data for staged repository ingestion. |
| `documentation/` | Supporting notes for Azure deployment and inspired external implementations. |
| `samples/logs/` | Post-push GitHub Actions inspection logs captured with `gh`. |
| `artifacts/` | Generated Azure manifests, tuning metadata, and notebook run logs. |
| `rust-cli/` | Thin Rust wrapper that delegates to `uv run repo-rag`. |

## Verification And Quality

The repository treats documentation, notebooks, utilities, and packaging as one workflow. The
main verification entrypoints are:

- `make compile`
- `make lint`
- `make typecheck`
- `make verify-surfaces`
- `make test`
- `make quality`
- `make build`

Git hooks are managed through `pre-commit`:

- `make hooks-install`
- `make hooks-run`
- `make hooks-run-push`

The pre-commit hook stays lightweight with Ruff checks. The pre-push hook runs the heavier
acceptance gates: mypy, basedpyright, pytest with coverage, and repository-surface verification.

## Azure Deployment Path

This repository does not fine-tune or deploy a model on its own. It writes deployment metadata
that downstream Azure workflows can consume after a tuned artifact already exists.

```bash
make azure-manifest MODEL_ID=my-ft-model DEPLOYMENT_NAME=repo-rag-ft
```

The manifest lands in `artifacts/azure/` and records the deployment name, endpoint, and required
runtime environment variables.

## Agent Guidance

Repository-local agent instructions live in `AGENTS.md`. Agents and contributors should start with
named `make` targets or `uv run repo-rag ...` commands before inventing one-off workflows so
notebooks, tests, CI, and automation stay aligned.

## Post-Push Workflow

After every push:

1. Inspect recent runs with `gh run list --limit 10`.
2. Capture the relevant `gh run view` details.
3. Store the summary in `samples/logs/`.

That step is part of the repository contract, not optional cleanup.
