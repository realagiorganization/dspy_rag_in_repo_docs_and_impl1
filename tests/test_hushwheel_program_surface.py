from __future__ import annotations

import subprocess
import tarfile
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "hushwheel_lexiconarium"
VERSION = (FIXTURE_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def run_fixture_make(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", *args],
        cwd=FIXTURE_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_hushwheel_fixture_makefile_exposes_project_harness() -> None:
    makefile = (FIXTURE_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "lint:" in makefile
    assert "static-analysis:" in makefile
    assert "complexity:" in makefile
    assert "coverage:" in makefile
    assert "reports:" in makefile
    assert "quality:" in makefile
    assert "unit:" in makefile
    assert "integration:" in makefile
    assert "bdd:" in makefile
    assert "dist:" in makefile
    assert "install:" in makefile
    assert "uninstall:" in makefile


def test_hushwheel_fixture_docs_describe_quality_reports() -> None:
    readme = (FIXTURE_ROOT / "README.md").read_text(encoding="utf-8")
    testing_doc = (FIXTURE_ROOT / "docs" / "testing.md").read_text(encoding="utf-8")

    assert "make quality" in readme
    assert "build/reports" in readme
    assert "HUSHWHEEL_BIN" in readme
    assert "cppcheck" in testing_doc
    assert "lizard" in testing_doc
    assert "gcovr" in testing_doc


def test_hushwheel_fixture_check_target_passes() -> None:
    try:
        result = run_fixture_make("check")
        combined_output = result.stdout + result.stderr

        assert "hushwheel lint passed" in result.stdout
        assert "hushwheel unit tests passed" in result.stdout
        assert "Ran 12 tests" in combined_output
        assert "scenario passed: Report aggregate statistics" in result.stdout
    finally:
        run_fixture_make("clean")


def test_hushwheel_fixture_docs_target_builds_pdf() -> None:
    pdf_path = FIXTURE_ROOT / "docs" / "hushwheel-reference.pdf"
    original_pdf = pdf_path.read_bytes()

    try:
        run_fixture_make("docs")
        assert pdf_path.exists()
    finally:
        pdf_path.write_bytes(original_pdf)
        run_fixture_make("clean")


def test_hushwheel_fixture_packaging_targets_stage_install_and_dist(tmp_path: Path) -> None:
    pdf_path = FIXTURE_ROOT / "docs" / "hushwheel-reference.pdf"
    original_pdf = pdf_path.read_bytes()

    try:
        run_fixture_make("dist")

        tarball_path = FIXTURE_ROOT / "dist" / f"hushwheel-{VERSION}.tar.gz"
        assert tarball_path.exists()

        with tarfile.open(tarball_path, "r:gz") as archive:
            names = set(archive.getnames())

        assert f"hushwheel-{VERSION}/README.md" in names
        assert f"hushwheel-{VERSION}/packaging/hushwheel.package.json" in names
        assert f"hushwheel-{VERSION}/tests/bdd/hushwheel.feature" in names

        install_root = tmp_path / "install-root"
        run_fixture_make("install", f"DESTDIR={install_root}", "PREFIX=/usr")

        assert (install_root / "usr/bin/hushwheel").exists()
        assert (install_root / "usr/share/doc/hushwheel/docs/testing.md").exists()
        assert (install_root / "usr/share/doc/hushwheel/docs/hushwheel-reference.pdf").exists()
        assert (install_root / "usr/share/doc/hushwheel/packaging/hushwheel.package.json").exists()
        assert (install_root / "usr/share/man/man1/hushwheel.1").exists()

        run_fixture_make("uninstall", f"DESTDIR={install_root}", "PREFIX=/usr")

        assert not (install_root / "usr/bin/hushwheel").exists()
        assert not (install_root / "usr/share/doc/hushwheel").exists()
    finally:
        pdf_path.write_bytes(original_pdf)
        run_fixture_make("clean")
