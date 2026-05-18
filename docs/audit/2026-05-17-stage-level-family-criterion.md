# Stage-Level Prompt-Family Criterion

Date: `2026-05-17`

## Why this note exists

The repository needed one explicit written rule for judging whether prompt-family assignment is
correct. Earlier discussion mixed two different interpretations:

- workflow-level grouping
- stage-level semantic grouping

The active contract is now fixed explicitly as **stage-level semantic grouping**, or more
concretely: one family equals one stable semantic stage / code block.

## Contract

A prompt family is:

- one **stable semantic stage / code block**
- reusable across different workflows

A prompt family is **not**:

- one whole end-to-end workflow
- one user request from start to finish

This means:

- one workflow may legitimately populate multiple prompt families when it passes through multiple
  distinct stages
- two different workflows may legitimately populate the same prompt family when they reach the same
  stage

## Practical interpretation

The following are valid examples of distinct families even when they appear inside one broader
workflow:

- root objective / task reframing
- repo-state existence check
- semantic artifact validation
- rerun-versus-reuse decision
- constrained close-out without regeneration

Under this contract, family quality must be judged by asking:

- did trainer group traces by stable reusable stages?

and **not** by asking:

- did trainer collapse one workflow into one family?

## Implementation consequence

The already-adopted singleton-family ingestion path remains consistent with this contract:

- each imported trace is lifted into a temporary family-of-1
- trainer matches that singleton family against persisted families with symmetric family-to-family
  comparison
- assignment should converge on reusable stages, not workflow-local batches

## Scope of this turn

- documentation-only clarification
- no code-path changes
- no new verification run was required because executable surfaces did not change
