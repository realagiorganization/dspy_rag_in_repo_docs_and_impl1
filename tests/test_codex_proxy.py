from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from repo_rag_lab.codex_proxy import (
    CodexMediationResult,
    CodexProxyConfig,
    _resolve_program_path_and_bundle_version,
    augment_responses_payload,
    build_codex_mediation,
    extract_codex_task_text,
    running_codex_proxy,
)
from repo_rag_lab.retrieval import Chunk


def test_extract_codex_task_text_prefers_latest_user_message() -> None:
    payload = {
        "input": [
            {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "rules"}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "first task"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "working"}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "second task"}],
            },
        ]
    }

    assert extract_codex_task_text(payload) == "second task"


def test_augment_responses_payload_inserts_developer_message_after_existing_developers() -> None:
    payload = {
        "input": [
            {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "existing developer"}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "task"}],
            },
        ]
    }

    updated = augment_responses_payload(
        payload,
        developer_message="repo-rag mediation",
    )

    assert isinstance(updated["input"], list)
    inserted = updated["input"][1]
    assert inserted["role"] == "developer"
    assert inserted["content"][0]["text"] == "repo-rag mediation"


def test_running_codex_proxy_forwards_sse_and_injects_mediation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    class UpstreamHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            captured["payload"] = json.loads(body)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            completed_event = {
                "type": "response.completed",
                "response": {
                    "id": "resp_1",
                    "object": "response",
                    "status": "completed",
                    "output": [],
                    "usage": {
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "total_tokens": 2,
                    },
                },
            }
            self.wfile.write(
                b"event: response.completed\ndata: "
                + json.dumps(completed_event).encode("utf-8")
                + b"\n\n"
            )
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    upstream = HTTPServer(("127.0.0.1", 0), UpstreamHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    upstream_port = upstream.server_address[1]

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", f"http://127.0.0.1:{upstream_port}")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.4")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

    mediation = CodexMediationResult(
        question="inspect repo",
        mediation_mode="dspy_rag",
        rag_status="success",
        dspy_status="success",
        summary="use README first",
        retrieval_mode="hybrid-vector",
        sources=["README.md"],
        warnings=[],
        bundle_version="stable",
        program_path="artifacts/dspy/remote/stable/program.json",
        evidence_previews=[{"source": "README.md", "text": "summary"}],
        developer_message="repo-rag mediation block",
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy.build_codex_mediation",
        lambda *args, **kwargs: mediation,
    )

    root = tmp_path / "repo"
    root.mkdir()
    config = CodexProxyConfig(
        repository_root=root,
        bundle_root=root,
        artifact_dir=tmp_path / "artifacts",
    )

    with running_codex_proxy(config) as proxy:
        response = httpx.post(
            f"{proxy.base_url}/responses?api-version=2024-12-01-preview",
            headers={"Accept": "text/event-stream"},
            json={
                "model": "gpt-5.4",
                "instructions": "base instructions",
                "input": [
                    {
                        "type": "message",
                        "role": "developer",
                        "content": [{"type": "input_text", "text": "existing developer"}],
                    },
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "inspect repo"}],
                    },
                ],
                "stream": True,
            },
            timeout=10,
        )

        assert response.status_code == 200
        assert "response.completed" in response.text

    upstream.shutdown()
    upstream_thread.join(timeout=5)

    upstream_payload = captured["payload"]
    assert isinstance(upstream_payload, dict)
    input_items = upstream_payload["input"]
    assert isinstance(input_items, list)
    assert input_items[1]["role"] == "developer"
    assert input_items[1]["content"][0]["text"] == "repo-rag mediation block"


def test_build_codex_mediation_suppresses_low_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy.ask_repository",
        lambda question, root, retrieval_mode=None: SimpleNamespace(
            context=[],
            summary="thin",
            retrieval_mode=retrieval_mode or "lexical",
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy._build_heuristic_previews",
        lambda root: [],
    )

    mediation = build_codex_mediation(
        "hi",
        repository_root=repo,
        bundle_root=repo,
        prefer_dspy=False,
        low_signal_min_sources=1,
    )

    assert mediation.task_classification == "trivial"
    assert mediation.injected is False
    assert mediation.developer_message == ""
    assert any("suppressed" in warning.lower() for warning in mediation.warnings)


