# Hushwheel Testing

The hushwheel fixture has five verification layers:

## Lint

`make lint` compiles every source file with strict warnings and runs `tools/lint_hushwheel.py` to
check text surfaces, target markers, README references, and the Doxygen mainpage block.

## Unit

`tests/unit/test_hushwheel_unit.c` now links against the split production sources instead of
including the implementation directly. The build defines `HUSHWHEEL_NO_MAIN` so the coordinator can
participate in the link without exporting a duplicate `main(...)`.

## Integration

`tests/integration/cli_suite.py` treats hushwheel like a built executable and checks lookup,
prefix, category, stats, and about behavior.

## BDD

`tests/bdd/hushwheel.feature` and `tests/bdd/run_bdd.py` keep the operator-facing command stories
aligned with the compiled program.

## Documentation

`make docs` runs Doxygen, builds the LaTeX output with `lualatex`, and refreshes
`docs/hushwheel-reference.pdf`.
