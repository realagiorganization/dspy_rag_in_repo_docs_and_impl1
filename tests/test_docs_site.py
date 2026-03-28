from __future__ import annotations

from pathlib import Path

from repo_rag_lab.site import build_docs_site, verify_docs_site_sources

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_docs_site_creates_prominent_test_plan_page(tmp_path: Path) -> None:
    output_dir = build_docs_site(REPO_ROOT, tmp_path / "site")

    index_html = (output_dir / "index.html").read_text(encoding="utf-8")
    test_plan_html = (output_dir / "test-plan.html").read_text(encoding="utf-8")

    assert "Feature-Focused Test Plan" in index_html
    assert 'href="test-plan.html"' in index_html
    assert "Primary Features" in test_plan_html
    assert "Core Commands" in test_plan_html


def test_verify_docs_site_sources_reports_expected_fields() -> None:
    payload = verify_docs_site_sources(REPO_ROOT)

    assert payload["issue_count"] == 0
    assert payload["checked_page_count"] >= 2
