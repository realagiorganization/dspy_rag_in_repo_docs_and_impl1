# GitHub Run Inspection

- Timestamp: `20260501T201242Z`
- Repository: `realagiorganization/dspy_rag_in_repo_docs_and_impl1`
- Branch: `develop`
- HEAD after main push: `a354af32768db0b34621b01765ba0c415db2b29e`

## Commands

- `make gh-runs GH_RUN_LIMIT=10`
- `gh run list --limit 10 --json databaseId,workflowName,displayTitle,event,status,conclusion,headBranch,headSha,createdAt,updatedAt,url`
- `gh run view 25226453714 --json databaseId,displayTitle,workflowName,event,status,conclusion,headBranch,headSha,createdAt,updatedAt,url,jobs`
- `gh run view 25226453712 --json databaseId,displayTitle,workflowName,event,status,conclusion,headBranch,headSha,createdAt,updatedAt,url,jobs`

## Result

No new GitHub Actions run appeared for `HEAD` `a354af32768db0b34621b01765ba0c415db2b29e`.

The newest `develop` runs visible after the push still pointed at the earlier head SHA
`a1235bd3291946296449e415c2b6f80c58393dc9`:

- `25226453737` — `Hushwheel Quality` — `pull_request` on `develop` — `success`
- `25226453729` — `Publication PDF` — `pull_request` on `develop` — `success`
- `25226453714` — `CI` — `pull_request` on `develop` — `failure`
- `25226453712` — `GitHub Pages` — `pull_request` on `develop` — `cancelled`

The latest `push` workflows in the repository were merge-to-`master` runs for PR `#11`, not runs
for the freshly pushed `develop` head:

- `25226461714` — `CI` — `push` on `master` — `failure` — head SHA `34aa91569f921dd4b5c80b79ebc9cd61bdf83de6`
- `25226461698` — `Hushwheel Quality` — `push` on `master` — `success`
- `25226461687` — `Publication PDF` — `push` on `master` — `success`
- `25226461671` — `GitHub Pages` — `push` on `master` — `failure`

## Interpretation

The push that switched worker/runtime bundle selection to explicit immutable
`DSPY_BUNDLE_VERSION` pinning did not trigger a fresh GitHub Actions run for the new `develop`
head. The visible failures belong to earlier `develop` PR runs on `a1235bd...` or to merge runs
on `master`, so they are not evidence for or against `a354af3`.
