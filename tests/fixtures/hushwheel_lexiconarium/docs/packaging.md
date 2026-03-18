# Packaging Guide

The hushwheel fixture packages like a small standalone command-line utility.

## Versioning

- `VERSION` holds the release version used by `make dist`.
- `packaging/hushwheel.package.json` provides machine-readable package metadata.
- `packaging/hushwheel.1` is the installed manual page.

## Distribution Archive

Build a source-style release tarball with:

```sh
make dist
```

That produces `dist/hushwheel-0.1.0.tar.gz` containing:

- the production source and header
- the project `Makefile`
- documentation and licensing files
- test harness sources
- packaging metadata

## Installation Layout

The install target honors both `PREFIX` and `DESTDIR`.

| Installed path | Contents |
| --- | --- |
| `$(PREFIX)/bin/hushwheel` | The compiled executable. |
| `$(PREFIX)/share/doc/hushwheel/` | README, changelog, license, version, manifest, and markdown docs. |
| `$(PREFIX)/share/doc/hushwheel/packaging/` | Package metadata JSON. |
| `$(PREFIX)/share/man/man1/hushwheel.1` | Manual page. |

Example staging install:

```sh
make install DESTDIR="$PWD/build/install-root" PREFIX=/usr
```

Remove the same layout with:

```sh
make uninstall DESTDIR="$PWD/build/install-root" PREFIX=/usr
```
