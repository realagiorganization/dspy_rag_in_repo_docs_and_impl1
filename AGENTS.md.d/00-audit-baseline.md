# Audit Baseline Instructions

Before summarizing repository verification state:

- Read `docs/audit/README.md`.
- Read the newest dated audit file under `docs/audit/`.
- Separate configured checks, checks executed in the current turn, and checks that do not exist.

When writing status updates:

- Use exact commands.
- Record explicit pass, fail, or blocker outcomes.
- Call out missing verification categories directly: UI, integration, coverage, lint, type checking, and deployment checks.
- Prefer current local evidence, then add recent CI evidence from `samples/logs/` when it exists.
