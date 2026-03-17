# Verification Loop Instructions

Use the audit files to drive verification work, not just to describe it after the fact.

## Required Loop

1. Start from the latest `docs/audit/*.md` note and identify unresolved or unverified areas.
2. Run the repository-native verification commands first:
   - `uv run python -m compileall src tests`
   - `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
   - `uv run repo-rag smoke-test`
   - `cargo build --manifest-path rust-cli/Cargo.toml` when `cargo` is available
3. If a verification category is missing, say so explicitly and treat that absence as repository state.
4. After changing tests, verification tooling, or verification documentation, update `docs/audit/*.md` in the same turn.
5. When CI evidence exists in `samples/logs/`, compare it against local results and note any mismatch.

## Reporting Rules

- Do not claim coverage, lint, UI, or integration health unless a concrete tool or suite was found and run.
- Prefer dated audit notes over memory when answering what currently passes.
- If local tooling is missing, record the exact blocker and preserve any remote CI evidence that still exists.
