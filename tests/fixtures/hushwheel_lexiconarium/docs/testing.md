# Hushwheel Testing

The hushwheel fixture now carries a full verification and instrumentation stack:

## Lint

`make lint` compiles every source file with strict warnings and runs `tools/lint_hushwheel.py` to
check text surfaces, target markers, README references, and the Doxygen mainpage block.

## Static Analysis

`make static-analysis` runs `cppcheck` with exhaustive style, portability, performance, and warning
checks, then writes both XML and GCC-style text reports into `build/reports/cppcheck/`.

## Complexity

`make complexity` runs `lizard` against the coordinator, spokes, headers, and C unit test with
thresholds for cyclomatic complexity, function length, and parameter count. The persisted outputs
live in `build/reports/complexity/`.

## Hardening

`make hardening` rebuilds hushwheel with hardened compile and link flags, reruns the unit,
integration, and BDD harnesses against that binary, then persists `file`, `size`, `readelf`, and
`nm` outputs under `build/reports/hardening/`. The target fails if PIE, RELRO, BIND_NOW, or a
non-executable stack are missing from the emitted ELF metadata.

## Sanitizers

`make sanitizers` rebuilds hushwheel with AddressSanitizer and UndefinedBehaviorSanitizer, reruns
the same harness surfaces, and saves the command logs plus sanitizer environment details under
`build/reports/sanitizers/`.

## Unit

`tests/unit/test_hushwheel_unit.c` now links against the split production sources instead of
including the implementation directly. The build defines `HUSHWHEEL_NO_MAIN` so the coordinator can
participate in the link without exporting a duplicate `main(...)`.

## Integration

`tests/integration/cli_suite.py` treats hushwheel like a built executable and checks lookup,
prefix, category, stats, and about behavior. The runner accepts `HUSHWHEEL_BIN` so coverage or
other instrumented builds can reuse the same assertions.

## BDD

`tests/bdd/hushwheel.feature` and `tests/bdd/run_bdd.py` keep the operator-facing command stories
aligned with the compiled program. Like the integration suite, the runner accepts `HUSHWHEEL_BIN`
for instrumented builds.

## Coverage And Reports

`make coverage` rebuilds hushwheel with `--coverage`, reruns the unit, integration, and BDD
surfaces, and writes gcovr text, XML, HTML, JSON, and Markdown summary reports under
`build/reports/coverage/`. The coverage report intentionally excludes the generated
`src/hushwheel_spoke_*.c` tables and `src/hushwheel_spokes.c`, because those files are data-heavy
catalog surfaces rather than executable control-flow logic.

## Profiling

`make profiling` runs a repeated CLI workload against an instrumented binary, records per-scenario
wall-clock timings in `build/reports/profiling/runtime-profile.tsv`, and writes a Markdown report
plus sample stdout and stderr captures for the profiled commands.

## Documentation

`make docs` runs Doxygen, builds the LaTeX output with `lualatex`, and refreshes
`docs/hushwheel-reference.pdf`.

## Combined Gate

`make reports` refreshes all persisted analysis artifacts and writes
`build/reports/quality-summary.md`. `make quality` is the CI-facing superset that runs `check`
plus static analysis, complexity, hardening, sanitizers, coverage, profiling, and the aggregated
report surface in one pass.
