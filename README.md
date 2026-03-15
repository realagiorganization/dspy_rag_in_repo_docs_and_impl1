# DSPy RAG In-Repo Research Lab

[![Python CI](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/workflows/python-ci.yml/badge.svg)](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/workflows/python-ci.yml)
[![Rust Wrapper CI](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/workflows/rust-wrapper-ci.yml/badge.svg)](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/workflows/rust-wrapper-ci.yml)

This repository is a scaffold for researching how agents can perform Retrieval-Augmented Generation (RAG) over the repository itself while reusing MCP servers found in the repository, its submodules, or its Python packages.

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
- `samples/logs/`: Post-push GitHub Actions inspection logs captured with `gh`.

## Quick Start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
make ask QUESTION="What does this repository research?"
make bdd
make rust-cli-build
```

## Workflow Surfaces

- Python CLI: `python -m repo_rag_lab.cli ask --question "..."`
- Python CLI with DSPy: `python -m repo_rag_lab.cli ask --question "..." --use-dspy`
- Utility summary: `python -m repo_rag_lab.cli utility-summary`
- Smoke test: `python -m repo_rag_lab.cli smoke-test`
- Make: `make ask QUESTION="..."`
- Make utility summary: `make utility-summary`
- Make smoke test: `make smoke-test`
- Rust CLI: `cargo run --manifest-path rust-cli/Cargo.toml -- ask --question "..."`
- Notebook: `notebooks/01_repo_rag_research.ipynb`

## Agent Guidance

Repository-local agent instructions live in `AGENTS.md`. Agents should prefer the utility entrypoints above when they cover the task, then validate changes with the repository tests.

## Post-Push Verification

After each push:

1. Inspect the latest GitHub Actions runs with `gh run list`.
2. Capture the relevant `gh run view` details.
3. Save the output under `samples/logs/`.

This repository treats that step as part of the normal push workflow rather than an optional follow-up.

## Azure Deployment Path

The code does not fine-tune a model by itself. It prepares artifacts and configuration needed to move a tuned model into Azure AI Foundry / Azure OpenAI deployment workflows:

```bash
make azure-manifest MODEL_ID=my-ft-model DEPLOYMENT_NAME=repo-rag-ft
```

This writes a deployment manifest to `artifacts/azure/`.
