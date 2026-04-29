# pyright: reportUnknownLambdaType=false, reportPrivateUsage=false

from __future__ import annotations

import io
import json
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any, cast

import pytest

import repo_rag_lab.mcp_server as mcp_server


def test_build_mcp_tool_definitions_exposes_only_bounded_tools() -> None:
    tools = mcp_server.build_mcp_tool_definitions()

    assert [tool.name for tool in tools] == [
        "ask_repo",
        "bundle_status",
        "dspy_artifacts",
        "publish_trace",
    ]
    assert all("trainer" not in tool.name for tool in tools)


def test_server_version_falls_back_when_package_metadata_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_version(_: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(mcp_server, "version", fake_version)

    assert mcp_server._server_version() == "0.0.0"


def test_resolve_root_and_string_list_helpers_cover_default_relative_and_absolute_cases(
    tmp_path: Path,
) -> None:
    absolute_target = (tmp_path / "absolute").resolve()
    relative_target = tmp_path / "relative"

    assert mcp_server._resolve_root(tmp_path, None) == tmp_path
    assert mcp_server._resolve_root(tmp_path, "") == tmp_path
    assert mcp_server._resolve_root(tmp_path, "relative") == relative_target.resolve()
    assert mcp_server._resolve_root(tmp_path, str(absolute_target)) == absolute_target
    assert mcp_server._string_list_field({"sources": ["a", 2]}, "sources") == ["a", "2"]
    assert mcp_server._string_list_field({"sources": "not-a-list"}, "sources") == []


def test_call_mcp_tool_ask_repo_returns_structured_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FakeChunk:
        source = tmp_path / "README.md"
        text = "Repository research context."

    class FakeResult:
        def to_payload(self, *, root: Path) -> dict[str, object]:
            del root
            return {
                "question": "What does this repository research?",
                "answer": "Repository summary",
                "response_text": "Question: ...",
                "sources": ["README.md"],
                "context": [
                    {
                        "source": "README.md",
                        "preview": "Repository research context.",
                        "text": FakeChunk.text,
                    }
                ],
                "mcp_candidates": [{"path": "mcp.json", "hint": "Configured MCP"}],
                "retrieval_mode": "idf-rerank",
            }

    monkeypatch.setattr(mcp_server, "ask_repository", lambda **kwargs: FakeResult())

    payload = mcp_server.call_mcp_tool(
        "ask_repo",
        {"question": "What does this repository research?", "retrieval_mode": "idf-rerank"},
        server_root=tmp_path,
    )

    assert payload["isError"] is False
    structured = cast(dict[str, Any], payload["structuredContent"])
    trace = cast(dict[str, Any], structured["trace"])
    assert structured["command"] == "ask"
    assert structured["mode"] == "baseline"
    assert trace["mode"] == "baseline"
    assert trace["mcp_candidate_count"] == 1


def test_call_mcp_tool_ask_repo_supports_lexical_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    class FakeResult:
        def to_payload(self, *, root: Path) -> dict[str, object]:
            del root
            return {
                "question": "What does this repository research?",
                "answer": "Repository summary",
                "response_text": "Question: ...",
                "sources": ["README.md"],
                "context": [],
                "mcp_candidates": [],
                "retrieval_mode": "lexical",
            }

    def fake_ask_repository(**kwargs: object) -> FakeResult:
        captured.update(kwargs)
        return FakeResult()

    monkeypatch.setattr(mcp_server, "ask_repository", fake_ask_repository)

    payload = mcp_server.call_mcp_tool(
        "ask_repo",
        {"question": "What does this repository research?", "retrieval_mode": "lexical"},
        server_root=tmp_path,
    )

    assert payload["isError"] is False
    assert captured["retrieval_mode"] == "lexical"


def test_call_mcp_tool_ask_repo_validates_question_and_retrieval_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="question"):
        mcp_server.call_mcp_tool("ask_repo", {"question": ""}, server_root=tmp_path)

    with pytest.raises(ValueError, match="retrieval_mode"):
        mcp_server.call_mcp_tool(
            "ask_repo",
            {"question": "What does this repository research?", "retrieval_mode": "dense"},
            server_root=tmp_path,
        )


