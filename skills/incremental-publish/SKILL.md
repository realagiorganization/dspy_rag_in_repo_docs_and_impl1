---
name: incremental-publish
description: Use when the user wants code changes committed and pushed in narrow increments, with validation, rationale-rich commit messages, and post-push GitHub run logging.
---

# Incremental Publish

Use this skill when the user asks to commit and push iteratively.

## Workflow

1. Inspect `git status --short --untracked-files=all`.
2. Split the worktree into narrow, coherent commit groups.
3. For each group:
   - stage only the intended files
   - run the most relevant checks
   - use `commit-history-summarizer` for commit-body rationale when useful
   - commit with a subject that states the change directly
4. Push only after the branch is in a valid state.
5. After each push:
   - run `gh run list --limit 10 --branch <branch>` when available
   - record the outcome in `samples/logs/`
   - if branch-scoped runs are absent, log that exact fact
6. Open or update a draft PR when the user wants the branch published upstream.

## Commit Rules

- Keep commits narrow.
- State both **what** changed and **why** in the commit message.
- Do not sweep unrelated user changes into the same commit.
- If a hook blocks the push, fix the issue and create a follow-up commit instead of rewriting history by default.

## Companion Skills

- `commit-history-summarizer`: use for file-aware commit rationale from local Codex history
- `session-pattern-miner`: use when the user asks what repeated workflow patterns should become skills
