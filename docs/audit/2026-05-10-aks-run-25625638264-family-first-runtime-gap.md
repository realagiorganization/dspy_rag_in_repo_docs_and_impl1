# Repository audit note for 2026-05-10 AKS run 25625638264 family-first runtime gap

## Scope

- Inspect the locally downloaded run artifacts under `../dataset/artifacts` for the latest AKS
  pipeline run `25625638264_20260510_100640`.
- Verify what worked and what did not in the live `codex_cli_repo_rag_proxy` path after the
  `family-first` contract changes were pushed.
- Quantify whether the prompt-token growth came from live DSPy family mediation or from other
  transcript/session behavior.

## Artifact set inspected

- `../dataset/artifacts/upload_summary.json`
- `../dataset/artifacts/redis_results.json`
- `../dataset/artifacts/all_artifacts.tar.gz`
- `../dataset/artifacts/processed.tar.gz`

Relevant files inside `all_artifacts.tar.gz`:

- `execution_artifacts/prompt-worker-0-rehydrated/artifacts/prompts_debt_relief-p00000-cfc990/repo_rag_backend.json`
- `execution_artifacts/prompt-worker-0-rehydrated/artifacts/prompts_debt_relief-p00000-cfc990/repo_rag_codex_proxy_last.json`
- `execution_artifacts/prompt-worker-0-rehydrated/artifacts/prompts_debt_relief-p00000-cfc990/repo_rag_codex_proxy_payload.json`
- `execution_artifacts/prompt-worker-0-rehydrated/artifacts/prompts_debt_relief-p00000-cfc990/repo_rag_trace.json`
- `execution_artifacts/prompt-worker-0-rehydrated/artifacts/prompts_debt_relief-p00000-cfc990/repo_rag_trace_export.json`
- `execution_artifacts/prompt-worker-0-rehydrated/artifacts/prompts_debt_relief-p00000-cfc990/repo_rag_trace_enqueue.json`
- `execution_artifacts/prompt-worker-0-rehydrated/artifacts/prompts_debt_relief-p00000-cfc990/repo_rag_outcome.json`
- `execution_artifacts/prompt-worker-0-rehydrated/artifacts/prompts_debt_relief-p00000-cfc990/repo_rag_mcp_usage_summary.json`
- `execution_artifacts/prompt-worker-0-rehydrated/artifacts/prompts_debt_relief-p00000-cfc990/codex_response.txt`
- `execution_artifacts/prompt-worker-0-rehydrated/artifacts/prompts_debt_relief-p00000-cfc990/codex_session_state.json`

## Run summary

- `success=true`
- `backend_used=codex_cli_repo_rag_proxy`
- `execution_time=232.50768`
- `prompt_tokens=102024`
- `completion_tokens=0`
- `total_tokens=102024`
- `acceptance_status=candidate`
- `trace_handoff_status=queued`
- `bundle_version=null`

## What worked

### 1. The proxy-backed worker path was active

`repo_rag_backend.json` shows:

- `backend=codex_cli_repo_rag_proxy`
- `use_dspy_requested=true`
- `trace_exported=true`
- `trace_queued=true`
- `trace_handoff_status=queued`

### 2. Basic repo-RAG retrieval worked

The live mediation fell back to `rag_heuristic_dspy` with:

- `rag_status=success`
- sources `README.md`, `package-lock.json`, `package.json`, `tsconfig.json`

### 3. MCP was actually used by Codex

`codex_session_state.json` shows:

- `search_repo=2`
- `ask_repo=1`

So the worker did not bypass repo-RAG entirely.

### 4. The queue handoff succeeded

`repo_rag_trace_enqueue.json` shows:

- `queue_status=queued`
- `queue_item_path=queued/repo-rag-training/20260510T100639Z-prompts_debt_relief-p00000-cfc990.json`

## What did not work

### 1. The live DSPy bundle/family artifact path did not load

The strongest failure indicators are:

- `bundle_resolved=false`
- `bundle_version=null`
- `program_loaded=false`
- `program_path=null`
- `dspy_status=heuristic`
- warning contains Azure `BlobNotFound`

That means the run did not use a live family artifact from `repo-rag-bundles`; it fell back to
heuristic repo mediation.

