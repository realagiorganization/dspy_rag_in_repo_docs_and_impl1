"""Azure runtime normalization, live probes, and cloud-completion helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

from .notebook_runner import load_env_vars

if TYPE_CHECKING:
    from azure.ai.inference import ChatCompletionsClient as AzureInferenceChatCompletionsClient
    from azure.ai.inference.models import SystemMessage as AzureInferenceSystemMessage
    from azure.ai.inference.models import UserMessage as AzureInferenceUserMessage
    from azure.core.credentials import AzureKeyCredential as AzureCredentialClass
    from openai import AzureOpenAI as AzureOpenAIClient


@dataclass(frozen=True)
class EnvLoadReport:
    """Describe whether a repository-local ``.env`` file was loaded."""

    env_file_path: str
    env_file_found: bool
    loaded_env_keys: tuple[str, ...]


@dataclass(frozen=True)
class AzureOpenAIRuntimeConfig:
    """The normalized Azure OpenAI runtime settings required for chat calls."""

    endpoint: str
    endpoint_source: str
    deployment_name: str
    deployment_name_source: str
    api_key: str
    api_version: str
    model_name: str | None


@dataclass(frozen=True)
class AzureInferenceRuntimeConfig:
    """The normalized Azure AI Inference runtime settings required for chat calls."""

    endpoint: str
    endpoint_source: str
    original_endpoint: str | None
    endpoint_was_normalized: bool
    deployment_name: str | None
    deployment_name_source: str | None
    credential: str
    api_version: str | None


@dataclass(frozen=True)
class ChatCompletionResult:
    """A normalized chat-completion payload returned by a cloud provider."""

    provider: str
    answer: str
    model: str | None
    finish_reason: str | None


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value is None:
            continue
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return None


def _normalize_url_origin(value: str | None) -> str | None:
    cleaned = _first_non_empty(value)
    if cleaned is None:
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return cleaned.rstrip("/")


def _extract_deployment_name(value: str | None) -> str | None:
    cleaned = _first_non_empty(value)
    if cleaned is None:
        return None

    parsed = urlparse(cleaned)
    path = parsed.path if parsed.scheme or parsed.netloc else cleaned.split("?", 1)[0]
    parts = [part for part in path.split("/") if part]
    for index, part in enumerate(parts[:-1]):
        if part == "deployments":
            return parts[index + 1]
    return None


def _compose_inference_endpoint(
    openai_endpoint: str | None, deployment_name: str | None
) -> str | None:
    if openai_endpoint is None or deployment_name is None:
        return None
    return f"{openai_endpoint}/openai/deployments/{deployment_name}"


def normalize_azure_openai_endpoint(
    endpoint: str | None,
    chat_completions_uri: str | None,
) -> str | None:
    """Normalize Azure OpenAI endpoint input to the SDK-ready host origin."""

    return _first_non_empty(
        _normalize_url_origin(endpoint),
        _normalize_url_origin(chat_completions_uri),
    )


def normalize_azure_inference_endpoint(endpoint: str | None) -> str | None:
    """Normalize Azure AI Inference endpoint input to the deployment-base form."""

    cleaned = _first_non_empty(endpoint)
    if cleaned is None:
        return None

    parsed = urlparse(cleaned)
    path = parsed.path if parsed.scheme or parsed.netloc else cleaned.split("?", 1)[0]
    normalized_path = path.rstrip("/")
    if normalized_path.endswith("/chat/completions"):
        normalized_path = normalized_path[: -len("/chat/completions")]
    normalized_path = normalized_path.rstrip("/")

    if parsed.scheme and parsed.netloc:
        return urlunparse((parsed.scheme, parsed.netloc, normalized_path, "", "", ""))
    return normalized_path


def load_runtime_environment(
    root: Path,
    *,
    load_env_file: bool = False,
) -> tuple[dict[str, str], EnvLoadReport]:
    """Return a runtime env mapping plus ``.env`` load metadata."""

    env = dict(os.environ)
    env_file_path = root / ".env"
    loaded_env_keys: list[str] = []
    if load_env_file:
        loaded_env_keys = load_env_vars(env_file_path, environ=env)
    return env, EnvLoadReport(
        env_file_path=str(env_file_path),
        env_file_found=env_file_path.exists(),
        loaded_env_keys=tuple(loaded_env_keys),
    )


def resolve_azure_openai_runtime(
    env: Mapping[str, str],
) -> AzureOpenAIRuntimeConfig:
    """Resolve Azure OpenAI runtime settings from the selected environment."""

    endpoint_source = "AZURE_OPENAI_ENDPOINT"
    endpoint = _normalize_url_origin(env.get("AZURE_OPENAI_ENDPOINT"))
    if endpoint is None:
        endpoint = _normalize_url_origin(env.get("AZURE_OPENAI_CHAT_COMPLETIONS_URI"))
        endpoint_source = "AZURE_OPENAI_CHAT_COMPLETIONS_URI"

    deployment_name_source = "AZURE_OPENAI_DEPLOYMENT_NAME"
    deployment_name = _first_non_empty(env.get("AZURE_OPENAI_DEPLOYMENT_NAME"))
    if deployment_name is None:
        deployment_name = _extract_deployment_name(env.get("AZURE_OPENAI_CHAT_COMPLETIONS_URI"))
        deployment_name_source = "AZURE_OPENAI_CHAT_COMPLETIONS_URI"

    api_key = _first_non_empty(env.get("AZURE_OPENAI_API_KEY"))
    api_version = _first_non_empty(env.get("AZURE_OPENAI_API_VERSION"))

    missing: list[str] = []
    if endpoint is None:
        missing.append("AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_CHAT_COMPLETIONS_URI")
    if deployment_name is None:
        missing.append("AZURE_OPENAI_DEPLOYMENT_NAME or AZURE_OPENAI_CHAT_COMPLETIONS_URI")
    if api_key is None:
        missing.append("AZURE_OPENAI_API_KEY")
    if api_version is None:
        missing.append("AZURE_OPENAI_API_VERSION")

    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"Missing Azure OpenAI runtime settings: {joined}. "
            "Load the repository .env or export the values before running the probe."
        )

    assert endpoint is not None
    assert deployment_name is not None
    assert api_key is not None
    assert api_version is not None
    return AzureOpenAIRuntimeConfig(
        endpoint=endpoint,
        endpoint_source=endpoint_source,
        deployment_name=deployment_name,
        deployment_name_source=deployment_name_source,
        api_key=api_key,
        api_version=api_version,
        model_name=_first_non_empty(env.get("AZURE_OPENAI_MODEL_NAME")),
    )


def resolve_azure_inference_runtime(
    env: Mapping[str, str],
) -> AzureInferenceRuntimeConfig:
    """Resolve Azure AI Inference runtime settings from the selected environment."""

    raw_endpoint = _first_non_empty(env.get("AZURE_INFERENCE_ENDPOINT"))
    endpoint_source = "AZURE_INFERENCE_ENDPOINT"
    fallback_deployment_name_source = "AZURE_OPENAI_DEPLOYMENT_NAME"

    if raw_endpoint is None:
        openai_endpoint = normalize_azure_openai_endpoint(
            env.get("AZURE_OPENAI_ENDPOINT"),
            env.get("AZURE_OPENAI_CHAT_COMPLETIONS_URI"),
        )
        deployment_name = _first_non_empty(env.get("AZURE_OPENAI_DEPLOYMENT_NAME"))
        if deployment_name is None:
            deployment_name = _extract_deployment_name(env.get("AZURE_OPENAI_CHAT_COMPLETIONS_URI"))
            fallback_deployment_name_source = "AZURE_OPENAI_CHAT_COMPLETIONS_URI"
        raw_endpoint = _compose_inference_endpoint(openai_endpoint, deployment_name)
        endpoint_source = "AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_DEPLOYMENT_NAME"

    normalized_endpoint = normalize_azure_inference_endpoint(raw_endpoint)
    credential = _first_non_empty(
        env.get("AZURE_INFERENCE_CREDENTIAL"),
        env.get("AZURE_OPENAI_API_KEY"),
    )
    deployment_name_source = "AZURE_INFERENCE_ENDPOINT"
    deployment_name = _extract_deployment_name(raw_endpoint)
    if endpoint_source != "AZURE_INFERENCE_ENDPOINT" and deployment_name is not None:
        deployment_name_source = fallback_deployment_name_source
    if deployment_name is None:
        deployment_name = _first_non_empty(
            env.get("AZURE_OPENAI_DEPLOYMENT_NAME"),
            _extract_deployment_name(env.get("AZURE_OPENAI_CHAT_COMPLETIONS_URI")),
        )
        deployment_name_source = "AZURE_OPENAI_DEPLOYMENT_NAME"

    missing: list[str] = []
    if normalized_endpoint is None:
        missing.append(
            "AZURE_INFERENCE_ENDPOINT or AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_DEPLOYMENT_NAME"
        )
    if credential is None:
        missing.append("AZURE_INFERENCE_CREDENTIAL or AZURE_OPENAI_API_KEY")

    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"Missing Azure AI Inference runtime settings: {joined}. "
            "Load the repository .env or export the values before running the probe."
        )

    assert normalized_endpoint is not None
    assert credential is not None
    return AzureInferenceRuntimeConfig(
        endpoint=normalized_endpoint,
        endpoint_source=endpoint_source,
        original_endpoint=raw_endpoint,
        endpoint_was_normalized=raw_endpoint != normalized_endpoint,
        deployment_name=deployment_name,
        deployment_name_source=deployment_name_source if deployment_name is not None else None,
        credential=credential,
        api_version=_first_non_empty(env.get("AZURE_OPENAI_API_VERSION")),
    )


def _require_openai_client() -> type[AzureOpenAIClient]:
    try:
        from openai import AzureOpenAI
    except ImportError as exc:  # pragma: no cover - import path is environment-dependent
        raise RuntimeError(
            "Azure OpenAI utilities require the `openai` package. Run `uv sync --extra azure`."
        ) from exc
    return AzureOpenAI


def _require_azure_inference_sdk() -> tuple[
    type[AzureInferenceChatCompletionsClient],
    type[AzureInferenceSystemMessage],
    type[AzureInferenceUserMessage],
    type[AzureCredentialClass],
]:
    try:
        from azure.ai.inference import ChatCompletionsClient
        from azure.ai.inference.models import SystemMessage, UserMessage
        from azure.core.credentials import AzureKeyCredential
    except ImportError as exc:  # pragma: no cover - import path is environment-dependent
        raise RuntimeError(
            "Azure AI Inference utilities require the Azure SDK. Run `uv sync --extra azure`."
        ) from exc
    return ChatCompletionsClient, SystemMessage, UserMessage, AzureKeyCredential


def _complete_with_azure_openai(
    config: AzureOpenAIRuntimeConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
) -> ChatCompletionResult:
    azure_openai_client = _require_openai_client()
    client = azure_openai_client(
        azure_endpoint=config.endpoint,
        api_key=config.api_key,
        api_version=config.api_version,
    )
    response = client.chat.completions.create(
        model=config.deployment_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        max_tokens=max_tokens,
    )
    choice = response.choices[0]
    return ChatCompletionResult(
        provider="azure-openai",
        answer=choice.message.content or "",
        model=response.model,
        finish_reason=str(choice.finish_reason),
    )


def _complete_with_azure_inference(
    config: AzureInferenceRuntimeConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
) -> ChatCompletionResult:
    chat_completions_client, system_message, user_message, azure_key_credential = (
        _require_azure_inference_sdk()
    )
    client = chat_completions_client(
        endpoint=config.endpoint,
        credential=azure_key_credential(config.credential),
    )
    response = client.complete(
        messages=[
            system_message(content=system_prompt),
            user_message(content=user_prompt),
        ],
        temperature=0,
        max_tokens=max_tokens,
    )
    choice = response.choices[0]
    return ChatCompletionResult(
        provider="azure-inference",
        answer=choice.message.content or "",
        model=response.model,
        finish_reason=str(choice.finish_reason),
    )


def call_azure_openai_chat(
    system_prompt: str,
    user_prompt: str,
    *,
    root: Path,
    load_env_file: bool = False,
    max_tokens: int = 400,
) -> ChatCompletionResult:
    """Complete a repository prompt through Azure OpenAI."""

    env, _ = load_runtime_environment(root, load_env_file=load_env_file)
    config = resolve_azure_openai_runtime(env)
    return _complete_with_azure_openai(
        config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
    )


def call_azure_inference_chat(
    system_prompt: str,
    user_prompt: str,
    *,
    root: Path,
    load_env_file: bool = False,
    max_tokens: int = 400,
) -> ChatCompletionResult:
    """Complete a repository prompt through Azure AI Inference."""

    env, _ = load_runtime_environment(root, load_env_file=load_env_file)
    config = resolve_azure_inference_runtime(env)
    return _complete_with_azure_inference(
        config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
    )


def probe_azure_openai(root: Path, *, load_env_file: bool = False) -> dict[str, object]:
    """Run a minimal Azure OpenAI probe and return a machine-readable result."""

    env, env_report = load_runtime_environment(root, load_env_file=load_env_file)
    config = resolve_azure_openai_runtime(env)
    completion = _complete_with_azure_openai(
        config,
        system_prompt="Reply with the exact token OPENAI_OK.",
        user_prompt="Return OPENAI_OK and nothing else.",
        max_tokens=16,
    )
    payload: dict[str, object] = {
        "provider": completion.provider,
        "status": "success",
        "reply": completion.answer.strip(),
        "model": completion.model,
        "finish_reason": completion.finish_reason,
        "endpoint": config.endpoint,
        "endpoint_source": config.endpoint_source,
        "deployment_name": config.deployment_name,
        "deployment_name_source": config.deployment_name_source,
        "api_version": config.api_version,
        "model_name": config.model_name,
    }
    payload.update(asdict(env_report))
    return payload


def probe_azure_inference(root: Path, *, load_env_file: bool = False) -> dict[str, object]:
    """Run a minimal Azure AI Inference probe and return a machine-readable result."""

    env, env_report = load_runtime_environment(root, load_env_file=load_env_file)
    config = resolve_azure_inference_runtime(env)
    completion = _complete_with_azure_inference(
        config,
        system_prompt="Reply with the exact token INFERENCE_OK.",
        user_prompt="Return INFERENCE_OK and nothing else.",
        max_tokens=16,
    )
    payload: dict[str, object] = {
        "provider": completion.provider,
        "status": "success",
        "reply": completion.answer.strip(),
        "model": completion.model,
        "finish_reason": completion.finish_reason,
        "endpoint": config.endpoint,
        "endpoint_source": config.endpoint_source,
        "original_endpoint": config.original_endpoint,
        "endpoint_was_normalized": config.endpoint_was_normalized,
        "deployment_name": config.deployment_name,
        "deployment_name_source": config.deployment_name_source,
        "api_version": config.api_version,
    }
    payload.update(asdict(env_report))
    return payload
