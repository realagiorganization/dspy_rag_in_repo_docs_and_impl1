"""Minimal stdio MCP server for bounded repo-RAG operations.

This module intentionally exposes only short-running tool calls. It does not route
trainer-side recompilation, long retrieval evaluations, or notebook execution through MCP.
"""

from __future__ import annotations

import json
import os
import select
import time
import weakref
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, Literal, cast
from urllib.parse import SplitResult, parse_qs, urlsplit

if TYPE_CHECKING:
    from .mcp import MCPServerCandidate
    from .retrieval_profile import RetrievalProfile
    from .workflow import Chunk, RAGAnswer

RetrievalMode = Literal["lexical", "idf-rerank", "vector", "hybrid-vector"]

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SERVER_NAME = "repo-rag-mcp"
MCP_SERVER_INSTRUCTIONS = (
    "Use this MCP surface only for bounded repo-RAG operations. For repository discovery, call "
    "`search_repo` first and then `ask_repo` if you need one concise repo-grounded answer. Do not "
    "treat empty resource listings as absence of repo-RAG; tools are the primary discovery path. "
    "Do not route long DSPy training, full retrieval-eval sweeps, or notebook execution through "
    "this MCP surface."
)
SUPPORTED_RETRIEVAL_MODES = frozenset(
    {
        "lexical",
        "idf-rerank",
        "vector",
        "hybrid-vector",
    }
)
RETRIEVAL_MODE_ENUM = sorted(SUPPORTED_RETRIEVAL_MODES)
MCP_USAGE_LOG_ENV = "REPO_RAG_MCP_USAGE_LOG"
MCP_DEFAULT_RETRIEVAL_MODE_ENV = "REPO_RAG_MCP_DEFAULT_RETRIEVAL_MODE"
MCP_DEBUG_LOG_ENV = "REPO_RAG_MCP_DEBUG_LOG"
MCP_RESOURCE_SCHEME = "repo-rag"
MCP_STARTUP_CONTEXT_QUESTION = (
    "repository guidance current gameplay slice transmutation alchemy assumptions "
    "environment usage readme agents devplan"
)
_STREAM_READ_BUFFERS: weakref.WeakKeyDictionary[object, bytearray] = weakref.WeakKeyDictionary()
_STREAM_PROTOCOL_MODES: weakref.WeakKeyDictionary[object, str] = weakref.WeakKeyDictionary()


@dataclass(frozen=True)
class MCPToolDefinition:
    """One bounded repo-RAG MCP tool definition."""

    name: str
    description: str
    input_schema: dict[str, object]
    annotations: dict[str, object] | None = None

    def to_payload(self) -> dict[str, object]:
        """Return the JSON-serializable tool definition payload."""

        payload: dict[str, object] = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        if self.annotations:
            payload["annotations"] = dict(self.annotations)
        return payload


def _readonly_tool_annotations() -> dict[str, object]:
    """Return tool annotations for bounded read-only MCP tools."""

    return {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }


def _queue_write_tool_annotations() -> dict[str, object]:
    """Return tool annotations for bounded queue-write MCP tools."""

    return {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }


@dataclass(frozen=True)
class MCPResourceDefinition:
    """One direct MCP resource definition."""

    uri: str
    name: str
    description: str
    mime_type: str
    title: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
            "annotations": {"audience": ["assistant"], "priority": 0.9},
        }
        if self.title:
            payload["title"] = self.title
        return payload


@dataclass(frozen=True)
class MCPResourceTemplateDefinition:
    """One parameterized MCP resource template definition."""

    uri_template: str
    name: str
    description: str
    mime_type: str
    title: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "uriTemplate": self.uri_template,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
            "annotations": {"audience": ["assistant"], "priority": 1.0},
        }
        if self.title:
            payload["title"] = self.title
        return payload


def _server_version() -> str:
    """Return the installed package version when available."""

    try:
        return version("repo-rag-lab")
    except PackageNotFoundError:
        return "0.0.0"


def _artifact_metadata() -> dict[str, list[str]]:
    """Return an empty artifact metadata payload."""

    return {"input_paths": [], "generated_paths": [], "related_paths": []}


def load_retrieval_profile(server_root: Path) -> RetrievalProfile:
    from .retrieval_profile import load_retrieval_profile

    return load_retrieval_profile(server_root)


def build_corpus_manifest(server_root: Path) -> dict[str, object]:
    from .corpus import build_corpus_manifest

    return build_corpus_manifest(server_root)


def collect_repository_context(
    *,
    question: str,
    root: Path,
    top_k: int = 4,
    retrieval_mode: RetrievalMode | None = None,
    profile: RetrievalProfile | None = None,
) -> list[Chunk]:
    from .workflow import collect_repository_context

    return collect_repository_context(
        question=question,
        root=root,
        top_k=top_k,
        retrieval_mode=retrieval_mode,
        profile=profile,
    )


def serialize_chunk(chunk: Chunk, *, root: Path) -> dict[str, str]:
    from .workflow import serialize_chunk

    return serialize_chunk(chunk, root=root)


def discover_mcp_servers(root: Path) -> list[MCPServerCandidate]:
    from .mcp import discover_mcp_servers as _discover_mcp_servers

    return _discover_mcp_servers(root)


