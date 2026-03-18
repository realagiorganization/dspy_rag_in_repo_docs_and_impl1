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
    assert "unit:" in makefile
    assert "integration:" in makefile
    assert "bdd:" in makefile
    assert "dist:" in makefile
    assert "install:" in makefile
    assert "uninstall:" in makefile


def test_hushwheel_fixture_check_target_passes() -> None:
    try:
        result = run_fixture_make("check")
        combined_output = result.stdout + result.stderr

        assert "hushwheel lint passed" in result.stdout
        assert "hushwheel unit tests passed" in result.stdout
        assert "Ran 6 tests" in combined_output
        assert "scenario passed: Report aggregate statistics" in result.stdout
    finally:
        run_fixture_make("clean")


def test_hushwheel_fixture_packaging_targets_stage_install_and_dist(tmp_path: Path) -> None:
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
        assert (install_root / "usr/share/doc/hushwheel/packaging/hushwheel.package.json").exists()
        assert (install_root / "usr/share/man/man1/hushwheel.1").exists()

        run_fixture_make("uninstall", f"DESTDIR={install_root}", "PREFIX=/usr")

        assert not (install_root / "usr/bin/hushwheel").exists()
        assert not (install_root / "usr/share/doc/hushwheel").exists()
    finally:
        run_fixture_make("clean")
