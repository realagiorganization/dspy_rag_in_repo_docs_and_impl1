# File Summary Instructions

Use these maintained surfaces for repository-wide file summaries:

- `FILES.md`: human-readable inventory of tracked repository files.
- `FILES.csv`: machine-readable export of the same inventory for scripts and diffs.

## Required Workflow

- Regenerate both files with `make files-sync` or `uv run repo-rag sync-file-summaries --root .`.
- Run that command after tracked file adds, removals, renames, or material role changes.
- Treat `FILES.md` and `FILES.csv` as generated outputs. Do not hand-edit them.
- Keep hooks installed with `make hooks-install`; the managed pre-commit hook
  `sync-file-summaries-pre-commit` refreshes the inventory before commit when it drifts.
- If the hook rewrites either file, restage the generated files and rerun the commit.

## Narrative Summaries

- Start repo-wide file summarization from `FILES.md` and `FILES.csv`, then use the repo-bound
  utilities such as `make utility-summary`, `make ask QUESTION="..."`, `make ask-dspy QUESTION="..."`,
  and `make ask-live QUESTION="..."` for higher-level synthesis.
- The inventory generator itself is deterministic and does not require secrets.
- If LM-backed synthesis is needed, source `.env` first without echoing values:
  `set -a; source .env; set +a`.
- Expected LM configuration comes from the existing repository environment surfaces:
  `DSPY_*`, `AZURE_OPENAI_*`, or `OPENAI_API_KEY`.
- Never print secret values from `.env`; reference variable names only.

## Maintenance Notes

- Keep this instruction file aligned with the inventory workflow whenever commands, hook behavior,
  or environment expectations change.
- If a repo-local file-summary skill is added under `.codex/skills/`, keep it aligned with this
  guide and the repo-native `make files-sync` / `repo-rag sync-file-summaries` surfaces.
- When verification or repo-health reporting is part of the task, also follow
  `repo-verification-audit-loop`.
- After each push, follow `post-push-gh-run-logging`.