def ask_repository(
    *,
    question: str,
    root: Path,
    retrieval_mode: RetrievalMode | None = None,
) -> RAGAnswer:
    from .workflow import ask_repository

    return ask_repository(
        question=question,
        root=root,
        retrieval_mode=retrieval_mode,
    )


def build_runtime_trace_payload(
    *,
    question: str,
    retrieval_mode: str,
    sources: list[str],
    context_items: list[dict[str, object]],
    bundle_version: str | None,
    overlay_path: str | None,
    mcp_candidate_count: int,
    answer_length: int,
) -> dict[str, object]:
    from .runtime_artifacts import RuntimeTraceContext, build_runtime_trace

    return build_runtime_trace(
        RuntimeTraceContext(
            question=question,
            mode="baseline",
            retrieval_mode=retrieval_mode,
            sources=sources,
            context_count=len(context_items),
            top_k=4,
            bundle_version=bundle_version,
            overlay_path=overlay_path,
            mcp_candidate_count=mcp_candidate_count,
            answer_length=answer_length,
            context_field="context",
            evidence_items=context_items,
        )
    )


def run_bundle_inspection(root: Path, *, run_name: str | None, channel: str | None) -> str:
    from .utilities import run_bundle_inspection

    return run_bundle_inspection(root, run_name=run_name, channel=channel)


def run_dspy_artifacts(root: Path) -> str:
    from .utilities import run_dspy_artifacts

    return run_dspy_artifacts(root)


def run_trace_enqueue(
    root: Path,
    *,
    trace_path: Path,
    trace_name: str | None,
    queue_name: str,
    outcome_path: Path | None,
) -> str:
    from .utilities import run_trace_enqueue

    return run_trace_enqueue(
        root,
        trace_path=trace_path,
        trace_name=trace_name,
        queue_name=queue_name,
        outcome_path=outcome_path,
    )


def _log_usage_event(
    *,
    method: str,
    tool_name: str | None = None,
    server_root: Path,
    details: Mapping[str, object] | None = None,
) -> None:
    log_path_text = str(os.getenv(MCP_USAGE_LOG_ENV) or "").strip()
    if not log_path_text:
        return
    log_path = Path(log_path_text)
    payload = {
        "timestamp_epoch": time.time(),
        "method": method,
        "tool_name": tool_name,
        "server_root": str(server_root),
        "details": dict(details or {}),
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
    except OSError:
        return


def _mcp_debug_log_path() -> Path | None:
    raw = str(os.getenv(MCP_DEBUG_LOG_ENV) or "").strip()
    return Path(raw) if raw else None


def _log_mcp_debug(message: str) -> None:
    path = _mcp_debug_log_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.time():.6f} {message}\n")
    except OSError:
        return


def _fd_target(fd: int) -> str:
    try:
        return os.readlink(f"/proc/{os.getpid()}/fd/{fd}")
    except OSError:
        return ""


def _resolve_root(server_root: Path, requested_root: object) -> Path:
    """Resolve one optional tool-local root against the server root."""

    if not isinstance(requested_root, str) or not requested_root.strip():
        return server_root
    candidate = Path(requested_root)
    if candidate.is_absolute():
        return candidate.resolve()
    return (server_root / candidate).resolve()


def _json_content(payload: Mapping[str, object], *, is_error: bool = False) -> dict[str, object]:
    """Return one MCP content payload with both text and structured content."""

    normalized = dict(payload)
    return {
        "content": [{"type": "text", "text": json.dumps(normalized, indent=2)}],
        "structuredContent": normalized,
        "isError": is_error,
    }


