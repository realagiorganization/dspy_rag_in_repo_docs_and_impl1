from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FEATURE_PATH = Path(__file__).with_name("hushwheel.feature")
BINARY = Path(os.environ.get("HUSHWHEEL_BIN", str(ROOT / "hushwheel")))


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(BINARY), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def extract_scenarios() -> list[str]:
    scenarios: list[str] = []
    for raw_line in FEATURE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("Scenario: "):
            scenarios.append(line.removeprefix("Scenario: "))
    return scenarios


def scenario_lookup_a_canonical_term() -> None:
    result = run_cli("lookup", "ember-index")
    if result.returncode != 0:
        raise RuntimeError(f"expected lookup success, got {result.returncode}")
    if "category: storm-index" not in result.stdout:
        raise RuntimeError("lookup scenario did not print the expected category")


def scenario_explain_the_archive() -> None:
    result = run_cli("about")
    if result.returncode != 0:
        raise RuntimeError(f"expected about success, got {result.returncode}")
    if "giant static glossary table" not in result.stdout:
        raise RuntimeError("about scenario did not describe the archive")


def scenario_reject_an_incomplete_prefix_query() -> None:
    result = run_cli("prefix")
    if result.returncode != 2:
        raise RuntimeError(
            f"expected status 2 for incomplete prefix query, got {result.returncode}"
        )
    if "prefix requires a PREFIX" not in result.stderr:
        raise RuntimeError("prefix scenario did not report the missing argument")


def scenario_report_aggregate_statistics() -> None:
    result = run_cli("stats")
    if result.returncode != 0:
        raise RuntimeError(f"expected stats success, got {result.returncode}")
    if "entries: 4108" not in result.stdout:
        raise RuntimeError("stats scenario did not report the expected entry count")


SCENARIOS = {
    "Lookup a canonical term": scenario_lookup_a_canonical_term,
    "Explain the archive": scenario_explain_the_archive,
    "Reject an incomplete prefix query": scenario_reject_an_incomplete_prefix_query,
    "Report aggregate statistics": scenario_report_aggregate_statistics,
}


def main() -> int:
    if not BINARY.exists():
        raise RuntimeError("expected the hushwheel binary to exist before BDD tests run")

    declared = extract_scenarios()
    missing = [name for name in declared if name not in SCENARIOS]
    if missing:
        raise RuntimeError(f"feature scenarios are missing implementations: {missing}")

    undeclared = [name for name in SCENARIOS if name not in declared]
    if undeclared:
        raise RuntimeError(f"runner scenarios are missing from the feature file: {undeclared}")

    for name in declared:
        SCENARIOS[name]()
        print(f"scenario passed: {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
