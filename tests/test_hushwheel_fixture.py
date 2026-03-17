from __future__ import annotations

from pathlib import Path

from repo_rag_lab.corpus import iter_text_files, load_documents
from repo_rag_lab.retrieval import chunk_documents
from repo_rag_lab.workflow import ask_repository

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "hushwheel_lexiconarium"


def test_hushwheel_fixture_is_large_and_c_indexable() -> None:
    source_path = FIXTURE_ROOT / "src" / "hushwheel.c"
    assert source_path.stat().st_size >= 1_000_000

    indexed_paths = {path.relative_to(FIXTURE_ROOT) for path in iter_text_files(FIXTURE_ROOT)}
    assert Path("src/hushwheel.c") in indexed_paths
    assert Path("include/hushwheel.h") in indexed_paths
    assert Path("docs/concepts.md") in indexed_paths
    assert Path("fixture-manifest.json") in indexed_paths


def test_hushwheel_fixture_builds_a_large_chunkable_corpus() -> None:
    documents = load_documents(FIXTURE_ROOT)
    chunks = chunk_documents(documents)

    assert len(documents) >= 8
    assert len(chunks) >= 1500


def test_hushwheel_fixture_answers_document_question() -> None:
    answer = ask_repository("What is the ember index?", FIXTURE_ROOT)

    assert "heat-memory score" in answer.answer.lower()
    assert "lantern vowel" in answer.answer.lower()
    assert any(chunk.source.suffix == ".md" for chunk in answer.context)


def test_hushwheel_fixture_answers_code_question() -> None:
    answer = ask_repository("How does print_prefix_matches handle prefix search?", FIXTURE_ROOT)

    assert "print_prefix_matches" in answer.answer
    assert "prefix search" in answer.answer.lower()
    assert any(chunk.source.name == "hushwheel.c" for chunk in answer.context)