def test_call_mcp_tool_bundle_status_reuses_bundle_inspection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        mcp_server,
        "run_bundle_inspection",
        lambda root, run_name=None, channel=None: json.dumps(
            {
                "command": "bundle-inspect",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "bundle_version": run_name or channel or "stable",
            }
        ),
    )

    payload = mcp_server.call_mcp_tool(
        "bundle_status",
        {"run_name": "demo-run"},
        server_root=tmp_path,
    )

    assert payload["isError"] is False
    structured = cast(dict[str, Any], payload["structuredContent"])
    assert structured["command"] == "bundle-inspect"
    assert structured["bundle_version"] == "demo-run"


def test_call_mcp_tool_bundle_status_validates_channel(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="channel"):
        mcp_server.call_mcp_tool(
            "bundle_status",
            {"channel": "beta"},
            server_root=tmp_path,
        )


def test_call_mcp_tool_dspy_artifacts_round_trips_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        mcp_server,
        "run_dspy_artifacts",
        lambda root: json.dumps(
            {
                "command": "dspy-artifacts",
                "command_status": "success",
                "root": str(root),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "run_count": 0,
            }
        ),
    )

    payload = mcp_server.call_mcp_tool("dspy_artifacts", {"root": "."}, server_root=tmp_path)

    assert payload["isError"] is False
    structured = cast(dict[str, Any], payload["structuredContent"])
    assert structured["command"] == "dspy-artifacts"
    assert structured["run_count"] == 0


def test_call_mcp_tool_publish_trace_validates_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="trace_path"):
        mcp_server.call_mcp_tool("publish_trace", {}, server_root=tmp_path)

    with pytest.raises(ValueError, match="queue_name"):
        mcp_server.call_mcp_tool(
            "publish_trace",
            {"trace_path": "trace.json", "queue_name": ""},
            server_root=tmp_path,
        )


def test_call_mcp_tool_publish_trace_round_trips_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        mcp_server,
        "run_trace_enqueue",
        lambda root, trace_path, trace_name=None, queue_name="default", outcome_path=None: (
            json.dumps(
                {
                    "command": "trace-enqueue",
                    "command_status": "success",
                    "root": str(root),
                    "warnings": [],
                    "artifact_metadata": {
                        "input_paths": [str(trace_path)],
                        "generated_paths": ["artifacts/traces/queued/demo.json"],
                        "related_paths": ["artifacts/traces/queued"],
                    },
                    "trace_name": trace_name or "demo-trace",
                    "queue_name": queue_name,
                    "outcome_path": str(outcome_path) if outcome_path is not None else None,
                }
            )
        ),
    )

    payload = mcp_server.call_mcp_tool(
        "publish_trace",
        {
            "trace_path": "trace.json",
            "trace_name": "demo-trace",
            "queue_name": "dataset",
            "outcome_path": "outcome.json",
        },
        server_root=tmp_path,
    )

    structured = cast(dict[str, Any], payload["structuredContent"])
    assert structured["command"] == "trace-enqueue"
    assert structured["queue_name"] == "dataset"
    assert structured["trace_name"] == "demo-trace"


def test_call_mcp_tool_rejects_unsupported_tools(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported MCP tool"):
        mcp_server.call_mcp_tool("trainer_cycle", {}, server_root=tmp_path)


def test_handle_mcp_message_lists_tools(tmp_path: Path) -> None:
    response = mcp_server.handle_mcp_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        server_root=tmp_path,
    )

    assert response is not None
    result = cast(dict[str, Any], response["result"])
    tools = cast(list[dict[str, Any]], result["tools"])
    assert tools[0]["name"] == "ask_repo"


def test_handle_mcp_message_wraps_tool_errors(tmp_path: Path) -> None:
    response = mcp_server.handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "publish_trace", "arguments": {}},
        },
        server_root=tmp_path,
    )

    assert response is not None
    result = cast(dict[str, Any], response["result"])
    assert result["isError"] is True
    structured = cast(dict[str, Any], result["structuredContent"])
    error = cast(dict[str, Any], structured["error"])
    assert error["type"] == "ValueError"


