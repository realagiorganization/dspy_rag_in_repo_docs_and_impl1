# Exploratorium Translation

This subdocument is the repository's bilingual fetch-and-summary atlas.

## Purpose

- inventory the current state of fetched versus non-fetched referenced papers and documentation
- summarize every tracked repository file except the exploratorium's own generated outputs
- summarize every authored explicit HTTP or HTTPS link in the project
- repeat the same content three ways: side-by-side, line-by-line, and page-by-page in English and Russian

## Build

```bash
make exploratorium-build
```

That command regenerates the JSON and LaTeX inventory assets from the repository root, then builds
`exploratorium_translation.pdf`.

## Files

- `exploratorium_translation.tex`: main bilingual LaTeX source
- `generated/exploratorium-content.tex`: generated bilingual content include
- `generated/exploratorium-manifest.json`: machine-readable inventory snapshot
- `exploratorium_translation.pdf`: committed PDF output for stable linking
- `Makefile`: local build helpers
