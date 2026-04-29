# Live Azure And DSPy Integration Gating

- Audit date: `2026-04-28` (`America/New_York`)
- Repository root: `/home/standard/Desktop/realagi_work/dspy_rag_in_repo_docs_and_impl1`

## Scope

This turn closes the hardening-plan gap around explicit LM-configured DSPy integration coverage by
adding a live Azure OpenAI integration test slice that is safe for local runs, safe for forks, and
ready to use repository secrets and variables inside GitHub Actions.

Changes in scope:

- add `tests/test_live_azure_integration.py`
- add a CI step that exports Azure runtime settings into that test slice
- update environment and Azure deployment docs so operators know which GitHub secret and variables
  the optional live CI path expects
- update the DSPy guide and research narrative so the repo no longer claims that real LM-configured
  DSPy coverage is absent

## Executed Commands

Executed successfully in this turn:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_live_azure_integration.py tests/test_azure_runtime.py tests/test_workflow_live.py tests/test_cli_and_dspy.py tests/test_project_surfaces.py`
- `make files-sync`
- `make exploratorium-sync`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make verify-surfaces`
- `uv run pytest tests/test_project_surfaces.py tests/test_file_summaries.py tests/test_exploratorium_translation.py`

## Results

- `uv run python -m compileall src tests`: passed
- live-Azure and related regression slice: passed, `45 passed, 3 skipped`
  - the new `tests/test_live_azure_integration.py` file skipped all three live tests locally
    because the full Azure runtime contract was not present in the local shell environment
  - the skip behavior itself is the intended local/fork-safe contract
- `make files-sync`: passed
- `make exploratorium-sync`: passed
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `make verify-surfaces`: passed with `issue_count: 0`
- post-sync generated-surface pytest slice: passed, `28 passed`

## Current Verification Status

Configured and exercised in this turn:

- live Azure OpenAI probe coverage through an env-gated pytest surface
- live Azure-backed repository answer coverage through an env-gated pytest surface
- LM-configured DSPy runtime coverage through an env-gated pytest surface
- CI wiring for the optional live Azure integration step
- documentation updates for the GitHub secret and variable contract
- generated file inventory and exploratorium regeneration
- repository surface verification

Configured but not exercised in this turn:

- an actual live network round trip, because the local shell did not contain the full Azure
  runtime contract
- `make quality`
- `make coverage`

## Notes

- The optional CI integration step now reads:
  - secret: `AZURE_OPENAI_API_KEY`
  - variables: `AZURE_OPENAI_ENDPOINT` or `AZURE_OPENAI_CHAT_COMPLETIONS_URI`
  - variable: `AZURE_OPENAI_DEPLOYMENT_NAME`
  - variable: `AZURE_OPENAI_API_VERSION`
  - optional variable: `AZURE_OPENAI_MODEL_NAME`
- The new test slice intentionally skips instead of failing when the environment is incomplete.
  That keeps fork PRs and local contributor runs green while still allowing the canonical
  repository CI to exercise the live path when secrets and variables are configured.
- This change closes the plan item about explicit LM-configured DSPy integration coverage, but it
  does not mean the repository now has a full artifact lifecycle, a generalized retriever, or
  `dataset` integration. Those remain separate open phases in the planning docs.
