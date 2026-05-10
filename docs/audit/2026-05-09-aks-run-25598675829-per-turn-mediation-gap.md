# Repository audit note for 2026-05-09 AKS run 25598675829 per-turn mediation gap

## Scope

- Inspect the locally downloaded `../dataset/artifacts` bundle for execution `25598675829_20260509_103304`.
- Determine what worked, what failed, why token usage spiked, why no separate champion container appeared, and whether the observed `2` trace-like calls match the LLM self-loop.

## Live artifact summary

Artifacts inspected from `../dataset/artifacts`:

- `all_artifacts.tar.gz`
- `processed.tar.gz`
- `redis_results.json`
- `upload_summary.json`

The run succeeded overall:

- `success=true`
- `backend_used=codex_cli_repo_rag_proxy`
- `prompt_tokens=80519`
- `bundle_version=null`
- `acceptance_status=candidate`
- `trace_handoff_status=queued`

The artifacts uploaded successfully to:

- `execution-artifacts/executions/25598675829_20260509_103304`

The trusted trace handoff also succeeded for one queued item:

- `repo-rag-training-traces/queued/repo-rag-training/20260509T103302Z-prompts_debt_relief-p00000-cfc990.json`

## What worked

1. The worker used the local repo-RAG proxy path instead of the direct baseline path.
2. MCP discovery ran successfully inside the Codex session.
   - `search_repo`: `1`
   - `ask_repo`: `1`
3. The trace queue handoff succeeded into `repo-rag-training-traces`.
4. The container resumed the prior Codex session successfully.
   - `session_mode=resumed`
   - `resume_used=true`
   - `restore_status=restored`
5. The main task completed with a successful final Codex return code.

## What did not work

### 1. DSPy mediation did not load a bundle

The proxy status shows:

- `mediation_mode=rag_heuristic_dspy`
- `dspy_status=heuristic`
- `bundle_version=null`
- `program_path=null`

The recorded warning is explicit:

- `DSPy mediation was unavailable; using heuristic synthesis instead.`
- root cause: Azure `BlobNotFound`

So this run did **not** execute the intended bundle-backed DSPy mediation path. It fell back to heuristic RAG synthesis.

### 2. The live run did not produce per-turn trace artifacts

Expected stage-0 runtime surfaces from the current repository code include:

- `repo_rag_turn_traces/<batch>/...`
- `original_prompt`
- `reformulated_prompt`
- `command_trace`
- `turn_traces`
- `dspy_lm_model`

The downloaded live artifacts do **not** contain those runtime outputs:

- no `repo_rag_turn_traces/` directory in `all_artifacts.tar.gz`
- no archived `repo_rag_codex_proxy_payload.json`
- `repo_rag_trace.json` contains neither `original_prompt` nor `reformulated_prompt`
- `repo_rag_trace.json` contains no `command_trace`
- `repo_rag_trace.json` contains no `turn_traces`
- `repo_rag_codex_proxy_last.json` contains no `dspy_lm_model`

This means the live execution did **not** run the current per-turn export path that exists in the repository codebase.

### 3. No separate champion container was created

The user's observation is correct for this run.

The current repo-rag runtime code already has champion-container support:

- `src/repo_rag_lab/azure_artifacts.py`
- `src/repo_rag_lab/runtime_artifacts.py`

But the current dataset trainer deployment/bootstrap path still provisions only:

- trace container
- bundle container
- queue

It does **not** bootstrap a champion container in `../dataset/deploy_repo_rag_trainer.sh`.

So the absence of a live `repo-rag-champions` container is expected from the currently wired deploy path, even though champion-container support exists in repo-rag code.

## Token usage interpretation

The token spike is real, but the live artifacts do not support the theory that this came from per-turn DSPy mediation.

Observed values:

- current prompt tokens: `80519`
- previous resumed baseline prompt tokens: `31657`
- current run is `2.54348x` the previous resumed baseline

The more likely explanation from the transcript is:

1. the run resumed an existing Codex conversation;
2. Codex performed a long shell-heavy verification loop;
3. the session transcript grew large (`codex_response.txt` is about `910010` characters);
4. there was no successful bundle-backed DSPy path, so the extra cost was not buying the intended DSPy behavior.

## The observed `2` count does not mean two self-loop traces

The live artifacts show only **one** queued trace item for this run.

The visible `2` values come from other counters:

- `message_count=2` because the Discord prompt aggregated two messages
- `mcp_calls_started=2`
- `mcp_calls_completed=2`
- MCP tool counts:
  - `search_repo=1`
  - `ask_repo=1`

The Codex transcript itself shows a much larger internal loop:

- `user` blocks: `1`
- `codex` blocks: `11`
- `exec` calls: `19`
- `mcp` calls started: `2`

So the `2` does **not** correspond to “two prompt turns in the LLM self-query cycle.” It corresponds to two MCP tool calls, while the persisted trace handoff still remained a single run-level trace.

## Strongest live/runtime mismatch indicators

The current checked-in code would persist the missing fields and artifacts at:

- `src/repo_rag_lab/codex_proxy.py`
- `src/repo_rag_lab/runtime_artifacts.py`
- `../dataset/docker/prompt-executor/worker_execution_prompt.py`

But the live artifacts still show the older behavior:

- no per-turn batch directory
- no reformulated prompt in traces
- no helper-model identity field
- trace export still behaved like the old single-payload run-level handoff

This is strong evidence that the AKS run did not yet execute the fully updated live image/path intended by the current repository state.

## Verification executed in this turn

Artifact inspection commands:

- `tar -tzf ../dataset/artifacts/all_artifacts.tar.gz`
  - `pass`
- `tar -tzf ../dataset/artifacts/processed.tar.gz`
  - `pass`
- `python -m json.tool ../dataset/artifacts/redis_results.json`
  - `pass`
- `python -m json.tool ../dataset/artifacts/upload_summary.json`
  - `pass`
- targeted Python inspection of `repo_rag_*` JSON payloads inside `all_artifacts.tar.gz`
  - `pass`
- targeted transcript counting of `codex_response.txt`
  - `pass`

Repository-native checks:

- `uv run python -m compileall src tests`
  - `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q`
  - `pass` (`44 passed`)
- `uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`

## Verification categories not executed in this turn

- lint: not run
- type checking: not run
- coverage: not run
- notebook execution: not run
- AKS redeploy: not run
- live Azure Blob listing for champion container: not run in this turn

## Current conclusion

This run proves that:

1. the proxy path is live;
2. one run-level trace is still being queued;
3. bundle-backed DSPy mediation did not activate;
4. per-turn prompt reformulation + per-turn trace capture did not make it into the live runtime path for this execution;
5. the champion container is still not provisioned by the active deployment/bootstrap wiring.

So the user-visible behavior matches the artifacts:

- high token cost
- no champion container
- only one queued run-level trace
- two MCP calls, not two persisted self-loop traces
