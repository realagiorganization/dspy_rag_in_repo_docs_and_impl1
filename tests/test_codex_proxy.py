# pyright: reportUnknownLambdaType=false

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import NoReturn, cast

import httpx
import pytest

import repo_rag_lab.codex_proxy as codex_proxy_module
from repo_rag_lab.codex_proxy import (
    CodexMediationResult,
    CodexProxyConfig,
    augment_responses_payload,
    build_codex_mediation,
    extract_codex_task_text,
    extract_codex_turn_state,
    running_codex_proxy,
)
from repo_rag_lab.retrieval import Chunk, RetrievalMode


def _payload_mapping(value: object) -> Mapping[str, object]:
    assert isinstance(value, dict)
    return value


def _resolve_program_path_and_bundle_version(
    *,
    repository_root: Path,
    bundle_root: Path,
    bundle_version: str | None,
    bundle_channel: str,
) -> tuple[Path | None, str | None]:
    resolver = cast(
        Callable[..., tuple[Path | None, str | None]],
        codex_proxy_module.__dict__["_resolve_program_path_and_bundle_version"],
    )
    return resolver(
        repository_root=repository_root,
        bundle_root=bundle_root,
        bundle_version=bundle_version,
        bundle_channel=bundle_channel,
    )


def _resolve_bundle_family_registry(
    *,
    bundle_root: Path,
    bundle_version: str | None,
    bundle_channel: str,
) -> dict[str, object] | None:
    resolver = cast(
        Callable[..., dict[str, object] | None],
        codex_proxy_module.__dict__["_resolve_bundle_family_registry"],
    )
    return resolver(
        bundle_root=bundle_root,
        bundle_version=bundle_version,
        bundle_channel=bundle_channel,
    )


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

    assert extract_codex_task_text(_payload_mapping(payload)) == "second task"


def test_extract_codex_turn_state_captures_command_trace() -> None:
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
                "content": [{"type": "output_text", "text": "run pytest -q"}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "second task"}],
            },
        ]
    }

    state = extract_codex_turn_state(_payload_mapping(payload))

    assert state["original_prompt"] == "second task"
    assert state["command_trace"] == [
        {"type": "message", "role": "user", "text": "first task"},
        {"type": "message", "role": "assistant", "text": "run pytest -q"},
        {"type": "message", "role": "user", "text": "second task"},
    ]


def test_extract_codex_turn_state_strips_dataset_execution_envelope() -> None:
    payload = {
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Discord channel: prompts_debt_relief\n"
                            "Channel ID: 1491133577327411321\n"
                            "Queue label: prompts_debt_relief\n"
                            "Messages aggregated: 2\n"
                            "Available repository: acme/repo -> /tmp/repo\n\n"
                            "Messages with required reaction:\n"
                            "[1] (2026-05-06T14:36:10.829+00:00 | user | id=1) "
                            "In https://github.com/acme/repo\n\n"
                            "Add an automated demo GIF of this wireframe.\n\n"
                            "[forwarded] @Tyler ATTTENTION. @|DT| drybox\n\n"
                            "EXECUTION CONTEXT:\n"
                            "- You are running in an automated container environment\n\n"
                            "AUTONOMOUS EXECUTION CONTRACT:\n"
                            "1. Operate fully autonomously.\n"
                        ),
                    }
                ],
            }
        ]
    }

    state = extract_codex_turn_state(_payload_mapping(payload))

    assert state["original_prompt"] == (
        "In https://github.com/acme/repo\n\nAdd an automated demo GIF of this wireframe."
    )
    assert state["command_trace"] == [
        {
            "type": "message",
            "role": "user",
            "text": (
                "In https://github.com/acme/repo\n\nAdd an automated demo GIF of this wireframe."
            ),
        }
    ]


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
        _payload_mapping(payload),
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

    try:
        upstream = HTTPServer(("127.0.0.1", 0), UpstreamHandler)
    except PermissionError:
        pytest.skip("Sandbox does not allow local HTTPServer sockets.")
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    upstream_port = upstream.server_address[1]

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", f"http://127.0.0.1:{upstream_port}")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.4")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

    mediation = CodexMediationResult(
        question="inspect repo",
        original_prompt="inspect repo",
        reformulated_prompt="inspect repo",
        reformulation_status="identity",
        mediation_mode="dspy_rag",
        rag_status="success",
        dspy_status="success",
        dspy_lm_model="azure/dspy-helper",
        summary="use README first",
        retrieval_mode="hybrid-vector",
        sources=["README.md"],
        warnings=[],
        bundle_version="stable",
        program_path="artifacts/dspy/remote/stable/program.json",
        evidence_previews=[{"source": "README.md", "text": "summary"}],
        developer_message="repo-rag mediation block",
    )

    def fake_build_codex_mediation(*args: object, **kwargs: object) -> CodexMediationResult:
        del args, kwargs
        return mediation

    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy.build_codex_mediation",
        fake_build_codex_mediation,
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
    turn_trace_dir = tmp_path / "artifacts" / "repo_rag_turn_traces"
    manifest_paths = list(turn_trace_dir.glob("*/manifest.json"))
    assert len(manifest_paths) == 1


