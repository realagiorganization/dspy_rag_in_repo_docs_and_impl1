# Commit And Push Instructions

When the user asks for repository publishing work:

- Commit in narrow increments rather than batching unrelated changes together.
- Use commit subjects that state the main change directly.
- Add a commit body when practical so the rationale is visible in Git history.
- If local Codex history is available and the user asked for context-aware commit messages, use the
  repository skill at `skills/commit-history-summarizer/` as a best-effort source of prior user
  requests.
- After each push, inspect `gh run list` and record the observed status in `samples/logs/`.
