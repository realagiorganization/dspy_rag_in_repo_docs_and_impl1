# File Summary Test Churn Fix

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Repository root: `/tmp/repo-logfix-step1-20260318`
- Base `origin/master`: `3c4cf29`

## Scope

This audit captures a narrow verification-tooling fix:

- make `tests/test_utilities.py::test_run_file_summary_sync_reports_expected_fields` restore
  `FILES.md` and `FILES.csv` after exercising `run_file_summary_sync(REPO_ROOT)`
- verify that the coverage path no longer leaves tracked file-inventory churn behind before a
  commit or log-only push

## Executed Commands

Executed successfully in this turn:

- `make hooks-install`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make coverage`

## Results

- `make hooks-install`: passed
- `uv run python -m compileall src tests`: passed
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`: passed, `15` tests
- `uv run repo-rag smoke-test`: passed with:
  - `answer_contains_repository: true`
  - `mcp_candidate_count: 1`
  - `manifest_path: artifacts/azure/repo-rag-smoke.json`
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `make coverage`: passed with `131` tests and `87.96%` total coverage

## Behavioral Check

The regression that mattered here was repository churn during verification. After `make coverage`
completed, `git status -sb` still reported only the intended test edit:

- `M tests/test_utilities.py`

That means the test no longer leaves `FILES.md` and `FILES.csv` modified in the worktree after it
calls the inventory sync utility.

## CI Comparison

Recent remote evidence in `samples/logs/20260318T101939Z-gh-runs-land-each-unlanded.md` shows the
latest landed `CI` run `23239808187` and `Hushwheel Quality` run `23239808138` both completed
`success` before this fix. There is no mismatch with the local checks above; this turn only changes
test isolation, not the repo's expected runtime behavior.

## Current Verification Status

Configured and exercised in this turn:

- hook installation
- Python compile checks
- focused utility and repository BDD pytest coverage
- repository smoke coverage
- Rust wrapper build
- full coverage run, including the path that previously triggered file-inventory churn

Configured but not exercised in this turn:

- `uv run repo-rag verify-surfaces`
- `make quality`
- Hushwheel fixture quality checks
- publication PDF build

Verification categories that still do not exist as explicit suites:

- UI checks
- dedicated live Azure integration tests
- full notebook batch execution gates

## Notes

- The production utility in `src/repo_rag_lab/file_summaries.py` still writes the tracked inventory
  files as designed. The fix is intentionally limited to test cleanup so repository behavior stays
  unchanged while verification becomes non-destructive.
