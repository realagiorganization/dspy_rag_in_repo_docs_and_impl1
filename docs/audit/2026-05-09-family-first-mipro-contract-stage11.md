# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 11

## Scope

- Stop trusting matched family runtime artifacts blindly when their validated `hit_rate` regresses
  below the current family baseline.
- Replace optimistic proxy-draft turn metrics with the final run outcome before turn traces are
  exported or queued for trainer ingestion.

## Contract status in this turn

The repository now advances the family-first contract in two connected ways:

1. Proxy family routing now checks the matched family artifact's validated `hit_rate` from the
   bundle registry against the current family baseline and refuses degraded family artifacts.
2. Worker-side batch handoff for proxy turn traces now rewrites each saved turn payload with the
   final run `execution_status`, `acceptance_status`, and post-run
   `mediation_metric_hits / mediation_metric_total` before `trace-export` / `trace-enqueue`.

This closes one important quality loop: the trainer no longer needs to learn from optimistic
"proxy mediation succeeded" draft metrics when the full `codex exec` run later failed.

## Repository surfaces changed in this turn

- Planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Architecture narrative:
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
- Proxy/runtime code:
  - `src/repo_rag_lab/codex_proxy.py`
  - `src/repo_rag_lab/runtime_artifacts.py`
- Proxy/runtime tests:
  - `tests/test_codex_proxy.py`
- Dataset worker code:
  - `../dataset/docker/prompt-executor/worker_execution_prompt.py`
- Dataset worker tests:
  - `../dataset/tests/unit/test_worker_execution_prompt_repo_rag_cli.py`

## What is implemented now

### 1. Family artifact use is now guarded by measured family quality

When bundle family registry data exposes both:

- the family baseline `hit_rate`
- the family runtime artifact validated `hit_rate`

the proxy now refuses that family artifact when the artifact score is lower than the family
baseline and falls back to fresh/global mediation for the turn.

### 2. Turn traces now carry the final run outcome, not proxy optimism

Proxy-local turn traces are still drafted during the run, but before worker-side batch export they
are rewritten with:

- final `execution_status`
- final `acceptance_status`
- final `accepted`
- final `mediation_metric_hits`
- final `mediation_metric_total`

for that completed `codex exec` result.

### 3. Batch summaries now expose the final turn-metric envelope

The worker-side batch manifest plus `trace-export-batch` / `trace-enqueue-batch` summaries now
also record:

- `execution_status`
- `acceptance_status`
- `metric_hits`
- `metric_total`

so later artifact review can see whether the whole turn batch was exported from a successful or a
failed run.

## What is not implemented yet

- dirty-family cycles still rebuild the global DSPy object after family artifact compile
- aggregate `family-state.json` / `champion-index.json` still remains beside the newer per-family
  replay-set mirror as a compatibility-backed source of truth
- complete removal of champion alias naming from repo and dataset wiring has not happened yet
- live AKS validation of the newer turn-metric enrichment and family-artifact gate has not been
  run

## Verification executed in this turn

Targeted checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_codex_proxy.py tests/test_runtime_artifacts_azure.py -q`
  - `pass` (`23 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/codex_proxy.py src/repo_rag_lab/runtime_artifacts.py tests/test_codex_proxy.py`
  - `pass`
- `cd ../dataset && pytest tests/unit/test_worker_execution_prompt_repo_rag_cli.py -q`
  - `pass` (`15 passed`)
- `cd ../dataset && python -m compileall docker/prompt-executor/worker_execution_prompt.py tests/unit/test_worker_execution_prompt_repo_rag_cli.py`
  - `pass`

Verification categories still not covered in this turn:

- notebook execution: not run in this turn
- coverage: not run in this turn
- live deployment / AKS validation: not run in this turn
- UI / browser verification: not applicable in-repo and not run

## Current conclusion

The family-first system now has a less misleading runtime/trainer boundary:

- matched family artifacts are no longer accepted blindly
- queued turn traces no longer pretend that proxy draft success equals final run success

The next highest-signal gap is now live validation: confirm in a real AKS run that the enriched
turn traces and family-artifact `hit_rate` gate both survive the end-to-end worker handoff path.
