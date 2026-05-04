# GitHub Run Check After `Document Codex resume restore fallback debug`

- Timestamp: `2026-05-04T11:14:27Z`
- Branch checked: `develop`
- Pushed commit: `c383a02ae37113c5b65ea2837314cc1eca99062f`
- Result: no new GitHub Actions run appeared for this `headSha`

## Commands

```bash
make gh-runs GH_RUN_LIMIT=10
python - <<'PY'
import json, subprocess
for sha in [
    'c383a02ae37113c5b65ea2837314cc1eca99062f',
    '1be2934b33b2951776445a8975c4286b48a2f40c',
]:
    out = subprocess.check_output([
        'gh', 'run', 'list', '--limit', '30',
        '--json',
        'databaseId,displayTitle,headSha,headBranch,status,conclusion,event,workflowName,createdAt,updatedAt,url',
    ])
    runs = json.loads(out)
    matched = [run for run in runs if run.get('headSha') == sha]
    print('SHA', sha)
    print(json.dumps(matched, indent=2))
PY
gh run view 25310714757 --json databaseId,displayTitle,workflowName,event,status,conclusion,headBranch,headSha,createdAt,updatedAt,url,jobs
gh run view 25310714751 --json databaseId,displayTitle,workflowName,event,status,conclusion,headBranch,headSha,createdAt,updatedAt,url,jobs
gh run view 25310714748 --json databaseId,displayTitle,workflowName,event,status,conclusion,headBranch,headSha,createdAt,updatedAt,url,jobs
gh run view 25310714738 --json databaseId,displayTitle,workflowName,event,status,conclusion,headBranch,headSha,createdAt,updatedAt,url,jobs
RUN_ID=25310714757 make gh-failed-logs
```

## Observations

- `gh run list` showed no runs for `c383a02ae37113c5b65ea2837314cc1eca99062f`.
- The newest visible `develop` PR runs still referenced `1be2934b33b2951776445a8975c4286b48a2f40c`.
- The visible `develop` CI run (`25310714757`) failed in `Python Quality, Tests, And Build` at `Check Python formatting`.
- `RUN_ID=25310714757 make gh-failed-logs` showed `uv run ruff format --check src tests` failing because twelve existing files would be reformatted:
  - `src/repo_rag_lab/cli.py`
  - `src/repo_rag_lab/codex_proxy.py`
  - `src/repo_rag_lab/dspy_training.py`
  - `src/repo_rag_lab/retrieval.py`
  - `src/repo_rag_lab/runtime_artifacts.py`
  - `src/repo_rag_lab/semantic_retrieval.py`
  - `src/repo_rag_lab/trainer_deployment.py`
  - `src/repo_rag_lab/training_samples.py`
  - `src/repo_rag_lab/utilities.py`
  - `tests/test_codex_proxy.py`
  - `tests/test_training_samples.py`
  - `tests/test_utilities.py`
- Those formatting failures predate this restore-fallback patch and were not expanded into a repo-wide formatting churn in this turn.

## Recent Visible Runs

- `25310714757` `CI` `failure`
  - head SHA: `1be2934b33b2951776445a8975c4286b48a2f40c`
  - failed job: `Python Quality, Tests, And Build`
- `25310714751` `Publication PDF` `success`
  - head SHA: `1be2934b33b2951776445a8975c4286b48a2f40c`
  - publication gate skipped because no relevant files changed
- `25310714748` `Hushwheel Quality` `success`
  - head SHA: `1be2934b33b2951776445a8975c4286b48a2f40c`
  - hushwheel gate skipped because no relevant files changed
- `25310714738` `GitHub Pages` `cancelled`
  - head SHA: `1be2934b33b2951776445a8975c4286b48a2f40c`

## Conclusion

At the time of inspection, the push for `c383a02ae37113c5b65ea2837314cc1eca99062f` had not triggered a visible GitHub Actions run. This log captures the current observable run state without creating a recursive follow-up log for the eventual log-only push.
