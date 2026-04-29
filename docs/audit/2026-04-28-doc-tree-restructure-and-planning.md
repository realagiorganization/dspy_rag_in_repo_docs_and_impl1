# Doc Tree Restructure And Planning

- Audit date: `2026-04-28` (`America/New_York`)
- Repository root: `/home/standard/Desktop/realagi_work/dspy_rag_in_repo_docs_and_impl1`

## Scope

This turn restructures the repository documentation tree, adds execution-plan checklists for repo
hardening and `dataset` integration, updates repo-local references to the new paths, and verifies
that the repository still passes its core local surface checks afterward.

The authored documentation was moved into a single `docs/` tree with these primary buckets:

- `docs/architecture/`
- `docs/operations/`
- `docs/guides/`
- `docs/archive/`
- `docs/planning/`
- `docs/audit/`

The turn also keeps a deliberate boundary:

- active repository surfaces were updated to the new paths
- historical audit notes and historical `samples/logs/` entries were preserved as evidence and
  were not rewritten retroactively
- root-generated surfaces such as `FILES.md`, `FILES.csv`, and `TODO.MD` remain in the root for
  now because existing CLI, publication, and workflow surfaces still expect them there

## Executed Commands

Executed successfully in this turn:

- `make todo-sync`
- `make files-sync`
- `make exploratorium-sync`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `uv run repo-rag smoke-test`
- `uv run pytest tests/test_project_surfaces.py tests/test_benchmarks_and_notebook_scaffolding.py tests/test_file_summaries.py tests/test_pages_site.py tests/test_population_samples.py tests/test_retrieval.py tests/test_todo_backlog.py tests/test_workflow.py tests/test_dspy_training.py tests/test_exploratorium_translation.py`
- `uv run pytest tests/test_pages_site.py tests/test_repository_rag_bdd.py`
- `make verify-surfaces`
- `uv run repo-rag smoke-test`

## Results

- `make todo-sync`: passed
  - refreshed `TODO.MD`
  - refreshed `publication/todo-backlog-table.tex`
- `make files-sync`: passed
  - refreshed `FILES.md`
  - refreshed `FILES.csv`
- `make exploratorium-sync`: passed
  - refreshed the exploratorium generated manifest and TeX outputs
- `uv run python -m compileall src tests`: passed
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`: passed, `17 passed`
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `uv run pytest ...` on the doc-tree and path-sensitive regression slice: passed, `85 passed`
- `uv run pytest tests/test_pages_site.py tests/test_repository_rag_bdd.py`: passed, `7 passed`
- `make verify-surfaces`: passed with:
  - `checked_notebook_count: 5`
  - `issue_count: 0`
- final `uv run repo-rag smoke-test`: passed with:
  - `answer_contains_repository: true`
  - `mcp_candidate_count: 1`
  - `manifest_path: artifacts/azure/repo-rag-smoke.json`

## Current Verification Status

Configured and exercised in this turn:

- doc-tree path updates across code, tests, samples, and authored docs
- backlog regeneration
- tracked-file inventory regeneration
- exploratorium translation regeneration
- compile checks
- utility plus repository-RAG BDD pytest coverage
- Rust wrapper build
- broad path-sensitive regression coverage
- repository surface verification
- smoke-test coverage

Configured but not exercised in this turn:

- `make quality`
- `make coverage`
- live Azure endpoint probes
- notebook-by-notebook execution
- post-push GitHub Actions logging

## Notes

- Active repository surfaces no longer refer to the former `documentation/` tree. The remaining
  historical references live only in preserved evidence layers such as older audit notes and older
  `samples/logs/` entries.
- The new planning docs are:
  - `docs/planning/repo-hardening-plan.md`
  - `docs/planning/dataset-integration-plan.md`
- The hardening plan now records that `FILES.md`, `FILES.csv`, and `TODO.MD` stay in the root in
  the near term. That is an explicit compatibility decision, not leftover clutter by accident.
- This turn does not claim that the repository is already generalized for arbitrary repos or fully
  integrated with `../dataset`. It claims that the repository structure and documentation surfaces
  are now cleaner, the working plan is local and checklisted, and the existing runtime still
  verifies after the restructure.
