# Repository Agent Instructions

Agents working in this repository should prefer repository-local utilities over ad hoc one-off commands whenever the utility already covers the task.

## Primary Utilities

- `make ask QUESTION="..."`: ask a repository-grounded RAG question through the Python workflow.
- `make discover-mcp`: inspect repository, submodule, and package metadata for MCP server candidates.
- `make smoke-test`: run the repository utility smoke tests.
- `python3 -m repo_rag_lab.cli utility-summary`: print the available utility surfaces and their purpose.
- `python3 -m repo_rag_lab.cli ask --question "..." --use-dspy`: exercise the DSPy-shaped workflow when DSPy is installed.

## Working Rules

1. Start by checking whether an existing `make` target or Python CLI subcommand already covers the task.
2. Use repository-local workflows for RAG experiments so notebooks, tests, and CLIs stay aligned.
3. When changing retrieval, MCP discovery, or deployment behavior, update both tests and notebook guidance in the same turn.
4. If adding a new utility, expose it through both the Python CLI and `Makefile` when practical.
5. Prefer tests that validate user-facing behavior of the utility, not only internal helper functions.
6. After every push, inspect GitHub Actions with `gh`, then write a log file into `samples/logs/` summarizing the latest run statuses.

## Validation Expectations

- For Python changes, run `python3 -m compileall src tests`.
- For utility changes, run `PYTHONPATH=src python3 -m pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`.
- If `cargo` exists, also run `cargo build --manifest-path rust-cli/Cargo.toml`.
- After pushing, run `gh run list --limit 10` and store the relevant run details in `samples/logs/`.

## Notebook Expectations

Notebooks in `notebooks/` should read like research playbooks:

- Use Markdown headers and subheaders to describe the goal of each step.
- Keep code cells short and tied to a specific research action.
- Reuse repository-local utilities and package APIs rather than duplicating logic inline.
