# DSPy RAG In-Repo Research Lab

[![CI](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/workflows/ci.yml/badge.svg)](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/workflows/ci.yml)
[![Publish](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/workflows/publish.yml/badge.svg)](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/workflows/publish.yml)
[![Coverage](https://img.shields.io/badge/coverage-94.12%25-brightgreen)](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/workflows/ci.yml)

This repository is a scaffold for researching how agents can perform Retrieval-Augmented Generation (RAG) over the repository itself while reusing MCP servers found in the repository, its submodules, or its Python packages.

The build, packaging, and CI flow is standardized around Astral tooling:

- `uv` manages Python installation, dependency resolution, lockfiles, execution, builds, and publishing.
- `uv_build` provides the package build backend.
- `ruff` handles formatting and linting.

## Scope

The scaffold covers three functional requirements:

1. Notebook-first research for DSPy RAG over repository contents, with MCP server discovery hooks.
2. The same workflows exposed through Python, `make`, a Rust CLI, and BDD tests with example RAG questions.
3. A path to package tuning artifacts and deploy the tuned model behind an Azure inference endpoint.

## Repository Layout

- `notebooks/`: Jupyter notebooks for experiments and reproducible research.
- `src/repo_rag_lab/`: Python package with corpus discovery, MCP discovery, retrieval, workflow, CLI, and Azure manifest helpers.
- `rust-cli/`: Thin Rust entrypoint that delegates to the Python workflow.
- `tests/`: BDD feature and step definitions for example repository questions.
- `documentation/inspired/`: Cleaned and shortened summaries of external implementations that inform this scaffold.
- `artifacts/`: Generated outputs such as Azure deployment manifests.
- `samples/training/` and `samples/population/`: sample datasets that drive notebook experiments.
- `samples/logs/`: Post-push GitHub Actions inspection logs captured with `gh`.

## Quick Start

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --extra azure
make quality
make ask QUESTION="What does this repository research?"
```

## Workflow Surfaces

- Python CLI: `uv run repo-rag ask --question "..."`
- Python CLI with DSPy: `uv run repo-rag ask --question "..." --use-dspy`
- Utility summary: `uv run repo-rag utility-summary`
- Smoke test: `uv run repo-rag smoke-test`
- Surface verification: `uv run repo-rag verify-surfaces`
- Make: `make ask QUESTION="..."`
- Make utility summary: `make utility-summary`
- Make smoke test: `make smoke-test`
- Make surface verification: `make verify-surfaces`
- Rust CLI: `uv run cargo run --manifest-path rust-cli/Cargo.toml -- ask --question "..."`
- Notebook: `notebooks/01_repo_rag_research.ipynb`
- Training notebook: `notebooks/03_dspy_training_lab.ipynb`
- Sample population notebook: `notebooks/04_sample_population_lab.ipynb`

## Agent Guidance

Repository-local agent instructions live in `AGENTS.md`. Agents should prefer the utility entrypoints above when they cover the task, then validate changes with the repository tests.

## Post-Push Verification

After each push:

1. Inspect the latest GitHub Actions runs with `gh run list`.
2. Capture the relevant `gh run view` details.
3. Save the output under `samples/logs/`.

This repository treats that step as part of the normal push workflow rather than an optional follow-up.

## Packaging And Publishing

The repository is packaged as a standard Python project with a `src/` layout, a `repo-rag` console script, and an Astral-managed lockfile.

```bash
make build
uv run repo-rag utility-summary
```

CI publishes wheels and source distributions from Git tags that start with `v`, using GitHub trusted publishing and `uv publish`.

## Azure Deployment Path

The code does not fine-tune a model by itself. It prepares artifacts and configuration needed to move a tuned model into Azure AI Foundry / Azure OpenAI deployment workflows:

```bash
make azure-manifest MODEL_ID=my-ft-model DEPLOYMENT_NAME=repo-rag-ft
```

This writes a deployment manifest to `artifacts/azure/`.

## Quality Gates

- `make sync`: install the locked dev environment with `uv`.
- `make lock`: refresh `uv.lock`.
- `make fmt`: format Python sources with Ruff.
- `make lint-python`: Ruff formatting and linting for Python modules and notebook code cells.
- `make lint`: run the Python lint gates.
- `make typecheck`: mypy and basedpyright static analysis.
- `make verify-surfaces`: notebook structure and Makefile verification.
- `make complexity`: radon complexity threshold check.
- `make test`: pytest, doctests, and coverage reporting.
- `make coverage`: run pytest coverage and print the coverage summary.
- `make coverage-html`: generate an HTML coverage report in `htmlcov/`.
- `make rust-quality`: Rust formatting, clippy, build, and wrapper execution.
- `make quality`: run the main repository quality stack end to end.
- `make build`: build wheel and sdist with `uv build`.
- `make publish`: publish artifacts with `uv publish`.

## Git Hooks

The repository uses `pre-commit` as the managed Git hook system.

- `make hooks-install`: install repository-managed `pre-commit` and `pre-push` hooks.
- `make hooks-run`: execute all managed hooks manually.
- `make hooks-run-push`: execute the managed `pre-push` gate manually.

Hook split:

- `pre-commit`: Ruff lint and formatting checks.
- `pre-push`: mypy, pytest with coverage, and repository-surface verification.

This keeps fast feedback on commit and heavier acceptance gates on push, which fits normal Git flow better than forcing the whole stack into every commit.
