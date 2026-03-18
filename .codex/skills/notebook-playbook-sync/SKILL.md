---
name: notebook-playbook-sync
description: Use when editing notebooks, notebook-facing docs, notebook scaffolding, or training and sample-population helpers in this repository. It keeps `notebooks/`, `src/repo_rag_lab/*notebook*`, assertions, tests, and user-facing guidance aligned.
---

# Notebook Playbook Sync

Use this skill when changing notebook playbooks or the Python helpers that notebooks call. The goal is to keep notebooks thin, reusable logic under `src/`, and notebook-facing tests and docs consistent.

## Trigger Conditions

- Edits under `notebooks/`
- Edits to `src/repo_rag_lab/notebook_scaffolding.py`, `src/repo_rag_lab/notebook_support.py`, or `src/repo_rag_lab/benchmarks.py`
- Changes to notebook-facing docs, training samples, population samples, or retrieval playbooks

## Rules

- Keep reusable logic in Python modules under `src/`; notebooks should orchestrate and explain, not duplicate implementation.
- Preserve the research-playbook style:
  - clear Markdown headers and subheaders
  - short code cells tied to one research action
  - repository-local utilities and package APIs instead of inline duplicates
  - explicit assertions and logging near the end of notebook flows
- Preserve notebook metadata and cell IDs when practical.
- When notebook behavior changes, update the paired tests and docs in the same turn.

## Sync Checklist

1. Update the helper modules under `src/`.
2. Update the notebook or notebooks that call them.
3. Update notebook-facing tests.
4. Update docs or audit notes if user-visible notebook expectations changed.
5. Run notebook-relevant validation:
   - `make verify-surfaces`
   - targeted `uv run pytest ...` for notebook scaffolding, benchmarks, or project surfaces
   - `make quality` when the change is broad or user-facing

## Common Files

- `notebooks/`
- `src/repo_rag_lab/notebook_scaffolding.py`
- `src/repo_rag_lab/notebook_support.py`
- `src/repo_rag_lab/benchmarks.py`
- `tests/test_benchmarks_and_notebook_scaffolding.py`
- `tests/test_project_surfaces.py`
- `samples/training/`
- `samples/population/`
