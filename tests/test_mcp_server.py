# pyright: reportUnknownLambdaType=false, reportPrivateUsage=false

from __future__ import annotations

import io
import json
import os
import threading
import time
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any, cast

import pytest

import repo_rag_lab.mcp_server as mcp_server
from repo_rag_lab.retrieval_profile import RetrievalProfile


def test_build_mcp_tool_definitions_exposes_only_bounded_tools() -> None:
    tools = mcp_server.build_mcp_tool_definitions()

    assert [tool.name for tool in tools] == [
        "search_repo",
        "ask_repo",
        "bundle_status",
        "dspy_artifacts",
        "publish_trace",
    ]
    assert all("trainer" not in tool.name for tool in tools)
    by_name = {tool.name: tool for tool in tools}
    assert by_name["search_repo"].annotations == {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    assert by_name["ask_repo"].annotations == by_name["search_repo"].annotations
    assert by_name["publish_trace"].annotations == {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
    assert by_name["search_repo"].description.startswith("Use this when")
    assert by_name["ask_repo"].description.startswith("Use this when")


def test_call_mcp_tool_search_repo_returns_structured_shortlist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FakeChunk:
        source = tmp_path / "README.md"
        text = "Repository research context."

    monkeypatch.setattr(
        mcp_server,
        "collect_repository_context",
        lambda **kwargs: [FakeChunk()],
    )
    monkeypatch.setattr(
        mcp_server,
        "serialize_chunk",
        lambda chunk, *, root: {
            "source": "README.md",
            "preview": "Repository research context.",
            "text": chunk.text,
        },
    )
    monkeypatch.setattr(
        mcp_server,
        "discover_mcp_servers",
        lambda root: [],
    )

    payload = mcp_server.call_mcp_tool(
        "search_repo",
        {"question": "Where should I start?", "retrieval_mode": "hybrid-vector", "top_k": 3},
        server_root=tmp_path,
    )

    assert payload["isError"] is False
    structured = cast(dict[str, Any], payload["structuredContent"])
    assert structured["command"] == "search-repo"
    assert structured["retrieval_mode"] == "hybrid-vector"
    assert structured["sources"] == ["README.md"]


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
    assert tools[0]["name"] == "search_repo"
    assert tools[0]["annotations"]["readOnlyHint"] is True
    assert tools[0]["inputSchema"]["properties"]["question"]["description"]
    assert tools[-1]["name"] == "publish_trace"
    assert tools[-1]["annotations"]["readOnlyHint"] is False


def test_handle_mcp_message_lists_resources_and_templates(tmp_path: Path) -> None:
    resources_response = mcp_server.handle_mcp_message(
        {"jsonrpc": "2.0", "id": 20, "method": "resources/list"},
        server_root=tmp_path,
    )
    templates_response = mcp_server.handle_mcp_message(
        {"jsonrpc": "2.0", "id": 21, "method": "resources/templates/list"},
        server_root=tmp_path,
    )

    assert resources_response is not None
    assert templates_response is not None
    resources_result = cast(dict[str, Any], resources_response["result"])
    templates_result = cast(dict[str, Any], templates_response["result"])
    resources = cast(list[dict[str, Any]], resources_result["resources"])
    resource_templates = cast(list[dict[str, Any]], templates_result["resourceTemplates"])
    assert any(item["uri"] == "repo-rag://overview" for item in resources)
    assert any(item["uri"] == "repo-rag://startup-context" for item in resources)
    assert any(
        item["uriTemplate"] == "repo-rag://search{?question,top_k,retrieval_mode}"
        for item in resource_templates
    )


def test_handle_mcp_message_reads_overview_resource(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        mcp_server,
        "load_retrieval_profile",
        lambda root: RetrievalProfile(name="demo-profile", retrieval_mode="hybrid-vector"),
    )
    monkeypatch.setattr(
        mcp_server,
        "build_corpus_manifest",
        lambda root: {
            "schema_version": 1,
            "root": str(root),
            "document_count": 3,
            "entries": [],
            "corpus_fingerprint": "demo-fingerprint",
        },
    )

    response = mcp_server.handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 22,
            "method": "resources/read",
            "params": {"uri": "repo-rag://overview"},
        },
        server_root=tmp_path,
    )

    assert response is not None
    result = cast(dict[str, Any], response["result"])
    contents = cast(list[dict[str, Any]], result["contents"])
    assert contents[0]["mimeType"] == "text/markdown"
    assert "demo-profile" in contents[0]["text"]
    assert "search_repo" in contents[0]["text"]
    assert "ask_repo" in contents[0]["text"]


def test_handle_mcp_message_reads_startup_context_resource(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FakeChunk:
        source = tmp_path / "README.md"
        text = "Repository research context."

    monkeypatch.setattr(
        mcp_server,
        "collect_repository_context",
        lambda **kwargs: [FakeChunk()],
    )
    monkeypatch.setattr(
        mcp_server,
        "serialize_chunk",
        lambda chunk, *, root: {
            "source": "README.md",
            "preview": "Repository research context.",
            "text": chunk.text,
        },
    )
    monkeypatch.setattr(
        mcp_server,
        "load_retrieval_profile",
        lambda root: RetrievalProfile(name="demo-profile", retrieval_mode="hybrid-vector"),
    )

    response = mcp_server.handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 24,
            "method": "resources/read",
            "params": {"uri": "repo-rag://startup-context"},
        },
        server_root=tmp_path,
    )

    assert response is not None
    result = cast(dict[str, Any], response["result"])
    contents = cast(list[dict[str, Any]], result["contents"])
    payload = json.loads(contents[0]["text"])
    assert payload["command"] == "startup-context-resource"
    assert payload["retrieval_mode"] == "hybrid-vector"
    assert payload["sources"] == ["README.md"]
    assert payload["examples"]["search_tool"]["name"] == "search_repo"
    assert payload["examples"]["ask_tool"]["name"] == "ask_repo"


