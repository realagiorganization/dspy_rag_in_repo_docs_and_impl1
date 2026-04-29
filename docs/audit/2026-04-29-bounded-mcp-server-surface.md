# 2026-04-29 Bounded MCP Server Surface

## Summary

This audit records the first real MCP transport surface in the repository. The repository no longer
stops at MCP discovery notes alone: it now exposes a bounded stdio MCP server through
`repo-rag serve-mcp` and `make serve-mcp`.

That server is intentionally narrow. It exposes only short-running tools:

- `ask_repo`
- `bundle_status`
- `dspy_artifacts`
- `publish_trace`

It explicitly does **not** route heavyweight work such as:

- `dspy-train`
- `trainer-recompile`
- `trainer-cycle`
- `trainer-service`
- `retrieval-eval`
- notebook execution

This closes the optional MCP planning gap without undermining the earlier architecture decision
that `dataset` should stay CLI-first for main runtime and trainer flows.

The follow-up hardening pass in the same turn also closed the final quality gaps that the new
surface exposed:

- fixed `mypy` and `basedpyright` regressions in `utilities.py`, `runtime_artifacts.py`,
  `mcp_server.py`, and the new MCP tests
- restored the strict `make quality` retrieval gate by rebalancing broad repository-summary
  ranking in `src/repo_rag_lab/retrieval.py`
- pushed `src/repo_rag_lab/mcp_server.py` to `99%` coverage and brought the repository-wide
  coverage gate back above the configured threshold

## Code And Documentation Changes

Changes landed in this repository:

- added the bounded MCP transport implementation in:
  - `src/repo_rag_lab/mcp_server.py`
- exposed the new surface in:
  - `src/repo_rag_lab/cli.py`
  - `src/repo_rag_lab/utilities.py`
  - `src/repo_rag_lab/verification.py`
  - `Makefile`
- added regression coverage in:
  - `tests/test_mcp_server.py`
  - `tests/test_cli_and_dspy.py`
  - `tests/test_utilities.py`
- added retrieval regression coverage in:
  - `tests/test_retrieval.py`
- rebalanced broad repository-summary ranking in:
  - `src/repo_rag_lab/retrieval.py`
- updated operator, architecture, planning, and integration docs in:
  - `README.md`
  - `docs/architecture/package-api.md`
  - `docs/architecture/mcp-discovery.md`
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
  - `docs/planning/repo-hardening-plan.md`
  - `docs/planning/dataset-integration-plan.md`
  - `docs/audit/README.md`
- updated `../dataset` operator docs to match that bounded MCP stance:
  - `../dataset/README.md`
  - `../dataset/USAGE.md`
  - `../dataset/agents.md`

No `../dataset` runtime code changed in this turn.

## Verification

Configured verification surfaces in this repository still include:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make files-sync`
- `make exploratorium-sync`
- `make verify-surfaces`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

Commands executed locally on `2026-04-29` for this turn:

- `uv run python -m compileall src tests`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `uv run pytest tests/test_mcp_server.py tests/test_cli_and_dspy.py tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run pytest tests/test_mcp_server.py tests/test_cli_and_dspy.py tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_azure_runtime.py tests/test_training_samples.py`
- `uv run pytest tests/test_mcp_server.py tests/test_utilities.py tests/test_retrieval.py tests/test_repository_rag_bdd.py`
- `uv run pytest tests/test_retrieval.py`
- `uv run repo-rag smoke-test`
- `uv run repo-rag retrieval-eval --root . --training-path samples/training/repository_training_examples.yaml --top-k 4 --top-k-sweep "1,2,4,8" --minimum-pass-rate 1.0 --minimum-source-recall 1.0 --output json`
- `make quality`

Observed results:

- `uv run python -m compileall src tests`: passed
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `uv run pytest tests/test_mcp_server.py tests/test_cli_and_dspy.py tests/test_utilities.py tests/test_repository_rag_bdd.py`:
  passed, `71 passed`
- `uv run pytest tests/test_mcp_server.py tests/test_cli_and_dspy.py tests/test_utilities.py tests/test_repository_rag_bdd.py tests/test_azure_runtime.py tests/test_training_samples.py`:
  passed, `85 passed`
- `uv run pytest tests/test_mcp_server.py tests/test_utilities.py tests/test_retrieval.py tests/test_repository_rag_bdd.py`:
  passed, `64 passed`
- `uv run pytest tests/test_retrieval.py`:
  passed, `11 passed`
- `uv run repo-rag smoke-test`:
  passed with `command_status: "success"` and `answer_contains_repository: true`
- `uv run repo-rag retrieval-eval --root . --training-path samples/training/repository_training_examples.yaml --top-k 4 --top-k-sweep "1,2,4,8" --minimum-pass-rate 1.0 --minimum-source-recall 1.0 --output json`:
  passed with `status: "pass"`, `pass_rate: 1.0`, `fully_covered_rate: 1.0`, and no threshold
  failures
- `make quality`:
  passed; `ruff`, `nbqa`, `mypy`, `basedpyright`, `verify-surfaces`, strict `retrieval-eval`,
  `radon`, and the full `pytest --cov` suite all completed successfully, with repository coverage
  at `85.19%`

Post-doc-sync commands executed after the documentation and audit updates:

- `make files-sync`
- `make exploratorium-sync`
- `make verify-surfaces`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

Observed post-sync results:

- `make files-sync`:
  passed and refreshed `FILES.md`, `FILES.csv`, and `AGENTS.md.d/FILES.md`
- `make exploratorium-sync`:
  passed and refreshed the exploratorium translation TeX, manifest, and PDF surfaces
- `make verify-surfaces`:
  passed with `issue_count: 0`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`:
  passed, `28 passed`

Verification categories not executed in this turn:

- `make coverage` as a standalone command
- live Azure/OpenAI round trips for this exact turn
- `../dataset` worker execution in this exact turn

## Status Impact

- The repository now has a real MCP transport, not just discovery heuristics.
- The MCP story is now aligned with the earlier architecture decisions instead of conflicting with
  them: bounded short calls go through MCP, while heavy runtime and trainer workflows stay on the
  direct CLI path.
- The `dataset` integration plan no longer has open ambiguity about whether MCP is required before
  the runtime is considered viable.
- The repository ended this turn fully green again under the configured local quality gates,
  including strict retrieval thresholds and coverage.
