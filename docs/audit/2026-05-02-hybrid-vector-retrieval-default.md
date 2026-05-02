# Hybrid Vector Retrieval Default

- Date: `2026-05-02`
- Scope: replace the repository-only lexical RAG baseline with a real Azure OpenAI embedding-backed
  semantic retrieval path while preserving safe lexical fallback
- Preceding note: `2026-05-02-live-trainer-still-not-publishing-bundles.md`

## Summary

The repository now has a real vector retrieval implementation instead of only lexical retrieval.

The new retrieval contract is:

1. lookup-first narrowing through Rust/SQLite FTS still runs first
2. lexical retrieval still exists as `lexical`
3. lexical reranking still exists as `idf-rerank`
4. new semantic retrieval now exists as `vector`
5. new hybrid retrieval now exists as `hybrid-vector`
6. the repo-local default profile now requests `hybrid-vector`
7. when semantic runtime is unavailable, retrieval falls back to `idf-rerank` and records an
   explicit warning instead of silently pretending vector retrieval ran

## Code Changes

Primary implementation surfaces:

- `src/repo_rag_lab/semantic_retrieval.py`
- `src/repo_rag_lab/retrieval.py`
- `src/repo_rag_lab/azure_runtime.py`
- `src/repo_rag_lab/workflow.py`
- `src/repo_rag_lab/dspy_training.py`
- `src/repo_rag_lab/benchmarks.py`
- `src/repo_rag_lab/cli.py`
- `src/repo_rag_lab/mcp_server.py`
- `config/retrieval-profile.json`

Important behavior changes:

- semantic retrieval now uses Azure OpenAI embeddings through:
  - `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME`
  - optional `AZURE_OPENAI_EMBEDDING_API_VERSION`
  - existing `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY`
- the repo now persists a local semantic chunk index at:
  - `artifacts/retrieval/semantic-index.json`
- ask-family results now include:
  - `retrieval_warnings`
- Codex mediation now inherits those retrieval warnings, so worker-side artifacts can show when
  semantic retrieval fell back to lexical ranking
- benchmark and notebook-facing retrieval quality summaries now report the **effective** retrieval
  mode after semantic fallback instead of only echoing the requested profile mode

## Verification

Repository-local checks executed in this turn:

- `uv run python -m compileall src tests` -> `pass`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py -q` -> `pass` (`40 passed`)
- `uv run pytest tests/test_retrieval.py tests/test_workflow.py tests/test_workflow_live.py tests/test_mcp_server.py tests/test_lookup_first.py tests/test_dspy_training.py tests/test_cli_and_dspy.py tests/test_benchmarks_and_notebook_scaffolding.py tests/test_project_surfaces.py tests/test_training_samples.py -q` -> `pass` (`137 passed`)
- `uv run repo-rag smoke-test` -> `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` -> `pass`
- `make files-sync` -> `pass`
- `make verify-surfaces` -> `pass`

## Limits

This note does **not** claim live Azure embedding retrieval was exercised end to end.

Specifically not verified in this turn:

- live `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME` round trips
- first-build latency or spend for `artifacts/retrieval/semantic-index.json`
- live worker-side AKS mediation using the new semantic retrieval mode

What is verified here is:

- code compiles
- retrieval/workflow/MCP fallback behavior is covered by local tests
- the repository default now requests `hybrid-vector`
