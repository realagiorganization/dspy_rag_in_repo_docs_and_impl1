# Repository Agent Instructions

Agents working in this repository should prefer repository-local utilities over ad hoc one-off commands whenever the utility already covers the task.

Additional standing instructions live in `AGENTS.md.d/*.md`. Agents should read those files before running or reporting verification work, and use the latest `docs/audit/*.md` files to anchor follow-up checks.

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
7. If a permission-gated action is interrupted or blocked, explicitly offer the user the option to make the permission permanent in Codex settings for their user or for this repository before retrying.
8. Training and sample-population notebook logic should live in modular Python helpers under `src/` and be covered by doctests or normal pytest tests.
9. Use the repository-managed `pre-commit` hooks; lightweight checks belong on `pre-commit`, while heavier checks belong on `pre-push`.

## Validation Expectations

- For Python changes, run `python3 -m compileall src tests`.
- For utility changes, run `PYTHONPATH=src python3 -m pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`.
- For quality-sensitive changes, run `make quality` from the project venv.
- For coverage-specific checks, run `make coverage`.
- After syncing the environment, run `make hooks-install` so the managed hook policy is active locally.
- If `cargo` exists, also run `cargo build --manifest-path rust-cli/Cargo.toml`.
- After pushing, run `gh run list --limit 10` and store the relevant run details in `samples/logs/`.

## Audit Files

- Review `docs/audit/README.md` and the newest dated audit note before changing or describing repository verification state.
- When verification status changes, update the relevant `docs/audit/*.md` files in the same turn so future agents inherit current evidence.

## Notebook Expectations

Notebooks in `notebooks/` should read like research playbooks:

- Use Markdown headers and subheaders to describe the goal of each step.
- Keep code cells short and tied to a specific research action.
- Reuse repository-local utilities and package APIs rather than duplicating logic inline.
- For training and corpus-population notebooks, move reusable logic into doctested Python modules instead of embedding it in notebook cells.
