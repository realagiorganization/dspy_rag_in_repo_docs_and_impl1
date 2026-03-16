from __future__ import annotations

from pathlib import Path

from repo_rag_lab.mcp import discover_mcp_servers


def test_discover_mcp_servers_covers_config_and_package_branches(tmp_path: Path) -> None:
    (tmp_path / "mcp.json").write_text(
        '{"mcpServers": {"repo-docs": {"command": "python", "args": ["server.py"]}}}',
        encoding="utf-8",
    )
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "mcp-repo"\n', encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"name": "repo-node", "scripts": {"mcp": "node server.js"}}',
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "repo-python"\ndescription = "mcp helper"\n',
        encoding="utf-8",
    )

    candidates = discover_mcp_servers(tmp_path)
    hints = {candidate.path: candidate.hint for candidate in candidates}

    assert "mcp.json" in hints
    assert "Configured servers: repo-docs" in hints["mcp.json"]
    assert "Cargo.toml" in hints
    assert "package.json" in hints
    assert "pyproject.toml" in hints
