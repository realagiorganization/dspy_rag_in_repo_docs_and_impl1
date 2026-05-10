# 2026-05-10 Stale Submodule Runtime Image Root Cause And Source-Preference Fix

## Context

Latest uploaded execution artifacts still showed the same live failure pattern:

- `bundle_resolved=false`
- `bundle_version=null`
- `program_loaded=false`
- `dspy_status=heuristic`

At the same time the operator-visible `repo-rag-training-families` container still looked empty,
and the live trainer pod continued writing `artifacts/trainer/champion-index.json` instead of
`artifacts/trainer/family-state.json`.

That meant the remaining blocker was no longer trace export, queue handoff, or family-state upload
logic in the repository source tree. The live runtime image itself was stale.

## Root Cause

The issue turned out to be the `../dataset` image/deploy source-root selection.

Evidence gathered in this turn:

- `../dataset/build_and_push_images.sh` preferred
  `../dataset/submodules/dspy_rag_in_repo_docs_and_impl1` before the sibling checkout
  `../dspy_rag_in_repo_docs_and_impl1`
- the dataset submodule was still pinned at `76c13a110575e61fb310ddfe795b266ff85a1d95`
- the active sibling checkout was already far ahead at
  `a70facc3780713f9b95c69b0775f7a4f44d515b0`
- inside the live trainer pod, `repo_rag_lab.training_samples` still lacked
  `DEFAULT_TRAINER_FAMILY_STATE_PATH` and `upload_remote_family_state(...)`, confirming that the
  container was running champion-era code baked from the stale submodule rather than the current
  family-first repository checkout

So `repo-rag-training-families` stayed empty not because family uploads failed in current code, but
because the live trainer image was built from the wrong source tree.

## Local Fix

### 1. Prefer the active sibling repo checkout over the stale submodule

`../dataset/build_and_push_images.sh` and `../dataset/deploy_repo_rag_trainer.sh` now resolve the
repo-RAG source root in this order:

1. explicit `REPO_RAG_SOURCE_ROOT`
2. sibling checkout `../dspy_rag_in_repo_docs_and_impl1`
3. fallback submodule `submodules/dspy_rag_in_repo_docs_and_impl1`

This keeps normal workstation builds and trainer deploys aligned with the actual active repo-RAG
checkout instead of silently baking whichever older submodule revision happens to be pinned in the
dataset repo.

### 2. Strip residual runtime envelope metadata from mediation lineage

`src/repo_rag_lab/codex_proxy.py` and
`../dataset/docker/prompt-executor/worker_execution_prompt.py` now also strip:

- `Repository checkout: ...`
- `Attachment mount: ...`

from dataset-execution-envelope normalization. That keeps `question`, `reformulated_prompt`, and
command-trace user steps closer to the agreed family-first contract instead of mixing execution
metadata into prompt-family comparison.

## Token Interpretation

The latest inspected run used very high prompt tokens, but the artifact evidence shows that the
main cost was a long real Codex rollout rather than repo-RAG prompt bloat alone:

- `prompt_tokens=363816`
- `codex_response.txt` was `354260` bytes / `5343` lines
- the transcript contained large numbers of real iterative tool steps such as `exec`, `ffmpeg`,
  `playwright`, and `npm`

So the token spike is at least substantially explained by Codex actually developing and iterating
on code/assets. The residual prompt-envelope pollution was still worth fixing because it polluted
family matching, but it was not the dominant source of the token explosion anymore.

## Verification

Ran locally:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_codex_proxy.py -q`
  - `17 passed`
- `cd ../dataset && pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/unit/test_deploy_repo_rag_trainer_script.py -q`
  - `27 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `45 passed`
- `cd ../dataset && python -m compileall docker/prompt-executor/worker_execution_prompt.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py tests/unit/test_deploy_repo_rag_trainer_script.py`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `UV_CACHE_DIR=/tmp/uvcache make files-sync`
- `UV_CACHE_DIR=/tmp/uvcache make exploratorium-sync`
- `UV_CACHE_DIR=/tmp/uvcache make verify-surfaces`

Shell validity for `../dataset/build_and_push_images.sh` and
`../dataset/deploy_repo_rag_trainer.sh` is covered by `bash -n` inside
`tests/unit/test_deploy_repo_rag_trainer_script.py`.

## Remaining Risk

This turn fixes the local source-selection bug, but no new live image rebuild/redeploy has been
verified yet.

The next live proof points should be:

- trainer pod source now contains `DEFAULT_TRAINER_FAMILY_STATE_PATH`
- trainer artifacts write `artifacts/trainer/family-state.json`
- `repo-rag-training-families` visibly contains root `family-state.json` and
  `families/<prompt_family_id>/...`
- execution artifacts stop reporting `bundle_version=null` / `dspy_status=heuristic`
