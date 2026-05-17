# 2026-05-17 Symmetric Singleton-Family Routing

- Scope: replace trainer-side prompt-family assignment based on directional `trace -> family`
  routing with a symmetric `singleton-family -> existing-family` comparison so near-duplicate
  operational traces stop fragmenting into separate one-record families.
- Preceding note: `2026-05-17-trainer-pending-cycle-recovery.md`

## Problem

- Live trainer output for batch `20260517T112909Z` successfully published all `15` traces into
  `repo-rag-training-families`, but the semantic grouping was still too fragmented:
  - `15` traces landed across `12` families
  - several one-record families represented near-identical repo-state inspection turns
- Root cause in source:
  - trainer assignment used `_find_or_create_prompt_family(...)` with a directional
    `_prompt_family_similarity(question, family_payload)` score
  - a new trace was compared as a plain question against an existing family summary
  - if that one-way score missed the `0.8` threshold, a new family was created immediately
  - once created, there was no merge pass to collapse the new singleton family back into a nearby
    existing family
- This made family assignment order-dependent and asymmetric:
  - `trace X -> family A` could fail
  - but later `family A -> family(X)` could score highly after the singleton family had its own
    prompt-profile terms and father question

## Source Fixes Landed

- `src/repo_rag_lab/training_samples.py`
  - added `_singleton_prompt_family_payload(...)` so every incoming trainer trace is first lifted
    into a temporary family-like structure with the same routing surfaces as persisted families
  - added `_family_profile_summary(...)` and `_family_routing_question(...)` helpers so family
    comparison reuses the same normalized summaries regardless of whether the family is persisted or
    temporary
  - added `_family_to_family_similarity(...)`, a symmetric trainer-side score that compares:
    - prompt-profile overlap
    - command/constraint overlap
    - best question similarity across family variants
    - shared anchor-term support
  - `_find_or_create_prompt_family(...)` now matches
    `singleton-family-of-new-trace -> existing-family` instead of `question -> existing-family`
  - the trainer-side family-assignment score no longer depends on one-sided target-family success
    priors during ingestion
- Trainer call sites now pass the full candidate record into `_find_or_create_prompt_family(...)`
  during:
  - legacy family-state seeding
  - normal `materialize_training_candidates(...)` replay ingestion

## Contract Update

Trainer ingestion now follows this sequence:

1. Normalize one imported trace into one trainer candidate record.
2. Build one temporary singleton family from that record.
3. Compare that singleton family against every existing family with one **symmetric**
   family-to-family similarity score.
4. If the best symmetric score is `>= 0.8`, merge the trace into that family.
5. Otherwise create a new persisted family.

This keeps the active routing threshold unchanged while removing the earlier asymmetry where a
fresh trace and a freshly created singleton family could produce materially different match scores.

## Verification

Checks executed in this turn:

- `UV_CACHE_DIR=/tmp/uvcache uv run python -m compileall src tests` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/test_training_samples.py tests/test_utilities.py tests/test_runtime_artifacts_azure.py tests/test_repository_rag_bdd.py -q` — `pass` (`122 passed`)
- `UV_CACHE_DIR=/tmp/uvcache uv run repo-rag smoke-test` — `pass`
- `cargo build --manifest-path rust-cli/Cargo.toml` — `pass`
- `UV_CACHE_DIR=/tmp/uvcache make quality` — `pass`
  - `ruff format --check` — `pass`
  - `ruff check` — `pass`
  - `nbqa ruff notebooks` — `pass`
  - `mypy` — `pass`
  - `basedpyright` — `pass`
  - `uv run repo-rag verify-surfaces` — `pass`
  - `uv run repo-rag retrieval-eval ... --minimum-pass-rate 1.0 --minimum-source-recall 1.0` — `pass`
  - coverage `81%`

Added regression:

- `test_materialize_training_candidates_uses_symmetric_singleton_family_matching`
  - two checkout/asset-inspection traces now merge into one family
  - one distinct live-wireframe baseline trace remains separate

Checks not executed in this turn:

- No new post-fix live AKS batch has been inspected yet after this family-assignment change.

## Current Status

- Trainer family assignment is no longer based on an asymmetric one-way `trace -> family` score.
- Near-duplicate operational traces now enter family matching as singleton families with the same
  structural surfaces as persisted families.
- Local verification is green through `make quality`; the remaining validation step is a fresh live
  batch proving that this change reduces the singleton-family explosion seen in the
  `20260517T112909Z` publish.
