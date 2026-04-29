# CLI Envelope Normalization

- Audit date: `2026-04-28` (`America/New_York`)
- Repository root: `/home/standard/Desktop/realagi_work/dspy_rag_in_repo_docs_and_impl1`

## Scope

This turn closes the next hardening-plan block after the initial JSON contract work:

- normalize `success`, `fail`, and `error` behavior across the JSON-producing CLI surfaces
- add shared `warnings` and `artifact_metadata` fields to the command envelope
- expose first-pass artifact metadata for retrieval, DSPy artifact inspection, notebook runs, sync
  commands, probes, and smoke checks
- document the resulting worker-facing contract in the architecture and planning docs

## Executed Commands

Executed successfully in this turn:

- `uv run python -m compileall src tests`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `uv run pytest tests/test_utilities.py tests/test_cli_and_dspy.py tests/test_workflow.py tests/test_project_surfaces.py`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `make verify-surfaces`
- `uv run repo-rag retrieval-eval --output json --top-k-sweep 1,4`
- `uv run repo-rag dspy-artifacts --output json`

Executed successfully after documentation and inventory updates:

- `make files-sync`
- `make exploratorium-sync`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

## Results

- `uv run python -m compileall src tests`: passed
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- CLI/utilities/workflow/surface regression slice: passed, `53 passed`
- utilities plus BDD regression slice: passed, `17 passed`
- `uv run repo-rag smoke-test`: passed with `command_status: "success"`
- `make verify-surfaces`: passed with `command_status: "success"` and `issue_count: 0`
- `uv run repo-rag retrieval-eval --output json --top-k-sweep 1,4`: passed with
  `command_status: "success"` and `threshold_failures: []`
- `uv run repo-rag dspy-artifacts --output json`: passed with `command_status: "success"` and
  warning `No saved DSPy runs are available yet.`
- `make files-sync`: passed
- `make exploratorium-sync`: passed
- post-sync generated-surface pytest slice: passed, `28 passed`

## Current Contract Status

Configured and exercised in this turn:

- shared command envelope fields:
  - `command`
  - `command_status`
  - `root`
  - `warnings`
  - `artifact_metadata`
- `artifact_metadata` subfields:
  - `input_paths`
  - `generated_paths`
  - `related_paths`
- threshold-aware `command_status: "fail"` behavior for retrieval evaluation
- issue-aware `command_status: "fail"` behavior for repository-surface verification
- failure-aware `command_status: "fail"` behavior for notebook batch execution
- structured `command_status: "error"` behavior for JSON CLI exception paths
- first-pass worker-facing artifact handoff metadata for retrieval and DSPy-related surfaces

Configured but not exercised in this turn:

- the env-gated live Azure OpenAI integration tests introduced in the earlier audit note
- `make quality`
- `make coverage`
- a successful `dspy-train` run with live LM credentials in the local shell

Missing verification categories in the repository state:

- no lint result was produced in this turn
- no type-checking result was produced in this turn
- no coverage result was produced in this turn
- no UI validation exists
- no `dataset` integration test exists yet

## Notes

- The normalized envelope is now broad enough to support the next `dataset`-side decision work:
  minimal worker inputs and outputs can refer to `warnings` and `artifact_metadata` instead of
  scraping individual commands.
- The envelope work does not solve retrieval generalization, bundle/overlay lifecycle, or worker
  trace upload. Those remain open phases in the planning documents.
- `dspy-artifacts` currently returns a warning rather than a failure when no saved compiled runs
  exist. That is intentional because an empty artifact catalog is valid repository state.
