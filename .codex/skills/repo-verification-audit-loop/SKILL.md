---
name: repo-verification-audit-loop
description: Use when repository verification, audit-note updates, CI parity checks, or repo health reporting are part of the task. It covers `docs/audit/*.md`, `samples/logs/*.md`, and the repo-native verification commands that should anchor status claims.
---

# Repo Verification Audit Loop

Use this skill whenever the task includes verification work or any statement about what currently passes in the repository. The goal is to anchor every claim to current evidence and update the right audit note in the same turn.

## Read First

- `AGENTS.md`
- `AGENTS.md.d/00-audit-baseline.md`
- `AGENTS.md.d/10-verification-loop.md`
- `docs/audit/README.md`
- The newest dated note under `docs/audit/`

Read recent `samples/logs/*.md` entries when CI evidence matters.

## Required Loop

1. Identify the verification categories touched by the task and which ones still do not exist in the repo.
2. Run the repository-native checks first from the repo root:
   - `uv run python -m compileall src tests`
   - `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
   - `uv run repo-rag smoke-test`
   - `cargo build --manifest-path rust-cli/Cargo.toml` when `cargo` is available
3. Add broader checks only when the change justifies them:
   - `make quality` for broad or quality-sensitive changes
   - `make coverage` when coverage status is the question
   - targeted `uv run pytest ...` for changed notebook helpers, utilities, or samples
4. Compare local evidence with recent CI logs in `samples/logs/` when those logs are relevant.
5. Update the current dated audit note, or add a newer dated note if the repository state materially changed.

## Reporting Rules

- Separate configured checks, checks executed in the current turn, and checks that do not exist.
- Use exact commands and explicit outcomes: `pass`, `fail`, or `blocked`.
- Do not claim lint, type-checking, coverage, UI, integration, notebook execution, or deployment validation unless a concrete tool or suite was found and run.
- If tooling is missing, record the exact blocker.
- Treat absent verification categories as repository state, not implied success.

## Common Triggers

- The user asks what currently passes or fails.
- The task changes CI, tests, smoke checks, verification tooling, or audit notes.
- The task changes retrieval, notebook helpers, deployment metadata, or other surfaces that should be re-audited.

## Finish

- Cite the dated audit note you used or updated.
- If you also pushed changes, immediately hand off to `post-push-gh-run-logging`.
