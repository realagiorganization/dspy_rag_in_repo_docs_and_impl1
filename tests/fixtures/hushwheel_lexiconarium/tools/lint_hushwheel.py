from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC_TEXT_FILES = (
    Path("README.md"),
    Path("CHANGELOG.md"),
    Path("LICENSE.md"),
    Path("VERSION"),
    Path("Makefile"),
    Path("Doxyfile"),
    Path("fixture-manifest.json"),
    Path("include/hushwheel.h"),
    Path("docs/concepts.md"),
    Path("docs/operations.md"),
    Path("docs/districts.md"),
    Path("docs/catalog.md"),
    Path("docs/architecture.md"),
    Path("docs/testing.md"),
    Path("docs/packaging.md"),
    Path("docs/doxygen-fonts.sty"),
    Path("packaging/hushwheel.package.json"),
    Path("packaging/hushwheel.1"),
    Path("tests/unit/test_hushwheel_unit.c"),
    Path("tests/integration/cli_suite.py"),
    Path("tests/bdd/hushwheel.feature"),
    Path("tests/bdd/run_bdd.py"),
    Path("tools/regenerate_hushwheel_fixture.py"),
)
REQUIRED_MAKE_TARGETS = (
    "lint:",
    "static-analysis:",
    "complexity:",
    "coverage:",
    "reports:",
    "quality:",
    "unit:",
    "integration:",
    "bdd:",
    "check:",
    "dist:",
    "docs:",
    "install:",
    "uninstall:",
)
REQUIRED_README_SNIPPETS = (
    "make check",
    "make quality",
    "build/reports",
    "HUSHWHEEL_BIN",
    "make docs",
    "make dist",
    "make install",
    "docs/hushwheel-reference.pdf",
    "tests/unit/test_hushwheel_unit.c",
    "tests/bdd/hushwheel.feature",
)


def read_text(path: Path) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def text_files() -> tuple[Path, ...]:
    source_files = tuple(sorted(Path("src").glob("*.c")))
    source_headers = tuple(sorted(Path("src").glob("*.h")))
    return STATIC_TEXT_FILES + source_files + source_headers


def assert_no_tabs_or_trailing_whitespace() -> None:
    for relative_path in text_files():
        for line_number, raw_line in enumerate(read_text(relative_path).splitlines(), start=1):
            if "\t" in raw_line and not (
                relative_path == Path("Makefile") and raw_line.startswith("\t")
            ):
                raise RuntimeError(f"{relative_path}:{line_number} contains a tab character")
            if raw_line.rstrip() != raw_line:
                raise RuntimeError(f"{relative_path}:{line_number} contains trailing whitespace")


def assert_makefile_targets() -> None:
    makefile = read_text(Path("Makefile"))
    for target in REQUIRED_MAKE_TARGETS:
        if target not in makefile:
            raise RuntimeError(f"Makefile is missing required target marker: {target}")


def assert_readme_mentions_harness() -> None:
    readme = read_text(Path("README.md"))
    for snippet in REQUIRED_README_SNIPPETS:
        if snippet not in readme:
            raise RuntimeError(f"README.md is missing required snippet: {snippet}")


def assert_feature_and_source_are_aligned() -> None:
    source = read_text(Path("src/hushwheel.c"))
    feature = read_text(Path("tests/bdd/hushwheel.feature"))
    if "#ifndef HUSHWHEEL_NO_MAIN" not in source:
        raise RuntimeError("src/hushwheel.c is missing the HUSHWHEEL_NO_MAIN guard")
    if "Feature: Hushwheel CLI" not in feature:
        raise RuntimeError("tests/bdd/hushwheel.feature is missing the feature declaration")
    if "@mainpage Hushwheel Lexiconarium" not in source:
        raise RuntimeError("src/hushwheel.c is missing the Doxygen mainpage block")


def main() -> int:
    assert_no_tabs_or_trailing_whitespace()
    assert_makefile_targets()
    assert_readme_mentions_harness()
    assert_feature_and_source_are_aligned()
    print("hushwheel lint passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
