# GitHub Actions Run Log

- Log captured at: `2026-05-10T11:11:52Z`
- Repository root: `/home/standard/Desktop/realagi_work/dspy_rag_in_repo_docs_and_impl1`
- Command sequence:
  - `make gh-runs GH_RUN_LIMIT=10`
  - `RUN_ID=25627101125 make gh-watch`
  - `RUN_ID=25627101120 make gh-watch`
  - `RUN_ID=25627156143 make gh-watch`
  - `RUN_ID=25627156142 make gh-watch`
  - `RUN_ID=25627156137 make gh-watch`
  - `gh run view <id> --json databaseId,displayTitle,workflowName,event,status,conclusion,headBranch,headSha,createdAt,updatedAt,url,jobs`

## Latest Runs

- Workflow: `CI`
- Display title: `Fix family-first runtime bundle activation and trace compaction`
- Run ID: `25627101125`
- Event: `pull_request`
- Branch: `develop`
- Head SHA: `f58638c54b666174893e140a860390ba2a007452`
- Status: `completed`
- Conclusion: `failure`
- Created at: `2026-05-10T11:06:17Z`
- Updated at: `2026-05-10T11:07:14Z`
- URL: `https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/25627101125`

- Workflow: `Publication PDF`
- Display title: `Fix family-first runtime bundle activation and trace compaction`
- Run ID: `25627101120`
- Event: `pull_request`
- Branch: `develop`
- Head SHA: `f58638c54b666174893e140a860390ba2a007452`
- Status: `completed`
- Conclusion: `success`
- Created at: `2026-05-10T11:06:17Z`
- Updated at: `2026-05-10T11:08:27Z`
- URL: `https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/25627101120`

- Workflow: `CI`
- Display title: `Merge pull request #41 from realagiorganization/develop`
- Run ID: `25627156143`
- Event: `push`
- Branch: `master`
- Head SHA: `02bd10dce0659b458f9291735034baf62c3e354e`
- Status: `completed`
- Conclusion: `failure`
- Created at: `2026-05-10T11:09:05Z`
- Updated at: `2026-05-10T11:10:05Z`
- URL: `https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/25627156143`

- Workflow: `GitHub Pages`
- Display title: `Merge pull request #41 from realagiorganization/develop`
- Run ID: `25627156142`
- Event: `push`
- Branch: `master`
- Head SHA: `02bd10dce0659b458f9291735034baf62c3e354e`
- Status: `completed`
- Conclusion: `success`
- Created at: `2026-05-10T11:09:05Z`
- Updated at: `2026-05-10T11:09:54Z`
- URL: `https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/25627156142`

- Workflow: `Publication PDF`
- Display title: `Merge pull request #41 from realagiorganization/develop`
- Run ID: `25627156137`
- Event: `push`
- Branch: `master`
- Head SHA: `02bd10dce0659b458f9291735034baf62c3e354e`
- Status: `completed`
- Conclusion: `success`
- Created at: `2026-05-10T11:09:05Z`
- Updated at: `2026-05-10T11:11:14Z`
- URL: `https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/25627156137`

## Job Summary

### Run `25627101125`
- `Python Quality, Tests, And Build` (`75224072256`): `failure`, started `2026-05-10T11:06:21Z`, completed `2026-05-10T11:06:37Z`
- `Rust Wrapper` (`75224072260`): `success`, started `2026-05-10T11:06:21Z`, completed `2026-05-10T11:07:14Z`

### Run `25627101120`
- `Build Publication PDF` (`75224072142`): `success`, started `2026-05-10T11:06:21Z`, completed `2026-05-10T11:08:26Z`

### Run `25627156143`
- `Python Quality, Tests, And Build` (`75224215291`): `failure`, started `2026-05-10T11:09:14Z`, completed `2026-05-10T11:09:27Z`
- `Rust Wrapper` (`75224215308`): `success`, started `2026-05-10T11:09:08Z`, completed `2026-05-10T11:10:04Z`

### Run `25627156142`
- `Build GitHub Pages Site` (`75224215362`): `success`, started `2026-05-10T11:09:08Z`, completed `2026-05-10T11:09:41Z`
- `Deploy GitHub Pages Site` (`75224243830`): `success`, started `2026-05-10T11:09:45Z`, completed `2026-05-10T11:09:54Z`

### Run `25627156137`
- `Build Publication PDF` (`75224215289`): `success`, started `2026-05-10T11:09:08Z`, completed `2026-05-10T11:11:13Z`

## Notes

- At least one run failed. Inspect it with `RUN_ID=<id> make gh-failed-logs`; failed run IDs: `25627101125`, `25627156143`.
- Both recorded CI failures belong to the pre-format-fix SHA lineage (`f58638c...`) and the
  immediate `master` merge commit (`02bd10d...`) that was created from it.
- A follow-up formatting hotfix was pushed later as `ec0e0e7`, but no distinct GitHub Actions run
  for that SHA was visible in `make gh-runs GH_RUN_LIMIT=12` at log-capture time.
