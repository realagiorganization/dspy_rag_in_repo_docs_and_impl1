# Retrieval Quality Doc Priority Audit

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Repository root: `/home/standard/repo-rag-retrieval-home`
- Base `origin/master`: `a86dc7c`

## Scope

This audit captures a retrieval-quality pass focused on full-corpus answer quality rather than DSPy
plumbing. The change set does three things together:

- demote meta and synthetic repo surfaces such as tests, training samples, audits, generated
  inventories, and summary overlays during live retrieval
- add light lexical normalization and doc-seeking / code-seeking path heuristics so primary docs,
  source files, and headers win more often on "which file explains..." style questions
- tighten the fairness-filtered benchmark corpus so repo-meta overlays such as `README.AGENTS.md`,
  `FILES.md`, `env.md`, `TODO.MD`, `todo-backlog.yaml`, `AGENTS.md.d/`, and generated
  exploratorium manifests do not contaminate the benchmark loop

The user-visible regression guard for this work is now the full-corpus retrieval test slice in
`tests/test_retrieval.py`, which asserts that the tracked repository questions do not route through
test files, training samples, audit notes, or generated meta surfaces in the top four hits.

## Executed Commands

Executed successfully in this turn:

- `TMPDIR=/home/standard/.tmp uv run python -m compileall src tests`
- `TMPDIR=/home/standard/.tmp uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `TMPDIR=/home/standard/.tmp uv run pytest tests/test_retrieval.py`
- `TMPDIR=/home/standard/.tmp uv run pytest tests/test_retrieval.py tests/test_benchmarks_and_notebook_scaffolding.py`
- `TMPDIR=/home/standard/.tmp uv run repo-rag smoke-test`
- `TMPDIR=/home/standard/.tmp uv run repo-rag retrieval-eval --root . --top-k 4 --top-k-sweep 1,2,4,8 --minimum-pass-rate 1.0 --minimum-source-recall 1.0`
- `TMPDIR=/home/standard/.tmp make hooks-install`
- `TMPDIR=/home/standard/.tmp make verify-surfaces`
- `TMPDIR=/home/standard/.tmp CARGO_TARGET_DIR=/home/standard/.cargo-target/repo-rag-retrieval-home cargo build --manifest-path rust-cli/Cargo.toml`
- `TMPDIR=/home/standard/.tmp make quality`

## Results

- `uv run python -m compileall src tests`: passed
- focused utility + repository BDD slice: passed, `15` tests
- retrieval regression slice: passed, `7` tests
- retrieval + benchmark/notebook scaffold slice: passed, `19` tests
- `uv run repo-rag smoke-test`: passed with
  - `answer_contains_repository: true`
  - `mcp_candidate_count: 1`
  - `manifest_path: artifacts/azure/repo-rag-smoke.json`
- strict retrieval gate: passed with
  - `pass_rate: 1.0`
  - `average_source_recall: 1.0`
  - `threshold_failures: []`
- `make hooks-install`: passed
- `make verify-surfaces`: passed with `issue_count: 0`
- Rust wrapper build: passed after moving both `TMPDIR` and `CARGO_TARGET_DIR` off `/tmp`
- `make quality`: passed with `133` tests and `88.17%` total coverage

## Notes

- The host had `/tmp` at `100%` usage during this turn. An initial Rust build attempt failed for
  that reason, not because of a source regression. Re-running with `TMPDIR=/home/standard/.tmp`
  and `CARGO_TARGET_DIR=/home/standard/.cargo-target/repo-rag-retrieval-home` passed cleanly.
- The retrieval benchmark gate remains strict on pass rate and average source recall. This turn did
  not change those thresholds; it improved the live full-corpus ranking behavior and documented the
  narrower benchmark corpus contract.
- Not exercised in this turn: live Azure endpoint probes, notebook batch execution, publication PDF
  build, and post-push GitHub Actions evidence.