def _string_list_field(payload: Mapping[str, object], key: str) -> list[str]:
    """Return one string-list payload field when present."""

    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _jsonify(value: object) -> object:
    """Normalize nested values into JSON-serializable structures."""

    if isinstance(value, dict):
        return {str(key): _jsonify(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(
            (_jsonify(item) for item in value),
            key=lambda item: json.dumps(item, sort_keys=True, default=str),
        )
    return value


def build_mcp_tool_definitions() -> list[MCPToolDefinition]:
    """Return the bounded MCP tool catalog exposed by this repository."""

    return [
        MCPToolDefinition(
            name="search_repo",
            description=(
                "Use this when you need repository discovery. Search the local repository corpus "
                "and return a bounded shortlist of relevant files plus matching text previews. "
                "Call this first before broad shell reads and do not wait for resource listings."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": ("Natural-language repository question or search target."),
                    },
                    "root": {
                        "type": "string",
                        "description": (
                            "Optional repository root override relative to the server root."
                        ),
                    },
                    "retrieval_mode": {
                        "type": "string",
                        "enum": RETRIEVAL_MODE_ENUM,
                        "description": (
                            "Optional low-level retrieval mode override. Omit to use the "
                            "repository default profile."
                        ),
                    },
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 12,
                        "description": "Maximum number of matching context chunks to return.",
                    },
                },
                "required": ["question"],
                "additionalProperties": False,
            },
            annotations=_readonly_tool_annotations(),
        ),
        MCPToolDefinition(
            name="ask_repo",
            description=(
                "Use this when `search_repo` already narrowed the file set and you need one "
                "bounded repo-grounded answer. This tool stays local to the repository corpus and "
                "does not invoke live providers or DSPy compilation."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Natural-language repository question to answer concisely.",
                    },
                    "root": {
                        "type": "string",
                        "description": (
                            "Optional repository root override relative to the server root."
                        ),
                    },
                    "retrieval_mode": {
                        "type": "string",
                        "enum": RETRIEVAL_MODE_ENUM,
                        "description": (
                            "Optional low-level retrieval mode override. Omit to use the "
                            "repository default profile."
                        ),
                    },
                    "bundle_version": {
                        "type": "string",
                        "description": "Optional bundle version hint to echo in the trace payload.",
                    },
                    "overlay_path": {
                        "type": "string",
                        "description": "Optional overlay path hint to echo in the trace payload.",
                    },
                },
                "required": ["question"],
                "additionalProperties": False,
            },
            annotations=_readonly_tool_annotations(),
        ),
        MCPToolDefinition(
            name="bundle_status",
            description=(
                "Use this when you need bundle metadata only. Inspect the latest or named DSPy "
                "bundle manifest, including promoted stable/canary channel state."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "root": {
                        "type": "string",
                        "description": (
                            "Optional repository root override relative to the server root."
                        ),
                    },
                    "run_name": {
                        "type": "string",
                        "description": "Optional specific bundle run name to inspect.",
                    },
                    "channel": {
                        "type": "string",
                        "enum": ["stable", "canary"],
                        "description": "Optional promoted channel to inspect.",
                    },
                },
                "additionalProperties": False,
            },
            annotations=_readonly_tool_annotations(),
        ),
        MCPToolDefinition(
            name="dspy_artifacts",
            description=(
                "Use this when you need saved-run inventory only. List saved DSPy runs, "
                "published bundles, and the latest bundle metadata without triggering new "
                "compilation."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "root": {
                        "type": "string",
                        "description": (
                            "Optional repository root override relative to the server root."
                        ),
                    }
                },
                "additionalProperties": False,
            },
            annotations=_readonly_tool_annotations(),
        ),
        MCPToolDefinition(
            name="publish_trace",
            description=(
                "Use this when you need to enqueue one normalized worker trace for later "
                "trainer-side drain. This writes queue state and is not a read-only tool."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "trace_path": {
                        "type": "string",
                        "description": "Path to the normalized trace payload to enqueue.",
                    },
                    "root": {
                        "type": "string",
                        "description": (
                            "Optional repository root override relative to the server root."
                        ),
                    },
                    "trace_name": {
                        "type": "string",
                        "description": "Optional explicit trace name override.",
                    },
                    "queue_name": {
                        "type": "string",
                        "description": "Target trainer queue name.",
                    },
                    "outcome_path": {
                        "type": "string",
                        "description": (
                            "Optional outcome payload path to attach to the enqueue record."
                        ),
                    },
                },
                "required": ["trace_path"],
                "additionalProperties": False,
            },
            annotations=_queue_write_tool_annotations(),
        ),
    ]


def build_mcp_resource_definitions() -> list[MCPResourceDefinition]:
    """Return the bounded MCP direct-resource catalog."""

    return [
        MCPResourceDefinition(
            uri=f"{MCP_RESOURCE_SCHEME}://overview",
            name="Repository Overview",
            title="repo-rag repository overview",
            description=(
                "Optional supporting overview. Summarizes the repository root, active retrieval "
                "profile, and the preferred tool-first repo-RAG discovery workflow."
            ),
            mime_type="text/markdown",
        ),
        MCPResourceDefinition(
            uri=f"{MCP_RESOURCE_SCHEME}://startup-context",
            name="Repository Startup Context",
            title="repo-rag bounded startup context",
            description=(
                "Optional supporting working set. Returns a small startup shortlist for the "
                "current repo plus example MCP tool calls to continue discovery without broad "
                "shell exploration."
            ),
            mime_type="text/markdown",
        ),
        MCPResourceDefinition(
            uri=f"{MCP_RESOURCE_SCHEME}://discovery-guide",
            name="Repository Discovery Guide",
            title="repo-rag MCP discovery guide",
            description=(
                "Explains the preferred tool-first MCP discovery path. Use this if you want a "
                "concrete `search_repo` / `ask_repo` calling pattern."
            ),
            mime_type="text/markdown",
        ),
        MCPResourceDefinition(
            uri=f"{MCP_RESOURCE_SCHEME}://retrieval-profile",
            name="Retrieval Profile",
            title="repo-rag retrieval profile",
            description=(
                "Returns the effective retrieval profile and default low-level retrieval mode "
                "for the current repository root."
            ),
            mime_type="application/json",
        ),
        MCPResourceDefinition(
            uri=f"{MCP_RESOURCE_SCHEME}://corpus-manifest",
            name="Corpus Manifest",
            title="repo-rag corpus manifest summary",
            description=(
                "Returns the current indexed text-corpus fingerprint and file manifest used "
                "for repo-RAG retrieval invalidation."
            ),
            mime_type="application/json",
        ),
    ]


