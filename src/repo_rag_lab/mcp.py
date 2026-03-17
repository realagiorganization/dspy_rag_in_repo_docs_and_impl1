"""Discovery helpers for MCP-related repository artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class MCPServerCandidate:
    """A repository artifact that may expose or configure MCP behavior."""

    kind: str
    path: str
    hint: str


def discover_mcp_servers(root: Path) -> list[MCPServerCandidate]:
    """Find MCP-related configuration and package manifests under ``root``."""

    candidates: list[MCPServerCandidate] = []
    patterns = [
        ("mcp-config", "mcp.json"),
        ("mcp-config", ".mcp.json"),
        ("python-package", "pyproject.toml"),
        ("rust-package", "Cargo.toml"),
        ("node-package", "package.json"),
    ]
    for kind, filename in patterns:
        for path in root.rglob(filename):
            if ".git" in path.parts or "target" in path.parts or ".venv" in path.parts:
                continue
            hint = _hint_for(kind=kind, path=path)
            if hint:
                candidates.append(
                    MCPServerCandidate(kind=kind, path=str(path.relative_to(root)), hint=hint)
                )
    return _dedupe(candidates)


def _hint_for(kind: str, path: Path) -> str:
    """Generate a short operator hint for a discovered MCP candidate."""

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="ignore")

    lowered = text.lower()
    if "mcp" not in lowered and path.name not in {"mcp.json", ".mcp.json"}:
        return ""

    if kind == "python-package":
        return "Inspect package scripts or console entrypoints for MCP server commands."
    if kind == "rust-package":
        return "Inspect Rust binaries or examples for MCP transport/server implementation."
    if kind == "node-package":
        return "Inspect package scripts and dependencies for @modelcontextprotocol usage."
    if kind == "mcp-config":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return "Repository-local MCP config candidate."
        servers = payload.get("mcpServers") or payload.get("servers")
        if isinstance(servers, dict):
            return f"Configured servers: {', '.join(sorted(servers.keys()))}"
    return "Potential MCP-related artifact."


def _dedupe(candidates: list[MCPServerCandidate]) -> list[MCPServerCandidate]:
    """Remove duplicate candidates while preserving the latest discovered value."""

    unique: dict[tuple[str, str], MCPServerCandidate] = {}
    for candidate in candidates:
        unique[(candidate.kind, candidate.path)] = candidate
    return list(unique.values())


def dump_candidates(candidates: list[MCPServerCandidate]) -> str:
    """Serialize discovered MCP candidates as indented JSON."""

    return json.dumps([asdict(candidate) for candidate in candidates], indent=2)
