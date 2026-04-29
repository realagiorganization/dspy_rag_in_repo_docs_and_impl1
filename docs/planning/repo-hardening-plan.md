# Repository Hardening Plan

This checklist tracks the work needed to turn the current repository from a research-heavy
prototype into a cleaner, more reusable `repo-rag + DSPy program` runtime.

## Scope

- `repo-rag` remains a repository-grounded RAG and DSPy orchestration package.
- This repository does not become a model-weight training system in the first phase.
- The first target is a stable runtime, artifact, and integration contract.

## Status

- [x] Audit the current repository structure, authored docs, audit surfaces, and integration gaps.
- [x] Separate core authored docs from audit history, CI logs, generated inventories, and fixture docs.
- [x] Define the target documentation hierarchy under `docs/`.

## Phase 1. Repository Structure

- [x] Move authored DSPy, narrative, environment, guide, and checklist docs out of the root clutter and into `docs/`.
- [x] Finish updating every repo-local link, reference, and surface test to the new doc paths.
- [x] Remove any remaining active references to the former `documentation/` tree outside preserved historical evidence.
- [x] Decide that root-generated surfaces such as `FILES.md`, `FILES.csv`, and `TODO.MD` stay in the root for now and move only in a second cleanup pass if their workflows are generalized safely.

## Phase 2. Runtime Contract

- [x] Add a uniform machine-readable `--output json` contract for `ask`, `ask --use-dspy`, `ask-live`, `retrieval-eval`, and `dspy-artifacts`.
- [x] Normalize success, warning, and error payloads across CLI surfaces.
- [x] Define explicit artifact metadata for retrieval runs, DSPy runs, and future integration handoff.

## Phase 3. Retrieval Generalization

- [x] Remove repo-specific retrieval tuning from hardcoded logic where it should be profile-driven instead.
- [x] Generalize Rust lookup and lookup-first narrowing so they work cleanly against arbitrary repository roots.
- [x] Add a retrieval profile/config layer for source weighting, exclusions, and corpus policies.
- [x] Add a stronger retrieval option beyond lexical overlap, starting with embeddings or reranking.

## Phase 4. DSPy Artifact Model

- [x] Define a versioned `global bundle` format for compiled DSPy programs and runtime metadata.
- [x] Define a `local overlay` format for repo-specific retrieval state, examples, and worker-local adaptations.
- [x] Capture trace data in a stable schema that can feed later optimization work.
- [x] Add artifact inspection commands that expose bundle version, provenance, and benchmark status.

## Phase 5. Training And Optimization Surfaces

- [x] Keep DSPy compile/reload as the first optimization layer instead of pretending local weight training already exists.
- [x] Add trace export and trace import surfaces for asynchronous global optimization.
- [x] Add queued trace handoff surfaces so workers can stage optimization data without waiting on synchronous trainer-side import.
- [x] Add a single-pass trainer-cycle entrypoint that can be wrapped by cron or Kubernetes Jobs before a longer-lived trainer service exists.
- [x] Add a long-lived trainer-service loop that records trainer-side state/history while reusing the same publish/promote contract.
- [x] Materialize imported trace records into trainer-side DSPy candidate examples instead of leaving them only as raw ingestion artifacts.
- [x] Materialize a generated merged training set from the base corpus plus cumulative trainer-side candidates.
- [x] Add an explicit trainer-side recompilation surface that turns that generated merged training set into a fresh DSPy run.
- [x] Add bundle publish, promote, and rollback semantics for `stable` and `canary` versions.
- [x] Document the boundary between DSPy program optimization, retrieval quality work, and future model-level tuning.

## Phase 6. Verification

- [x] Add explicit integration coverage for LM-configured DSPy execution.
- [x] Add tests for the generalized repo-root mode and future JSON output contract.
- [x] Keep notebooks, CLI surfaces, and docs aligned around the same package helpers.
- [x] Refresh audit evidence after the hardening pass stabilizes.

## Exit Criteria

- [x] The repository layout is coherent enough that a new operator can find architecture, operations, plans, and evidence without scanning the root.
- [x] The main runtime surfaces are machine-consumable and documented.
- [x] Retrieval and DSPy artifacts are reusable across repositories, not only for this repository itself.
- [x] The repository is ready to act as a real worker-side runtime for `dataset`.