def build_mcp_resource_template_definitions() -> list[MCPResourceTemplateDefinition]:
    """Return the bounded MCP parameterized-resource catalog."""

    return [
        MCPResourceTemplateDefinition(
            uri_template=f"{MCP_RESOURCE_SCHEME}://search{{?question,top_k,retrieval_mode}}",
            name="Repository Discovery Search",
            title="repo-rag bounded discovery search",
            description=(
                "Optional resource-backed discovery view. Prefer MCP tool `search_repo` first; "
                "use this only when you intentionally want a concrete resource URI."
            ),
            mime_type="application/json",
        ),
        MCPResourceTemplateDefinition(
            uri_template=f"{MCP_RESOURCE_SCHEME}://ask{{?question,retrieval_mode}}",
            name="Repository Ask",
            title="repo-rag bounded ask",
            description=(
                "Optional resource-backed bounded answer. Prefer MCP tool `ask_repo` after "
                "discovery; use this only when you intentionally want a concrete resource URI."
            ),
            mime_type="application/json",
        ),
    ]


def _text_resource_content(uri: str, *, text: str, mime_type: str) -> dict[str, object]:
    """Return one MCP text resource content record."""

    return {"uri": uri, "mimeType": mime_type, "text": text}


def _resource_read_result(uri: str, *, text: str, mime_type: str) -> dict[str, object]:
    """Return one MCP `resources/read` payload."""

    return {"contents": [_text_resource_content(uri, text=text, mime_type=mime_type)]}


def _resource_query_value(parsed: object, key: str) -> str | None:
    """Return one normalized query parameter from one parsed resource URI."""

    if not isinstance(parsed, SplitResult):
        return None
    values = parse_qs(parsed.query, keep_blank_values=False).get(key)
    if not values:
        return None
    text = str(values[-1]).strip()
    return text or None


def _resource_retrieval_mode_from_uri(parsed: object) -> RetrievalMode | None:
    """Return the requested retrieval mode from one resource URI when provided."""

    raw_value = _resource_query_value(parsed, "retrieval_mode")
    if raw_value is None:
        default_value = str(os.getenv(MCP_DEFAULT_RETRIEVAL_MODE_ENV) or "").strip()
        raw_value = default_value or None
    if raw_value is None:
        return None
    if raw_value not in SUPPORTED_RETRIEVAL_MODES:
        supported = ", ".join(sorted(SUPPORTED_RETRIEVAL_MODES))
        raise ValueError(f"`retrieval_mode` must be one of: {supported}")
    return cast(RetrievalMode, raw_value)


def _overview_resource_text(server_root: Path) -> str:
    """Return the repository overview resource text."""

    profile = load_retrieval_profile(server_root)
    manifest = build_corpus_manifest(server_root)
    lines = [
        "# repo-rag Repository Overview",
        "",
        f"- Root: `{server_root}`",
        f"- Retrieval profile: `{profile.name}`",
        f"- Default retrieval mode: `{profile.retrieval_mode}`",
        f"- Indexed document count: `{manifest['document_count']}`",
        f"- Corpus fingerprint: `{manifest['corpus_fingerprint']}`",
        "",
        "Preferred workflow:",
        "1. Call MCP tool `search_repo` first for repository discovery.",
        "2. Use MCP tool `ask_repo` for one concise repo-grounded answer after discovery.",
        "3. Treat resources as optional supporting surfaces, not the primary discovery path.",
        "4. Use shell reads only for exact file verification and post-edit validation.",
    ]
    return "\n".join(lines)


def _startup_context_resource_text(server_root: Path) -> str:
    """Return one bounded startup working set resource."""

    profile = load_retrieval_profile(server_root)
    context = collect_repository_context(
        question=MCP_STARTUP_CONTEXT_QUESTION,
        root=server_root,
        top_k=4,
        retrieval_mode=cast(RetrievalMode, profile.retrieval_mode),
    )
    serialized = [serialize_chunk(chunk, root=server_root) for chunk in context]
    payload = {
        "command": "startup-context-resource",
        "root": str(server_root),
        "question": MCP_STARTUP_CONTEXT_QUESTION,
        "retrieval_mode": profile.retrieval_mode,
        "sources": [item.get("source") for item in serialized],
        "context": serialized,
        "next_actions": [
            (
                "If you need repository discovery, call MCP tool search_repo with "
                "question=<your question> and top_k=4."
            ),
            ("Use MCP tool ask_repo for one bounded repo-grounded answer after discovery."),
            (
                "Use shell reads only after MCP tool discovery narrowed the file set or when exact "
                "post-edit verification is required."
            ),
        ],
        "examples": {
            "search_tool": {
                "name": "search_repo",
                "arguments": {
                    "question": "transmutation preview flow",
                    "top_k": 4,
                },
            },
            "ask_tool": {
                "name": "ask_repo",
                "arguments": {
                    "question": "current transmutation entry points",
                },
            },
        },
    }
    return json.dumps(payload, indent=2)


def _discovery_guide_resource_text(server_root: Path) -> str:
    """Return one explicit guide for MCP-first repository discovery."""

    profile = load_retrieval_profile(server_root)
    lines = [
        "# repo-rag MCP Discovery Guide",
        "",
        f"- Root: `{server_root}`",
        f"- Default retrieval mode: `{profile.retrieval_mode}`",
        "",
        "Use these exact patterns:",
        (
            '- `call_mcp_tool("search_repo", {"question": "<your question>", "top_k": 4})` '
            "for repository discovery."
        ),
        (
            '- `call_mcp_tool("ask_repo", {"question": "<your question>"})` for one concise '
            "repo-grounded answer."
        ),
        (
            '- `read_mcp_resource("repo-rag://startup-context")` only if you want one optional '
            "supporting working set."
        ),
        "",
        (
            "Do not interpret empty or template-only resource listings as absence of repo-rag. "
            "The primary discovery path is direct MCP tool calls, not resource listing."
        ),
    ]
    return "\n".join(lines)


