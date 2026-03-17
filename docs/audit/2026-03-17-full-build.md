# Full Build Audit

- Audit date: `2026-03-17`
- Repository root: `/home/standard/dspy_rag_in_repo_docs_and_impl1`
- Git HEAD built locally: `d4cc6925ce47e5f19bd6faf91a6dc76cdbd1cf49`

## Summary

The repository was fully built with the repo-managed `make` targets after installing `uv` locally and redirecting `uv` and Cargo state into `/tmp`. The first `make hooks-install` attempt failed because `uv sync` ran out of space while extracting `nodejs-wheel-binaries` into `~/.cache/uv`. A second pass completed successfully with the same repo targets and a `/tmp`-backed environment. [first failure](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064722Z-full-build.raw.log#L51) [disk error detail](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064722Z-full-build.raw.log#L56) [redirected environment](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L6)

## Executed Commands

- `make hooks-install`: passed after creating the environment under `/tmp/dspy-rag-in-repo-venv` and installing the managed Git hooks. [env create](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L16) [hooks](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L238)
- `make utility-summary`: passed and reported the expected repository utility surfaces. [utility summary](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L246)
- `make quality`: passed. This covered compile, Ruff formatting and linting, notebook linting, mypy, basedpyright, surface verification, radon, pytest, and coverage threshold enforcement. [compile](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L258) [ruff](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L275) [mypy](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L281) [basedpyright](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L283) [surface verification](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L285) [pytest](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L303) [coverage threshold](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L342)
- `make smoke-test`: passed and produced the expected smoke manifest path plus one MCP candidate. [smoke test](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L369)
- `make build`: passed and produced both the sdist and wheel in `dist/`. [sdist](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L382) [wheel](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L383)
- `make rust-quality`: passed. `cargo fmt --check`, `cargo clippy`, `cargo build`, and the Rust CLI `ask` path all succeeded. [fmt/clippy](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L386) [cargo build](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L390) [cargo run](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L393) [CLI answer](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L396)

## Verification Status

Configured and executed in this turn:

- Lint: present and passed through Ruff for Python plus notebook code. [ruff](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L277) [nbqa](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L279)
- Type checking: present and passed through mypy and basedpyright. [mypy](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L282) [basedpyright](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L284)
- Coverage: present and passed at `92.86%` against the `85%` threshold. [coverage result](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L342)
- Tests: present and passed with `24` pytest cases. [pytest result](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L343)
- Packaging: present and passed for both Python distribution artifacts and the Rust CLI build path. [python build](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L379) [rust build](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L392)

Configured but not separately executed as standalone commands in this turn:

- `PYTHONPATH=src python3 -m pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`: not run as a separate targeted command because the broader `make quality` pytest run covered both files and the rest of the suite. [full pytest collection](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L309)

Absent or still not verified locally:

- UI or browser tests: none found in the repository configuration.
- Dedicated integration-test suite separate from the pytest surface: none found.
- Deployment validation against a live Azure endpoint: not executed in this turn; only the offline smoke manifest path was exercised. [smoke manifest](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log#L372)

## Artifacts

- Raw first-attempt log: [20260317T064722Z-full-build.raw.log](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064722Z-full-build.raw.log)
- Raw successful build log: [20260317T064833Z-full-build-attempt2.raw.log](/home/standard/dspy_rag_in_repo_docs_and_impl1/samples/logs/20260317T064833Z-full-build-attempt2.raw.log)
- Python build outputs: [dist/repo_rag_lab-0.1.0.tar.gz](/home/standard/dspy_rag_in_repo_docs_and_impl1/dist/repo_rag_lab-0.1.0.tar.gz) and [dist/repo_rag_lab-0.1.0-py3-none-any.whl](/home/standard/dspy_rag_in_repo_docs_and_impl1/dist/repo_rag_lab-0.1.0-py3-none-any.whl)
