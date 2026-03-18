# 2026-03-18 Answer Synthesis Refresh

## Scope

- Added an explicit `Answer:` section to baseline `ask_repository(...)` output in
  `src/repo_rag_lab/workflow.py`.
- Ranked answer-summary highlights separately from raw retrieval order so the rendered summary
  prefers direct-answer chunks over question-list echoes.
- Updated notebook-facing and API-facing docs in `README.md`, `README.DSPY.MD`,
  `documentation/package-api.md`, and `utilities/README.md`.
- Added focused workflow coverage in `tests/test_workflow.py` and extended the research-playbook
  assertion in `tests/test_benchmarks_and_notebook_scaffolding.py`.
- Fixed root-`README.md` detection in `src/repo_rag_lab/retrieval.py` so the intended repo-summary
  source bonus still applies when the corpus is loaded with absolute paths.
- Moved pytest cache and coverage database outputs into `~/.cache` in `Makefile` so `make quality`
  remains stable when the worktree lives under `/tmp`.

## Verification

- `make hooks-install`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_workflow.py tests/test_workflow_live.py tests/test_repository_rag_bdd.py tests/test_hushwheel_fixture.py tests/test_benchmarks_and_notebook_scaffolding.py tests/test_utilities.py`
- `uv run pytest tests/test_hushwheel_program_surface.py tests/test_retrieval.py -q`
- `uv run repo-rag retrieval-eval --root . --top-k 4 --top-k-sweep 1,2,4,8`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make quality`

## Results

- `uv run repo-rag smoke-test` returned `answer_contains_repository: true`,
  `mcp_candidate_count: 1`, and `manifest_path: artifacts/azure/repo-rag-smoke.json`.
- `uv run pytest tests/test_hushwheel_program_surface.py tests/test_retrieval.py -q` passed with
  `10 passed`.
- `uv run repo-rag retrieval-eval --root . --top-k 4 --top-k-sweep 1,2,4,8` passed with
  `benchmark_count: 8`, `pass_rate: 1.0`, `average_source_recall: 1.0`, and `README.md` restored
  to rank `1` for the repository-summary case.
- `make quality` passed end-to-end with `136 passed` and `87.68%` total coverage.
- The retrieval gate passed with `benchmark_count: 8`, `pass_rate: 1.0`,
  `average_source_recall: 1.0`, and no threshold failures.

## Notes

- The remaining post-rebase regression was not in synthesis logic itself. The root cause was that
  `_is_root_readme(...)` only matched relative paths, while the live corpus loader uses absolute
  paths. Fixing that path check restored the expected repo-summary ordering without weakening the
  retrieval benchmark.
