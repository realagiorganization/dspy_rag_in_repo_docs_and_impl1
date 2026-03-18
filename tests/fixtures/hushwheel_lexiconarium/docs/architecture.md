# Architecture Notes

The Hushwheel Lexiconarium is intentionally structured like a tiny old-school C utility:

- `ENTRY_TABLE` is a giant compile-time array of `GlossaryEntry` records.
- lookups, prefix scans, and category scans are plain linear loops over that array.
- `hushwheel_main(...)` acts as the public entry point so tests can exercise CLI dispatch without
  spawning a subprocess.

## Core Components

| Component | Role |
| --- | --- |
| `GlossaryEntry` | Declares the term, category, district, ember index, summary, and usage text. |
| `find_entry(...)` | Resolves exact term matches. |
| `print_prefix_matches(...)` | Performs prefix search over the full table. |
| `print_category_matches(...)` | Emits every entry filed under a category. |
| `print_stats(...)` | Reports entry, category, district, and average ember totals. |
| `print_about(...)` | Explains the fixture's purpose in human terms. |

## Testing Seam

The production source now supports a deliberate embed mode:

- define `HUSHWHEEL_NO_MAIN`
- include `src/hushwheel.c` from a unit test translation unit
- call internal helpers directly because they remain in the same compilation unit

That keeps the shipped program simple while still allowing helper-level tests without refactoring
the giant fixture into a library.

## Why It Works Well For RAG

- The implementation is mechanically simple enough to summarize.
- The source file is large enough to force chunking and retrieval tradeoffs.
- The docs, header, tests, and packaging metadata repeat the same nouns with different framing.
