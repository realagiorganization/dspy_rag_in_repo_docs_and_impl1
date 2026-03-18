# Retrieval Ranking Refresh Audit

- Audit date: `2026-03-18` (`Asia/Tbilisi`)
- Repository root: `/home/standard/dspy_rag_in_repo_docs_and_impl1_retrieval_clean`
- Git HEAD during verification: `da10ad70b3fc1e1971a2baf2c2d23ae1542dc112`

## Scope

This audit captures a retrieval-quality refresh to the baseline repository RAG path. The final
implementation keeps the existing path-aware ranking and source-diversity behavior, but changes the
chunker to preserve paragraph boundaries before falling back to fixed-width slices. The final
scorer also adds a definition bonus for `what is ...` questions and a penalty for chunks that only
echo the full question text. That was driven by a real regression caught in the hushwheel fixture:
the retriever needed to keep definition sections coherent enough to surface `heat-memory score` and
`lantern vowel` evidence for the question `What is the ember index?`. During final push validation,
this turn also hardened the pytest and fixture-doc build paths to use cache-backed temp directories
instead of the host's full `/tmp` tmpfs. The final branch state was then rebased onto the latest
`origin/master`, which already carried upstream fixes that made the utility-sync tests side-effect
free under git-hook execution.

## Executed Commands

Executed successfully in this turn:

- `make hooks-install`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `uv run pytest tests/test_retrieval.py tests/test_hushwheel_fixture.py tests/test_benchmarks_and_notebook_scaffolding.py tests/test_project_surfaces.py tests/test_cli_and_dspy.py tests/test_verification.py`
- `uv run repo-rag verify-surfaces`
- `uv run repo-rag retrieval-eval --root . --top-k 4 --top-k-sweep 1,2,4,8`
- `PRE_COMMIT_HOME=.pre-commit-cache uv run pre-commit run --all-files --hook-stage pre-push -v`
- `make coverage`
- `make quality`

## Notable Results

- `uv run python -m compileall src tests`: passed
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`: passed, `11` tests
- `uv run repo-rag smoke-test`: passed with `answer_contains_repository: true`,
  `mcp_candidate_count: 1`, and `manifest_path: artifacts/azure/repo-rag-smoke.json`
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- focused retrieval, hushwheel fixture, notebook, project-surface, CLI, and verification pytest
  slice: passed, `46` tests
- `uv run repo-rag verify-surfaces`: passed with `issue_count: 0`
- `uv run repo-rag retrieval-eval --root . --top-k 4 --top-k-sweep 1,2,4,8`: passed and reported:
  - default `top_k: 4`
  - `pass_rate: 1.0`
  - `fully_covered_rate: 1.0`
  - `average_source_recall: 1.0`
  - `average_source_precision: 0.5833333333333334`
  - `average_reciprocal_rank: 1.0`
  - `best_pass_rate_top_k: 4`
- `PRE_COMMIT_HOME=.pre-commit-cache uv run pre-commit run --all-files --hook-stage pre-push -v`:
  passed; mypy, basedpyright, coverage, and repository-surface verification all completed cleanly
- `make coverage`: passed with `119` tests and `87.98%` total coverage
- `make quality`: passed with `119` tests and `87.98%` total coverage

## Current Verification Status

Configured and verified in this turn:

- Compile checks: present and passed through `uv run python -m compileall src tests`
- Utility and baseline pytest slice: present and passed through
  `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- Repository smoke test: present and passed through `uv run repo-rag smoke-test`
- Rust build: present and passed through `cargo build --manifest-path rust-cli/Cargo.toml`
- Retrieval, hushwheel fixture, benchmark, notebook-scaffolding, project-surface, CLI, and
  verification tests: present and passed through the focused `uv run pytest ...` slice above
- Repository-surface verification: present and passed through `uv run repo-rag verify-surfaces`
- Retrieval-quality evaluation utility: present and passed through
  `uv run repo-rag retrieval-eval --root . --top-k 4 --top-k-sweep 1,2,4,8`
- Installed git-hook pre-push gate: present and passed through
  `PRE_COMMIT_HOME=.pre-commit-cache uv run pre-commit run --all-files --hook-stage pre-push -v`
- Full pytest and coverage gate: present and passed through `make coverage`
- Lint, notebook lint, mypy, basedpyright, complexity, full pytest, and coverage: present and
  passed through `make quality`

Still absent or not exercised in this turn:

- UI or browser tests: none found in repository configuration
- Full notebook execution batch: notebook lint and surface checks passed, but
  `make notebook-report` was not rerun end-to-end in this turn
- Live Azure OpenAI and Azure AI Inference probes: not rerun in this turn
- Post-push GitHub Actions evidence: not yet available before the push for this change set

## Notes

- The final retrieval change is the paragraph-aware chunker in `src/repo_rag_lab/retrieval.py`.
  It keeps concept definitions and similar prose blocks intact before splitting long paragraphs by
  width.
- The final scoring tweak also rewards definitional `term is ...` chunks for `what is ...`
  questions and penalizes chunks that merely repeat the entire question text.
- Path-aware ranking and source diversity remain in place, so docs and implementation files still
  outrank synthetic question-echo surfaces from `tests/`, `samples/`, and `data/`.
- The hushwheel fixture regression was caught locally during this turn and resolved before the
  final audit. The passing fixture tests confirm that the document question about the ember index
  again surfaces context containing both `heat-memory score` and `lantern vowel`.
- A stopword-filter scoring variant was explored and rejected in this turn because it improved the
  hushwheel probe but reduced the repository benchmark's top-4 source coverage. Paragraph-aware
  chunking fixed the real issue without sacrificing benchmark completeness.
- The root `Makefile` and the hushwheel fixture `Makefile` now route pytest and doc-build temp data
  through cache-backed directories under `$(HOME)/.cache`, which keeps the verification path stable
  even when `/tmp` is saturated on the host.
- The final rebased branch was validated against the current upstream hook configuration, so the
  push path no longer mutates tracked publication or inventory surfaces as a side effect of running
  the utility tests.
