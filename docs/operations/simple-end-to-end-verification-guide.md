# Simple End-To-End Verification Guide

This is the shortest useful local proof that the repository is working end to end. It exercises the
lookup-first ask path, the repo-level smoke test, and the Makefile/notebook surface verifier without
requiring Azure credentials or a full `make quality` run.

## What The Three Main Commands Exercise

- [`make ask`](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/blob/master/Makefile#L65-L66)
  reaches the [`repo-rag ask` CLI wiring](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/blob/master/src/repo_rag_lab/cli.py#L72-L88)
  and then the
  [lookup-first retrieval path](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/blob/master/src/repo_rag_lab/workflow.py#L54-L72).
- [`make smoke-test`](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/blob/master/Makefile#L142-L143)
  reaches the
  [`run_smoke_test(...)` helper](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/blob/master/src/repo_rag_lab/utilities.py#L108-L124),
  which validates baseline answer generation, MCP discovery, and Azure manifest writing together.
- [`make verify-surfaces`](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/blob/master/Makefile#L153-L154)
  reaches
  [`run_surface_verification(...)`](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/blob/master/src/repo_rag_lab/utilities.py#L190-L193)
  over the
  [`verify_repository_surfaces(...)` contract](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/blob/master/src/repo_rag_lab/verification.py#L133-L146).

## Prerequisites

```bash
uv sync --extra azure
make hooks-install
```

The `azure` extra is still part of the standard sync because the shared CLI, tests, and smoke
surfaces import the same package graph even when this specific walkthrough stays local-only.

## Three-Command Walkthrough

1. Ask one repository question through the default lookup-first path:

```bash
make ask QUESTION="What does this repository research?"
```

Expected shape:

- the output starts with `Question:` and `Answer:`
- the output includes an `Evidence:` section because
  [`synthesize_answer(...)`](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/blob/master/src/repo_rag_lab/workflow.py#L119-L145)
  renders explicit supporting file hits

2. Run the compact end-to-end smoke test:

```bash
make smoke-test
```

Expected shape:

```json
{
  "answer_contains_repository": true,
  "mcp_candidate_count": 1,
  "manifest_path": "artifacts/azure/repo-rag-smoke.json"
}
```

3. Verify the committed repo surfaces:

```bash
make verify-surfaces
```

Expected shape:

```json
{
  "checked_makefile": "Makefile",
  "checked_notebook_count": 5,
  "issue_count": 0,
  "issues": []
}
```

## Optional Baseline I Use Before A Push

If you want the slightly broader local baseline that matches the repo's audit loop, run:

```bash
uv run python -m compileall src tests
uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py
cargo build --manifest-path rust-cli/Cargo.toml
```

Those commands cover syntax/import health, the utility-facing pytest slice, and the Rust wrapper
build without escalating to the heavier full-coverage gate.

## Fast Failure Triage

- If `make ask` returns weak evidence, inspect the native candidate pass first with
  [`make rust-lookup`](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/blob/master/Makefile#L248-L251)
  before moving to the DSPy path.
- If `make smoke-test` fails, inspect the three checks inside
  [`run_smoke_test(...)`](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/blob/master/src/repo_rag_lab/utilities.py#L108-L124):
  answer text, MCP discovery count, and smoke-manifest output.
- If `make verify-surfaces` reports issues, compare the
  [required target list](https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/blob/master/src/repo_rag_lab/verification.py#L11-L51)
  with the current `Makefile` and notebook headings.
