# RAG Guide For The Hushwheel Fixture

The hushwheel fixture is a deliberately oversized but mechanically simple C application under
`tests/fixtures/hushwheel_lexiconarium/`. It is useful for repository-grounded RAG because it
combines three traits that often matter in real codebases:

- one very large source file
- multiple documentation files that restate the same concepts in different language
- a mix of code questions, concept questions, and lore-heavy questions

The application itself is easy to understand. The retrieval problem is where the fun starts.

## What To Use

Use the fixture together with the shared sample suites:

| Path | Role |
| --- | --- |
| `tests/fixtures/hushwheel_lexiconarium/` | The target corpus: docs, header, and giant C source. |
| `samples/training/hushwheel_fixture_training_examples.yaml` | Benchmark-style questions with expected sources. |
| `samples/population/hushwheel_fixture_population_candidates.yaml` | Initial staged-ingestion plan for the fixture corpus. |
| `notebooks/05_hushwheel_fixture_rag_lab.ipynb` | Executable playbook for retrieval experiments against the fixture. |

## Fast Start

First confirm the repository surfaces as usual:

```bash
make utility-summary
```

Then ask the existing CLI to treat the fixture as the retrieval root:

```bash
uv run repo-rag ask \
  --root tests/fixtures/hushwheel_lexiconarium \
  --question "What is the ember index?"
```

Try one concept question and one code question:

```bash
uv run repo-rag ask \
  --root tests/fixtures/hushwheel_lexiconarium \
  --question "How does print_prefix_matches handle prefix search?"
```

Those two questions exercise both retrieval regimes:

- documentation-heavy retrieval around `README.md` and `docs/concepts.md`
- implementation-heavy retrieval around `docs/operations.md`, `include/hushwheel.h`, and `src/hushwheel.c`

## Why The Fixture Works Well

The hushwheel corpus has deliberate redundancy. The same nouns recur across files:

- `ember index`
- `lantern vowel`
- `moss ledger`
- `print_prefix_matches`
- `GlossaryEntry`

That repetition makes lexical retrieval easy to inspect. When ranking shifts, you can usually tell
whether the retriever leaned toward top-level docs, the detailed catalog, or the code itself.

The giant `src/hushwheel.c` file is especially useful because it is large enough to force chunking
behavior to matter, but simple enough that a human can still reason about why a chunk matched.

## Benchmark Suite

The training sample file already encodes a practical fixture benchmark:

| Question shape | Expected evidence |
| --- | --- |
| Concept definition | `README.md`, `docs/concepts.md`, `src/hushwheel.c` |
| Command behavior | `docs/operations.md`, `src/hushwheel.c` |
| Header contract | `include/hushwheel.h` |

The current fixture suite is intentionally balanced:

- concept questions keep documentation retrieval honest
- code questions force the retriever to surface C and header evidence
- command questions test whether comments and docs agree with implementation

If you expand the suite, prefer user-visible questions over internal helper trivia.

## Population Strategy

Start the corpus with:

1. `README.md`
2. `docs/concepts.md`
3. `docs/operations.md`
4. `src/hushwheel.c`

Then widen the population with:

1. `include/hushwheel.h`
2. `docs/catalog.md`
3. `docs/districts.md`

That order keeps early experiments readable while still leaving enough long-tail lore for retrieval
to become interesting once the basics are stable.

## Notebook Workflow

Open `notebooks/05_hushwheel_fixture_rag_lab.ipynb` when you want a guided run instead of ad hoc
questions. The notebook does not own retrieval logic itself. It delegates to the tested
`build_hushwheel_fixture_lab_context(...)` scaffold so the notebook, tests, and article all share
the same benchmark and corpus-plan inputs.

The notebook covers:

- fixture corpus scale and manifest inspection
- benchmark pass-rate review
- one concept answer and one code answer
- reranked population candidates
- notebook-run logging under `artifacts/notebook_logs/`

## Failure Modes Worth Watching

- If `README.md` dominates every result, the retriever may be over-valuing repeated glossary words.
- If `docs/catalog.md` crowds out `src/hushwheel.c`, the retriever may be matching term repetition
  without surfacing the actual implementation.
- If header questions stop retrieving `include/hushwheel.h`, check chunking and benchmark filtering
  before changing the question suite.
- If nested fixture roots produce zero benchmark hits, verify that benchmark filtering is working on
  root-relative paths rather than absolute ancestor paths.

## Suggested Next Experiments

- Compare direct `repo-rag ask --root ...` results with the notebook benchmark summary.
- Add a few adversarial questions whose keywords appear in both docs and code comments.
- Try narrower chunk sizes to see when the `print_prefix_matches` explanation becomes easier to rank.