def read_mcp_resource(uri: str, *, server_root: Path) -> dict[str, object]:
    """Read one direct or template resource and return its MCP payload."""

    parsed = urlsplit(uri)
    if parsed.scheme != MCP_RESOURCE_SCHEME:
        raise FileNotFoundError(f"Unsupported MCP resource URI: {uri}")

    if parsed.netloc == "overview":
        return _resource_read_result(
            uri,
            text=_overview_resource_text(server_root),
            mime_type="text/markdown",
        )

    if parsed.netloc == "startup-context":
        return _resource_read_result(
            uri,
            text=f"{_startup_context_resource_text(server_root)}\n",
            mime_type="application/json",
        )

    if parsed.netloc == "discovery-guide":
        return _resource_read_result(
            uri,
            text=_discovery_guide_resource_text(server_root),
            mime_type="text/markdown",
        )

    if parsed.netloc == "retrieval-profile":
        profile = load_retrieval_profile(server_root)
        payload = {
            "root": str(server_root),
            "profile": _jsonify(asdict(profile)),
        }
        return _resource_read_result(
            uri,
            text=f"{json.dumps(payload, indent=2)}\n",
            mime_type="application/json",
        )

    if parsed.netloc == "corpus-manifest":
        manifest = build_corpus_manifest(server_root)
        return _resource_read_result(
            uri,
            text=f"{json.dumps(manifest, indent=2)}\n",
            mime_type="application/json",
        )

    if parsed.netloc == "search":
        question = _resource_query_value(parsed, "question")
        if not question:
            raise ValueError("`repo-rag://search` requires a non-empty `question` query parameter.")
        raw_top_k = _resource_query_value(parsed, "top_k") or "4"
        try:
            top_k = max(1, min(12, int(raw_top_k)))
        except ValueError:
            raise ValueError("`top_k` must be an integer between 1 and 12.") from None
        retrieval_mode_value = _resource_retrieval_mode_from_uri(parsed)
        profile = load_retrieval_profile(server_root)
        resolved_mode = retrieval_mode_value or profile.retrieval_mode
        context = collect_repository_context(
            question=question,
            root=server_root,
            top_k=top_k,
            retrieval_mode=retrieval_mode_value,
        )
        mcp_candidates = [candidate.__dict__ for candidate in discover_mcp_servers(server_root)]
        serialized_context = [serialize_chunk(chunk, root=server_root) for chunk in context[:top_k]]
        sources = list(
            dict.fromkeys(item["source"] for item in serialized_context if "source" in item)
        )
        payload = {
            "command": "search-repo-resource",
            "command_status": "success",
            "root": str(server_root),
            "question": question,
            "top_k": top_k,
            "retrieval_mode": resolved_mode,
            "sources": sources,
            "context": serialized_context,
            "mcp_candidates": mcp_candidates,
            "warnings": [],
        }
        return _resource_read_result(
            uri,
            text=f"{json.dumps(payload, indent=2)}\n",
            mime_type="application/json",
        )

    if parsed.netloc == "ask":
        question = _resource_query_value(parsed, "question")
        if not question:
            raise ValueError("`repo-rag://ask` requires a non-empty `question` query parameter.")
        retrieval_mode_value = _resource_retrieval_mode_from_uri(parsed)
        payload = ask_repository(
            question=question,
            root=server_root,
            retrieval_mode=retrieval_mode_value,
        ).to_payload(root=server_root)
        payload["command"] = "ask-resource"
        payload["command_status"] = "success"
        payload["root"] = str(server_root)
        return _resource_read_result(
            uri,
            text=f"{json.dumps(payload, indent=2)}\n",
            mime_type="application/json",
        )

    raise FileNotFoundError(f"Resource not found: {uri}")


