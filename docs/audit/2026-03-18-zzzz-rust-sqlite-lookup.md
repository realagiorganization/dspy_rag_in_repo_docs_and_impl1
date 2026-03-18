# Rust SQLite Lookup And Retrieval Tag Audit

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Repository root: `/home/standard/dspy_rag_in_repo_docs_and_impl1_continue`
- Git HEAD during final verification: `4c635c712f2143a91da756dd0568e02674acb2ac`

## Scope

This audit records two follow-up changes on top of the upstream repository-benchmark broadening
that landed on `origin/master` in the same session:

- the repository benchmark summaries now expose per-tag rollups and exclude repo-local `.codex`
  skill surfaces from the benchmark corpus
- the Rust wrapper now exposes a SQLite `index` / `lookup` path so agents can do cheap tracked-file
  discovery before escalating to DSPy-backed synthesis

## Executed Commands

Executed successfully in this turn:

- `make hooks-install`
- `uv run python -m compileall src tests`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make rust-lookup-index`
- `make rust-lookup QUERY='dspy training'`
- `uv run pytest tests/test_utilities.py tests/test_project_surfaces.py tests/test_cli_and_dspy.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `uv run repo-rag verify-surfaces`
- `uv run repo-rag retrieval-eval --root . --top-k 4 --top-k-sweep 1,2,4,8`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `make quality`

Observed and then corrected in this turn:

- `make rust-lookup QUERY='dspy training'` failed with `failed to initialize SQLite schema:
  database is locked` when it was launched in parallel with `make rust-lookup-index`. The
  serialized rerun above passed, which is the supported workflow.

## Notable Results

- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `make rust-lookup-index`: passed and wrote
  `artifacts/sqlite/repo-file-index.sqlite3` with `indexed=204`, `skipped_binary=3`,
  `skipped_large=2`
- `make rust-lookup QUERY='dspy training'`: passed; the top ranked hits were
  `src/repo_rag_lab/notebook_scaffolding.py`, `README.DSPY.MD`,
  `src/repo_rag_lab/training_samples.py`, and `src/repo_rag_lab/dspy_training.py`
- `uv run pytest tests/test_utilities.py tests/test_project_surfaces.py tests/test_cli_and_dspy.py tests/test_repository_rag_bdd.py`:
  passed, `39` tests
- `uv run repo-rag smoke-test`: passed with `answer_contains_repository: true`,
  `mcp_candidate_count: 1`, and `manifest_path: artifacts/azure/repo-rag-smoke.json`
- `uv run repo-rag verify-surfaces`: passed with `issue_count: 0`
- `uv run repo-rag retrieval-eval --root . --top-k 4 --top-k-sweep 1,2,4,8`: passed and
  reported:
  - `benchmark_count: 8`
  - default `top_k: 4`
  - `pass_rate: 1.0`
  - `fully_covered_rate: 1.0`
  - `average_source_recall: 1.0`
  - `average_source_precision: 0.46875`
  - `average_reciprocal_rank: 1.0`
  - `best_pass_rate_top_k: 4`
  - non-empty `tag_summaries` for benchmark tags such as `agents`, `api`, `azure`, `docs`,
    `notebooks`, `publication`, `rag`, and `utilities`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`: passed, `13` tests
- `make quality`: passed with `120` tests and `88.02%` total coverage

## Current Verification Status

Configured and verified in this turn:

- Compile checks: present and passed through `uv run python -m compileall src tests`
- Rust wrapper build: present and passed through `cargo build --manifest-path rust-cli/Cargo.toml`
- Rust SQLite index and lookup path: present and passed through `make rust-lookup-index` and the
  serialized `make rust-lookup QUERY='dspy training'`
- Utility, project-surface, CLI, and BDD pytest coverage for the changed user-facing surfaces:
  present and passed through the targeted `uv run pytest ...` slice above
- Repository smoke test: present and passed through `uv run repo-rag smoke-test`
- Repository-surface verification: present and passed through `uv run repo-rag verify-surfaces`
- Retrieval-quality evaluation utility: present and passed through
  `uv run repo-rag retrieval-eval --root . --top-k 4 --top-k-sweep 1,2,4,8`
- Baseline utility and BDD pytest slice: present and passed through
  `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- Full repository quality gate: present and passed through `make quality`

Still absent or not exercised in this turn:

- UI or browser tests: none found in repository configuration
- Full notebook batch execution: notebook lint and surface checks passed through `make quality`,
  but `make notebook-report` was not rerun end-to-end in this turn
- Live Azure OpenAI and Azure AI Inference probes: not rerun in this turn
- Post-push GitHub Actions evidence: not yet available before the push for this change set

## Notes

- The upstream broadened benchmark corpus from `origin/master` was kept intact in this turn; the
  local retrieval change is the reporting layer around it, not a replacement of those 8 training
  examples.
- `src/repo_rag_lab/benchmarks.py` now excludes `.codex` from the benchmark corpus so repo-local
  skill instructions do not inflate retrieval-eval results.
- `summarize_benchmark_results(...)` now includes `tag_summaries`, which flow through the CLI,
  utility helpers, and notebook scaffolding without changing the answer-generation path itself.
- The Rust lookup path is intentionally lightweight and local-first: it builds an ignored SQLite
  FTS index over tracked UTF-8 files and prints ranked path/snippet hits before any DSPy step.
