# Node 24 Actions Opt-In

- Audit date: `2026-03-19` (`Asia/Tbilisi`)
- Repository root: `/home/standard/dspy_rag_in_repo_docs_and_impl1`
- Base `master` before this turn: `fc36b20`

## Scope

This turn addresses the remaining GitHub Actions Node.js 20 deprecation warnings that were still
visible after the public Pages and workflow-repair push sequence.

- opted the Pages, publication, and hushwheel workflows into GitHub's Node 24 JavaScript-action
  runtime using `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`
- added workflow-surface assertions so the Node 24 opt-in remains part of the committed workflow
  contract

## Executed Commands

Executed successfully in this turn:

- `uv run pytest tests/test_project_surfaces.py`
- `make verify-surfaces`

## Results

- `uv run pytest tests/test_project_surfaces.py`: passed, `20 passed`
- `make verify-surfaces`: passed with:
  - `checked_notebook_count: 5`
  - `issue_count: 0`
- updated workflow surfaces:
  - `.github/workflows/pages.yml`
  - `.github/workflows/publication-pdf.yml`
  - `.github/workflows/hushwheel-quality.yml`
- updated workflow-surface regression coverage:
  - `tests/test_project_surfaces.py`

## Current Verification Status

Configured and exercised in this turn:

- workflow-surface pytest coverage
- repository surface verification
- Node 24 opt-in for the workflows that previously emitted Node.js 20 deprecation warnings

Configured but not exercised in this turn:

- post-push GitHub Actions confirmation for the upcoming workflow updates

Absent or not exercised in this turn:

- notebook-by-notebook execution outside `make verify-surfaces`
- live Azure endpoint probes

## Notes

- This turn follows GitHub's current deprecation guidance for JavaScript actions on runners: opt
  workflows into Node 24 before GitHub flips the default runtime.
- Post-push `gh` evidence belongs in `samples/logs/` after the branch update completes.
