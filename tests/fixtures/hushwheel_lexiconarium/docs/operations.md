# Hushwheel Operations

The hushwheel CLI still exposes five operator-facing commands:

- `lookup TERM`
- `prefix PREFIX`
- `category NAME`
- `stats`
- `about`

## Prefix Search

The function `print_prefix_matches` handles prefix search. It walks the core entry table and then
every spoke table, uses the `starts_with(...)` helper, and prints one compact result row for each
matching term.

## Lookup

`lookup` uses `find_entry(...)`, which scans the coordinator's canonical entries before sweeping
the aggregated spoke mesh.

## Category Search

`category` prints the term, district, and ember index for every entry filed under a category. The
categories are intentionally reusable across all spokes so the archive still feels like one wheel.

## Statistics

`stats` reports the total entry count, category count, district count, and average ember index.

## About Output

`about` preserves the original theatrical description while adding the new cross-canon framing:
id Software, scripture, and legendary software developers now share one searchable glossary mesh.
