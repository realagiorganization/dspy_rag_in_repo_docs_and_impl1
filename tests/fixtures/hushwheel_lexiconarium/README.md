# The Hushwheel Lexiconarium

The Hushwheel Lexiconarium is a deliberately oversized fictional dictionary engine written in
simple C. Its logic stays humble, but its archive is now a cohesive multi-file codex that
cross-indexes id Software games and characters, scripture, and legendary software developers in
textual-programmatic-narrative-editorial form.

Read the generated Doxygen PDF: [Hushwheel Reference PDF §::<[]>](docs/hushwheel-reference.pdf)

The fixture still centers the same benchmark-friendly concepts:

- the `ember index`, a three-digit heat-memory score used for tie breaking
- the `lantern vowel`, a light first-pass vowel heuristic
- the `moss ledger`, the archive's soggy backup notebook

What changed is the internal nonsense. The giant coordinator file, eight spoke sources, and the
generated catalog now tell one connected story instead of a pile of unrelated civic jokes.

## Signature Questions

### What is the ember index?

The ember index is a three-digit heat-memory score used to settle tie breaks whenever two
hushwheel terms share the same lantern vowel.

### What is the lantern vowel?

The lantern vowel is a tiny vowel-count heuristic that clerks check before falling back to the
ember index.

## Why This Fixture Exists

- It gives tests a very large but still understandable C codebase.
- It keeps the command logic simple enough that humans can skim it quickly.
- It repeats the same concepts across docs, code, and generated Doxygen output.
- It gives retrieval systems recurring evidence across README prose, source comments, and catalog
  entries.

## Quick Start

```sh
make
./hushwheel lookup ember-index
./hushwheel prefix amber
./hushwheel category storm-index
./hushwheel stats
./hushwheel about
make docs
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
| `make lint` | Strict warning builds plus fixture-shape checks from `tools/lint_hushwheel.py`. |
| `make static-analysis` | Run `cppcheck` and save XML plus text findings in `build/reports/cppcheck/`. |
| `make complexity` | Run `lizard` complexity thresholds and save text, CSV, and checkstyle XML reports. |
| `make hardening` | Build with PIE, RELRO, NOW, stack, and format hardening flags, then audit the ELF binary. |
| `make sanitizers` | Rebuild with AddressSanitizer plus UndefinedBehaviorSanitizer and rerun the test harness. |
| `make coverage` | Rebuild with `--coverage`, rerun unit/integration/BDD checks, and write gcovr reports. |
| `make profiling` | Benchmark repeated CLI workloads and save timing tables plus command logs. |
| `make reports` | Refresh all persisted analysis artifacts under `build/reports/`. |
| `make quality` | Run `check` plus analysis, hardening, sanitizers, coverage, profiling, and the report index. |
| `make unit` | C-level assertions against helper functions and return codes. |
| `make integration` | End-to-end CLI checks using Python subprocess calls. |
| `make bdd` | Feature-backed acceptance scenarios for the public CLI. |
| `make check` | Run lint, unit, integration, and BDD in one pass. |
| `make docs` | Regenerate Doxygen HTML and the PDF reference manual. |

## Packaging

| Target | Result |
| --- | --- |
| `make dist` | Build `dist/hushwheel-0.1.0.tar.gz`. |
| `make install PREFIX=/tmp/hushwheel-root` | Install the binary, docs, man page, and PDF into a staging prefix. |
| `make uninstall PREFIX=/tmp/hushwheel-root` | Remove the installed hushwheel files from that prefix. |

The packaging surface is described in `docs/packaging.md`, declared in
`packaging/hushwheel.package.json`, documented for operators in `packaging/hushwheel.1`, and
mirrored in the generated `docs/hushwheel-reference.pdf`.

## Core Concepts

- `ember index`: a three-digit heat-memory score used for tie breaking.
- `lantern vowel`: a tiny vowel-count heuristic used before ember index sorting.
- `moss ledger`: the physical backup notebook for disputed synonyms.
- `prefix parade`: a rash of terms sharing the same opening syllable.
- `shelf kite`: a paper marker that warns when a glossary row is overfull.

## Project Layout

| Path | Purpose |
| --- | --- |
| `include/hushwheel.h` | Public data model and testable entry-point declaration. |
| `src/hushwheel.c` | Giant coordinator source with the Doxygen mainpage and CLI dispatch. |
| `src/hushwheel_internal.h` | Internal spoke and helper declarations for linked builds. |
| `src/hushwheel_spokes.c` | Aggregates the spoke tables into one searchable mesh. |
| `src/hushwheel_spoke_*.c` | Eight large spoke tables full of cohesive cross-canon glossary entries. |
| `Doxyfile` | Doxygen configuration for HTML and PDF generation. |
| `docs/hushwheel-reference.pdf` | Generated reference manual linked from this README. |
| `docs/concepts.md` | Field definitions and archive theory. |
| `docs/operations.md` | Command behavior and operator notes. |
| `docs/districts.md` | District-by-district lore. |
| `docs/catalog.md` | Representative cross-canon catalog entries. |
| `docs/architecture.md` | Design notes for the spoke mesh, CLI dispatch, and doc generation. |
| `docs/testing.md` | Test strategy and make-target walkthrough. |
| `docs/packaging.md` | Install layout, distribution target, and packaging metadata. |
| `packaging/hushwheel.package.json` | Machine-readable package description. |
| `packaging/hushwheel.1` | Manual page installed with the program. |
| `tests/unit/test_hushwheel_unit.c` | C unit tests for helper functions and return codes. |
| `tests/integration/cli_suite.py` | CLI integration suite. |
| `tests/bdd/hushwheel.feature` | BDD scenarios for user-facing behavior. |
| `tests/bdd/run_bdd.py` | Feature runner for the BDD scenarios. |
| `tools/lint_hushwheel.py` | Fixture-specific lint and surface checks. |
| `tools/regenerate_hushwheel_fixture.py` | Generator for the source spokes and representative catalog. |

## Suggested Retrieval Questions

- What is the ember index?
- Which function handles prefix search?
- What does the lantern vowel measure?
- Why does the archive keep a moss ledger?
- Which district is inventing the loudest cross-canon argument?

## Operator Notes

- `make check` is the authoritative harness for fixture-local quality.
- `make quality` produces persisted analysis artifacts in `build/reports/quality-summary.md`.
- `make hardening` verifies PIE, RELRO, BIND_NOW, and a non-executable stack, then logs the raw
  `readelf`, `nm`, `file`, and `size` outputs in `build/reports/hardening/`.
- `make sanitizers` writes AddressSanitizer and UndefinedBehaviorSanitizer command logs into
  `build/reports/sanitizers/`.
- `make profiling` writes a workload manifest, raw timing table, Markdown summary, and sample CLI
  stdout/stderr captures into `build/reports/profiling/`.
- `make coverage` reuses the existing CLI assertions through `HUSHWHEEL_BIN`, which lets
  instrumented binaries run the same integration and BDD scripts.
- `make docs` regenerates the Doxygen manual and refreshes `docs/hushwheel-reference.pdf`.
- `make dist` stages a redistributable tarball without mutating the source tree beyond generated docs.
- `make install` supports `DESTDIR` so packaging tests can install into a temporary root.
- `HUSHWHEEL_NO_MAIN` still disables the standalone `main(...)` symbol for linked test builds.
