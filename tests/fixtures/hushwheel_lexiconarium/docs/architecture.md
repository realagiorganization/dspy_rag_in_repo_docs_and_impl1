# Hushwheel Architecture

The fixture now uses a spoke-based layout instead of one monolithic implementation file.

## Coordinator

`src/hushwheel.c` remains intentionally huge because repository tests and retrieval experiments use
it as the anchor source. It now owns:

- the Doxygen mainpage and giant spiral register
- the canonical core entries
- helper functions such as `starts_with(...)`, `lantern_vowel_count(...)`, and `find_entry(...)`
- CLI dispatch in `hushwheel_main(...)`

## Internal Surface

`src/hushwheel_internal.h` declares the shared `GlossarySpan` shape and the helper functions used
by linked tests and spoke aggregation.

## Spokes

`src/hushwheel_spokes.c` assembles the eight generated spoke tables into one searchable array of
`GlossarySpan` values. Each `src/hushwheel_spoke_*.c` file contributes 512 entries, yielding 4096
generated entries plus 12 canonical coordinator entries for a total of 4108.

## Documentation

The source comments are part of the architecture. `Doxyfile` turns the coordinator, spokes, and
Markdown docs into HTML plus `docs/hushwheel-reference.pdf`, which is linked from the README and
packaged with the fixture. `docs/constellation-atlas.md` deliberately uses repeated orbit records
instead of code-shaped prose, giving the fixture one markdown-native structure that is visibly
different from the source tree while still describing the same canon.
