# GitHub Actions Run Log

- Log captured at: `2026-05-10T12:48:34Z`
- Repository root: `/home/standard/Desktop/realagi_work/dspy_rag_in_repo_docs_and_impl1`
- Command sequence:
  - `make gh-runs GH_RUN_LIMIT=10`
  - `RUN_ID=25629028256 make gh-watch`
  - `RUN_ID=25628871343 make gh-watch`
  - `RUN_ID=25628838202 make gh-watch`
  - `gh run view <id> --json databaseId,displayTitle,workflowName,event,status,conclusion,headBranch,headSha,createdAt,updatedAt,url,jobs`

## Latest Runs

- Workflow: `CI`
- Display title: `Develop`
- Run ID: `25629028256`
- Event: `pull_request`
- Branch: `develop`
- Head SHA: `64732c0ccc3e766ac2f16d0ae495ffd2158796fb`
- Status: `completed`
- Conclusion: `failure`
- Created at: `2026-05-10T12:42:49Z`
- Updated at: `2026-05-10T12:46:55Z`
- URL: `https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/25629028256`

- Workflow: `CI`
- Display title: `Develop`
- Run ID: `25628871343`
- Event: `pull_request`
- Branch: `develop`
- Head SHA: `e7d48a7c422584407ef7d5352f05bdda099d1735`
- Status: `completed`
- Conclusion: `failure`
- Created at: `2026-05-10T12:35:02Z`
- Updated at: `2026-05-10T12:35:57Z`
- URL: `https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/25628871343`

- Workflow: `CI`
- Display title: `Develop`
- Run ID: `25628838202`
- Event: `pull_request`
- Branch: `develop`
- Head SHA: `6854ed71b4055358a727ecdde70bd05f45c7216a`
- Status: `completed`
- Conclusion: `failure`
- Created at: `2026-05-10T12:33:22Z`
- Updated at: `2026-05-10T12:34:32Z`
- URL: `https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/25628838202`

## Job Summary

### Run `25629028256`
- `Rust Wrapper` (`75229239339`): `success`, started `2026-05-10T12:42:53Z`, completed `2026-05-10T12:43:48Z`
- `Python Quality, Tests, And Build` (`75229239362`): `failure`, started `2026-05-10T12:42:52Z`, completed `2026-05-10T12:46:55Z`

### Run `25628871343`
- `Rust Wrapper` (`75228816530`): `success`, started `2026-05-10T12:35:06Z`, completed `2026-05-10T12:35:56Z`
- `Python Quality, Tests, And Build` (`75228816637`): `failure`, started `2026-05-10T12:35:06Z`, completed `2026-05-10T12:35:43Z`

### Run `25628838202`
- `Python Quality, Tests, And Build` (`75228724173`): `failure`, started `2026-05-10T12:33:26Z`, completed `2026-05-10T12:33:41Z`
- `Rust Wrapper` (`75228724178`): `success`, started `2026-05-10T12:33:26Z`, completed `2026-05-10T12:34:32Z`

## Notes

- At least one run failed. Inspect it with `RUN_ID=<id> make gh-failed-logs`; failed run IDs: `25629028256`, `25628871343`, `25628838202`.
