---
name: session-pattern-miner
description: Use when the user asks to analyze recent Codex CLI sessions, identify repeated requests or workflow patterns, and turn them into concrete follow-up tasks or skill ideas.
---

# Session Pattern Miner

Use this skill to mine local Codex CLI history for repeated requests, themes, and follow-up ideas.

## Workflow

1. Run `scripts/session_pattern_report.py`.
2. Review the repeated keywords, repeated prompts, and recent matching entries.
3. Convert the output into:
   - candidate skills
   - TODO follow-ups
   - commit rationale
   - release notes or PR notes
4. If a pattern clearly deserves automation, create or update a repo-local skill in the same turn.

## Commands

```bash
python3 skills/session-pattern-miner/scripts/session_pattern_report.py
python3 skills/session-pattern-miner/scripts/session_pattern_report.py --limit 15 --top 20
```

## Notes

- This is best-effort and depends on local `~/.codex/history.jsonl` being present.
- Prefer the recent session window first; widen only if the immediate history is too sparse.
- Use `commit-history-summarizer` when you already know the file set and need commit-body context.