def call_mcp_tool(
    tool_name: str,
    arguments: Mapping[str, object] | None,
    *,
    server_root: Path,
) -> dict[str, object]:
    """Execute one bounded MCP tool call and return its result payload.

    Example:
        >>> from pathlib import Path
        >>> result = call_mcp_tool(
        ...     "bundle_status",
        ...     {"root": "."},
        ...     server_root=Path(".").resolve(),
        ... )
        >>> result["isError"] in {True, False}
        True
    """

    params = dict(arguments or {})
    root = _resolve_root(server_root, params.get("root"))
    default_retrieval_mode = os.getenv(MCP_DEFAULT_RETRIEVAL_MODE_ENV)

    def _resolve_tool_retrieval_mode() -> RetrievalMode | None:
        retrieval_mode = params.get("retrieval_mode")
        selected = retrieval_mode if retrieval_mode is not None else default_retrieval_mode
        if selected is None:
            return None
        if selected not in SUPPORTED_RETRIEVAL_MODES:
            raise ValueError(
                "`retrieval_mode` must be one of: " + ", ".join(sorted(SUPPORTED_RETRIEVAL_MODES))
            )
        return cast(RetrievalMode, selected)

    if tool_name == "search_repo":
        question = params.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("`search_repo` requires a non-empty `question`.")
        retrieval_mode_value = _resolve_tool_retrieval_mode()
        raw_top_k = params.get("top_k", 4)
        if isinstance(raw_top_k, bool):
            top_k = int(raw_top_k)
        elif isinstance(raw_top_k, int):
            top_k = raw_top_k
        elif isinstance(raw_top_k, float):
            top_k = int(raw_top_k)
        elif isinstance(raw_top_k, str):
            try:
                top_k = int(raw_top_k.strip())
            except ValueError:
                raise ValueError("`top_k` must be an integer between 1 and 12.") from None
        else:
            raise ValueError("`top_k` must be an integer between 1 and 12.") from None
        top_k = max(1, min(12, top_k))
        context = collect_repository_context(
            question=question,
            root=root,
            top_k=top_k,
            retrieval_mode=retrieval_mode_value,
        )
        sources = list(
            dict.fromkeys(serialize_chunk(chunk, root=root)["source"] for chunk in context)
        )
        search_payload: dict[str, object] = {
            "command": "search-repo",
            "command_status": "success",
            "root": str(root),
            "question": question,
            "sources": sources,
            "context": [serialize_chunk(chunk, root=root) for chunk in context],
            "retrieval_mode": retrieval_mode_value or "default-profile",
            "warnings": [],
            "artifact_metadata": _artifact_metadata(),
            "mcp_candidates": [candidate.__dict__ for candidate in discover_mcp_servers(root)],
        }
        return _json_content(search_payload)

    if tool_name == "ask_repo":
        question = params.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("`ask_repo` requires a non-empty `question`.")
        retrieval_mode_value = _resolve_tool_retrieval_mode()
        rag_result = ask_repository(
            question=question,
            root=root,
            retrieval_mode=retrieval_mode_value,
        )
        payload: dict[str, object] = rag_result.to_payload(root=root)
        bundle_version = params.get("bundle_version")
        overlay_path = params.get("overlay_path")
        bundle_version_value = bundle_version if isinstance(bundle_version, str) else None
        overlay_path_value = overlay_path if isinstance(overlay_path, str) else None
        context_items = payload.get("context")
        normalized_context_items = context_items if isinstance(context_items, list) else []
        mcp_candidates = payload.get("mcp_candidates")
        normalized_mcp_candidates = mcp_candidates if isinstance(mcp_candidates, list) else []
        payload["command"] = "ask"
        payload["command_status"] = "success"
        payload["root"] = str(root)
        payload["warnings"] = []
        payload["artifact_metadata"] = _artifact_metadata()
        payload["mode"] = "baseline"
        payload["top_k"] = cast(object, 4)
        payload["bundle_version"] = cast(object, bundle_version_value)
        payload["overlay_path"] = cast(object, overlay_path_value)
        payload["trace"] = build_runtime_trace_payload(
            question=question,
            retrieval_mode=str(payload.get("retrieval_mode") or "lexical"),
            sources=_string_list_field(payload, "sources"),
            context_items=[item for item in normalized_context_items if isinstance(item, dict)],
            bundle_version=bundle_version_value,
            overlay_path=overlay_path_value,
            mcp_candidate_count=len(normalized_mcp_candidates),
            answer_length=len(str(payload.get("answer") or "")),
        )
        return _json_content(payload)

    if tool_name == "bundle_status":
        channel = params.get("channel")
        if channel is not None and channel not in {"stable", "canary"}:
            raise ValueError("`channel` must be `stable` or `canary`.")
        raw_run_name = params.get("run_name")
        run_name: str | None = raw_run_name if isinstance(raw_run_name, str) else None
        payload = json.loads(
            run_bundle_inspection(
                root,
                run_name=run_name,
                channel=str(channel) if isinstance(channel, str) else None,
            )
        )
        return _json_content(payload, is_error=payload.get("command_status") != "success")

    if tool_name == "dspy_artifacts":
        payload = json.loads(run_dspy_artifacts(root))
        return _json_content(payload, is_error=payload.get("command_status") != "success")

    if tool_name == "publish_trace":
        trace_path = params.get("trace_path")
        if not isinstance(trace_path, str) or not trace_path.strip():
            raise ValueError("`publish_trace` requires a non-empty `trace_path`.")
        queue_name = params.get("queue_name")
        if queue_name is not None and (not isinstance(queue_name, str) or not queue_name.strip()):
            raise ValueError("`queue_name` must be a non-empty string when provided.")
        outcome_path = params.get("outcome_path")
        raw_trace_name = params.get("trace_name")
        trace_name: str | None = raw_trace_name if isinstance(raw_trace_name, str) else None
        payload = json.loads(
            run_trace_enqueue(
                root,
                trace_path=Path(trace_path),
                trace_name=trace_name,
                queue_name=str(queue_name) if isinstance(queue_name, str) else "default",
                outcome_path=Path(outcome_path)
                if isinstance(outcome_path, str) and outcome_path.strip()
                else None,
            )
        )
        return _json_content(payload, is_error=payload.get("command_status") != "success")

    raise ValueError(
        f"Unsupported MCP tool `{tool_name}`. Supported tools: "
        + ", ".join(tool.name for tool in build_mcp_tool_definitions())
    )


