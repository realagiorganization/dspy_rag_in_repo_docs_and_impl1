# GitHub Run Inspection

- Date: `2026-05-02T16:57:50Z`
- Repository: `dspy_rag_in_repo_docs_and_impl1`
- Branch: `develop`
- HEAD checked: `cde684cb0b298f6ca5161c199fa4de7f4951dfde`

## Commands

```bash
make gh-runs GH_RUN_LIMIT=10
gh run list --limit 10 --json databaseId,displayTitle,workflowName,event,status,conclusion,headBranch,headSha,createdAt,updatedAt,url
```

## Result

No GitHub Actions run for `headSha cde684cb0b298f6ca5161c199fa4de7f4951dfde` was visible at inspection time.

The newest `develop` pull-request runs were still pinned to the previous head:

- `25254543727` — `CI` — `failure` — `headSha 6cc704ea7bea18278189eedf7bc4fc3f16190fce`
- `25254543729` — `Publication PDF` — `success` — `headSha 6cc704ea7bea18278189eedf7bc4fc3f16190fce`
- `25254543735` — `GitHub Pages` — `cancelled` — `headSha 6cc704ea7bea18278189eedf7bc4fc3f16190fce`
- `25254543717` — `Hushwheel Quality` — `success` — `headSha 6cc704ea7bea18278189eedf7bc4fc3f16190fce`

The newest visible push runs were merge-to-`master` workflows unrelated to the just-pushed `develop` head:

- `25254545045` — `CI` — `failure` — `headSha 07d3b1f4f40221a96f84aab06503341d923120a1`
- `25254545043` — `GitHub Pages` — `failure` — `headSha 07d3b1f4f40221a96f84aab06503341d923120a1`

## Notes

- No `make gh-watch` follow-up was run because there was no relevant run to watch for `cde684c`.
- This log captures the post-push inspection for the code push that introduced trainer champion batching and deployment-threshold wiring.
