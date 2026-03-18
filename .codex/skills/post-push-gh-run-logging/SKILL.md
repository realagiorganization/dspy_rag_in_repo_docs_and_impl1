---
name: post-push-gh-run-logging
description: Use immediately after every push and when triaging GitHub Actions failures in this repository. It covers `make gh-runs`, `make gh-watch`, `make gh-failed-logs`, and writing timestamped `samples/logs/*.md` summaries without creating recursive log-only churn.
---

# Post Push Gh Run Logging

Use this skill as soon as a push completes or when the task is to inspect or fix CI after a push. It keeps the repo compliant with the rule that every push should be followed by a GitHub Actions check and a log under `samples/logs/`.

## Workflow

1. From the repository root, list recent runs:
   - `make gh-runs GH_RUN_LIMIT=10`
2. Watch the relevant run:
   - `RUN_ID=<id> make gh-watch`
   - If no `RUN_ID` is passed, the Makefile watches the newest run.
3. Capture structured run data:
   - `gh run view <id> --json databaseId,displayTitle,workflowName,event,status,conclusion,headBranch,headSha,createdAt,updatedAt,url,jobs`
4. Write a timestamped markdown log into `samples/logs/`.
   - Prefer `scripts/write_gh_run_log.py` for the log body and filename.
5. If the run failed:
   - `RUN_ID=<id> make gh-failed-logs`
   - fix the repository
   - rerun the required local validation
   - push again
   - repeat this skill

## Guardrails

- Do not stop at `gh run list`; wait for the relevant run to reach a terminal state unless the user explicitly says otherwise.
- When multiple workflows trigger from the same push, log the relevant runs together.
- Avoid recursive "log the log push" churn. If the only new change would be another run log for a previous log-only commit, summarize the result to the user instead of forcing another follow-up log commit unless repository state changed again.
- Keep logs factual: command sequence, run metadata, job summary, and notable failures or warnings.

## Resource

- `scripts/write_gh_run_log.py <repo_root> [run_id ...]`
  - Uses `gh run view --json ...`
  - Defaults to the newest run when no run ID is given
  - Writes a repo-style markdown file under `samples/logs/`