def _json_rpc_success(message_id: object, result: Mapping[str, object]) -> dict[str, object]:
    """Return one JSON-RPC success response."""

    return {"jsonrpc": "2.0", "id": message_id, "result": dict(result)}


def _json_rpc_error(message_id: object, code: int, message: str) -> dict[str, object]:
    """Return one JSON-RPC error response."""

    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def _remember_stream_protocol(stream: object, mode: Literal["framed", "line"]) -> None:
    """Persist the detected JSON-RPC transport mode for one stream object."""

    _STREAM_PROTOCOL_MODES[stream] = mode


def _stream_protocol(stream: object) -> str | None:
    """Return the last detected JSON-RPC transport mode for one stream object."""

    return _STREAM_PROTOCOL_MODES.get(stream)


def _decode_json_rpc_payload(payload_bytes: bytes) -> dict[str, object]:
    """Decode one JSON-RPC payload body into a normalized mapping."""

    payload = json.loads(payload_bytes.decode("utf-8"))
    if not isinstance(payload, dict):
        _log_mcp_debug("payload-not-object")
        raise ValueError("JSON-RPC payload must be an object.")
    _log_mcp_debug(f"message method={payload.get('method') or ''!s} id={payload.get('id') or ''!s}")
    return {str(key): value for key, value in payload.items()}


