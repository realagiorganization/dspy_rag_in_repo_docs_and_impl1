---
name: quality-surface-hardening
description: Use when the user wants a feature hardened with BDD scenarios, stricter verification, coverage reporting, CI artifacts, and README or PR-visible quality signals.
---

# Quality Surface Hardening

Use this skill when a feature needs more than an implementation patch and should be turned into a
well-verified surface.

## Workflow

1. Identify the user-facing surface:
   - CLI
   - BDD flow
   - HTTP/UI output
   - notebook or documentation contract
2. Add or tighten tests in this order:
   - direct unit/integration tests
   - BDD scenario coverage when the behavior maps to user actions
   - smoke coverage for the repository-native entrypoint
3. Tighten verification only where the repo can actually enforce it:
   - lint
   - type checks
   - coverage
   - repository-surface verification
4. Update the user-visible quality signals:
   - README workflow badges when relevant
   - PR body validation notes
   - `docs/audit/*.md`
5. After push, log the observed GitHub Actions state in `samples/logs/`.

## Repository-Specific Commands

```bash
python3 -m compileall src tests
UV_CACHE_DIR=.uv-cache uv run pytest
UV_CACHE_DIR=.uv-cache uv run repo-rag smoke-test
UV_CACHE_DIR=.uv-cache uv run repo-rag verify-surfaces
```

## Rules

- Prefer user-facing tests over helper-only tests.
- Do not claim browser, integration, or deployment coverage unless an actual runnable surface exists.
- If you add stricter CI or lint rules, make sure the local path to satisfy them is also documented.
- When the user asks for “more strict checks,” ensure the README or audit notes reflect what is now
  blocking.
