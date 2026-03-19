from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from repo_rag_lab.exploratorium_translation import sync_exploratorium_translation

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_demo_repo(tmp_path: Path) -> None:
    (tmp_path / "documentation").mkdir(parents=True)
    (tmp_path / "publication").mkdir(parents=True)
    (tmp_path / "src" / "repo_rag_lab").mkdir(parents=True)

    (tmp_path / "README.md").write_text(
        "# Demo Repo\n\nSee https://github.com/example/project, "
        "https://github.com/example/project/blob/main/README.md#L1-L2, "
        "and https://astral.sh/.\n",
        encoding="utf-8",
    )
    (tmp_path / "Makefile").write_text(".PHONY: setup\nsetup:\n\t@true\n", encoding="utf-8")
    (tmp_path / "documentation" / "azure-deployment.md").write_text(
        "# Azure Deployment\n\nCompanion note.\n",
        encoding="utf-8",
    )
    (tmp_path / "documentation" / "mcp-discovery.md").write_text(
        "# MCP Discovery\n\nCompanion note.\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "repo_rag_lab" / "example.py").write_text(
        '"""Example module."""\n\nVALUE = 1\n',
        encoding="utf-8",
    )
    (tmp_path / "publication" / "references.bib").write_text(
        "@misc{mcp2024,\n"
        "  title = {Model Context Protocol},\n"
        "  howpublished = {\\url{https://modelcontextprotocol.io/}}\n"
        "}\n\n"
        "@misc{azureinference2025,\n"
        "  title = {Azure AI Inference Documentation},\n"
        "  howpublished = {\\url{https://learn.microsoft.com/azure/ai-services/}}\n"
        "}\n",
        encoding="utf-8",
    )


def _git_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, env=_git_env())
    subprocess.run(["git", "add", "."], cwd=root, check=True, env=_git_env())


def _git_add(root: Path, *paths: str) -> None:
    subprocess.run(["git", "add", *paths], cwd=root, check=True, env=_git_env())


def test_sync_exploratorium_translation_writes_bilingual_outputs(tmp_path: Path) -> None:
    _write_demo_repo(tmp_path)

    payload = sync_exploratorium_translation(tmp_path)

    tex_path = tmp_path / str(payload["tex_path"])
    manifest_path = tmp_path / str(payload["manifest_path"])
    assert tex_path.exists()
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["bibliography_entry_count"] == 2
    assert manifest["explicit_link_count"] >= 2
    assert manifest["summarized_file_count"] >= 5

    tex = tex_path.read_text(encoding="utf-8")
    assert "Side-By-Side / Параллельный показ" in tex
    assert "Line-By-Line / Построчный показ" in tex
    assert "Page-By-Page / Постраничный показ" in tex
    assert "Repository Fetching State / Состояние загрузки источников" in tex
    assert "https://modelcontextprotocol.io/" in tex
    assert "https://learn.microsoft.com/azure/ai-services/" in tex
    assert "https://github.com/example/project/blob/main/README.md\\#L1-L2" in tex


def test_sync_exploratorium_translation_reuses_timestamp_until_inventory_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_demo_repo(tmp_path)
    _init_git_repo(tmp_path)
    monkeypatch.setenv("GIT_DIR", str(REPO_ROOT / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(REPO_ROOT))

    timestamps = iter(
        [
            "2026-03-18T10:35:42Z",
            "2026-03-18T10:37:51Z",
            "2026-03-18T10:40:00Z",
        ]
    )
    monkeypatch.setattr(
        "repo_rag_lab.exploratorium_translation._iso_utc_now",
        lambda: next(timestamps),
    )

    payload = sync_exploratorium_translation(tmp_path)
    manifest_path = tmp_path / str(payload["manifest_path"])
    tex_path = tmp_path / str(payload["tex_path"])

    first_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first_tex = tex_path.read_text(encoding="utf-8")
    assert first_manifest["generated_at"] == "2026-03-18T10:35:42Z"
    assert "2026-03-18T10:35:42Z" in first_tex

    sync_exploratorium_translation(tmp_path)
    second_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    second_tex = tex_path.read_text(encoding="utf-8")
    assert second_manifest["generated_at"] == "2026-03-18T10:35:42Z"
    assert second_tex == first_tex

    (tmp_path / "documentation" / "fresh-note.md").write_text(
        "# Fresh Note\n\nAdds new inventory surface.\n",
        encoding="utf-8",
    )
    _git_add(tmp_path, "documentation/fresh-note.md")
    sync_exploratorium_translation(tmp_path)
    third_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    third_tex = tex_path.read_text(encoding="utf-8")
    assert third_manifest["generated_at"] == "2026-03-18T10:40:00Z"
    assert third_manifest["summarized_file_count"] == second_manifest["summarized_file_count"] + 1
    assert "2026-03-18T10:40:00Z" in third_tex
