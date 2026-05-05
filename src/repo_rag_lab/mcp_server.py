"""Minimal stdio MCP server for bounded repo-RAG operations.

This module intentionally exposes only short-running tool calls. It does not route
trainer-side recompilation, long retrieval evaluations, or notebook execution through MCP.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import BinaryIO

from .retrieval import RetrievalMode
from .retrieval_profile import SUPPORTED_RETRIEVAL_MODES
from .runtime_artifacts import RuntimeTraceContext, build_runtime_trace
from .utilities import run_bundle_inspection, run_dspy_artifacts, run_trace_enqueue
from .mcp import discover_mcp_servers
from .workflow import ask_repository, collect_repository_context, serialize_chunk

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SERVER_NAME = "repo-rag-mcp"
MCP_SERVER_INSTRUCTIONS = (
    "Use these tools only for bounded repo-RAG operations. Do not route long DSPy training, "
    "full retrieval-eval sweeps, or notebook execution through this MCP surface."
)
RETRIEVAL_MODE_ENUM = sorted(SUPPORTED_RETRIEVAL_MODES)
MCP_USAGE_LOG_ENV = "REPO_RAG_MCP_USAGE_LOG"
MCP_DEFAULT_RETRIEVAL_MODE_ENV = "REPO_RAG_MCP_DEFAULT_RETRIEVAL_MODE"


@dataclass(frozen=True)
class MCPToolDefinition:
    """One bounded repo-RAG MCP tool definition."""

    name: str
    description: str
    input_schema: dict[str, object]

    def to_payload(self) -> dict[str, object]:
        """Return the JSON-serializable tool definition payload."""

        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


def _server_version() -> str:
    """Return the installed package version when available."""

    try:
        return version("repo-rag-lab")
    except PackageNotFoundError:
        return "0.0.0"


def _artifact_metadata() -> dict[str, list[str]]:
    """Return an empty artifact metadata payload."""

    return {"input_paths": [], "generated_paths": [], "related_paths": []}


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


def build_mcp_tool_definitions() -> list[MCPToolDefinition]:
    """Return the bounded MCP tool catalog exposed by this repository."""

    return [
        MCPToolDefinition(
            name="search_repo",
            description=(
                "Search the repository corpus and return a bounded shortlist of relevant files "
                "plus matching text previews. Prefer this for repository discovery before shell reads."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "root": {"type": "string"},
                    "retrieval_mode": {"type": "string", "enum": RETRIEVAL_MODE_ENUM},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 12},
                },
                "required": ["question"],
                "additionalProperties": False,
            },
        ),
        MCPToolDefinition(
            name="ask_repo",
            description=(
                "Run the bounded baseline repo-RAG ask path with local retrieval only. "
                "This MCP tool does not invoke live providers or DSPy compilation."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "root": {"type": "string"},
                    "retrieval_mode": {"type": "string", "enum": RETRIEVAL_MODE_ENUM},
                    "bundle_version": {"type": "string"},
                    "overlay_path": {"type": "string"},
                },
                "required": ["question"],
                "additionalProperties": False,
            },
        ),
        MCPToolDefinition(
            name="bundle_status",
            description=(
                "Inspect the latest or named DSPy bundle manifest, including promoted "
                "stable/canary channel state."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "root": {"type": "string"},
                    "run_name": {"type": "string"},
                    "channel": {"type": "string", "enum": ["stable", "canary"]},
                },
                "additionalProperties": False,
            },
        ),
        MCPToolDefinition(
            name="dspy_artifacts",
            description=(
                "List saved DSPy runs, published bundles, and the latest bundle metadata "
                "without triggering new compilation."
            ),
            input_schema={
                "type": "object",
                "properties": {"root": {"type": "string"}},
                "additionalProperties": False,
            },
        ),
        MCPToolDefinition(
            name="publish_trace",
            description=(
                "Stage one normalized worker trace into a trainer-side queue for later "
                "asynchronous drain. This is the MCP-safe trace handoff surface."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "trace_path": {"type": "string"},
                    "root": {"type": "string"},
                    "trace_name": {"type": "string"},
                    "queue_name": {"type": "string"},
                    "outcome_path": {"type": "string"},
                },
                "required": ["trace_path"],
                "additionalProperties": False,
            },
        ),
    ]


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
        return selected  # type: ignore[return-value]

    if tool_name == "search_repo":
        question = params.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("`search_repo` requires a non-empty `question`.")
        retrieval_mode_value = _resolve_tool_retrieval_mode()
        raw_top_k = params.get("top_k", 4)
        try:
            top_k = max(1, min(12, int(raw_top_k)))
        except (TypeError, ValueError):
            raise ValueError("`top_k` must be an integer between 1 and 12.") from None
        context = collect_repository_context(
            question=question,
            root=root,
            top_k=top_k,
            retrieval_mode=retrieval_mode_value,
        )
        sources = list(dict.fromkeys(serialize_chunk(chunk, root=root)["source"] for chunk in context))
        payload = {
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
        return _json_content(payload)

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
        payload = rag_result.to_payload(root=root)
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
        payload["top_k"] = 4
        payload["bundle_version"] = bundle_version_value
        payload["overlay_path"] = overlay_path_value
        payload["trace"] = build_runtime_trace(
            RuntimeTraceContext(
                question=question,
                mode="baseline",
                retrieval_mode=str(payload.get("retrieval_mode") or "lexical"),
                sources=_string_list_field(payload, "sources"),
                context_count=len(normalized_context_items),
                top_k=4,
                bundle_version=bundle_version_value,
                overlay_path=overlay_path_value,
                mcp_candidate_count=len(normalized_mcp_candidates),
                answer_length=len(str(payload.get("answer") or "")),
                context_field="context",
                evidence_items=[
                    item for item in normalized_context_items if isinstance(item, dict)
                ],
            )
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
                "capabilities": {"tools": {}},
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
    """Read one `Content-Length` framed JSON-RPC message from ``stream``."""

    headers: dict[str, str] = {}

    while True:
        line = stream.readline()
        if line == b"":
            return None
        if line in {b"\r\n", b"\n"}:
            if headers:
                break
            continue
        key, separator, value = line.decode("utf-8").partition(":")
        if separator != ":":
            raise ValueError("Invalid JSON-RPC header line.")
        headers[key.strip().lower()] = value.strip()

    if "content-length" not in headers:
        raise ValueError("Missing Content-Length header.")
    content_length = int(headers["content-length"])
    body = stream.read(content_length)
    if len(body) != content_length:
        raise ValueError("Incomplete JSON-RPC message body.")
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON-RPC payload must be an object.")
    return {str(key): value for key, value in payload.items()}


def write_json_rpc_message(stream: BinaryIO, payload: Mapping[str, object]) -> None:
    """Write one `Content-Length` framed JSON-RPC message to ``stream``."""

    body = json.dumps(dict(payload)).encode("utf-8")
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

    while True:
        message = read_json_rpc_message(input_stream)
        if message is None:
            return 0
        response = handle_mcp_message(message, server_root=root)
        if response is not None:
            write_json_rpc_message(output_stream, response)
