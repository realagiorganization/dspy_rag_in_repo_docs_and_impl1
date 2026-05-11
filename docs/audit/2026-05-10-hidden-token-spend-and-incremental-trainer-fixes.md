# 2026-05-10 Hidden Token Spend And Incremental Trainer Fixes

## Context

The user asked two concrete questions after several live AKS runs:

1. Why does the Azure bill exceed the token counts that are visible in the main `codex exec`
   session summaries?
2. Does the trainer really process only newly queued traces, or does it keep replaying older
   history and therefore multiply optimizer cost over time?

The same investigation also surfaced an operator-facing blob-layout concern: the
`repo-rag-training-families` container had started storing both immutable `versions/...` history
and duplicate root-level `family-state.json` / `families/<id>/...` mirrors.

## Findings

### 1. Codex-visible token counts underreport the real Azure spend

The execution artifacts only account for the main Codex session usage. They do not include:

- proxy-side helper-model reformulation calls made before outbound turns reach Codex proper
- trainer-side DSPy optimizer calls made during background compile / recompile work

Live evidence from run `25637723574_20260510_195334` showed:

- `repo_rag_turn_trace_batch_manifest.json` captured `15` outbound turns
- each turn already carried `reformulation_status = "dspy"`
- the cleaned execution prompt was compact, but the total run still used `prompt_tokens = 69812`

So the Azure bill can legitimately exceed the token counts visible in `codex_session_state.json`,
because helper-model reformulation calls and trainer-side DSPy compile calls are separate Azure
requests.

One more important detail: the live trainer deployment is still using
`--recompile-optimizer bootstrapfewshot`, not `miprov2`. The current hidden trainer-side spend is
therefore not “MIPROv2 running over everything,” but it is still extra DSPy/LM spend outside the
main Codex session.

### 2. The trainer was not fully incremental

Queue draining was already incremental, but the durable-recovery/materialization path was not:

- `restore_processed_trace_records(...)` scanned the full `processed/...` blob prefix every cycle
- it mirrored those processed items back into
  `artifacts/trainer/recovered-imported-traces/`
- `run_trainer_cycle(...)` preferred those recovered paths
- if the recovered list was empty, `materialize_training_candidates(...)` still fell back to the
  full imported ledger unless `trace_paths` was truly `None`

In practice that meant a trainer cycle could keep reprocessing historical traces even when no new
queue items arrived.

### 3. The root-level family-state mirror was duplicate state

The live `repo-rag-training-families` container did populate successfully, but its layout carried
two levels of the same data:

- immutable `versions/<family_state_version>/...`
- duplicate root-level `family-state.json` and `families/<prompt_family_id>/...`

Runtime resolution only needs:

- `current.json`
- the versioned blob paths referenced by `current.json`

The root-level mirror was therefore operator-facing duplication, not a machine requirement.

### 4. Earlier live bundle blocking also had a deploy-side configuration cause

The repo-side trainer cycle no longer injected an implicit
`minimum_bundle_pass_rate = 1.0`, but the dataset deploy bootstrap still defaulted
`TRAINER_MIN_BUNDLE_PASS_RATE=1.0`. That meant live trainer pods could continue enforcing a hidden
publish gate even after the repo-side policy had been relaxed.

## Fixes Applied Locally

### Trainer incrementality

`src/repo_rag_lab/runtime_artifacts.py`

- `restore_processed_trace_records(...)` now skips already-restored processed blobs instead of
  restoring them again every cycle

`src/repo_rag_lab/training_samples.py`

- `materialize_training_candidates(...)` now treats explicit `trace_paths=[]` as “process nothing
  new” instead of falling back to the whole imported ledger
- `_load_champion_index(...)` now sanitizes previously persisted family questions / father records
  on read, so older dirty family state can be rewritten into the cleaned prompt surface

`src/repo_rag_lab/utilities.py`

- `run_trainer_candidates(...)` now preserves the old “default means read imported traces” behavior
  by passing `trace_paths=None` when no explicit trace list is provided
- `run_trainer_cycle(...)` already stopped auto-injecting `minimum_bundle_pass_rate = 1.0`

### Family-state hierarchy cleanup

`src/repo_rag_lab/runtime_artifacts.py`

- remote family-state upload now writes only:
  - `current.json`
  - `versions/<family_state_version>/family-state.json`
  - `versions/<family_state_version>/families/<prompt_family_id>/{family.json,father.json,records/<snapshot>.json}`
- the duplicate root-level `family-state.json` and `families/<id>/...` mirrors are no longer
  written
- each new upload also deletes any previously written root-level `family-state.json` and
  `families/...` alias blobs, so the container can converge back to the versioned-only layout on
  the next trainer cycle instead of keeping historical duplicates forever

### Deploy-side bundle gate cleanup

`../dataset/deploy_repo_rag_trainer.sh`

- `TRAINER_MIN_BUNDLE_PASS_RATE` now defaults to empty instead of `1.0`

`../dataset/.env.example`, `../dataset/README.md`, `../dataset/USAGE.md`

- updated to document that family-first deploy defaults no longer silently enforce a bundle pass
  gate

## Verification

Executed locally after the fixes:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_training_samples.py tests/test_utilities.py tests/test_runtime_artifacts_azure.py -q`
  - `90 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
- `cd ../dataset && pytest tests/unit/test_deploy_repo_rag_trainer_script.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py -q`
  - `27 passed`

Additional repository-wide checks should still be run after the current doc sync:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `UV_CACHE_DIR=/tmp/uvcache make files-sync`
- `UV_CACHE_DIR=/tmp/uvcache make exploratorium-sync`
- `UV_CACHE_DIR=/tmp/uvcache make verify-surfaces`

## Remaining Risk

No new live AKS rerun has been executed after these fixes.

The next live proof points should be:

- trainer cycles only process newly queued traces instead of replaying the whole processed ledger
- `repo-rag-training-families` contains only `current.json` plus the immutable `versions/...`
  tree
- live trainer pods no longer inherit a hidden `TRAINER_MIN_BUNDLE_PASS_RATE=1.0`
- the next published bundle appears in `repo-rag-bundles`
- runtime finally resolves a non-null `bundle_version` and leaves the heuristic fallback path