### 2. The family-first trace contract is still missing in the live artifacts

The exported trace payload still uses the older run-level shape. The following expected family-first
fields are absent from `repo_rag_codex_proxy_payload.json` / queued trace payload:

- `original_prompt`
- `reformulated_prompt`
- `command_trace`
- `prompt_family_id`
- `family_artifact_hit_rate`
- `family_runtime_hit_rate`
- `mediation_metric_hits`
- `mediation_metric_total`

The tarball also contains no evidence of:

- `repo_rag_turn_traces/`
- `family-state`
- `father.json`
- `records/<snapshot>.json`
- `remote-family-state`

### 3. The queued training trace is still one giant run-level transcript

`repo_rag_trace_export.json` exported a single trace:

- `artifacts/traces/20260510T100506Z-worker-0-prompts_debt_relief-p00000-cfc990-realagiorganization_national-debt-relief.json`

That exported trace wraps the full `codex_response.txt` transcript inside the answer payload instead
of a compact per-turn family trace.

### 4. The current live path still has only one queued trace item for the whole run

There is one queued queue item under `queued/repo-rag-training/...json`, not a family-first batch of
multiple per-turn traces.

## Token growth analysis

## 1. The prompt growth is real, but not from live family DSPy

`codex_session_state.json` shows:

- current `prompt_tokens=102024`
- previous resumed baseline `baseline_prompt_tokens=80519`
- delta `+21505`
- delta ratio `+0.26708`

So compared with the immediate previous resumed run, the latest run is about `26.7%` larger, not a
small fluctuation.

## 2. The repo-RAG developer injection is not the main token sink

`repo_rag_codex_proxy_last.json` shows:

- `question_chars=3946`
- `question_lines=62`
- `developer_message_chars=1722`
- `developer_message_lines=22`

That is not small, but it is far too small to explain a `102024`-token run by itself.

## 3. The dominant bloat is the resumed Codex transcript/export path

`codex_response.txt` is:

- `103602` bytes
- `2815` lines

Its `STDERR` transcript alone is:

- `98696` bytes

The same large user prompt appears twice:

- one copy in the outer command payload
- one copy again in the resumed Codex transcript

The transcript also contains:

- `32` `exec` steps
- `6` `mcp: repo-rag` mentions
- `30` `package-lock.json` mentions
- repeated `package-lock.json` diff blocks even though the final stdout says no tracked changes were
  needed

`repo_rag_trace.json` also reports `answer_length=103544`, which matches the fact that the exported
training trace is essentially the whole large transcript.

## 4. Current conclusion about “лишний мусор”

Yes, the model is still carrying too much useless text, but the evidence in this run points much
more strongly to:

- resumed-session transcript carry-over
- exporting the entire `codex_response.txt` into the trace answer
- repeated shell/diff chatter

and not to the intended family-first DSPy mediation. The live family-first path did not activate, so
it cannot be the main source of the extra token spend in this run.

## Contract gap against the agreed family-first design

The live run still does not match the intended contract:

1. prompt arrives in proxy
2. prompt gets reformulated
3. proxy routes by family father / family registry from the bundle
4. family artifact is used when its validated hit rate beats the fallback path
5. fresh meditation is used only when no usable family artifact exists
6. compact per-turn traces are written and queued after the run

Instead, this run still behaved like:

1. large inbound prompt
2. heuristic repo-RAG developer injection
3. resumed Codex transcript growth
4. single run-level trace export
5. single queued trace item

## Verification executed in this turn

Repository-native checks run from the current repo root:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`45 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`

Additional artifact inspection commands were run locally against the downloaded tarballs and JSON
artifacts under `../dataset/artifacts`.

## Verification categories not run in this turn

- UI/browser verification
- coverage
- lint beyond the existing current repo state
- type checking
- notebook execution
- live Azure/AKS redeploy validation beyond the already downloaded artifact set

## Current conclusion

The latest AKS run succeeded operationally, but it did not exercise the intended family-first DSPy
runtime path. The live worker still fell back to heuristic repo mediation, exported one large
run-level transcript as the training trace, and queued only that single coarse trace item. The main
token bloat in this run is better explained by resumed Codex transcript accumulation and transcript
export verbosity than by DSPy family mediation.
