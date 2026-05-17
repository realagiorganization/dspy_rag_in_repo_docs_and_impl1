# GitHub Runs After `adfea05`

- Timestamp (UTC): `2026-05-17T05:06:35Z`
- Branch: `develop`
- Head SHA: `adfea058061c36ff11b473ab4a71530727613a5f`
- Push subject: `Reset stale trainer cache after remote cleanup`

## Commands

```bash
make gh-runs GH_RUN_LIMIT=10
RUN_ID=25981931685 make gh-failed-logs
RUN_ID=25981931665 make gh-watch
gh run view 25981931685 --json databaseId,displayTitle,workflowName,event,status,conclusion,headBranch,headSha,createdAt,updatedAt,url,jobs
```

## Run Summary

- `25981931685` `CI`: `failure`
- `25981931686` `GitHub Pages`: `success`
- `25981931676` `Hushwheel Quality`: `success`
- `25981931665` `Publication PDF`: `success`

## Notable Failure

`CI` failed in `Python Quality, Tests, And Build -> Run mypy`.

Representative errors from the run:

- `src/repo_rag_lab/term_extraction.py:1095`: `int(object)` typing failure
- `src/repo_rag_lab/runtime_artifacts.py:2843`: `seen_dedupe_keys` redefinition
- `tests/test_runtime_artifacts_azure.py:397-399`: indexing `object`
- multiple `arg-type` and `operator` failures in `src/repo_rag_lab/training_samples.py`
- `src/repo_rag_lab/utilities.py:887-888`: `list(object)` typing failure
- `src/repo_rag_lab/codex_proxy.py:416` and `:1314`: `int()` typing failures

`Publication PDF` completed successfully in `2m4s`. `GitHub Pages` and `Hushwheel Quality` were also green for this push.

## Notes

- This log is intentionally left local only to avoid recursive log-only churn.
- Follow-up work is required if we want `CI` green on `develop`; the push itself and the targeted local verification for the stale trainer cache fix were successful.
