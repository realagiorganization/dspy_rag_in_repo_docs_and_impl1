# Rust And Benchmark Hygiene Audit

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Repository root: `/home/standard/dspy_rag_in_repo_docs_and_impl1`

## Scope

This audit covers repository-hygiene follow-up for two recurring drift points:

- the Rust wrapper lockfile policy around `rust-cli/Cargo.lock`
- the benchmark corpus filter used by notebook and training assertions as audit notes and
  `samples/logs/` continue to grow

## Changes In This Turn

- `REPO_COMPLETENESS_CHECKLIST.md` now states that `rust-cli/Cargo.lock` is committed
  intentionally so the Rust wrapper behaves like an application-style entrypoint with
  reproducible dependency resolution.
- `TODO.MD` now treats the Rust lockfile decision as established policy instead of an open
  question.
- `src/repo_rag_lab/benchmarks.py` now exposes `is_benchmark_document_path(...)` and excludes
  `docs/audit/` in addition to the existing generated and operational surfaces.
- benchmark and project-surface tests now pin the benchmark exclusion policy and the committed
  Rust lockfile policy.

## Executed Commands

Executed successfully in this turn:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_benchmarks_and_notebook_scaffolding.py tests/test_project_surfaces.py`
- `cargo build --manifest-path rust-cli/Cargo.toml`

## Results

- compile: passed
- targeted pytest: passed
- Rust wrapper build: passed

## Verification Notes

- Benchmark assertions now ignore `docs/audit/` alongside `samples/logs/`, `samples/training/`,
  `samples/population/`, `artifacts/`, and other non-corpus surfaces that would otherwise let
  retrieval tests pass against operational summaries instead of the intended repository content.
- The repository now has a documented answer for `rust-cli/Cargo.lock`: keep it committed and
  refresh it deliberately when Rust dependencies change.

## Still Absent

- UI or browser tests: none found
- Automated DSPy training compile path: not implemented
- Azure AI Inference endpoint round-trip validation: not exercised in this turn
