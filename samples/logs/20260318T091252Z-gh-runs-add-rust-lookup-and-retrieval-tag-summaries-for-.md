# GitHub Actions Run Log

- Log captured at: `2026-03-18T09:12:52Z`
- Repository root: `/tmp/repo-session-salvage-clean.7gGBkT`
- Command sequence:
  - `make gh-runs GH_RUN_LIMIT=10`
  - `RUN_ID=23237027246 make gh-watch`
  - `RUN_ID=23237027308 make gh-watch`
  - `gh run view <id> --json databaseId,displayTitle,workflowName,event,status,conclusion,headBranch,headSha,createdAt,updatedAt,url,jobs`

## Latest Runs

- Workflow: `CI`
- Display title: `Add Rust lookup and retrieval tag summaries for "carry on commit and …`
- Run ID: `23237027246`
- Event: `push`
- Branch: `master`
- Head SHA: `c007d638802fe7cbb2042811c835b21289ffc954`
- Status: `completed`
- Conclusion: `failure`
- Created at: `2026-03-18T09:04:38Z`
- Updated at: `2026-03-18T09:06:38Z`
- URL: `https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/23237027246`

- Workflow: `Publication PDF`
- Display title: `Add Rust lookup and retrieval tag summaries for "carry on commit and …`
- Run ID: `23237027308`
- Event: `push`
- Branch: `master`
- Head SHA: `c007d638802fe7cbb2042811c835b21289ffc954`
- Status: `completed`
- Conclusion: `success`
- Created at: `2026-03-18T09:04:38Z`
- Updated at: `2026-03-18T09:06:47Z`
- URL: `https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/23237027308`

## Job Summary

### Run `23237027246`
- `Python Quality, Tests, And Build` (`67543404176`): `success`, started `2026-03-18T09:04:41Z`, completed `2026-03-18T09:06:37Z`
- `Rust Wrapper` (`67543404184`): `failure`, started `2026-03-18T09:04:41Z`, completed `2026-03-18T09:04:59Z`

### Run `23237027308`
- `Build Publication PDF` (`67543404226`): `success`, started `2026-03-18T09:04:41Z`, completed `2026-03-18T09:06:47Z`

## Notes

- At least one run failed. Inspect it with `RUN_ID=<id> make gh-failed-logs`; failed run IDs: `23237027246`.
- The overall `CI` failure came from the `Rust Wrapper` job: `Check Rust formatting` failed, so
  `Run Clippy`, `Build Rust wrapper`, and the packaged-workflow smoke step were skipped.
- The Python job in the same `CI` run completed successfully through compile, lint, type checks,
  repository-surface verification, coverage, smoke test, and dist build.
