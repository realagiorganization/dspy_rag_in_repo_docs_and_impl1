from __future__ import annotations

from repo_rag_lab.term_extraction import (
    TECHNICAL_TERM_CATEGORIES,
    TECHNICAL_TERM_LOOKUP,
    extract_profile_terms,
    select_profile_summary_terms,
)


def test_extract_profile_terms_prioritizes_hashed_technical_lookup() -> None:
    terms = extract_profile_terms(
        [
            (
                "Please just really describe whether the recorder should update the "
                "README gif bundle and publish the artifact through playwright on azure"
            )
        ],
        limit=8,
    )

    assert terms == [
        "recorder",
        "readme",
        "gif",
        "bundle",
        "publish",
        "artifact",
        "playwright",
        "azure",
    ]


def test_extract_profile_terms_backfills_with_filtered_nontechnical_tokens() -> None:
    terms = extract_profile_terms(
        ["Repository cleanup roadmap for migration planning and governance notes"],
        limit=6,
    )

    assert terms[0] == "repository"
    assert "migration" in terms[:3]
    assert "cleanup" in terms
    assert "migration" in terms
    assert "planning" in terms
    assert len(terms) == 6


def test_technical_term_categories_form_large_flat_lookup() -> None:
    assert "playwright" in TECHNICAL_TERM_CATEGORIES["browser_automation"]
    assert "artifact" in TECHNICAL_TERM_CATEGORIES["repo"]
    assert "trainer" in TECHNICAL_TERM_CATEGORIES["python_ml"]
    assert "rust" in TECHNICAL_TERM_CATEGORIES["programming_languages"]
    assert "postgresql" in TECHNICAL_TERM_CATEGORIES["databases_storage"]
    assert "graphql" in TECHNICAL_TERM_CATEGORIES["api_web_backend"]
    assert "pandas" in TECHNICAL_TERM_CATEGORIES["data_science_analytics"]
    assert "transformer" in TECHNICAL_TERM_CATEGORIES["neural_networks_ai"]
    assert "publication" in TECHNICAL_TERM_CATEGORIES["research_science"]
    assert "kubernetes" in TECHNICAL_TERM_CATEGORIES["infrastructure_devops"]
    assert "grep" in TECHNICAL_TERM_CATEGORIES["linux_commands"]
    assert "powershell" in TECHNICAL_TERM_CATEGORIES["windows_commands"]
    assert "unity" in TECHNICAL_TERM_CATEGORIES["gamedev"]
    assert "kubectl" in TECHNICAL_TERM_CATEGORIES["kubernetes"]
    assert "aws" in TECHNICAL_TERM_CATEGORIES["cloud_services"]
    assert "docker" in TECHNICAL_TERM_CATEGORIES["systems"]
    assert "azure" in TECHNICAL_TERM_LOOKUP
    assert "worktree" in TECHNICAL_TERM_LOOKUP
    assert "transformer" in TECHNICAL_TERM_LOOKUP
    assert "postgresql" in TECHNICAL_TERM_LOOKUP
    assert "kubectl" in TECHNICAL_TERM_LOOKUP
    assert "powershell" in TECHNICAL_TERM_LOOKUP
    assert len(TECHNICAL_TERM_LOOKUP) >= 430


def test_select_profile_summary_terms_prefers_technical_terms_over_narrative_noise() -> None:
    summary = select_profile_summary_terms(
        {
            "already": 3,
            "commands": 3,
            "contains": 3,
            "decision": 3,
            "does": 3,
            "fields": 3,
            "gif": 3,
            "git": 3,
            "readme": 3,
            "recorder": 3,
            "repo": 3,
            "script": 3,
            "worktree": 3,
        },
        limit=8,
        min_count=2,
    )

    assert summary[:6] == ["gif", "recorder", "git", "readme", "repo", "worktree"]
    assert "script" in summary
    assert "already" not in summary
    assert "contains" not in summary
    assert "does" not in summary
    assert "fields" not in summary
    assert "commands" not in summary
