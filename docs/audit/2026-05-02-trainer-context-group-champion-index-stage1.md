# Trainer Context-Group Champion Index Stage 1

- Date: `2026-05-02`
- Scope: replace question-level `last write wins` trainer candidate materialization with a
  prompt-family/context-group/family-champion state model that remains compatible with the current
  DSPy compile contract
- Preceding note: `2026-05-02-hybrid-vector-retrieval-default.md`

## Summary

The trainer no longer treats `training-candidates.yaml` as a pure question-level overwrite file.

Instead, imported worker traces now flow through a new persistent trainer state surface:

- `artifacts/trainer/champion-index.json`

That state groups imported traces in two stages:

1. `prompt_family`
   - stable identity derived from the normalized visible question
2. `context_group`
   - stable-ish grouping derived from retrieval-context similarity, currently using retrieved source
     overlap plus retrieval mode

Each context group keeps one context-group champion. Each prompt family then keeps one
family champion across those context groups. The compile-facing
`artifacts/trainer/training-candidates.yaml` file is materialized only from the family champions.

This is a deliberate first-stage constraint: the current DSPy compile dataset still behaves like
`question -> expected_answer`, so it is not yet safe to materialize multiple conflicting answers
for the exact same visible question into the generated compile set.

## Code Changes

Primary implementation surfaces:

- `src/repo_rag_lab/training_samples.py`
- `src/repo_rag_lab/runtime_artifacts.py`
- `tests/test_training_samples.py`
- `docs/planning/trainer-context-group-champion-plan.md`
- `docs/architecture/research-narrative.md`
- `docs/planning/dataset-integration-plan.md`

Important behavior changes:

- imported traces now receive:
  - `prompt_family_id`
  - `exact_snapshot_id`
  - `quality_score`
  - `context_snapshot`
- trainer candidate materialization now persists:
  - `artifacts/trainer/champion-index.json`
- family champion selection now replaces `last write wins` for compile-facing candidate updates
- `new_candidate_count` now reflects effective family-champion changes instead of raw ledger replay
- legacy `training-candidates.yaml` snapshots can still seed the champion index during migration
- trainer-cycle and trainer-service payloads now also expose:
  - `prompt_family_count`
  - `context_group_count`
  - `champion_index_path`
- repeated traces for the same answer variant inside one context group now accumulate explicit
  support for that champion variant instead of only incrementing group-wide `trace_count`
- context-group summaries now also merge gradual retrieval-source drift, so a prompt whose
  retrieved sources evolve from `README.md` to `README.md + docs/USAGE.md` to `docs/USAGE.md`
  can remain in one stable training group instead of fragmenting into new groups on every small
  retrieval shift
- runtime traces now also carry `evidence_fingerprints`, and `trace-export` backfills them from
  stored `context` / `retrieved_context` rows when older command envelopes do not include them
  explicitly; trainer grouping can therefore distinguish same-source retrievals that actually used
  different chunk evidence
- family-champion selection now also applies a stability gate across context groups: a new group
  must clear the score delta or win on support/evidence tie-breaks before it can replace the
  existing family champion, so one earlier high-score trace does not permanently lock in the
  family champion and one later low-support trace does not flip it by arrival order alone
- trainer-cycle and trainer-service now also expose `min_new_candidates_for_recompile`, and
  recompile can be skipped as `skipped-below-new-candidate-threshold` when the current cycle
  produces some new family-champion changes but not enough to justify a new bundle compile yet
- trainer Kubernetes manifest generation now also threads
  `TRAINER_MIN_NEW_CANDIDATES_FOR_RECOMPILE` through the generated ConfigMap plus
  `trainer-cycle` / `trainer-service` command lines, and the sibling `dataset`
  `deploy_repo_rag_trainer.sh` helper now forwards the same threshold into the AKS deployment path

## Verification

Repository-local checks executed in this turn:

