from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT / "hushwheel"
MANIFEST_PATH = ROOT / "fixture-manifest.json"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(BINARY), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def load_manifest() -> dict[str, Any]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("fixture manifest must decode to an object")
    return payload


def parse_key_value_output(stdout: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in stdout.strip().splitlines():
        key, value = raw_line.split(": ", 1)
        parsed[key] = value
    return parsed


class HushwheelIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not BINARY.exists():
            raise RuntimeError(
                "expected the hushwheel binary to exist before integration tests run"
            )

    def test_lookup_prints_full_entry(self) -> None:
        result = run_cli("lookup", "ember-index")
        assert result.returncode == 0
        assert "term: ember-index" in result.stdout
        assert "category: storm-index" in result.stdout
        assert "district: Coal Arcade" in result.stdout
        assert "lantern vowel: 4" in result.stdout

    def test_lookup_reports_missing_terms(self) -> None:
        result = run_cli("lookup", "missing-term")
        assert result.returncode == 3
        assert "term not found: missing-term" in result.stderr

    def test_prefix_lists_matching_entries(self) -> None:
        result = run_cli("prefix", "amber")
        assert result.returncode == 0
        assert "amber-abacus-0000 | bellframe | ember=100" in result.stdout

    def test_category_lists_matching_entries(self) -> None:
        result = run_cli("category", "storm-index")
        assert result.returncode == 0
        assert "ember-index | Coal Arcade | ember=777" in result.stdout
        assert "storm-compass | Tin Wharf | ember=690" in result.stdout

    def test_stats_match_fixture_manifest(self) -> None:
        result = run_cli("stats")
        manifest = load_manifest()
        parsed = parse_key_value_output(result.stdout)
        assert result.returncode == 0
        assert parsed["entries"] == str(manifest["entry_count"])
        assert parsed["categories"] == "12"
        assert parsed["districts"] == "8"
        assert float(parsed["average ember index"]) > 0.0

    def test_about_describes_the_archive(self) -> None:
        result = run_cli("about")
        assert result.returncode == 0
        assert "theatrical city dictionary" in result.stdout
        assert "giant static glossary table" in result.stdout


if __name__ == "__main__":
    unittest.main()
