# Rust SQLite Lookup Instructions

Use the Rust lookup path before DSPy when the task is really about locating likely files or exact
passages inside the tracked repository tree.

## Required Workflow

- `make ask QUESTION="..."` and `uv run repo-rag ask --question "..."` now perform this Rust
  lookup-first narrowing automatically before the broader repository retriever runs.
- Refresh the local SQLite index with `make rust-lookup-index` after tracked-file changes, or let
  `make rust-lookup QUERY="..."` refresh it automatically when stale.
- Start with short noun-phrase queries such as `dspy training`, `azure runtime`, or
  `file summaries`.
- Use `make rust-lookup QUERY="..."` or
  `cargo run --manifest-path rust-cli/Cargo.toml -- lookup "..."` to inspect direct path/content
  hits before `make ask-dspy`.
- Escalate to `make ask-dspy` only when the question needs DSPy synthesis across multiple hits
  instead of the default lookup-first answer path.

## Output Contract

- The index lives under the ignored path `artifacts/sqlite/repo-file-index.sqlite3`.
- Lookup output is ranked, line-oriented, and compact so agents can scan it quickly:
  `rank<TAB>path<TAB>lines=<n><TAB>score=<bm25><TAB>snippet`.
- The index only includes tracked UTF-8 text files below the size cap enforced by the Rust CLI.

## Maintenance Notes

- Keep this guide aligned with `rust-cli/src/main.rs`, the `Makefile`, and `README.md` whenever the
  lookup workflow changes.
- When this workflow changes materially, update `README.AGENTS.md` and the relevant audit note in
  `docs/audit/`.
