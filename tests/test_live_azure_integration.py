from __future__ import annotations

import os
from pathlib import Path

import pytest

from repo_rag_lab.azure_runtime import probe_azure_openai
from repo_rag_lab.dspy_training import resolve_dspy_lm_config
from repo_rag_lab.dspy_workflow import RepositoryRAG
from repo_rag_lab.workflow import ask_repository_live

REPO_ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.live_azure


def _missing_live_azure_env() -> list[str]:
    missing: list[str] = []
    if not os.getenv("AZURE_OPENAI_API_KEY", "").strip():
        missing.append("AZURE_OPENAI_API_KEY")
    if not (
        os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
        or os.getenv("AZURE_OPENAI_CHAT_COMPLETIONS_URI", "").strip()
    ):
        missing.append("AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_CHAT_COMPLETIONS_URI")
    if not os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "").strip():
        missing.append("AZURE_OPENAI_DEPLOYMENT_NAME")
    if not os.getenv("AZURE_OPENAI_API_VERSION", "").strip():
        missing.append("AZURE_OPENAI_API_VERSION")
    return missing


def _skip_if_live_azure_not_configured() -> None:
    missing = _missing_live_azure_env()
    if missing:
        pytest.skip(
            "Live Azure integration env is incomplete: " + ", ".join(missing),
        )


def test_probe_azure_openai_live_when_env_configured() -> None:
    _skip_if_live_azure_not_configured()

    payload = probe_azure_openai(REPO_ROOT, load_env_file=False)

    assert payload["provider"] == "azure-openai"
    assert payload["status"] == "success"
    assert "OPENAI_OK" in str(payload["reply"])
    assert payload["deployment_name"] == os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]


def test_ask_repository_live_uses_real_azure_openai_when_env_configured() -> None:
    _skip_if_live_azure_not_configured()

    answer = ask_repository_live(
        question="What does this repository research?",
        root=REPO_ROOT,
        provider="azure-openai",
        load_env_file=False,
    )

    assert answer.answer.strip()
    assert answer.context
    assert answer.mcp_servers


def test_repository_rag_dspy_runtime_uses_real_lm_when_env_configured() -> None:
    _skip_if_live_azure_not_configured()
    lm_config = resolve_dspy_lm_config()
    if lm_config is None:
        pytest.skip("DSPy LM configuration could not be resolved from the live Azure env.")

    result = RepositoryRAG(
        REPO_ROOT,
        top_k=4,
        lm_config=lm_config,
        require_configured_lm=True,
    )("What does this repository research?")

    assert result.program_loaded is True
    assert result.answer.strip()
    assert result.context
