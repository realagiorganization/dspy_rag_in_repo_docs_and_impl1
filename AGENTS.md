# Repository Agent Instructions

Agents working in this repository should stay inside the shared `uv`-managed workflow whenever
possible. Prefer repository-local utilities over ad hoc one-off commands when the repository
already exposes the behavior through `make` or `uv run repo-rag ...`.

Additional standing instructions live in `AGENTS.md.d/*.md`. Read them before reporting
verification results, and anchor status statements to the newest file in `docs/audit/`.

## Primary Utilities

- `make utility-summary`
- `make ask QUESTION="..."`
- `make discover-mcp`
- `make smoke-test`
- `make verify-surfaces`
- `make gh-runs`
- `make gh-watch`
- `make gh-failed-logs`
- `uv run repo-rag utility-summary`
- `uv run repo-rag ask --question "..." --use-dspy`

## Working Rules

1. Start with an existing `make` target or `uv run repo-rag ...` command before inventing a new workflow.
2. Keep notebooks, tests, CLI behavior, and docs aligned around the same package helpers.
3. When changing retrieval, MCP discovery, deployment metadata, or verification behavior, update tests and notebook guidance in the same turn.
4. If adding a new user-facing utility, expose it through both the Python CLI and the `Makefile` when practical.
5. Prefer tests that validate user-visible behavior instead of only internal helpers.
6. After every push, run `make gh-runs`, then `make gh-watch`, and write a summary log into `samples/logs/`. If the watched run fails, inspect it with `make gh-failed-logs`, fix the repository, rerun local validation, and push again.
7. If a permission-gated action is blocked, explicitly offer the user the option to make that permission permanent in Codex settings before retrying.
8. Keep reusable notebook logic in `src/` with doctests or normal pytest coverage instead of embedding it in notebook cells.
9. Keep the repository fully `uv`-managed unless `uv` no longer covers a required workflow.

## Validation Expectations

- For Python changes, run `uv run python -m compileall src tests`.
- For utility changes, run `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`.
- For quality-sensitive changes, run `make quality`.
- For coverage-specific checks, run `make coverage`.
- After syncing the environment, run `make hooks-install`.
- If `cargo` exists, also run `cargo build --manifest-path rust-cli/Cargo.toml`.
- After pushing, run `make gh-runs GH_RUN_LIMIT=10`, then `make gh-watch`, and store the relevant run details in `samples/logs/`.

## Audit Files

- Review `docs/audit/README.md` and the newest dated audit note before describing repository health.
- When verification status changes, update the relevant `docs/audit/*.md` files in the same turn.

## Notebook Expectations

Notebooks in `notebooks/` should read like research playbooks:

- Use Markdown headers and subheaders to explain each step.
- Keep code cells short and tied to one research action.
- Reuse repository-local utilities and package APIs instead of duplicating logic inline.
- Move training and corpus-population logic into doctested Python modules under `src/`.
