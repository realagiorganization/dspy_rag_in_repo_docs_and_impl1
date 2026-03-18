---
name: exploratorium-translation-sync
description: Keep the bilingual exploratorium translation surfaces in sync across the inventory generator, the publication subdocument, file and link summaries, and fetch-state reporting whenever repository documentation, bibliography, or publication summaries change.
---

# Exploratorium Translation Sync

Use this skill when the task touches bilingual repository summaries, fetch-state reporting for
referenced papers or documentation, the `publication/exploratorium_translation/` subdocument, or
the generator that inventories files and explicit URLs.

## Required Flow

1. Treat `src/repo_rag_lab/exploratorium_translation.py` as the single source of truth for the
   generated inventory and bilingual wording rules.
2. Regenerate the generated assets with `make exploratorium-sync`.
3. If the publication surface is in scope, run `make exploratorium-build` and then `make paper-build`
   so the committed PDFs match the generated inventory.
4. Keep `README.md`, `publication/README.md`, `AGENTS.md`, and workflow triggers aligned when the
   exploratorium surface or its maintenance contract changes.
5. When new summary categories or translation rules appear, update both English and Russian
   templates in the generator instead of hand-editing generated `.tex` or `.json` files.

## Validation

- Run `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`.
- Run the targeted exploratorium tests you changed.
- Run `make verify-surfaces`.
- Run `make exploratorium-build` when the subdocument or generator changed.
- Run `make paper-build` when the publication bundle changed.
- Update the latest `docs/audit/*.md` note when verification status changes.
