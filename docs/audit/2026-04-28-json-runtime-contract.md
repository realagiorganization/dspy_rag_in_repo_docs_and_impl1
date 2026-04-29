# JSON Runtime Contract

- Audit date: `2026-04-28` (`America/New_York`)
- Repository root: `/home/standard/Desktop/realagi_work/dspy_rag_in_repo_docs_and_impl1`

## Scope

This turn executes the first runtime-contract step from the repo hardening plan:

- add explicit `--output json` support for `repo-rag ask`
- add explicit `--output json` support for `repo-rag ask --use-dspy`
- add explicit `--output json` support for `repo-rag ask-live`
- normalize `retrieval-eval` and `dspy-artifacts` around shared command metadata
- repair `RepoSettings.from_root()` so the active docs root is `docs/`, not the removed
  `documentation/` tree
- document the new machine-readable contract in the README, package API notes, DSPy guide, and
  research narrative

The contract added in this turn is intentionally scoped to the worker-facing CLI layer. It does
not yet claim that every CLI surface uses a shared warning/error vocabulary or that artifact
metadata is complete enough for the full `global bundle + local overlay` lifecycle.

## Executed Commands

Executed successfully in this turn:

- `make files-sync`
- `make exploratorium-sync`
- `uv run python -m compileall src tests`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `uv run pytest tests/test_cli_and_dspy.py tests/test_utilities.py tests/test_workflow.py tests/test_dspy_training.py`
- `uv run pytest tests/test_workflow.py tests/test_cli_and_dspy.py`
- `uv run pytest tests/test_workflow.py tests/test_cli_and_dspy.py tests/test_utilities.py tests/test_project_surfaces.py`
- `uv run pytest tests/test_project_surfaces.py tests/test_file_summaries.py tests/test_exploratorium_translation.py`
- `make verify-surfaces`
- `uv run repo-rag smoke-test`
- `uv run repo-rag ask --question "What does this repository research?" --output json`
- `uv run repo-rag retrieval-eval --output json --top-k-sweep 1,4`
- `uv run repo-rag dspy-artifacts --output json`

Executed and returned the expected structured failure in this turn:

- `uv run repo-rag ask --question "What does this repository research?" --use-dspy --output json`

## Results

- `make files-sync`: passed
  - refreshed `FILES.md`
  - refreshed `FILES.csv`
- `make exploratorium-sync`: passed
  - refreshed the exploratorium manifest and TeX outputs
- `uv run python -m compileall src tests`: passed
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- targeted CLI and runtime pytest slice: passed, `52 passed`
- refreshed workflow plus surface pytest slice: passed, `53 passed`
- post-sync generated-surface pytest slice: passed, `28 passed`
- `make verify-surfaces`: passed with:
  - `checked_notebook_count: 5`
  - `issue_count: 0`
- `uv run repo-rag smoke-test`: passed with:
  - `answer_contains_repository: true`
  - `mcp_candidate_count: 1`
  - `manifest_path: artifacts/azure/repo-rag-smoke.json`
- `uv run repo-rag ask --output json`: passed
  - emitted `command: "ask"`
  - emitted `command_status: "success"`
  - emitted repo-relative `sources` and serialized `context`
  - emitted `mode: "baseline"`
- `uv run repo-rag ask --use-dspy --output json`: expected structured failure without LM config
  - exit code `1`
  - emitted `command: "ask"`
  - emitted `command_status: "error"`
  - emitted `error.type: "RuntimeError"`
  - emitted the missing-DSPy-LM-config message as JSON instead of a stack trace
- `uv run repo-rag retrieval-eval --output json --top-k-sweep 1,4`: passed
  - emitted `command: "retrieval-eval"`
  - emitted `command_status: "success"`
  - emitted benchmark metrics with `status: "pass"`
- `uv run repo-rag dspy-artifacts --output json`: passed
  - emitted `command: "dspy-artifacts"`
  - emitted `command_status: "success"`
  - emitted `run_count: 0` in the current checkout

## Current Verification Status

Configured and exercised in this turn:

- compile checks for the changed Python surfaces
- Rust wrapper build
- CLI regression coverage for baseline ask, live ask, DSPy ask, retrieval eval, and DSPy artifact
  inspection
- direct runtime verification of the new JSON output surfaces
- machine-readable error handling for the DSPy ask path when LM configuration is absent
- README and package-doc surface regression coverage
- generated inventory and exploratorium regeneration
- repository surface verification
- smoke-test coverage

Configured but not exercised in this turn:

- `make quality`
- `make coverage`
- live Azure-backed `ask-live --output json`
- post-push GitHub Actions logging

## Notes

- The JSON contract uses shared top-level metadata:
  - `command`
  - `command_status`
  - `root`
- The ask-family JSON payloads now also carry:
  - `question`
  - `answer`
  - `response_text`
  - `sources`
  - `context`
  - `mcp_candidates`
  - `mode`
- The DSPy ask JSON payload additionally carries:
  - `retrieved_context`
  - `program_loaded`
  - `program_path`
  - `top_k`
- The retrieval and artifact commands now emit the same top-level command metadata instead of raw
  anonymous JSON blobs.
- The broad repository question `"What does this repository research?"` still over-ranks
  meta-docs such as the research narrative for the baseline answer path. That is not a runtime
  contract bug; it remains part of the open retrieval-generalization work in
  `docs/planning/repo-hardening-plan.md`.
