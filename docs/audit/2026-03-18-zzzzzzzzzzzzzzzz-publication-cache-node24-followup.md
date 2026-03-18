# Publication Cache Node 24 Follow-Up

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Repository root: `/tmp/repo-land-final-20260318-v2`
- Base `origin/master`: `3c4cf29`

## Scope

This audit captures the narrow follow-up after the first Node 24 workflow refresh landed.

The previous head passed all workflows, but the `Publication PDF` run still emitted a Node 20
deprecation warning from `actions/cache@v4` in the LaTeX auxiliary cache step.

This turn only:

- upgrades the publication cache step from `actions/cache@v4` to `actions/cache@v5`
- updates workflow surface tests so the cache action version is enforced locally
- refreshes the audit index and tracked-file inventories

## Prior Post-Push Evidence

Observed on the already-pushed `3c4cf29` head:

- `CI` run `23244329208`: `success`
- `Hushwheel Quality` run `23244329179`: `success`
- `Publication PDF` run `23244329234`: `success`

Residual warning from that `Publication PDF` run:

- `actions/cache@v4` still reported the Node 20 deprecation notice

Non-fatal operational warning also observed:

- `setup-uv` cache reservation contention in concurrent jobs

## Executed Commands

Executed successfully in this turn:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_project_surfaces.py`
- `uv run repo-rag verify-surfaces`
- `make quality`
- `make files-sync`

## Results

- `uv run python -m compileall src tests`: passed
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_project_surfaces.py`:
  passed, `33` tests
- `uv run repo-rag verify-surfaces`: passed with `issue_count: 0`
- `make quality`: passed with `131` tests and `87.96%` coverage
- `make files-sync`: passed and refreshed `FILES.md` plus `FILES.csv`

## Workflow Pin State

After this follow-up:

- publication PDF uses `actions/cache@v5` for the LaTeX auxiliary cache
- publication PDF continues to use `actions/checkout@v6`
- publication PDF continues to use `astral-sh/setup-uv@v7`
- publication PDF continues to use `actions/upload-artifact@v6`

`tests/test_project_surfaces.py` now asserts the cache pin at `actions/cache@v5`.

## Current Verification Status

Configured and exercised in this turn:

- Python compile checks
- focused utility, repository BDD, and workflow-surface pytest coverage
- repository surface verification
- full repository lint, notebook lint, type checks, retrieval gate, complexity, pytest, and
  coverage through `make quality`
- tracked file inventory regeneration

Not exercised in this turn:

- live Azure endpoint probes
- full notebook batch execution
- Rust build
- repository smoke coverage
- post-push GitHub Actions evidence for the `actions/cache@v5` follow-up head

## Notes

- This follow-up is limited to the remaining publication workflow deprecation warning. No runtime or
  retrieval behavior changed.
