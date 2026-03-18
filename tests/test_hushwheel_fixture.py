from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from repo_rag_lab.corpus import iter_text_files, load_documents
from repo_rag_lab.retrieval import chunk_documents
from repo_rag_lab.workflow import ask_repository

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "hushwheel_lexiconarium"
EXPECTED_SPOKE_USAGE_TEXT = (
    "Used when archivists must align id heroics, scripture, and legendary software-developer "
    "actions inside one textual-programmatic-narrative-editorial thread, usually after the moss "
    "ledger, whisper funnel, and clock oath have documented the disagreement as a searchable "
    "retrieval record."
)
LEGACY_SPOKE_USAGE_TEXT = (
    "Used when archivists must align id heroics, scripture, and legendary software-developer "
    "actions inside one textual-programmatic-narrative-editorial thread, usually after the moss "
    "ledger, whisper funnel, and clock oath have turned a quarrel into a durable retrieval trail."
)


def test_hushwheel_fixture_is_large_and_c_indexable() -> None:
    source_path = FIXTURE_ROOT / "src" / "hushwheel.c"
    assert source_path.stat().st_size >= 1_000_000

    indexed_paths = {path.relative_to(FIXTURE_ROOT) for path in iter_text_files(FIXTURE_ROOT)}
    assert Path("src/hushwheel.c") in indexed_paths
    assert Path("include/hushwheel.h") in indexed_paths
    assert Path("docs/concepts.md") in indexed_paths
    assert Path("docs/testing.md") in indexed_paths
    assert Path("docs/packaging.md") in indexed_paths
    assert Path("fixture-manifest.json") in indexed_paths
    assert Path("packaging/hushwheel.package.json") in indexed_paths
    assert Path("tests/bdd/hushwheel.feature") in indexed_paths


def test_hushwheel_fixture_builds_a_large_chunkable_corpus() -> None:
    documents = load_documents(FIXTURE_ROOT)
    chunks = chunk_documents(documents)

    assert len(documents) >= 14
    assert len(chunks) >= 1500


def test_hushwheel_fixture_answers_document_question() -> None:
    answer = ask_repository("What is the ember index?", FIXTURE_ROOT)

    assert "ember index" in answer.answer.lower()
    assert any("heat-memory score" in chunk.text.lower() for chunk in answer.context)
    assert any("lantern vowel" in chunk.text.lower() for chunk in answer.context)
    assert any(chunk.source.suffix == ".md" for chunk in answer.context)


def test_hushwheel_fixture_answers_code_question() -> None:
    answer = ask_repository("How does print_prefix_matches handle prefix search?", FIXTURE_ROOT)

    assert "print_prefix_matches" in answer.answer
    assert "prefix search" in answer.answer.lower()
    assert any(chunk.source.name == "hushwheel.c" for chunk in answer.context)


def test_hushwheel_fixture_replaces_legacy_usage_phrase_with_literal_record_text() -> None:
    generator_path = FIXTURE_ROOT / "tools" / "regenerate_hushwheel_fixture.py"
    generator_source = generator_path.read_text(encoding="utf-8")
    generator_spec = importlib.util.spec_from_file_location(
        "hushwheel_fixture_generator", generator_path
    )
    assert generator_spec is not None
    assert generator_spec.loader is not None
    generator_module = importlib.util.module_from_spec(generator_spec)
    sys.modules[generator_spec.name] = generator_module
    generator_spec.loader.exec_module(generator_module)
    catalog = (FIXTURE_ROOT / "docs" / "catalog.md").read_text(encoding="utf-8")
    spoke = (FIXTURE_ROOT / "src" / "hushwheel_spoke_argent.c").read_text(encoding="utf-8")

    assert generator_module.SPOKE_USAGE_TEXT == EXPECTED_SPOKE_USAGE_TEXT
    assert LEGACY_SPOKE_USAGE_TEXT not in generator_source
    assert catalog.count(EXPECTED_SPOKE_USAGE_TEXT) == 32
    assert LEGACY_SPOKE_USAGE_TEXT not in catalog
    assert spoke.count(EXPECTED_SPOKE_USAGE_TEXT) == 512
    assert LEGACY_SPOKE_USAGE_TEXT not in spoke
