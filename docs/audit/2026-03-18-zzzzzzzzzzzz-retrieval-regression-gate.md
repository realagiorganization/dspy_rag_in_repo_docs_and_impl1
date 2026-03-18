# Retrieval Regression Gate Audit

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Repository root: `/tmp/repo-retrieval-gate-eFWeTo`
- Verification branch: `retrieval-gate-20260318130809`

## Scope

This audit captures the change that turns repository retrieval evaluation from an informational
report into a shared regression gate. The same threshold-aware `retrieval-eval` surface now backs:

- `make quality`
- the managed pre-push hook
- the GitHub Actions `CI` workflow

The enforced defaults are intentionally simple and strict for the checked-in benchmark corpus:

- `minimum_pass_rate=1.0`
- `minimum_source_recall=1.0`

## Implemented Surfaces

- `src/repo_rag_lab/benchmarks.py` now exposes shared threshold helpers for pass rate and average
  source recall.
- `src/repo_rag_lab/utilities.py` serializes threshold configuration, failures, and overall status
  in `run_retrieval_evaluation(...)`.
- `src/repo_rag_lab/cli.py` now accepts `--minimum-pass-rate` and
  `--minimum-source-recall`, and exits nonzero when threshold failures are present.
- `Makefile` now sets repository defaults for those thresholds and makes `retrieval-eval` part of
  `make quality`.
- `.pre-commit-config.yaml` now adds a dedicated pre-push retrieval benchmark gate.
- `.github/workflows/ci.yml` now runs `make retrieval-eval` as an explicit CI step.

## Executed Commands

Executed successfully in this turn:

- `make hooks-install`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_benchmarks_and_notebook_scaffolding.py tests/test_utilities.py tests/test_cli_and_dspy.py tests/test_project_surfaces.py`
- `uv run repo-rag retrieval-eval --root . --top-k 4 --top-k-sweep 1,2,4,8 --minimum-pass-rate 1.0 --minimum-source-recall 1.0`
- `uv run repo-rag retrieval-eval --root . --top-k 4 --top-k-sweep 1,2,4,8 --minimum-pass-rate 1.1 --minimum-source-recall 1.1`
- `make quality`
- `cargo build --manifest-path rust-cli/Cargo.toml`

## Results

- threshold-aware focused pytest slice: passed, `54 passed`
- threshold-aware passing retrieval evaluation: passed and reported
  - `benchmark_count: 8`
  - `pass_rate: 1.0`
  - `average_source_recall: 1.0`
  - `threshold_failures: []`
  - `status: "pass"`
- threshold-aware failing retrieval evaluation: failed intentionally with exit status `1` and
  reported both threshold failures when configured above the current benchmark metrics
- `make quality`: passed with the retrieval gate included, `124 passed`, `88.02%` total coverage
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed

## Notes

- The gate is strict because the current checked-in benchmark suite already achieves full pass rate
  and full source recall at the repository default `top_k=4`.
- The CLI still supports ad hoc informational runs by omitting the threshold flags directly, while
  the repo-local `Makefile`, hook, and CI surfaces keep the stricter contract.