def test_resolve_program_path_and_bundle_version_uses_local_bundle_root_without_remote_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    bundle_root = tmp_path / "bundle-root"
    program_dir = bundle_root / "artifacts" / "dspy" / "remote" / "stable-42"
    program_dir.mkdir(parents=True)
    program_path = program_dir / "program.json"
    program_path.write_text('{"program":"demo"}\n', encoding="utf-8")

    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy.fetch_remote_bundle", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy.inspect_bundle_channel",
        lambda root, channel: {
            "channel_found": True,
            "current_bundle_version": "stable-42",
            "current_program_path": "artifacts/dspy/remote/stable-42/program.json",
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy.RepositoryRAG",
        lambda *args, **kwargs: pytest.fail("RepositoryRAG fallback should not run"),
    )

    resolved_program_path, resolved_bundle_version = _resolve_program_path_and_bundle_version(
        repository_root=repository_root,
        bundle_root=bundle_root,
        bundle_version=None,
        bundle_channel="stable",
    )

    assert resolved_program_path == program_path.resolve()
    assert resolved_bundle_version == "stable-42"


def test_running_codex_proxy_uses_budgeted_disk_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[dict[str, object]] = []
    calls = {"ask_repository": 0}

    class UpstreamHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            payload = json.loads(body)
            captured.append(payload)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            completed_event = {
                "type": "response.completed",
                "response": {
                    "id": "resp_2",
                    "object": "response",
                    "status": "completed",
                    "output": [],
                    "usage": {
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "total_tokens": 2,
                    },
                },
            }
            self.wfile.write(
                b"event: response.completed\ndata: "
                + json.dumps(completed_event).encode("utf-8")
                + b"\n\n"
            )
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    upstream = HTTPServer(("127.0.0.1", 0), UpstreamHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    upstream_port = upstream.server_address[1]

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", f"http://127.0.0.1:{upstream_port}")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.4")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    monkeypatch.setattr("repo_rag_lab.codex_proxy.resolve_dspy_lm_config", lambda: None)

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("repo summary\n" * 40, encoding="utf-8")

    def fake_ask_repository(
        question: str,
        root: Path,
        retrieval_mode: str | None = None,
    ) -> SimpleNamespace:
        calls["ask_repository"] += 1
        return SimpleNamespace(
            context=[
                Chunk(source=repo / "README.md", text="summary " * 120),
                Chunk(source=repo / "README.md", text="more summary " * 120),
            ],
            summary="Repository summary " * 40,
            retrieval_mode=retrieval_mode or "lexical",
        )

    monkeypatch.setattr("repo_rag_lab.codex_proxy.ask_repository", fake_ask_repository)

    config = CodexProxyConfig(
        repository_root=repo,
        bundle_root=repo,
        artifact_dir=tmp_path / "artifacts",
        token_budget=80,
        trivial_token_budget=60,
        essentials_count=2,
        cache_dir=tmp_path / "cache",
        cache_ttl_seconds=3600,
    )

    request_payload = {
        "model": "gpt-5.4",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "inspect repository summary"}],
            }
        ],
        "stream": True,
    }

    with running_codex_proxy(config) as proxy:
        first = httpx.post(
            f"{proxy.base_url}/responses?api-version=2024-12-01-preview",
            headers={"Accept": "text/event-stream"},
            json=request_payload,
            timeout=10,
        )
        assert first.status_code == 200
        status_first = json.loads(proxy.status_path.read_text(encoding="utf-8"))
        assert status_first["cache_hit"] is False
        assert status_first["injected"] is True
        assert status_first["estimated_tokens"] <= status_first["budget_tokens"]
        assert status_first["retrieval_mode"] == "lexical"

    with running_codex_proxy(config) as proxy:
        second = httpx.post(
            f"{proxy.base_url}/responses?api-version=2024-12-01-preview",
            headers={"Accept": "text/event-stream"},
            json=request_payload,
            timeout=10,
        )
        assert second.status_code == 200
        status_second = json.loads(proxy.status_path.read_text(encoding="utf-8"))
        assert status_second["cache_hit"] is True
        assert status_second["estimated_tokens"] <= status_second["budget_tokens"]
        assert status_second["retrieval_mode"] == "lexical"

    upstream.shutdown()
    upstream_thread.join(timeout=5)

    assert calls["ask_repository"] == 1
    assert len(captured) == 2
