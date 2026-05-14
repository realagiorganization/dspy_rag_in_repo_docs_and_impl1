# 2026-05-11 Latest Run: Handoff Restored But Family Runtime Still Heuristic

## Summary

The latest dataset run restored the execution-artifact upload path and the trusted repo-rag
handoff path, but the family-first DSPy runtime still did **not** execute a matched family
artifact.

From `../dataset/artifacts/`:

- execution artifacts were uploaded successfully into `execution-artifacts`
- worker-side per-turn batch capture succeeded with `30` turn traces
- trusted handoff succeeded and materialized `30` queue items
- proxy-side family lookup matched an existing family with `prompt_family_id=pf-c93cbc537b800fac`
  and `prompt_family_similarity=1.0`
- runtime still stayed on heuristic mediation:
  - `bundle_version=null`
  - `program_path=null`
  - `family_artifact_selected=false`
  - `dspy_status=heuristic`

So the run no longer fails at upload or queue handoff, but the family library is still not being
used for execution.

## Evidence

### Artifact upload and queue handoff

- `../dataset/artifacts/upload_summary.json`
  - `execution_id=25688428531_20260511_191845`
  - `storage_container=execution-artifacts`
  - `files_found=119`
  - `upload_attempted=true`
- `execution_artifacts/trusted_trace_handoff_summary.json`
  - `status=success`
  - `queued=1`
  - `failed=0`
- worker-side batch artifacts:
  - `repo_rag_turn_trace_batch_manifest.json`
    - `batch_name=20260511T182243Z`
    - `trace_paths=30`
  - `repo_rag_turn_trace_enqueue_batch.json`
    - `command_status=success`
    - `handled_count=30`
    - `turn_count=30`
- trusted queue-item mirrors:
  - `.trusted_trace_queue_item.<n>.json`
  - `30` queue items present in the uploaded execution bundle

### Runtime state

`execution_artifacts/prompt-worker-0-rehydrated/artifacts/prompts_debt_relief-p00000-cfc990/repo_rag_codex_proxy_last.json`
shows:

- `prompt_family_id=pf-c93cbc537b800fac`
- `prompt_family_similarity=1.0`
- `prompt_family_band=match`
- `family_runtime_hit_rate=1.0`
- `family_artifact_selected=false`
- `bundle_version=null`
- `program_path=null`
- `dspy_status=heuristic`
- `reformulation_status=identity`
- `mediation_mode=rag_heuristic_dspy`

`repo_rag_backend.json` confirms:

- `bundle_resolved=false`
- `dspy_status=heuristic`
- `trace_exported=true`
- `trace_handoff_status=queued`

### Exported trace records still lose family metadata

The exported trainer-facing trace records under:

- `execution_artifacts/.../artifacts/traces/*.json`

all preserve:

- `question`
- `original_prompt`
- `reformulated_prompt`
- `source_command=codex-proxy-turn-mediation`

but currently lose:

- `prompt_family_id`
- `prompt_family_similarity`
- `prompt_family_band`
- `family_artifact_selected`
- `bundle_version`
- `program_path`
- `dspy_status`
- `mediation_metric_hits/total`

That means the worker raw/runtime surface knows about family lookup, but the exported
trainer-facing trace record currently drops those fields.

## Token Usage Assessment

From `processed/token_usage.json`:

- `prompt_tokens=147163`
- `completion_tokens=0`
- `total_tokens=147163`

This number is high but looks valid for this specific run rather than obviously pathological:

- `codex_response.txt` size: `250734` bytes
- `codex_response.txt` line count: `6109`
- transcript mentions:
  - `playwright`: `61`
  - `ffmpeg`: `5`
  - `README.md`: `64`
  - `docs/assets`: `61`
  - `npm`: `126`
- `codex_session_state.json`
  - `session_mode=reset`
  - `restore_status=reset:resumed-run-threshold`
  - `latest_usage.prompt_tokens=147163`
  - this is **60.2% lower** than the previous fresh baseline (`370119`)

So the token spend is still large, but it is consistent with a long real build/automation run and
is no longer shaped like the previous trainer-side infinite loop or upload/handoff failure modes.

## What Worked

- execution finished successfully
- execution artifacts uploaded to blob storage
- worker-side inline artifact rehydration worked
- per-turn batch trace capture worked
- batch enqueue worked
- trusted repo-rag handoff worked
- queue items were produced for trainer ingestion
- family lookup matched an existing family father

## What Did Not Work

- runtime did not activate a family DSPy artifact
- no compiled family `program.json` was selected at execution time
- proxy stayed in heuristic mode despite an exact family match
- exported trainer-facing trace records still lose family/runtime metadata

## Current Interpretation

The system is now past the two earlier blockers:

1. missing execution-artifact upload
2. broken trusted-handoff path

The next active runtime bug is narrower:

- family matching works
- family runtime execution does not

The remaining likely break is therefore in the runtime bridge:

- matched family state exists
- but worker runtime still does not resolve that match into a runnable local family artifact

## Verification

Configured repository checks relevant to this verification pass:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make files-sync`
- `make verify-surfaces`

Executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` — `49 passed`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`

Not executed in this turn:

- coverage
- full lint/type-check
- live AKS redeploy
- trainer-side queue drain validation against the newly produced `30` queue items