def test_handle_mcp_message_reads_search_resource(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FakeChunk:
        source = tmp_path / "README.md"
        text = "Repository research context."

    monkeypatch.setattr(
        mcp_server,
        "collect_repository_context",
        lambda **kwargs: [FakeChunk()],
    )
    monkeypatch.setattr(
        mcp_server,
        "serialize_chunk",
        lambda chunk, *, root: {
            "source": "README.md",
            "preview": "Repository research context.",
            "text": chunk.text,
        },
    )
    monkeypatch.setattr(
        mcp_server,
        "load_retrieval_profile",
        lambda root: RetrievalProfile(name="demo-profile", retrieval_mode="hybrid-vector"),
    )
    monkeypatch.setattr(
        mcp_server,
        "discover_mcp_servers",
        lambda root: [],
    )

    response = mcp_server.handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 23,
            "method": "resources/read",
            "params": {"uri": "repo-rag://search?question=Where+should+I+start%3F&top_k=3"},
        },
        server_root=tmp_path,
    )

    assert response is not None
    result = cast(dict[str, Any], response["result"])
    contents = cast(list[dict[str, Any]], result["contents"])
    payload = json.loads(contents[0]["text"])
    assert payload["command"] == "search-repo-resource"
    assert payload["retrieval_mode"] == "hybrid-vector"
    assert payload["sources"] == ["README.md"]


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


def test_read_json_rpc_message_does_not_reselect_after_first_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _SelectableBytesIO(io.BytesIO):
        def fileno(self) -> int:
            return 123

    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
    buffer = _SelectableBytesIO()
    mcp_server.write_json_rpc_message(buffer, payload)
    buffer.seek(0)
    select_calls = 0

    def fake_select(read_fds, write_fds, error_fds, timeout):
        nonlocal select_calls
        select_calls += 1
        if select_calls == 1:
            return read_fds, write_fds, error_fds
        raise AssertionError("select() should not run again after the first header line")

    monkeypatch.setattr(mcp_server.select, "select", fake_select)

    assert mcp_server.read_json_rpc_message(buffer) == payload
    assert select_calls in {0, 1}


def test_read_json_rpc_message_accepts_line_delimited_jsonrpc_from_pipe() -> None:
    read_fd, write_fd = os.pipe()
    reader = os.fdopen(read_fd, "rb")
    writer = os.fdopen(write_fd, "wb", buffering=0)

    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    writer.write((json.dumps(payload) + "\n").encode("utf-8"))
    writer.flush()
    writer.close()

    assert mcp_server.read_json_rpc_message(reader) == payload
    reader.close()


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
    capabilities = cast(dict[str, Any], first_result["capabilities"])
    server_info = cast(dict[str, Any], first_result["serverInfo"])
    assert "resources" in capabilities
    assert server_info["name"] == "repo-rag-mcp"
    assert "search_repo" in str(first_result["instructions"])
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


def test_serve_repo_rag_mcp_replies_with_line_delimited_jsonrpc(tmp_path: Path) -> None:
    input_stream = io.BytesIO(
        (
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
            + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "resources/list"})
            + "\n"
        ).encode("utf-8")
    )
    output_stream = io.BytesIO()

    assert (
        mcp_server.serve_repo_rag_mcp(
            tmp_path,
            input_stream=input_stream,
            output_stream=output_stream,
        )
        == 0
    )

    output_lines = [line for line in output_stream.getvalue().splitlines() if line.strip()]
    assert len(output_lines) == 2
    first = json.loads(output_lines[0].decode("utf-8"))
    second = json.loads(output_lines[1].decode("utf-8"))
    assert first["id"] == 1
    assert second["id"] == 2
    assert "serverInfo" in first["result"]
    assert "resources" in second["result"]


def test_read_json_rpc_message_preserves_buffered_followup_messages_from_pipe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_fd, write_fd = os.pipe()
    reader = os.fdopen(read_fd, "rb")
    writer = os.fdopen(write_fd, "wb", buffering=0)

    first_payload = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    second_payload = {"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {}}
    mcp_server.write_json_rpc_message(writer, first_payload)
    mcp_server.write_json_rpc_message(writer, second_payload)

    close_started = threading.Event()

    def delayed_close() -> None:
        close_started.set()
        time.sleep(0.2)
        writer.close()

    thread = threading.Thread(target=delayed_close, daemon=True)
    thread.start()
    close_started.wait(timeout=1.0)

    select_calls = 0
    original_select = mcp_server.select.select

    def fake_select(read_fds, write_fds, error_fds, timeout):
        nonlocal select_calls
        select_calls += 1
        if select_calls == 1:
            return original_select(read_fds, write_fds, error_fds, timeout)
        raise AssertionError(
            "select() should not run again when the next MCP frame is already buffered"
        )

    monkeypatch.setattr(mcp_server.select, "select", fake_select)

    assert mcp_server.read_json_rpc_message(reader) == first_payload
    assert mcp_server.read_json_rpc_message(reader) == second_payload

    thread.join(timeout=1.0)
    reader.close()
