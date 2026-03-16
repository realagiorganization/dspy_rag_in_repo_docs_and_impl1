# Audit Baseline Instructions

Before summarizing repository verification state:

- Read `docs/audit/README.md`.
- Read the newest dated file under `docs/audit/`.
- Distinguish between checks that are configured, checks that were actually executed in the current turn, and checks that are absent.

When writing status updates:

- Use exact commands and explicit pass/fail/blocker outcomes.
- Call out missing verification categories directly: UI, integration, coverage, lint, type checking, deployment checks.
- Prefer current local evidence, then supplement with recent CI evidence from `samples/logs/` when available.
