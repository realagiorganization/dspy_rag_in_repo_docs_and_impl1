# Node 24 Actions Refresh

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Repository root: `/tmp/repo-land-final-20260318-v2`
- Base `origin/master`: `669e8a6`

## Scope

This audit captures the GitHub Actions maintenance pass that removes the remaining Node 20
deprecation surfaces from the repository workflows.

The change in this turn is limited to:

- refresh workflow action pins to current Node 24-capable releases
- extend workflow surface tests so the upgraded pins are enforced in-repo
- refresh the audit index and generated tracked-file inventories

## Changed Files

- `.github/workflows/ci.yml`
- `.github/workflows/hushwheel-quality.yml`
- `.github/workflows/publication-pdf.yml`
- `.github/workflows/publish.yml`
- `tests/test_project_surfaces.py`

## Executed Commands

Executed successfully in this turn:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_project_surfaces.py`
- `uv run repo-rag verify-surfaces`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make quality`
- `make files-sync`

## Results

- `uv run python -m compileall src tests`: passed
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_project_surfaces.py`:
  passed, `33` tests
- `uv run repo-rag verify-surfaces`: passed with `issue_count: 0`
- `uv run repo-rag smoke-test`: passed with:
  - `answer_contains_repository: true`
  - `mcp_candidate_count: 1`
  - `manifest_path: artifacts/azure/repo-rag-smoke.json`
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `make quality`: passed with `131` tests and `87.96%` coverage
- `make files-sync`: passed and refreshed `FILES.md` plus `FILES.csv`

## Workflow Pin State

After this refresh:

- CI uses `actions/checkout@v6` in both jobs
- CI uses `astral-sh/setup-uv@v7` in both jobs
- CI uploads `python-dist` and `coverage-report` with `actions/upload-artifact@v6`
- publish uses `actions/checkout@v6`
- publish uses `astral-sh/setup-uv@v7`
- Hushwheel quality uses `astral-sh/setup-uv@v7`
- publication PDF uses `astral-sh/setup-uv@v7`

`tests/test_project_surfaces.py` now asserts those exact workflow surfaces so future downgrades are
caught locally and in CI.

## Current Verification Status

Configured and exercised in this turn:

- Python compile checks
- focused utility, repository BDD, and workflow-surface pytest coverage
- repository surface verification
- repository smoke coverage
- Rust wrapper build
- full repository lint, notebook lint, type checks, retrieval gate, complexity, pytest, and
  coverage through `make quality`
- tracked file inventory regeneration

Not exercised in this turn:

- live Azure endpoint probes
- full notebook batch execution
- publication PDF build
- post-push GitHub Actions evidence for this refreshed workflow head

## Notes

- This is a CI-maintenance change only; no repository runtime, notebook, or retrieval behavior was
  modified.
