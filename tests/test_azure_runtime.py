from __future__ import annotations

from pathlib import Path

import pytest

from repo_rag_lab.azure_runtime import (
    load_runtime_environment,
    normalize_azure_inference_endpoint,
    normalize_azure_openai_endpoint,
    probe_azure_openai,
    resolve_azure_inference_runtime,
    resolve_azure_openai_runtime,
)


def test_normalize_azure_openai_endpoint_uses_host_origin() -> None:
    endpoint = normalize_azure_openai_endpoint(
        None,
        (
            "https://example.openai.azure.com/openai/deployments/repo-rag-ft/"
            "chat/completions?api-version=2025-01-01-preview"
        ),
    )

    assert endpoint == "https://example.openai.azure.com"


def test_normalize_azure_inference_endpoint_strips_chat_suffix_and_query() -> None:
    endpoint = normalize_azure_inference_endpoint(
        "https://example.openai.azure.com/openai/deployments/repo-rag-ft/"
        "chat/completions?api-version=2025-01-01-preview"
    )

    assert endpoint == "https://example.openai.azure.com/openai/deployments/repo-rag-ft"


def test_load_runtime_environment_reads_repository_env_file(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "AZURE_OPENAI_API_KEY=test-key\nexport GH_TOKEN=test-token\n", encoding="utf-8"
    )

    env, report = load_runtime_environment(tmp_path, load_env_file=True)

    assert env["AZURE_OPENAI_API_KEY"] == "test-key"
    assert env["GH_TOKEN"] == "test-token"
    assert report.env_file_found is True
    assert report.env_file_path == str(env_path)
    assert report.loaded_env_keys == ("AZURE_OPENAI_API_KEY", "GH_TOKEN")


def test_resolve_azure_openai_runtime_derives_deployment_from_chat_uri() -> None:
    config = resolve_azure_openai_runtime(
        {
            "AZURE_OPENAI_CHAT_COMPLETIONS_URI": (
                "https://example.openai.azure.com/openai/deployments/repo-rag-ft/"
                "chat/completions?api-version=2025-01-01-preview"
            ),
            "AZURE_OPENAI_API_KEY": "secret",
            "AZURE_OPENAI_API_VERSION": "2025-01-01-preview",
        }
    )

    assert config.endpoint == "https://example.openai.azure.com"
    assert config.endpoint_source == "AZURE_OPENAI_CHAT_COMPLETIONS_URI"
    assert config.deployment_name == "repo-rag-ft"
    assert config.deployment_name_source == "AZURE_OPENAI_CHAT_COMPLETIONS_URI"


def test_resolve_azure_inference_runtime_normalizes_full_chat_uri() -> None:
    config = resolve_azure_inference_runtime(
        {
            "AZURE_INFERENCE_ENDPOINT": (
                "https://example.openai.azure.com/openai/deployments/repo-rag-ft/"
                "chat/completions?api-version=2025-01-01-preview"
            ),
            "AZURE_INFERENCE_CREDENTIAL": "secret",
            "AZURE_OPENAI_API_VERSION": "2025-01-01-preview",
        }
    )

    assert config.endpoint == "https://example.openai.azure.com/openai/deployments/repo-rag-ft"
    assert config.endpoint_was_normalized is True
    assert config.original_endpoint is not None
    assert config.deployment_name == "repo-rag-ft"
    assert config.deployment_name_source == "AZURE_INFERENCE_ENDPOINT"


def test_resolve_azure_inference_runtime_falls_back_to_openai_values() -> None:
    config = resolve_azure_inference_runtime(
        {
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
            "AZURE_OPENAI_DEPLOYMENT_NAME": "repo-rag-ft",
            "AZURE_OPENAI_API_KEY": "secret",
        }
    )

    assert config.endpoint == "https://example.openai.azure.com/openai/deployments/repo-rag-ft"
    assert config.endpoint_source == "AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_DEPLOYMENT_NAME"
    assert config.credential == "secret"
    assert config.deployment_name == "repo-rag-ft"
    assert config.deployment_name_source == "AZURE_OPENAI_DEPLOYMENT_NAME"


def test_probe_azure_openai_prefers_max_completion_tokens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict[str, object]] = []

    class _FakeCompletions:
        def create(self, **kwargs: object) -> object:
            calls.append(dict(kwargs))
            return type(
                "Response",
                (),
                {
                    "model": "gpt-5.4",
                    "choices": [
                        type(
                            "Choice",
                            (),
                            {
                                "message": type("Message", (), {"content": "OPENAI_OK"})(),
                                "finish_reason": "stop",
                            },
                        )()
                    ],
                },
            )()

    class _FakeChat:
        def __init__(self) -> None:
            self.completions = _FakeCompletions()

    class _FakeClient:
        def __init__(self, **kwargs: object) -> None:
            del kwargs
            self.chat = _FakeChat()

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.4")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    monkeypatch.setattr("repo_rag_lab.azure_runtime._require_openai_client", lambda: _FakeClient)

    payload = probe_azure_openai(tmp_path, load_env_file=False)

    assert payload["reply"] == "OPENAI_OK"
    assert len(calls) == 1
    assert calls[0]["model"] == "gpt-5.4"
    assert calls[0]["max_completion_tokens"] == 16
    assert "max_tokens" not in calls[0]


def test_probe_azure_openai_falls_back_to_max_tokens_when_needed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict[str, object]] = []

    class _FakeCompletions:
        def create(self, **kwargs: object) -> object:
            calls.append(dict(kwargs))
            if "max_completion_tokens" in kwargs:
                raise RuntimeError(
                    "Unsupported parameter: 'max_completion_tokens' is not supported "
                    "with this model. Use 'max_tokens' instead."
                )
            return type(
                "Response",
                (),
                {
                    "model": "gpt-4o",
                    "choices": [
                        type(
                            "Choice",
                            (),
                            {
                                "message": type("Message", (), {"content": "OPENAI_OK"})(),
                                "finish_reason": "stop",
                            },
                        )()
                    ],
                },
            )()

    class _FakeChat:
        def __init__(self) -> None:
            self.completions = _FakeCompletions()

    class _FakeClient:
        def __init__(self, **kwargs: object) -> None:
            del kwargs
            self.chat = _FakeChat()

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    monkeypatch.setattr("repo_rag_lab.azure_runtime._require_openai_client", lambda: _FakeClient)

    payload = probe_azure_openai(tmp_path, load_env_file=False)

    assert payload["reply"] == "OPENAI_OK"
    assert len(calls) == 2
    assert "max_completion_tokens" in calls[0]
    assert calls[1]["max_tokens"] == 16
