---
name: file-summary-sync
description: Keep the tracked-file summary surfaces in sync across FILES.md, FILES.csv, the CLI and Makefile entrypoints, pre-commit automation, and agent guidance whenever tracked repository files or inventory expectations change.
---

# File Summary Sync

Use this skill when tracked files are added, removed, renamed, or materially repurposed, or when
`FILES.md`, `FILES.csv`, `AGENTS.md.d/FILES.md`, or the file-summary utility surfaces are in scope.

## Required Flow

1. Treat `src/repo_rag_lab/file_summaries.py` as the single source of truth for the generated file
   inventory.
2. Regenerate the inventory with `make files-sync`.
3. Keep `Makefile`, `src/repo_rag_lab/cli.py`, `src/repo_rag_lab/utilities.py`, and
   `.pre-commit-config.yaml` aligned when the sync workflow changes.
4. Keep `AGENTS.md`, `AGENTS.md.d/FILES.md`, and `README.md` aligned when the maintenance contract
   or user-facing workflow changes.
5. Update tests that validate user-visible file-summary behavior instead of hand-editing generated
   `FILES.md` or `FILES.csv`.

## Validation

- Run `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`.
- Run the targeted file-summary and surface tests you changed.
- Run `make verify-surfaces`.
- Run `make files-sync` before committing so generated inventories match the repository tree.
