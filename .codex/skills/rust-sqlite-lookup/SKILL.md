---
name: rust-sqlite-lookup
description: Use the compact Rust SQLite lookup path before DSPy when repo questions need exact file hits, path discovery, or a cheap local evidence pass.
---

# Rust SQLite Lookup

Use this skill when a repo question is likely answerable by direct file/path lookup before any
DSPy synthesis step.

## Required Flow

1. Refresh the index with `make rust-lookup-index` when the tracked tree changed materially, or
   let `make rust-lookup QUERY="..."` refresh it on demand.
2. Run `make rust-lookup QUERY="..."` with terse evidence-oriented terms from the user request.
3. Read the direct hits first. If they answer the question, stay local.
4. Escalate to `make ask-dspy QUESTION="..."` only after the lookup pass when the task needs
   synthesis across multiple files rather than exact passages.

## Surfaces To Keep Aligned

- `rust-cli/src/main.rs`
- `rust-cli/Cargo.toml`
- `Makefile`
- `README.md`
- `README.AGENTS.md`
- `AGENTS.md`
- `AGENTS.md.d/RUST_LOOKUP.md`

## Validation

- `cargo build --manifest-path rust-cli/Cargo.toml`
- `cargo run --manifest-path rust-cli/Cargo.toml -- index`
- `cargo run --manifest-path rust-cli/Cargo.toml -- lookup "dspy training"`
- `uv run pytest tests/test_utilities.py tests/test_project_surfaces.py`
