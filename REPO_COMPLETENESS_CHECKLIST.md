# Repository Completeness Checklist

This document is the operational snapshot for the repository as of `2026-03-17`. Use it to answer two questions:

1. What is already complete and usable in the repository today?
2. How do you verify that state step by step without inventing ad hoc commands?

It is a checklist for the current scaffold, not a claim that every planned feature already exists.

## Current State Summary

The repository is currently a `uv`-first research scaffold for repository-grounded RAG. It already provides:

- a packaged Python CLI in `src/repo_rag_lab/cli.py`
- a `make` surface for the same workflows
- notebook playbooks under `notebooks/`
- MCP candidate discovery
- offline Azure deployment-manifest generation
- a thin Rust wrapper in `rust-cli/`
- repo-surface verification for the Makefile and notebooks

What is complete now:

| Area | State | Primary proof |
| --- | --- | --- |
| Environment and dependency management | Complete | `uv sync --extra azure` and `uv_build` are the standard path. |
| Baseline repository RAG workflow | Complete | `make ask`, `uv run repo-rag ask`, and `make smoke-test` work. |
| MCP discovery | Complete | `make discover-mcp` and the smoke test expose MCP candidates. |
| Azure manifest generation | Complete for offline handoff | `make azure-manifest` writes metadata into `artifacts/azure/`. |
| Notebook and Makefile contract checks | Complete | `make verify-surfaces` reports zero issues. |
| Python quality gates | Complete | `make quality` passes locally. |
| Rust wrapper build path | Complete | `cargo build --manifest-path rust-cli/Cargo.toml` passes locally. |
| GitHub Actions inspection helpers | Complete | `make gh-runs`, `make gh-watch`, and `make gh-failed-logs` are part of the Makefile contract. |

What is still incomplete by design or backlog:

- Automated DSPy training is not implemented yet.
- The DSPy CLI path is still optional and depends on separate LM configuration.
- Retrieval is still a lexical baseline, not an embeddings-based retriever.
- There are no UI or browser tests.
- There is no dedicated integration-test suite beyond the current pytest and smoke surfaces.
- There is no live Azure deployment validation in this repository.
- Notebook execution is not enforced in CI; notebook structure is enforced instead.

## Step-By-Step Verification Checklist

Run the checklist in order. If a step fails, stop there and treat the repo as incomplete for that layer.

1. Sync the managed environment.

   Command:

   ```bash
   uv sync --extra azure
   ```

   Pass when:

   - the lockfile resolves cleanly
   - the environment sync completes without fallback tooling

2. Install the managed Git hooks.

   Command:

   ```bash
   make hooks-install
   ```

   Pass when:

   - both `pre-commit` and `pre-push` hooks are installed

3. Confirm the user-facing surfaces exist.

   Commands:

   ```bash
   make utility-summary
   make gh-runs GH_RUN_LIMIT=5
   ```

   Pass when:

   - the utility summary lists the baseline repo workflows
   - recent GitHub Actions runs are visible through `gh`

4. Check the baseline repository question-answering path.

   Command:

   ```bash
   make ask QUESTION="What does this repository research?"
   ```

   Pass when:

   - the answer is repository-grounded
   - the answer references the repository's RAG purpose rather than generic filler

5. Check the discovery and smoke surfaces together.

   Commands:

   ```bash
   make discover-mcp
   make smoke-test
   ```

   Pass when:

   - MCP candidates are returned
   - the smoke test reports `answer_contains_repository: true`
   - the smoke test writes an Azure manifest path under `artifacts/azure/`

6. Verify the repository-surface contract.

   Command:

   ```bash
   make verify-surfaces
   ```

   Pass when:

   - `issue_count` is `0`
   - the Makefile includes the required targets
   - all notebooks satisfy the repository playbook rules

7. Run the Python acceptance gates.

   Command:

   ```bash
   make quality
   ```

   Pass when:

   - `python -m compileall src tests` passes
   - Ruff format and lint checks pass
   - `mypy` and `basedpyright` pass
   - repository-surface verification passes
   - Radon stays within the configured complexity gate
   - pytest passes with coverage at or above `85%`

8. Run the more explicit coverage report when you need a current coverage snapshot.

   Command:

   ```bash
   make coverage
   ```

   Pass when:

   - pytest passes
   - the total coverage report stays at or above `85%`

9. Verify build and packaging surfaces.

   Command:

   ```bash
   make build
   ```

   Pass when:

   - both the wheel and sdist are created under `dist/`

10. Verify the Rust wrapper path.

    Commands:

    ```bash
    cargo build --manifest-path rust-cli/Cargo.toml
    make rust-quality
    ```

    Pass when:

    - Cargo builds the wrapper
    - format, clippy, build, and Rust CLI invocation all pass

11. Check the notebooks as playbooks, not just as files.

    Manual verification:

    - each notebook has Markdown headings that explain the goal of each step
    - reusable logic lives in `src/`, not inline notebook cells
    - notebook outputs and logs point back to repository utilities where possible

12. Audit after each push.

    Commands:

    ```bash
    make gh-runs GH_RUN_LIMIT=10
    make gh-watch
    make gh-failed-logs RUN_ID=<run-id>
    ```

    Pass when:

    - the latest CI run completes successfully
    - a dated summary is written into `samples/logs/`

## Evidence Snapshot For This State

Local evidence collected on `2026-03-17`:

- `uv run python -m compileall src tests`: passed
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`: passed, `6` tests
- `uv run repo-rag smoke-test`: passed with `answer_contains_repository: true` and `mcp_candidate_count: 1`
- `make verify-surfaces`: passed with `issue_count: 0`
- `make quality`: passed with `38` tests and `88.07%` total coverage
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed

Recent same-day historical evidence:

- `docs/audit/2026-03-17-full-build.md` records successful `make build` and `make rust-quality`
- `docs/audit/2026-03-17-gh-actions-watch-loop.md` records successful `gh` inspection helpers and the aligned Makefile verification surface
- `samples/logs/20260317T083207Z-gh-runs-todo-backlog.md` records a successful `CI` run for the previous pushed commit

## Completeness Decision Rule

Treat the repository as complete for its current stated scope only when all of the following are true:

- steps `1` through `12` are either passed or intentionally marked not applicable
- the latest audit note under `docs/audit/` matches the current local evidence
- the backlog items in `TODO.MD` are understood as future work, not silently assumed to be done

Do not call the repository complete for DSPy training, live deployment, or UI-level validation. Those areas are still backlog, not hidden implementation.
