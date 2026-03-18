from __future__ import annotations

from pathlib import Path

from repo_rag_lab.azure_runtime import (
    load_runtime_environment,
    normalize_azure_inference_endpoint,
    normalize_azure_openai_endpoint,
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