def test_build_codex_mediation_suppresses_low_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_ask_repository(
        question: str,
        root: Path,
        retrieval_mode: RetrievalMode | None = None,
    ) -> SimpleNamespace:
        del question, root
        return SimpleNamespace(
            context=[],
            summary="thin",
            retrieval_mode=retrieval_mode or "lexical",
        )

    def fake_build_heuristic_previews(root: Path) -> list[dict[str, str]]:
        del root
        return []

    monkeypatch.setattr("repo_rag_lab.codex_proxy.ask_repository", fake_ask_repository)
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy._build_heuristic_previews",
        fake_build_heuristic_previews,
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy._resolve_family_state_path",
        lambda *args, **kwargs: tmp_path / "artifacts" / "trainer" / "family-state.json",
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy.resolve_prompt_family_support",
        lambda *args, **kwargs: SimpleNamespace(
            prompt_family_id="pf-demo",
            similarity=1.0,
            band="match",
            supported=True,
        ),
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


def test_build_codex_mediation_prefers_bundle_family_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("repo summary\n", encoding="utf-8")

    def fake_ask_repository(
        question: str,
        root: Path,
        retrieval_mode: RetrievalMode | None = None,
    ) -> SimpleNamespace:
        del question, retrieval_mode
        return SimpleNamespace(
            context=[Chunk(source=root / "README.md", text="Repository summary text.")],
            summary="Repository summary text.",
            retrieval_mode="lexical",
        )

    monkeypatch.setattr("repo_rag_lab.codex_proxy.ask_repository", fake_ask_repository)
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy._resolve_bundle_family_registry",
        lambda **kwargs: {
            "schema_version": 1,
            "registry_kind": "repo-rag-family-registry",
            "families": [
                {
                    "prompt_family_id": "pf-demo",
                    "family_father_question": "Run the failing pytest target and inspect stderr.",
                    "family_father_record": {
                        "question": "Run the failing pytest target and inspect stderr."
                    },
                    "family_runtime_record": {
                        "question": "Run the failing pytest target and inspect stderr.",
                        "metric_hits": 1,
                        "metric_total": 1,
                        "metric_ratio": 1.0,
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy._resolve_family_state_path",
        lambda *args, **kwargs: pytest.fail("bundle family registry should be used first"),
    )

    mediation = build_codex_mediation(
        "Run the failing pytest target and inspect stderr.",
        repository_root=repo,
        bundle_root=repo,
        prefer_dspy=False,
    )

    assert mediation.prompt_family_id == "pf-demo"
    assert mediation.prompt_family_band == "match"
    assert mediation.mediation_mode != "passthrough"
    assert mediation.injected is True


def test_build_codex_mediation_executes_family_runtime_artifact_with_prompt_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("repo summary\n", encoding="utf-8")
    family_program_path = (
        repo
        / "artifacts"
        / "dspy"
        / "remote"
        / "stable-42"
        / "families"
        / "pf-demo"
        / "program.json"
    )
    family_program_path.parent.mkdir(parents=True)
    family_program_path.write_text('{"program":"family-demo"}\n', encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_ask_repository(
        question: str,
        root: Path,
        retrieval_mode: RetrievalMode | None = None,
    ) -> SimpleNamespace:
        del retrieval_mode
        assert question == "Run the failing pytest target and inspect stderr."
        return SimpleNamespace(
            context=[Chunk(source=root / "README.md", text="Repository summary text.")],
            summary="Repository summary text.",
            retrieval_mode="lexical",
        )

    class FakeRepositoryRAG:
        def __init__(
            self,
            root: Path,
            top_k: int = 4,
            *,
            program_path: Path | None = None,
            lm_config: object | None = None,
            require_configured_lm: bool = False,
            retrieval_mode: RetrievalMode | None = None,
        ) -> None:
            del root, top_k, require_configured_lm, retrieval_mode
            captured["program_path"] = program_path
            captured["lm_model"] = getattr(lm_config, "model", None)

        def __call__(
            self,
            question: str,
            *,
            original_prompt: str | None = None,
            reformulated_prompt: str | None = None,
            command_trace: object = (),
        ) -> SimpleNamespace:
            captured["question"] = question
            captured["original_prompt"] = original_prompt
            captured["reformulated_prompt"] = reformulated_prompt
            captured["command_trace"] = command_trace
            return SimpleNamespace(
                answer="Family-scoped DSPy answer.",
                retrieval_mode="lexical",
            )

    monkeypatch.setattr("repo_rag_lab.codex_proxy.ask_repository", fake_ask_repository)
    monkeypatch.setattr("repo_rag_lab.codex_proxy.RepositoryRAG", FakeRepositoryRAG)
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy.resolve_dspy_lm_config",
        lambda: SimpleNamespace(model="azure/dspy-helper"),
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy.reformulate_codex_prompt",
        lambda prompt, *, lm_config=None: (
            "Run the failing pytest target and inspect stderr.",
            "success",
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy._resolve_bundle_family_registry",
        lambda **kwargs: {
            "schema_version": 1,
            "registry_kind": "repo-rag-family-registry",
            "families": [
                {
                    "prompt_family_id": "pf-demo",
                    "family_father_question": "Run the failing pytest target and inspect stderr.",
                    "family_father_record": {
                        "question": "Run the failing pytest target and inspect stderr.",
                    },
                    "family_runtime_metric": {"hit_rate": 0.8},
                    "runtime_artifact": {
                        "artifact_kind": "compiled-family-program",
                        "artifact_ready": True,
                        "program_path": (
                            "artifacts/dspy/remote/stable-42/families/pf-demo/program.json"
                        ),
                        "metadata_path": (
                            "artifacts/dspy/remote/stable-42/families/pf-demo/metadata.json"
                        ),
                        "hit_rate": 1.0,
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy._resolve_program_path_and_bundle_version",
        lambda **kwargs: (
            repo / "artifacts" / "dspy" / "remote" / "stable-42" / "program.json",
            "stable-42",
        ),
    )

    command_trace = [
        {"role": "assistant", "text": "pytest tests/test_suite.py -q"},
        {"role": "tool", "text": "1 failed, 4 passed"},
    ]
    mediation = build_codex_mediation(
        "Investigate the failing pytest target and fix the broken test.",
        command_trace=command_trace,
        repository_root=repo,
        bundle_root=repo,
        prefer_dspy=True,
    )

    assert mediation.dspy_status == "success"
    assert mediation.bundle_version == "stable-42"
    assert mediation.program_path == (
        "artifacts/dspy/remote/stable-42/families/pf-demo/program.json"
    )
    assert mediation.family_runtime_hit_rate == 0.8
    assert mediation.family_artifact_hit_rate == 1.0
    assert mediation.family_artifact_selected is True
    assert captured["program_path"] == family_program_path.resolve()
    assert captured["lm_model"] == "azure/dspy-helper"
    assert captured["question"] == "Investigate the failing pytest target and fix the broken test."
    assert captured["original_prompt"] == (
        "Investigate the failing pytest target and fix the broken test."
    )
    assert captured["reformulated_prompt"] == ("Run the failing pytest target and inspect stderr.")
    assert captured["command_trace"] == command_trace


def test_build_codex_mediation_synthesizes_family_registry_from_family_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("repo summary\n", encoding="utf-8")
    bundle_root = tmp_path / "bundle-root"
    family_state_path = bundle_root / "artifacts" / "trainer" / "family-state.json"
    family_state_path.parent.mkdir(parents=True)
    family_program_path = (
        bundle_root
        / "versions"
        / "stable-42"
        / "families"
        / "pf-demo"
        / "program.json"
    )
    family_program_path.parent.mkdir(parents=True)
    family_program_path.write_text('{"program":"family-demo"}\n', encoding="utf-8")
    global_program_path = bundle_root / "versions" / "stable-42" / "program.json"
    global_program_path.write_text('{"program":"global-demo"}\n', encoding="utf-8")
    family_state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "family_state_kind": "repo-rag-family-state",
                "prompt_families": [
                    {
                        "prompt_family_id": "pf-demo",
                        "family_father_question": (
                            "Run the failing pytest target and inspect stderr."
                        ),
                        "family_father_record": {
                            "question": "Run the failing pytest target and inspect stderr."
                        },
                        "family_runtime_record": {
                            "question": "Run the failing pytest target and inspect stderr.",
                            "metric_hits": 4,
                            "metric_total": 5,
                            "metric_ratio": 0.8,
                        },
                        "family_runtime_artifact": {
                            "artifact_kind": "compiled-family-program",
                            "artifact_ready": True,
                            "program_path": "artifacts/dspy/missing/pf-demo/program.json",
                            "metadata_path": "artifacts/dspy/missing/pf-demo/metadata.json",
                            "hit_rate": 1.0,
                        },
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def fake_ask_repository(
        question: str,
        root: Path,
        retrieval_mode: RetrievalMode | None = None,
    ) -> SimpleNamespace:
        del retrieval_mode
        assert question == "Run the failing pytest target and inspect stderr."
        return SimpleNamespace(
            context=[Chunk(source=root / "README.md", text="Repository summary text.")],
            summary="Repository summary text.",
            retrieval_mode="lexical",
        )

    class FakeRepositoryRAG:
        def __init__(
            self,
            root: Path,
            top_k: int = 4,
            *,
            program_path: Path | None = None,
            lm_config: object | None = None,
            require_configured_lm: bool = False,
            retrieval_mode: RetrievalMode | None = None,
        ) -> None:
            del root, top_k, lm_config, require_configured_lm, retrieval_mode
            captured["program_path"] = program_path

        def __call__(
            self,
            question: str,
            *,
            original_prompt: str | None = None,
            reformulated_prompt: str | None = None,
            command_trace: object = (),
        ) -> SimpleNamespace:
            captured["question"] = question
            captured["original_prompt"] = original_prompt
            captured["reformulated_prompt"] = reformulated_prompt
            captured["command_trace"] = command_trace
            return SimpleNamespace(answer="Family-state DSPy answer.", retrieval_mode="lexical")

    monkeypatch.setattr("repo_rag_lab.codex_proxy.ask_repository", fake_ask_repository)
    monkeypatch.setattr("repo_rag_lab.codex_proxy.RepositoryRAG", FakeRepositoryRAG)
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy.resolve_dspy_lm_config",
        lambda: SimpleNamespace(model="azure/dspy-helper"),
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy.reformulate_codex_prompt",
        lambda prompt, *, lm_config=None: (
            "Run the failing pytest target and inspect stderr.",
            "success",
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy._resolve_bundle_family_registry",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy._resolve_program_path_and_bundle_version",
        lambda **kwargs: (global_program_path, "stable-42"),
    )

    mediation = build_codex_mediation(
        "Investigate the failing pytest target and fix the broken test.",
        repository_root=repo,
        bundle_root=bundle_root,
        prefer_dspy=True,
        bundle_version="stable-42",
    )

    assert mediation.dspy_status == "success"
    assert mediation.prompt_family_id == "pf-demo"
    assert mediation.family_runtime_hit_rate == 0.8
    assert mediation.family_artifact_hit_rate == 1.0
    assert mediation.family_artifact_selected is True
    assert mediation.program_path == "versions/stable-42/families/pf-demo/program.json"
    assert captured["program_path"] == family_program_path.resolve()


def test_build_codex_mediation_skips_family_artifact_when_hit_rate_drops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("repo summary\n", encoding="utf-8")
    global_program_path = repo / "artifacts" / "dspy" / "remote" / "stable-42" / "program.json"
    global_program_path.parent.mkdir(parents=True)
    global_program_path.write_text('{"program":"global-demo"}\n', encoding="utf-8")
    family_program_path = (
        repo
        / "artifacts"
        / "dspy"
        / "remote"
        / "stable-42"
        / "families"
        / "pf-demo"
        / "program.json"
    )
    family_program_path.parent.mkdir(parents=True)
    family_program_path.write_text('{"program":"family-demo"}\n', encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_ask_repository(
        question: str,
        root: Path,
        retrieval_mode: RetrievalMode | None = None,
    ) -> SimpleNamespace:
        del retrieval_mode
        assert question == "Run the failing pytest target and inspect stderr."
        return SimpleNamespace(
            context=[Chunk(source=root / "README.md", text="Repository summary text.")],
            summary="Repository summary text.",
            retrieval_mode="lexical",
        )

    class FakeRepositoryRAG:
        def __init__(
            self,
            root: Path,
            top_k: int = 4,
            *,
            program_path: Path | None = None,
            lm_config: object | None = None,
            require_configured_lm: bool = False,
            retrieval_mode: RetrievalMode | None = None,
        ) -> None:
            del root, top_k, lm_config, require_configured_lm, retrieval_mode
            captured["program_path"] = program_path

        def __call__(
            self,
            question: str,
            *,
            original_prompt: str | None = None,
            reformulated_prompt: str | None = None,
            command_trace: object = (),
        ) -> SimpleNamespace:
            del question, original_prompt, reformulated_prompt, command_trace
            return SimpleNamespace(answer="Global fallback answer.", retrieval_mode="lexical")

    monkeypatch.setattr("repo_rag_lab.codex_proxy.ask_repository", fake_ask_repository)
    monkeypatch.setattr("repo_rag_lab.codex_proxy.RepositoryRAG", FakeRepositoryRAG)
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy.resolve_dspy_lm_config",
        lambda: SimpleNamespace(model="azure/dspy-helper"),
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy.reformulate_codex_prompt",
        lambda prompt, *, lm_config=None: (
            "Run the failing pytest target and inspect stderr.",
            "success",
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy._resolve_bundle_family_registry",
        lambda **kwargs: {
            "schema_version": 1,
            "registry_kind": "repo-rag-family-registry",
            "families": [
                {
                    "prompt_family_id": "pf-demo",
                    "family_father_question": "Run the failing pytest target and inspect stderr.",
                    "family_father_record": {
                        "question": "Run the failing pytest target and inspect stderr."
                    },
                    "family_runtime_metric": {"hit_rate": 0.9},
                    "runtime_artifact": {
                        "artifact_kind": "compiled-family-program",
                        "artifact_ready": True,
                        "program_path": (
                            "artifacts/dspy/remote/stable-42/families/pf-demo/program.json"
                        ),
                        "metadata_path": (
                            "artifacts/dspy/remote/stable-42/families/pf-demo/metadata.json"
                        ),
                        "hit_rate": 0.4,
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy._resolve_program_path_and_bundle_version",
        lambda **kwargs: (global_program_path, "stable-42"),
    )

    mediation = build_codex_mediation(
        "Investigate the failing pytest target and fix the broken test.",
        repository_root=repo,
        bundle_root=repo,
        prefer_dspy=True,
    )

    assert mediation.dspy_status == "success"
    assert mediation.family_runtime_hit_rate == 0.9
    assert mediation.family_artifact_hit_rate == 0.4
    assert mediation.family_artifact_selected is False
    assert mediation.program_path == "artifacts/dspy/remote/stable-42/program.json"
    assert captured["program_path"] == global_program_path.resolve()
    assert any("fell back to fresh/global mediation" in warning for warning in mediation.warnings)


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

    def fake_fetch_remote_bundle(*args: object, **kwargs: object) -> None:
        del args, kwargs

    def fake_inspect_bundle_channel(root: Path, channel: str) -> dict[str, object]:
        del root, channel
        return {
            "channel_found": True,
            "current_bundle_version": "stable-42",
            "current_program_path": "artifacts/dspy/remote/stable-42/program.json",
        }

    def fail_repository_rag(*args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        pytest.fail("RepositoryRAG fallback should not run")

    monkeypatch.setattr("repo_rag_lab.codex_proxy.fetch_remote_bundle", fake_fetch_remote_bundle)
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy.inspect_bundle_channel",
        fake_inspect_bundle_channel,
    )
    monkeypatch.setattr("repo_rag_lab.codex_proxy.RepositoryRAG", fail_repository_rag)

    resolved_program_path, resolved_bundle_version = _resolve_program_path_and_bundle_version(
        repository_root=repository_root,
        bundle_root=bundle_root,
        bundle_version=None,
        bundle_channel="stable",
    )

    assert resolved_program_path == program_path.resolve()
    assert resolved_bundle_version == "stable-42"


def test_resolve_program_path_and_bundle_version_uses_mirror_fallback_for_explicit_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    bundle_root = tmp_path / "bundle-root"
    version_dir = bundle_root / "versions" / "stable-42"
    version_dir.mkdir(parents=True)
    (version_dir / "bundle.json").write_text(
        json.dumps(
            {
                "bundle_version": "stable-42",
                "program_path": "artifacts/dspy/missing/program.json",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    program_path = version_dir / "program.json"
    program_path.write_text('{"program":"demo"}\n', encoding="utf-8")

    def fake_fetch_remote_bundle(*args: object, **kwargs: object) -> None:
        del args, kwargs

    def fail_repository_rag(*args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        pytest.fail("RepositoryRAG fallback should not run")

    monkeypatch.setattr("repo_rag_lab.codex_proxy.fetch_remote_bundle", fake_fetch_remote_bundle)
    monkeypatch.setattr("repo_rag_lab.codex_proxy.RepositoryRAG", fail_repository_rag)

    resolved_program_path, resolved_bundle_version = _resolve_program_path_and_bundle_version(
        repository_root=repository_root,
        bundle_root=bundle_root,
        bundle_version="stable-42",
        bundle_channel="stable",
    )

    assert resolved_program_path == program_path.resolve()
    assert resolved_bundle_version == "stable-42"


def test_resolve_bundle_family_registry_fetches_remote_bundle_for_explicit_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_root = tmp_path / "bundle-root"
    bundle_root.mkdir()
    captured: dict[str, object] = {}

    def fake_fetch_remote_bundle(
        root: Path,
        *,
        bundle_version: str | None = None,
        channel: str | None = None,
    ) -> dict[str, object]:
        captured["root"] = root
        captured["bundle_version"] = bundle_version
        captured["channel"] = channel
        return {
            "bundle_version": "stable-42",
            "family_registry": {
                "family_count": 1,
                "families": [
                    {
                        "prompt_family_id": "docs-refresh",
                        "family_father_question": "Inspect repository documentation",
                    }
                ],
            },
        }

    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy.fetch_remote_bundle",
        fake_fetch_remote_bundle,
    )

    registry = _resolve_bundle_family_registry(
        bundle_root=bundle_root,
        bundle_version="stable-42",
        bundle_channel="stable",
    )

    assert registry == {
        "family_count": 1,
        "families": [
            {
                "prompt_family_id": "docs-refresh",
                "family_father_question": "Inspect repository documentation",
            }
        ],
    }
    assert captured == {
        "root": bundle_root,
        "bundle_version": "stable-42",
        "channel": None,
    }


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

    try:
        upstream = HTTPServer(("127.0.0.1", 0), UpstreamHandler)
    except PermissionError:
        pytest.skip("Sandbox does not allow local HTTPServer sockets.")
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    upstream_port = upstream.server_address[1]

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", f"http://127.0.0.1:{upstream_port}")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.4")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    monkeypatch.setattr("repo_rag_lab.codex_proxy.resolve_dspy_lm_config", lambda: None)
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy._resolve_family_state_path",
        lambda *args, **kwargs: tmp_path / "artifacts" / "trainer" / "family-state.json",
    )
    monkeypatch.setattr(
        "repo_rag_lab.codex_proxy.resolve_prompt_family_support",
        lambda *args, **kwargs: SimpleNamespace(
            prompt_family_id="pf-demo",
            similarity=1.0,
            band="match",
            supported=True,
        ),
    )

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
