# GitHub Actions Run Log

- Log captured at: `2026-05-11T09:04:38Z`
- Repository root: `/home/standard/Desktop/realagi_work/dspy_rag_in_repo_docs_and_impl1`
- Command sequence:
  - `make gh-runs GH_RUN_LIMIT=10`
  - `RUN_ID=25660302431 make gh-watch`
  - `RUN_ID=25660446587 make gh-watch`
  - `RUN_ID=25660612510 make gh-watch`
  - `gh run view <id> --json databaseId,displayTitle,workflowName,event,status,conclusion,headBranch,headSha,createdAt,updatedAt,url,jobs`

## Latest Runs

- Workflow: `CI`
- Display title: `Fix trainer incrementality and family-state versioned layout`
- Run ID: `25660302431`
- Event: `pull_request`
- Branch: `develop`
- Head SHA: `96da9697c5e925619d2f56bfafaeb0691dfc7f23`
- Status: `completed`
- Conclusion: `failure`
- Created at: `2026-05-11T08:54:52Z`
- Updated at: `2026-05-11T08:55:51Z`
- URL: `https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/25660302431`

- Workflow: `CI`
- Display title: `Fix trainer incrementality and family-state versioned layout`
- Run ID: `25660446587`
- Event: `pull_request`
- Branch: `develop`
- Head SHA: `40da684972927b6cc2c19d8bb6f4d97aa272948b`
- Status: `completed`
- Conclusion: `failure`
- Created at: `2026-05-11T08:57:49Z`
- Updated at: `2026-05-11T08:58:52Z`
- URL: `https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/25660446587`

- Workflow: `CI`
- Display title: `Fix trainer incrementality and family-state versioned layout`
- Run ID: `25660612510`
- Event: `pull_request`
- Branch: `develop`
- Head SHA: `ecf14765ef14c6afd8ef49df21833927e935b5e2`
- Status: `in_progress`
- Conclusion: `n/a`
- Created at: `2026-05-11T09:01:11Z`
- Updated at: `2026-05-11T09:01:16Z`
- URL: `https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/25660612510`

## Job Summary

### Run `25660302431`
- `Rust Wrapper` (`75318851852`): `success`, started `2026-05-11T08:54:56Z`, completed `2026-05-11T08:55:50Z`
- `Python Quality, Tests, And Build` (`75318851853`): `failure`, started `2026-05-11T08:55:02Z`, completed `2026-05-11T08:55:15Z`

### Run `25660446587`
- `Python Quality, Tests, And Build` (`75319343933`): `failure`, started `2026-05-11T08:57:58Z`, completed `2026-05-11T08:58:27Z`
- `Rust Wrapper` (`75319343949`): `success`, started `2026-05-11T08:57:58Z`, completed `2026-05-11T08:58:51Z`

### Run `25660612510`
- `Rust Wrapper` (`75319915120`): `success`, started `2026-05-11T09:01:15Z`, completed `2026-05-11T09:02:22Z`
- `Python Quality, Tests, And Build` (`75319915124`): `in_progress`, started `2026-05-11T09:01:14Z`, completed `0001-01-01T00:00:00Z`

## Notes

- At least one run failed. Inspect it with `RUN_ID=<id> make gh-failed-logs`; failed run IDs: `25660302431`, `25660446587`.
- At least one run was logged before reaching a terminal state: `25660612510`.
