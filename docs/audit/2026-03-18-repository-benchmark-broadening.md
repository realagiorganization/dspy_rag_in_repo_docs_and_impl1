# Repository Benchmark Broadening Audit

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Repository root: `/tmp/repo-benchmark-broaden-D0oBUc`
- Verification branch: `benchmark-broaden-2`

## Scope

This audit captures an expansion of the repository retrieval benchmark set from the original
three-case starter suite to an eight-case suite. The new checked-in examples now cover package API
notes, Azure AI Inference runtime guidance, MCP discovery notes, notebook execution/reporting, and
publication build guidance in addition to the existing repo-overview, inspired-docs, and
agent-utility questions. The notebook snapshots that present the benchmark suite were refreshed in
the same turn so the checked-in playbooks reflect the broader coverage.

## Executed Commands

Executed successfully in this turn:

- `make hooks-install`
- `uv run repo-rag retrieval-eval --root . --top-k 4 --top-k-sweep 1,2,4,8`
- `uv run pytest tests/test_training_samples.py tests/test_benchmarks_and_notebook_scaffolding.py tests/test_utilities.py tests/test_cli_and_dspy.py`
- `uv run jupyter nbconvert --to notebook --execute --inplace notebooks/02_agent_workflow_checklist.ipynb`
- `uv run jupyter nbconvert --to notebook --execute --inplace notebooks/03_dspy_training_lab.ipynb`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make quality`

## Notable Results

- `uv run repo-rag retrieval-eval --root . --top-k 4 --top-k-sweep 1,2,4,8`: passed and reported
  - `benchmark_count: 8`
  - `default_top_k: 4`
  - `pass_rate: 1.0`
  - `fully_covered_rate: 1.0`
  - `average_source_recall: 1.0`
  - `average_source_precision: 0.46875`
  - `average_reciprocal_rank: 1.0`
  - `best_pass_rate_top_k: 4`
- Focused benchmark/training/utility/CLI pytest slice: passed, `36` tests
- `uv run jupyter nbconvert --to notebook --execute --inplace notebooks/02_agent_workflow_checklist.ipynb`: passed
- `uv run jupyter nbconvert --to notebook --execute --inplace notebooks/03_dspy_training_lab.ipynb`: passed
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `make quality`: passed with `119` tests and `87.98%` total coverage

## Current Verification Status

Configured and verified in this turn:

- Expanded repository training-sample benchmark suite: present and passing through
  `uv run repo-rag retrieval-eval --root . --top-k 4 --top-k-sweep 1,2,4,8`
- Training-sample, benchmark, utility, and CLI tests: present and passing through the focused
  `uv run pytest ...` slice above
- Notebook snapshots for the benchmark-driven agent and training playbooks: present and refreshed
  through the two `uv run jupyter nbconvert --execute --inplace ...` commands above
- Rust wrapper build: present and passing through `cargo build --manifest-path rust-cli/Cargo.toml`
- Full Python quality gate: present and passing through `make quality`

Still absent or not exercised in this turn:

- Full notebook batch execution across all tracked notebooks: not rerun in this turn
- Live Azure OpenAI or Azure AI Inference probes: not rerun in this turn
- Post-push GitHub Actions evidence: not yet available before the push for this change set

## Notes

- The repository benchmark file `samples/training/repository_training_examples.yaml` now acts as a
  broader regression surface instead of a minimal starter trio.
- The new benchmark examples intentionally target repo surfaces that the current lexical retriever
  already ranks consistently at `top_k=4`, so the suite expands coverage without introducing
  synthetic red failures.
- `notebooks/02_agent_workflow_checklist.ipynb` and
  `notebooks/03_dspy_training_lab.ipynb` were re-executed so their checked-in outputs now show the
  eight-case suite instead of the earlier three-case snapshot.
