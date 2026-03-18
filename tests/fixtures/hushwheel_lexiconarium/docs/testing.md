# Testing Guide

The hushwheel fixture now has four verification layers that build on the same production source.

| Layer | Command | Scope |
| --- | --- | --- |
| Lint | `make lint` | Strict warning build plus fixture-shape checks. |
| Unit | `make unit` | Direct tests of helper functions and return codes in C. |
| Integration | `make integration` | Subprocess checks of the compiled CLI. |
| BDD | `make bdd` | Feature-backed acceptance scenarios for public behavior. |

## Full Harness

Run the full local harness with:

```sh
make check
```

That target executes the layers in this order:

1. compile the production source with stricter warning settings
2. validate project metadata and documentation surface
3. run the C unit test binary
4. run the CLI integration suite
5. run the BDD scenario runner

## Unit Strategy

`tests/unit/test_hushwheel_unit.c` defines `HUSHWHEEL_NO_MAIN` and includes the production source.
That lets the test call `starts_with(...)`, `lantern_vowel_count(...)`, `find_entry(...)`, and
`hushwheel_main(...)` directly without altering the shipped program shape.

## Integration Strategy

`tests/integration/cli_suite.py` treats hushwheel like an installed command:

- it runs `lookup`, `prefix`, `category`, `stats`, and `about`
- it verifies both success and error return codes
- it compares the stats output to `fixture-manifest.json`

## BDD Strategy

`tests/bdd/hushwheel.feature` describes operator-facing scenarios. The paired runner,
`tests/bdd/run_bdd.py`, executes each declared scenario against the built binary and fails if the
feature file and implementation drift apart.
