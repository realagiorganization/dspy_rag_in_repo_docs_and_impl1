# DSPy Training Path Audit

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Repository root: `/home/standard/dspy_rag_in_repo_docs_and_impl1_step1final`
- Git HEAD during verification: `7aca0a4ada051e4eca430d55a29c98e8fe4e1077`

## Scope

This audit captures step 1 of the repository roadmap: turning the DSPy path into a better-tested,
documented, notebook-visible compile and reload workflow, then verifying the repository-native
checks, the broad quality gate, and a live end-to-end DSPy compile plus saved-program reload.

## Executed Commands

Executed successfully in this turn:

- `make hooks-install`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag verify-surfaces`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `uv run pytest tests/test_dspy_training.py tests/test_cli_and_dspy.py tests/test_verification.py tests/test_benchmarks_and_notebook_scaffolding.py tests/test_project_surfaces.py`
- `make quality`
- `set -a; . /home/standard/dspy_rag_in_repo_docs_and_impl1/.env; set +a; uv run repo-rag dspy-train --root . --run-name step1-smoke-final --optimizer bootstrapfewshot --max-bootstrapped-demos 1 --max-labeled-demos 1`
- `set -a; . /home/standard/dspy_rag_in_repo_docs_and_impl1/.env; set +a; uv run repo-rag ask --root . --question "What does this repository research?" --use-dspy --dspy-program-path artifacts/dspy/step1-smoke-final/program.json`

## Notable Results

- `make hooks-install`: passed and refreshed the managed `pre-commit` plus `pre-push` hooks
- `uv run python -m compileall src tests`: passed
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`: passed, `8` tests
- `uv run repo-rag verify-surfaces`: passed after trimming the new notebook code cell back to the
  repository `25`-line limit
- `uv run repo-rag smoke-test`: passed with `answer_contains_repository: true`,
  `mcp_candidate_count: 1`, and `manifest_path: artifacts/azure/repo-rag-smoke.json`
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- focused DSPy and notebook-facing pytest slice: passed, `52` tests
- `make quality`: passed with `87` tests and `87%` total coverage
- live `repo-rag dspy-train` smoke: passed and wrote
  `artifacts/dspy/step1-smoke-final/program.json` plus
  `artifacts/dspy/step1-smoke-final/metadata.json`
- live `repo-rag ask --use-dspy --dspy-program-path ...`: passed and loaded the saved program

## Current Verification Status

Configured and verified in this turn:

- Compile checks: present and passed through `uv run python -m compileall src tests`
- Utility and baseline pytest slice: present and passed through
  `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- Notebook and Makefile contract verification: present and passed through
  `uv run repo-rag verify-surfaces`
- Repository smoke test: present and passed through `uv run repo-rag smoke-test`
- Rust build: present and passed through `cargo build --manifest-path rust-cli/Cargo.toml`
- Focused DSPy, notebook-scaffolding, verification, and surface tests: present and passed through
  the targeted `uv run pytest ...` slice above
- Lint, notebook lint, mypy, basedpyright, repository-surface verification, complexity, pytest,
  and coverage: present and passed through `make quality`
- Live DSPy compile and saved-program reload: present and passed through the two `.env`-backed
  `uv run repo-rag ...` commands above

Still absent or not exercised in this turn:

- UI or browser tests: none found in the repository configuration
- Full notebook execution batch: notebook lint and notebook-surface checks passed, but
  `make notebook-report` was not rerun end-to-end in this turn
- Live Azure deployment or inference tests: not rerun in this turn
- Post-push GitHub Actions evidence: not yet available before the push for this change set

## Notes

- The new DSPy tests cover LM config resolution from Azure/OpenAI env shapes, artifact path
  sanitization, paraphrase scoring in the repository answer metric, unsupported optimizer errors,
  and the runtime branches that skip or use compiled programs.
- The training notebook now stays within the playbook contract while exposing the latest compiled
  DSPy artifact for inspection or reuse when LM configuration is available in-process.
- The live `step1-smoke-final` compile succeeded, but its benchmark summary reported `0` passes
  out of `3` cases. That result confirms the next real bottleneck: retrieval quality under the
  DSPy layer, not the absence of a compile path.