- `uv run python -m compileall src tests` -> `pass`
- `uv run pytest tests/test_training_samples.py -q` -> `pass` (`11 passed`)
- `uv run pytest tests/test_training_samples.py -q` -> `pass` (`12 passed`)
- `uv run pytest tests/test_training_samples.py -q` -> `pass` (`13 passed`)
- `uv run pytest tests/test_training_samples.py -q` -> `pass` (`14 passed`)
- `uv run pytest tests/test_training_samples.py -q` -> `pass` (`15 passed`)
- `uv run pytest tests/test_dspy_training.py -q` -> `pass` (`22 passed`)
- `uv run pytest tests/test_utilities.py -k 'trainer_cycle or materialize_training_candidates or trainer_recompile_from_candidates' -q` -> `pass` (`5 passed`)
- `uv run pytest tests/test_utilities.py -k 'run_trainer_candidates or run_trainer_cycle or run_trainer_service' -q` -> `pass` (`8 passed`)
- `uv run pytest tests/test_utilities.py -k 'run_trace_export or run_trainer_candidates or run_trainer_cycle or run_trainer_service' -q` -> `pass` (`9 passed`)
- `uv run pytest tests/test_runtime_artifacts_azure.py tests/test_cli_and_dspy.py tests/test_mcp_server.py -k 'trace_export or ask_repo or publish_trace or queue_trace_record or drain_trace_queue or restore_processed_trace_records' -q` -> `pass` (`9 passed`)
- `uv run pytest tests/test_utilities.py -k 'run_trainer_candidates or run_trainer_cycle or run_trainer_service' -q` -> `pass` (`9 passed`)
- `uv run pytest tests/test_cli_and_dspy.py -k 'trainer_cycle_command or trainer_service_command' -q` -> `pass` (`2 passed`)
- `uv run pytest tests/test_utilities.py -k 'trainer_k8s or run_trainer_candidates or run_trainer_cycle or run_trainer_service' -q` -> `pass` (`10 passed, 28 deselected`)
- `uv run pytest tests/test_cli_and_dspy.py -k 'trainer_k8s_manifests or trainer_cycle_command or trainer_service_command' -q` -> `pass` (`3 passed, 29 deselected`)
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` -> `pass` (`41 passed`)
- `uv run repo-rag smoke-test` -> `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`
- `make files-sync` -> `pass`
- `make verify-surfaces` -> `pass`
- `bash -n deploy_repo_rag_trainer.sh && uv run pytest tests/unit/test_deploy_repo_rag_trainer_script.py -q` (in sibling `dataset`) -> `pass` (`4 passed`)

Focused regression now covered:

- one prompt family can now contain multiple context groups in `champion-index.json`
- only one family champion is materialized into `training-candidates.yaml`
- replaying unchanged imported traces no longer implies new compile work
- repeated same-answer traces inside one context group now increase champion support instead of
  being counted only as anonymous group volume
- gradual source drift inside one prompt family now updates the existing context-group summary
  instead of forcing a new context group whenever the retrieval sources shift slightly
- same-source traces with clearly different retrieved snippets can now split into separate context
  groups because grouping also uses snippet-level evidence fingerprints, not only source paths
- family champions now resist small score-only flips across context groups until a challenger
  either clears the score delta or wins on support/evidence tie-breaks
- trainer recompilation can now be intentionally batched behind a minimum new-candidate threshold
  instead of recompiling immediately on every single family-champion change
- trainer deployment manifests plus the sibling `dataset` AKS deploy helper now preserve that same
  batching threshold instead of silently dropping back to per-cycle recompilation in live deploys
- legacy worker-only expected sources remain stripped from trainer-candidate rows

## Limits

This first stage does **not** yet solve every context-drift problem.

Still deferred:

- chunk-hash-aware context grouping
- evidence-summary semantic similarity
- multi-answer compile datasets for one visible question
- exemplar-memory retrieval of similar historical traces at runtime

Still not covered by a current-turn deployment check:

- no live AKS redeploy or end-to-end trainer rollout was rerun after adding
  `TRAINER_MIN_NEW_CANDIDATES_FOR_RECOMPILE` to the deployment surfaces; current evidence for that
  piece is local manifest/script verification only

What this stage does solve immediately:

- parallel or repeated worker traces for the same prompt no longer automatically overwrite the
  trainer compile example by arrival order alone
- trainer-side recompile gating now keys off meaningful family-champion change instead of raw trace
  replay
