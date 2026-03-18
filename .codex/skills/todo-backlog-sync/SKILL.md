---
name: todo-backlog-sync
description: Keep the repository backlog in sync across todo-backlog.yaml, TODO.MD, the publication PDF include, and backlog-facing workflow docs whenever TODOs or roadmap summaries change.
---

# Todo Backlog Sync

Use this skill when the task touches repository TODOs, backlog summaries, the publication backlog
table, or any workflow that regenerates those surfaces.

## Required Flow

1. Treat `todo-backlog.yaml` as the single editable source of truth.
2. Regenerate the derived surfaces with `make todo-sync`.
3. If the publication surface is in scope, run `make paper-build` so the committed PDF and banner
   match the latest backlog table.
4. Keep `README.md`, `utilities/README.md`, `publication/README.md`, and `AGENTS.md` aligned when
   the workflow or utility surface changes.
5. Keep the publication workflow able to rebuild the table from source instead of relying on stale
   committed output.

## Validation

- Run `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`.
- Run any targeted backlog, CLI, or publication surface tests you changed.
- Run `make verify-surfaces`.
- Run `make paper-build` when the publication table or article changed.
- Update the latest `docs/audit/*.md` note when verification status changes.
