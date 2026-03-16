# Verification Loop Instructions

Use the audit files to drive further verification work, not just describe it.

## Required Loop

1. Start from the latest `docs/audit/*.md` note and identify unresolved or unverified areas.
2. Run the repository-native verification commands first:
   - `python3 -m compileall src tests`
   - `PYTHONPATH=src python3 -m pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
   - `PYTHONPATH=src python3 -m repo_rag_lab.cli smoke-test`
   - `cargo build --manifest-path rust-cli/Cargo.toml` when `cargo` is available
3. If a verification category is missing, say so explicitly and treat that absence as repository state, not silence.
4. After changing tests, verification tooling, or verification documentation, update `docs/audit/*.md` in the same turn.
5. When CI evidence exists in `samples/logs/`, compare it against local results and note any mismatch.

## Reporting Rules

- Do not claim coverage, lint, UI, or integration health unless a concrete tool or test suite was found and run.
- Prefer dated audit notes over memory when answering "what currently passes?"
- If local tooling is missing, record the exact blocker and preserve any remote CI evidence that still exists.
