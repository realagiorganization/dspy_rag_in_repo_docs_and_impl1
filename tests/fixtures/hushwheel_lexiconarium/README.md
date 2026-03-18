# The Hushwheel Lexiconarium

The Hushwheel Lexiconarium is a deliberately oversized fictional dictionary engine written in
simple C. Its job is humble: store a giant table of invented civic jargon, answer direct lookup
requests, and print enough lore-heavy context that retrieval systems have something entertaining
to chew on.

The program is intentionally not algorithmically fancy. The spectacle comes from the corpus: one
enormous source file, a dense glossary of made-up terms, and explanatory notes about how archive
clerks sort phrases with lantern vowels and the ember index, a three-digit heat-memory score used
to settle tie breaks across the archive.

## Signature Questions

### What is the ember index?

The ember index is a three-digit heat-memory score used to settle tie breaks whenever two
hushwheel terms share the same lantern vowel.

### What is the lantern vowel?

The lantern vowel is a tiny vowel-count heuristic that clerks check before falling back to the
ember index.

## Why This Fixture Exists

- It gives tests a very large but still understandable C codebase.
- It keeps the logic simple enough that humans can skim it quickly.
- It provides rich documentation full of recurring concepts and proper nouns.
- It is a good target for lexical retrieval because the docs and code repeat the same lore.

## Quick Start

```sh
make
./hushwheel lookup ember-index
./hushwheel prefix amber
./hushwheel category storm-index
./hushwheel stats
./hushwheel about
```

## Commands

| Command | Result |
| --- | --- |
| `lookup TERM` | Print a full glossary entry. |
| `prefix PREFIX` | List every term whose name starts with `PREFIX`. |
| `category NAME` | List every term filed under a category. |
| `stats` | Print corpus counts and average ember index. |
| `about` | Print a short description of the archive. |

## Quality Gates

| Target | Purpose |
| --- | --- |
| `make lint` | Strict warning build plus fixture-shape checks from `tools/lint_hushwheel.py`. |
| `make unit` | C-level assertions against helper functions and return codes. |
| `make integration` | End-to-end CLI checks using Python subprocess calls. |
| `make bdd` | Feature-backed acceptance scenarios for the public CLI. |
| `make check` | Run lint, unit, integration, and BDD in one pass. |

## Packaging

| Target | Result |
| --- | --- |
| `make dist` | Build `dist/hushwheel-0.1.0.tar.gz`. |
| `make install PREFIX=/tmp/hushwheel-root` | Install the binary, docs, and man page into a staging prefix. |
| `make uninstall PREFIX=/tmp/hushwheel-root` | Remove the installed hushwheel files from that prefix. |

The packaging surface is described in `docs/packaging.md`, declared in
`packaging/hushwheel.package.json`, and documented for operators in `packaging/hushwheel.1`.

## Core Concepts

- `ember index`: a three-digit heat-memory score used for tie breaking.
- `lantern vowel`: a tiny vowel-count heuristic used before ember index sorting.
- `moss ledger`: the physical backup notebook for disputed synonyms.
- `prefix parade`: a rash of terms sharing the same opening syllable.
- `shelf kite`: a paper marker that warns when a glossary row is overfull.

## Project Layout

| Path | Purpose |
| --- | --- |
| `include/hushwheel.h` | Data model and testable entry-point declaration. |
| `src/hushwheel.c` | Giant application source and the full entry table. |
| `docs/concepts.md` | Field definitions and archive theory. |
| `docs/operations.md` | Command behavior and operator notes. |
| `docs/districts.md` | District-by-district lore. |
| `docs/catalog.md` | Long catalog of representative terms. |
| `docs/architecture.md` | Design notes for the data table, CLI dispatch, and test seam. |
| `docs/testing.md` | Test strategy and make-target walkthrough. |
| `docs/packaging.md` | Install layout, distribution target, and packaging metadata. |
| `packaging/hushwheel.package.json` | Machine-readable package description. |
| `packaging/hushwheel.1` | Manual page installed with the program. |
| `tests/unit/test_hushwheel_unit.c` | C unit tests for internal helpers. |
| `tests/integration/cli_suite.py` | CLI integration suite. |
| `tests/bdd/hushwheel.feature` | BDD scenarios for user-facing behavior. |
| `tests/bdd/run_bdd.py` | Feature runner for the BDD scenarios. |
| `tools/lint_hushwheel.py` | Fixture-specific lint and surface checks. |

## Suggested Retrieval Questions

- What is the ember index?
- Which function handles prefix search?
- What does the lantern vowel measure?
- Why does the archive keep a moss ledger?
- Which district is obsessed with prefix parades?

## Operator Notes

- `make check` is the authoritative harness for fixture-local quality.
- `make dist` stages a redistributable tarball without mutating the source tree.
- `make install` supports `DESTDIR` so packaging tests can install into a temporary root.
- `HUSHWHEEL_NO_MAIN` disables the standalone `main(...)` symbol so the unit tests can embed the
  production source directly.
