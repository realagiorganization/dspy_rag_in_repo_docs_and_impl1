# Repository audit note for 2026-05-09 family-first MIPROv2 contract stage 2

## Scope

- Advance the stage-1 family-first contract from documentation plus initial trainer logic into the
  active proxy / trainer / bundle compatibility surfaces.
- Make `family_state` the preferred local interface while preserving `champion_*` aliases for
  live compatibility.

## Contract status in this turn

The repository now expresses the agreed family-first contract more directly in code:

1. Remote upload/fetch wrappers now expose `family_state` as the primary surface and mirror the
   same payload back through `champion_*` keys for compatibility.
2. Proxy prompt-family lookup now resolves one `family_state` path first and only keeps the old
   champion-named resolver as a wrapper alias.
3. Trainer summaries now emit:
   - `family_state_path`
   - `family_candidate_count`
   - `family_trace_record_paths`
   - `family_exact_snapshot_ids`
   - `family_record_hashes`
4. Bundle drift detection now compares family-state lineage first and falls back to older
   `champion_*` lineage fields when necessary.
5. Recompile lineage now preserves both family-state and champion-compatibility identifiers so
   later bundle stages can finish the migration without losing older state readers.

## Repository surfaces changed in this turn

- Updated planning source of truth:
  - `docs/planning/family-first-mipro-runtime-contract.md`
- Updated architecture narrative:
  - `docs/architecture/research-narrative.md`
- Updated runtime / trainer code:
  - `src/repo_rag_lab/runtime_artifacts.py`
  - `src/repo_rag_lab/training_samples.py`
  - `src/repo_rag_lab/utilities.py`
  - `src/repo_rag_lab/codex_proxy.py`
- Updated tests:
  - `tests/test_training_samples.py`
  - `tests/test_codex_proxy.py`

## What is implemented now

### 1. Family-state compatibility layer

The repository still persists the trainer state under `artifacts/trainer/champion-index.json`, but
the active helper layer now treats that file as family state:

- the file may advertise `family_state_kind`
- remote wrappers expose `family_state_path` first
- trainer summaries and bundle lineage now carry family-state fields directly

### 2. Family-state-first bundle drift checks

Trainer-side pending-recompile checks now prefer the family-state lineage lists:

- `family_trace_record_paths`
- `family_exact_snapshot_ids`
- `family_record_hashes`
- `prompt_family_ids`

Older bundle manifests that only expose `champion_*` lineage still remain readable.

### 3. Family-state-first proxy lookup

The proxy now resolves one family-state path, not one conceptual champion index. The old
champion-named resolver remains as a compatibility wrapper only.

## What is not implemented yet

The repository is still transitional:

- the persisted filename is still `champion-index.json`
- the live Azure deployment path still provisions champion-named compatibility storage
- per-family `MIPROv2` runtime artifacts are not yet published into the bundle
- the proxy still executes one global bundle program, not one family runtime artifact selected by
  family id
- post-run real `hits / total` enrichment is still not wired through the worker handoff path

## Verification executed in this turn

Repository-native checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_training_samples.py tests/test_utilities.py tests/test_codex_proxy.py tests/test_runtime_artifacts_azure.py -q`
  - `pass` (`85 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_repository_rag_bdd.py -q`
  - `pass` (`3 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test`
  - `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml`
  - `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run ruff check src/repo_rag_lab/codex_proxy.py src/repo_rag_lab/dspy_training.py src/repo_rag_lab/runtime_artifacts.py src/repo_rag_lab/training_samples.py`
  - `pass`

## Verification categories not executed in this turn

- repo-wide lint: not clean; existing unrelated failures remain in `mcp_server.py` and several
  test files outside the scope of this family-state change
- repo-wide type checking: not run
- coverage: not run
- notebook execution: not run
- dataset / AKS redeploy: not run

## Current conclusion

The repository now has a real stage-2 family-state layer:

- the contract is fixed in planning and architecture docs
- proxy / trainer / bundle lineage all prefer `family_state`
- compatibility `champion_*` fields still exist, but they are no longer the primary interface in
  the local code path

The next meaningful implementation step is no longer renaming. It is making trainer output and
bundle contents truly per-family:

- dirty-family `MIPROv2` recompilation
- family runtime artifacts inside the monolithic bundle
- proxy execution of those family runtime artifacts at runtime
