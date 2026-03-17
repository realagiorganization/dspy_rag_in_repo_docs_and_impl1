# The Hushwheel Lexiconarium

The Hushwheel Lexiconarium is a deliberately oversized fictional dictionary engine written in
simple C. Its job is humble: store a giant table of invented civic jargon, answer direct lookup
requests, and print enough lore-heavy context that retrieval systems have something entertaining
to chew on.

The program is intentionally not algorithmically fancy. The spectacle comes from the corpus: one
enormous source file, a dense glossary of made-up terms, and explanatory notes about how archive
clerks sort phrases with lantern vowels, ember indexes, shelf kites, and tea abacuses.

## Why This Fixture Exists

- It gives tests a very large but still understandable C codebase.
- It keeps the logic simple enough that humans can skim it quickly.
- It provides rich documentation full of recurring concepts and proper nouns.
- It is a good target for lexical retrieval because the docs and code repeat the same lore.

## Commands

- `lookup TERM`: print a single glossary entry.
- `prefix PREFIX`: list matching terms and short summaries.
- `category NAME`: list every term filed under a category.
- `stats`: print corpus counts and average ember index.
- `about`: print a short description of the archive.

## Core Concepts

- `ember index`: a three-digit heat-memory score used for tie breaking.
- `lantern vowel`: a tiny vowel-count heuristic used before ember index sorting.
- `moss ledger`: the physical backup notebook for disputed synonyms.
- `prefix parade`: a rash of terms sharing the same opening syllable.
- `shelf kite`: a paper marker that warns when a glossary row is overfull.

## Directory Map

- `include/hushwheel.h`: data model and function declarations.
- `src/hushwheel.c`: the giant application source and full entry table.
- `docs/concepts.md`: field definitions and archive theory.
- `docs/operations.md`: command behavior and operator notes.
- `docs/districts.md`: district-by-district lore.
- `docs/catalog.md`: a long catalog of representative terms.

## Suggested Retrieval Questions

- What is the ember index?
- Which function handles prefix search?
- What does the lantern vowel measure?
- Why does the archive keep a moss ledger?
- Which district is obsessed with prefix parades?
