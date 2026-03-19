# DSPy Backlog Reconciliation

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Verification worktree: `/tmp/dspy-rag-dspy-train-finish`
- Audit anchor before this turn: `2026-03-18-zzzzzzzzzzzzzz-node24-actions-refresh.md`

## Scope

This audit records a repository-state correction rather than a new DSPy runtime feature. The
repository already had the DSPy compile, artifact, reuse, and notebook surfaces established by the
earlier `2026-03-18-dspy-training-path.md` and
`2026-03-18-zzzzzz-dspy-pipeline-and-live-azure-proof.md` notes, but the generated backlog still
advertised that training path as missing.

This turn removes the stale DSPy TODO rows, regenerates the published backlog surfaces, and adds
tests that pin the corrected state.

## Executed Commands

Executed successfully in this turn:

- `make todo-sync`
- `make hooks-install`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_todo_backlog.py tests/test_project_surfaces.py`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag verify-surfaces`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make files-sync`
- `make quality`

## Results

- `make todo-sync`: passed and regenerated `TODO.MD` plus
  `publication/todo-backlog-table.tex` with `11` active backlog rows
- `make hooks-install`: passed
- `uv run python -m compileall src tests`: passed
- `uv run pytest tests/test_todo_backlog.py tests/test_project_surfaces.py`: passed, `23` tests
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`: passed, `15` tests
- `uv run repo-rag verify-surfaces`: passed with `issue_count: 0`
- `uv run repo-rag smoke-test`: passed with `answer_contains_repository: true`,
  `mcp_candidate_count: 1`, and `manifest_path: artifacts/azure/repo-rag-smoke.json`
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `make files-sync`: passed and refreshed `FILES.md` plus `FILES.csv`
- `make quality`: passed with `131` tests and `87.96%` total coverage

## Current Verification Status

Configured and exercised in this turn:

- backlog source-to-surface sync through `make todo-sync`
- targeted backlog and project-surface regression tests
- compile checks
- utility and BDD pytest slice
- repository surface verification
- smoke test
- Rust build
- full quality gate

Not rerun in this turn:

- live DSPy compile against a configured LM
- live Azure probe commands
- notebook batch execution
- publication PDF build

## Notes

- The practical correction here is that the repository no longer lists the DSPy training path, the
  DSPy CLI runtime path, or the DSPy training notebook flow as open TODO items. Those surfaces are
  already implemented and separately evidenced by prior audits.
- With that stale backlog removed, the first active TODO is now retrieval quality beyond the
  lexical baseline, which matches the current DSPy guide narrative in `README.DSPY.MD`.
