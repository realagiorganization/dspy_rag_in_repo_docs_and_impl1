---
name: commit-history-summarizer
description: Use when the user wants commit messages or commit planning to cite relevant prior Codex CLI requests from local session history, especially for uncommitted files or mixed worktrees.
---

# Commit History Summarizer

Use this skill when commit messages should include best-effort rationale from prior Codex CLI user
requests stored in local history.

## Workflow

1. Identify the files you plan to commit.
2. Run `scripts/history_commit_context.py` with those file paths.
3. Review the suggested summaries and verbatim history excerpts.
4. Use the output to write a concise commit body that says:
   - what changed
   - why it changed
   - which prior user requests support that rationale
5. Keep verbatim excerpts short and relevant.

## Command

```bash
python3 skills/commit-history-summarizer/scripts/history_commit_context.py path/to/file1 path/to/file2
```

## Notes

- This is best-effort only. Local history may not contain the relevant request.
- The script reads `~/.codex/history.jsonl` by default.
- Prefer exact file paths plus a few `--extra-term` values for better matches.
- If no relevant history is found, write the commit body from the current diff instead of forcing a
  weak citation.
