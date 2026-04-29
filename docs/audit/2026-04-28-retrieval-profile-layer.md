# Retrieval Profile Layer

- Audit date: `2026-04-28` (`America/New_York`)
- Repository root: `/home/standard/Desktop/realagi_work/dspy_rag_in_repo_docs_and_impl1`

## Scope

This turn moves the retrieval hardening work from ad hoc constants toward a reusable config layer:

- add a generic retrieval-profile module under `src/repo_rag_lab/retrieval_profile.py`
- add a repo-local override file at `config/retrieval-profile.json`
- route baseline workflow retrieval, DSPy retrieval helpers, and retrieval benchmarks through the
  same loaded profile
- preserve the existing benchmark behavior while removing repository-specific weighting from the
  core scorer implementation
- update architecture docs and planning docs so the retrieval profile becomes part of the explicit
  runtime contract

## Executed Commands

Executed successfully in this turn:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_retrieval.py tests/test_workflow.py tests/test_dspy_training.py tests/test_benchmarks_and_notebook_scaffolding.py`
- `uv run repo-rag retrieval-eval --output json --top-k-sweep 1,4`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make verify-surfaces`
- `make files-sync`
- `make exploratorium-sync`
- `make exploratorium-build`
- `make paper-build`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py tests/test_retrieval.py`
- `make quality`

## Results

- `uv run python -m compileall src tests`: passed
- retrieval-focused regression slice: passed, `44 passed`
- `uv run repo-rag retrieval-eval --output json --top-k-sweep 1,4`: passed with
  `command_status: "success"`, `pass_rate: 1.0`, and `threshold_failures: []`
- utilities plus BDD regression slice: passed, `17 passed`
- `uv run repo-rag smoke-test`: passed with `command_status: "success"`
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `make verify-surfaces`: passed with `command_status: "success"` and `issue_count: 0`
- `make files-sync`: passed
- `make exploratorium-sync`: passed
- `make exploratorium-build`: passed and rebuilt the subdocument PDF
- `make paper-build`: passed and rebuilt the publication PDF bundle
- post-sync file-summary, exploratorium, surface, and retrieval slice: passed, `37 passed`
- `make quality`: passed
  - `ruff format --check`: passed
  - `ruff check`: passed
  - `nbqa ruff notebooks`: passed
  - `mypy src tests`: passed
  - `basedpyright`: passed
  - full pytest plus coverage gate: passed, `162 passed, 3 skipped`, total coverage `85.45%`

## Current Verification Status

Configured and exercised in this turn:

- repo-local retrieval profile loading from `config/retrieval-profile.json`
- generic retrieval defaults plus repo-specific overrides
- profile-aware retrieval in baseline workflow, DSPy retrieval helpers, and retrieval benchmarks
- exclusion-aware retrieval profile support for future non-repo-specific runtimes
- synchronized file inventory, exploratorium inventory, and publication PDFs after the new tracked
  config file and new audit note landed

Configured but not exercised in this turn:

- live Azure OpenAI and LM-configured DSPy integration tests
- `make coverage`

Missing verification categories in the repository state:

- no lint result was produced in this turn
- no type-checking result was produced in this turn
- no coverage result was produced in this turn
- no `dataset` integration test exists yet

## Notes

- The retrieval benchmark suite remained stable after the profile extraction: `8/8` benchmark cases
  still passed at the default `top_k=4`.
- Repository-specific ranking tweaks no longer have to remain embedded in `src/repo_rag_lab/retrieval.py`;
  they now live in `config/retrieval-profile.json`.
- `make exploratorium-build` and `make paper-build` completed successfully. The LaTeX toolchain
  still emitted expected layout warnings such as `Underfull \hbox` and `Overfull \hbox`, but the
  build targets themselves succeeded and produced updated PDFs.