def handle_mcp_message(
    message: Mapping[str, object], *, server_root: Path
) -> dict[str, object] | None:
    """Handle one JSON-RPC MCP message and return an optional response."""

    method = message.get("method")
    if not isinstance(method, str):
        return _json_rpc_error(message.get("id"), -32600, "Invalid JSON-RPC request.")

    message_id = message.get("id")
    params = message.get("params")
    param_mapping = params if isinstance(params, Mapping) else {}

    if method == "initialize":
        _log_usage_event(method=method, server_root=server_root)
        return _json_rpc_success(
            message_id,
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {
                    "name": MCP_SERVER_NAME,
                    "version": _server_version(),
                },
                "instructions": MCP_SERVER_INSTRUCTIONS,
            },
        )

    if method == "notifications/initialized":
        return None

    if method == "ping":
        return _json_rpc_success(message_id, {})

    if method == "tools/list":
        _log_usage_event(method=method, server_root=server_root)
        return _json_rpc_success(
            message_id,
            {"tools": [tool.to_payload() for tool in build_mcp_tool_definitions()]},
        )

    if method == "resources/list":
        _log_usage_event(method=method, server_root=server_root)
        return _json_rpc_success(
            message_id,
            {"resources": [resource.to_payload() for resource in build_mcp_resource_definitions()]},
        )

    if method == "resources/templates/list":
        _log_usage_event(method=method, server_root=server_root)
        return _json_rpc_success(
            message_id,
            {
                "resourceTemplates": [
                    template.to_payload() for template in build_mcp_resource_template_definitions()
                ]
            },
        )

    if method == "resources/read":
        uri = param_mapping.get("uri")
        if not isinstance(uri, str) or not uri.strip():
            return _json_rpc_error(message_id, -32602, "Resource reads require a non-empty `uri`.")
        try:
            parsed_uri = urlsplit(uri.strip())
            _log_usage_event(
                method=method,
                server_root=server_root,
                details={"uri": uri.strip(), "resource_kind": parsed_uri.netloc},
            )
            result = read_mcp_resource(uri.strip(), server_root=server_root)
        except FileNotFoundError as exc:
            return _json_rpc_error(message_id, -32002, str(exc))
        except Exception as exc:
            return _json_rpc_error(message_id, -32603, str(exc))
        return _json_rpc_success(message_id, result)

    if method == "tools/call":
        tool_name = param_mapping.get("name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            return _json_rpc_error(message_id, -32602, "Tool calls require a non-empty `name`.")
        arguments = param_mapping.get("arguments")
        try:
            arguments_mapping = arguments if isinstance(arguments, Mapping) else None
            _log_usage_event(
                method=method,
                tool_name=tool_name,
                server_root=server_root,
                details={
                    "argument_keys": sorted(arguments_mapping.keys()) if arguments_mapping else [],
                },
            )
            result = call_mcp_tool(
                tool_name,
                arguments_mapping,
                server_root=server_root,
            )
        except Exception as exc:
            result = _json_content(
                {"error": {"type": type(exc).__name__, "message": str(exc)}}, is_error=True
            )
        return _json_rpc_success(message_id, result)

    return _json_rpc_error(message_id, -32601, f"Unsupported MCP method `{method}`.")


def read_json_rpc_message(stream: BinaryIO) -> dict[str, object] | None:
    """Read one JSON-RPC message from ``stream``.

    Supports both MCP `Content-Length` framing and the newline-delimited JSON-RPC
    variant emitted by current `codex exec` MCP clients.
    """

    buffered_bytes = _STREAM_READ_BUFFERS.setdefault(stream, bytearray())
    try:
        fileno = stream.fileno()
    except Exception:
        fileno = None
    if fileno is not None:
        try:
            os.fstat(fileno)
        except OSError:
            fileno = None
    waiting_logged = False

    if fileno is not None:
        while b"\r\n\r\n" not in buffered_bytes and b"\n" not in buffered_bytes:
            ready, _, _ = select.select([fileno], [], [], 5.0)
            if not ready:
                if not waiting_logged:
                    _log_mcp_debug("waiting-for-headers no-bytes-yet")
                    waiting_logged = True
                continue
            chunk = os.read(fileno, 4096)
            if chunk == b"":
                _log_mcp_debug("eof-before-headers")
                return None
            buffered_bytes.extend(chunk)

        stripped_buffer = bytes(buffered_bytes).lstrip()
        if stripped_buffer.startswith(b"{"):
            newline_index = buffered_bytes.find(b"\n")
            if newline_index < 0:
                raise ValueError("Incomplete line-delimited JSON-RPC message.")
            line_bytes = bytes(buffered_bytes[:newline_index]).rstrip(b"\r")
            del buffered_bytes[: newline_index + 1]
            _remember_stream_protocol(stream, "line")
            _log_mcp_debug(f"line-bytes {len(line_bytes)}")
            return _decode_json_rpc_payload(line_bytes)

        headers: dict[str, str] = {}
        if b"\r\n\r\n" not in buffered_bytes:
            raise ValueError("Missing Content-Length header terminator.")
        header_bytes, remainder = buffered_bytes.split(b"\r\n\r\n", 1)
        for raw_line in header_bytes.decode("utf-8", errors="ignore").split("\r\n"):
            if not raw_line:
                continue
            _log_mcp_debug(f"header-line {raw_line}")
            key, separator, value = raw_line.partition(":")
            if separator != ":":
                _log_mcp_debug("invalid-header-line")
                raise ValueError("Invalid JSON-RPC header line.")
            headers[key.strip().lower()] = value.strip()
        buffered_bytes[:] = remainder

        if "content-length" not in headers:
            _log_mcp_debug("missing-content-length")
            raise ValueError("Missing Content-Length header.")
        content_length = int(headers["content-length"])
        while len(buffered_bytes) < content_length:
            chunk = os.read(fileno, max(4096, content_length - len(buffered_bytes)))
            if not chunk:
                _log_mcp_debug(
                    f"eof-during-body received={len(buffered_bytes)} expected={content_length}"
                )
                raise ValueError("Incomplete JSON-RPC message body.")
            buffered_bytes.extend(chunk)
        body = bytes(buffered_bytes[:content_length])
        del buffered_bytes[:content_length]
        _remember_stream_protocol(stream, "framed")
        _log_mcp_debug(f"body-bytes {content_length}")
        return _decode_json_rpc_payload(body)

    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if line == b"":
            _log_mcp_debug("eof-before-headers")
            return None
        if not headers and line.lstrip().startswith(b"{"):
            _remember_stream_protocol(stream, "line")
            _log_mcp_debug(f"line-bytes {len(line.rstrip())}")
            return _decode_json_rpc_payload(line.rstrip(b"\r\n"))
        if line in {b"\r\n", b"\n"}:
            if headers:
                break
            continue
        _log_mcp_debug(f"header-line {line.decode('utf-8', errors='ignore').rstrip()}")
        key, separator, value = line.decode("utf-8").partition(":")
        if separator != ":":
            _log_mcp_debug("invalid-header-line")
            raise ValueError("Invalid JSON-RPC header line.")
        headers[key.strip().lower()] = value.strip()

    if "content-length" not in headers:
        _log_mcp_debug("missing-content-length")
        raise ValueError("Missing Content-Length header.")
    content_length = int(headers["content-length"])
    body = bytearray()
    while len(body) < content_length:
        chunk = stream.read(content_length - len(body))
        if not chunk:
            _log_mcp_debug(f"eof-during-body received={len(body)} expected={content_length}")
            raise ValueError("Incomplete JSON-RPC message body.")
        body.extend(chunk)
    _remember_stream_protocol(stream, "framed")
    _log_mcp_debug(f"body-bytes {content_length}")
    return _decode_json_rpc_payload(bytes(body))


def write_json_rpc_message(
    stream: BinaryIO,
    payload: Mapping[str, object],
    *,
    protocol: Literal["framed", "line"] = "framed",
) -> None:
    """Write one JSON-RPC message to ``stream``."""

    body = json.dumps(dict(payload)).encode("utf-8")
    if protocol == "line":
        stream.write(body + b"\n")
    else:
        stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
        stream.write(body)
    stream.flush()


def serve_repo_rag_mcp(
    root: Path,
    *,
    input_stream: BinaryIO,
    output_stream: BinaryIO,
) -> int:
    """Serve the bounded repo-RAG MCP surface over stdio until EOF."""

    _log_mcp_debug(
        "server-start "
        f"pid={os.getpid()} "
        f"cwd={os.getcwd()} "
        f"root={root} "
        f"stdin={_fd_target(0)} "
        f"stdout={_fd_target(1)} "
        f"stderr={_fd_target(2)}"
    )
    while True:
        message = read_json_rpc_message(input_stream)
        if message is None:
            _log_mcp_debug("server-stop eof")
            return 0
        response = handle_mcp_message(message, server_root=root)
        if response is not None:
            _log_mcp_debug(
                f"response method={message.get('method') or ''!s} id={message.get('id') or ''!s}"
            )
            protocol = cast(Literal["framed", "line"], _stream_protocol(input_stream) or "framed")
            write_json_rpc_message(output_stream, response, protocol=protocol)