def test_handle_mcp_message_covers_invalid_request_notifications_and_unknown_methods(
    tmp_path: Path,
) -> None:
    invalid_response = mcp_server.handle_mcp_message(
        {"jsonrpc": "2.0", "id": 9},
        server_root=tmp_path,
    )
    assert invalid_response is not None
    invalid_error = cast(dict[str, Any], invalid_response["error"])
    assert invalid_error["code"] == -32600

    assert (
        mcp_server.handle_mcp_message(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            server_root=tmp_path,
        )
        is None
    )

    missing_name = mcp_server.handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"arguments": {}},
        },
        server_root=tmp_path,
    )
    assert missing_name is not None
    missing_name_error = cast(dict[str, Any], missing_name["error"])
    assert missing_name_error["code"] == -32602

    unknown_method = mcp_server.handle_mcp_message(
        {"jsonrpc": "2.0", "id": 11, "method": "workers/run"},
        server_root=tmp_path,
    )
    assert unknown_method is not None
    unknown_method_error = cast(dict[str, Any], unknown_method["error"])
    assert unknown_method_error["code"] == -32601


def test_json_rpc_message_round_trip() -> None:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    buffer = io.BytesIO()

    mcp_server.write_json_rpc_message(buffer, payload)
    buffer.seek(0)

    assert mcp_server.read_json_rpc_message(buffer) == payload


def test_read_json_rpc_message_handles_header_and_payload_edge_cases() -> None:
    leading_blank = io.BytesIO()
    leading_blank.write(b"\r\n")
    mcp_server.write_json_rpc_message(leading_blank, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    leading_blank.seek(0)
    assert mcp_server.read_json_rpc_message(leading_blank) == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "ping",
    }

    with pytest.raises(ValueError, match="header"):
        mcp_server.read_json_rpc_message(io.BytesIO(b"Content-Length 10\r\n\r\n{}"))

    with pytest.raises(ValueError, match="Content-Length"):
        mcp_server.read_json_rpc_message(io.BytesIO(b"X-Test: 1\r\n\r\n{}"))

    with pytest.raises(ValueError, match="Incomplete"):
        mcp_server.read_json_rpc_message(io.BytesIO(b"Content-Length: 3\r\n\r\n{}"))

    with pytest.raises(ValueError, match="must be an object"):
        mcp_server.read_json_rpc_message(io.BytesIO(b"Content-Length: 2\r\n\r\n[]"))


def test_serve_repo_rag_mcp_handles_initialize_and_ping(tmp_path: Path) -> None:
    input_stream = io.BytesIO()
    output_stream = io.BytesIO()

    mcp_server.write_json_rpc_message(
        input_stream,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    mcp_server.write_json_rpc_message(
        input_stream,
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
    )
    input_stream.seek(0)

    assert (
        mcp_server.serve_repo_rag_mcp(
            tmp_path,
            input_stream=input_stream,
            output_stream=output_stream,
        )
        == 0
    )

    output_stream.seek(0)
    first = mcp_server.read_json_rpc_message(output_stream)
    second = mcp_server.read_json_rpc_message(output_stream)

    assert first is not None
    first_result = cast(dict[str, Any], first["result"])
    server_info = cast(dict[str, Any], first_result["serverInfo"])
    assert server_info["name"] == "repo-rag-mcp"
    assert second is not None
    second_result = cast(dict[str, Any], second["result"])
    assert second_result == {}


def test_serve_repo_rag_mcp_skips_notification_responses(tmp_path: Path) -> None:
    input_stream = io.BytesIO()
    output_stream = io.BytesIO()

    mcp_server.write_json_rpc_message(
        input_stream,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    mcp_server.write_json_rpc_message(
        input_stream,
        {"jsonrpc": "2.0", "id": 3, "method": "ping"},
    )
    input_stream.seek(0)

    assert (
        mcp_server.serve_repo_rag_mcp(
            tmp_path,
            input_stream=input_stream,
            output_stream=output_stream,
        )
        == 0
    )

    output_stream.seek(0)
    only_response = mcp_server.read_json_rpc_message(output_stream)
    assert only_response is not None
    assert mcp_server.read_json_rpc_message(output_stream) is None
