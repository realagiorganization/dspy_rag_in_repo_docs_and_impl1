# Hushwheel Packaging

The hushwheel fixture packages like a small standalone command-line utility, even though its
archive is deliberately oversized.

## Packaged Surfaces

- `packaging/hushwheel.package.json` provides machine-readable package metadata.
- `packaging/hushwheel.1` is the installed manual page.
- `docs/constellation-atlas.md` provides the markdown-native orbit atlas for the archive.
- `docs/hushwheel-reference.pdf` is the generated Doxygen reference manual.

## Distribution

Run:

```sh
make dist
```

That produces `dist/hushwheel-0.1.0.tar.gz` containing the split source tree, Markdown docs,
Doxygen config, and generated PDF.

## Installation Layout

| Path | Contents |
| --- | --- |
| `$(PREFIX)/bin/hushwheel` | The compiled executable. |
| `$(PREFIX)/share/doc/hushwheel/` | README, changelog, license, version, manifest, and top-level docs. |
| `$(PREFIX)/share/doc/hushwheel/docs/` | Markdown guides, the orbit atlas, plus `hushwheel-reference.pdf`. |
| `$(PREFIX)/share/doc/hushwheel/packaging/` | Package metadata JSON. |
| `$(PREFIX)/share/man/man1/hushwheel.1` | Manual page. |
