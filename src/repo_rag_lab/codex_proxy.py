"""Local streaming proxy that injects repo-RAG + DSPy mediation for Codex."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from .azure_runtime import resolve_azure_openai_runtime
from .corpus import build_corpus_manifest, write_corpus_manifest
from .dspy_training import (
    DSPyLMConfig,
    configure_dspy_lm,
    resolve_dspy_helper_lm_config,
)
from .dspy_workflow import RepositoryRAG
from .retrieval import RetrievalMode
from .runtime_artifacts import (
    DEFAULT_TRAINER_FAMILY_STATE_PATH,
    RuntimeTraceContext,
    build_bundle_family_registry,
    build_runtime_trace,
    fetch_remote_bundle,
    fetch_remote_bundle_family_artifact,
    fetch_remote_family_state,
    inspect_bundle_channel,
    inspect_remote_bundle_channel,
    load_bundle_manifest,
    resolve_bundle_manifest,
    resolve_bundle_version_for_program,
)
from .training_samples import (
    resolve_prompt_family_support,
    resolve_prompt_family_support_from_payload,
)
from .workflow import ask_repository

try:
    import dspy as _dspy
except ImportError:  # pragma: no cover - optional runtime dependency during scaffolding
    _dspy = None

# Backward-compatible alias retained for tests and older local integrations.
resolve_dspy_lm_config = resolve_dspy_helper_lm_config

_DEFAULT_SNIPPET_LIMIT = 280
_DEFAULT_PREVIEW_COUNT = 2
_DEFAULT_ESSENTIAL_COUNT = 2
_DEFAULT_TOKEN_BUDGET = 420
_DEFAULT_TRIVIAL_TOKEN_BUDGET = 180
_DEFAULT_CACHE_TTL_SECONDS = 3600
_DEFAULT_FAMILY_EXPLORATION_RATE = 0.05
_TASK_TOKEN_DEEP_THRESHOLD = 10
_LOW_SIGNAL_SUMMARY_LIMIT = 40
_FORWARDED_DISCORD_LINE_PATTERN = re.compile(r"(?is)^\[forwarded\]\s*@.*$")
_REPO_GROUNDING_HINTS = {
    "repo",
    "repository",
    "code",
    "bug",
    "fix",
    "test",
    "tests",
    "file",
    "files",
    "module",
    "function",
    "class",
    "implementation",
    "refactor",
    "config",
    "readme",
    "src",
}


@dataclass(frozen=True)
class CodexMediationResult:
    """Describe one repo-grounded mediation pass for a Codex request."""

    question: str
    original_prompt: str
    reformulated_prompt: str
    reformulation_status: str
    mediation_mode: str
    rag_status: str
    dspy_status: str
    dspy_lm_model: str | None
    summary: str
    retrieval_mode: str
    sources: list[str]
    warnings: list[str]
    bundle_version: str | None
    program_path: str | None
    evidence_previews: list[dict[str, str]]
    developer_message: str
    prompt_family_id: str | None = None
    prompt_family_similarity: float = 0.0
    prompt_family_band: str = "new"
    family_runtime_hit_rate: float | None = None
    family_artifact_hit_rate: float | None = None
    family_predicted_hit_rate: float | None = None
    family_predicted_hit_rate_lower_bound: float | None = None
    family_prediction_uncertainty: float | None = None
    family_feedback_count: int | None = None
    family_artifact_selected: bool | None = None
    family_exploration_selected: bool | None = None
    task_classification: str = "deep"
    budget_tokens: int = _DEFAULT_TOKEN_BUDGET
    estimated_tokens: int = 0
    injected: bool = True
    cache_hit: bool = False

    def to_payload(self) -> dict[str, object]:
        """Return the JSON-serializable mediation payload."""

        return asdict(self)


@dataclass(frozen=True)
class CodexProxyConfig:
    """Runtime settings for one local Codex mediation proxy."""

    repository_root: Path
    bundle_root: Path
    artifact_dir: Path
    host: str = "127.0.0.1"
    port: int = 0
    dspy_top_k: int = 4
    prefer_dspy: bool = True
    bundle_channel: str = "stable"
    bundle_version: str | None = None
    status_filename: str = "repo_rag_codex_proxy_last.json"
    token_budget: int = _DEFAULT_TOKEN_BUDGET
    trivial_token_budget: int = _DEFAULT_TRIVIAL_TOKEN_BUDGET
    essentials_count: int = _DEFAULT_ESSENTIAL_COUNT
    low_signal_min_sources: int = 1
    family_exploration_rate: float = _DEFAULT_FAMILY_EXPLORATION_RATE
    retrieval_mode: RetrievalMode | None = None
    cache_dir: Path | None = None
    cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS


@dataclass(frozen=True)
class RunningCodexProxy:
    """One running local Codex proxy instance."""

    server: HTTPServer
    thread: threading.Thread
    base_url: str
    status_path: Path


def _truncate_text(text: str, *, limit: int = _DEFAULT_SNIPPET_LIMIT) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3].rstrip()}..."


def _estimate_token_count(text: str) -> int:
    cleaned = " ".join(str(text).split())
    if not cleaned:
        return 0
    return max(1, (len(cleaned) + 3) // 4)


def _clamp_probability(value: float) -> float:
    """Clamp one exploration-like probability into the closed unit interval."""

    return max(0.0, min(1.0, float(value)))


def _stable_fraction(*parts: object) -> float:
    """Return a deterministic pseudo-random fraction derived from stable identity parts."""

    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    numerator = int(digest, 16)
    denominator = float(16**16 - 1)
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _task_tokens(question: str) -> list[str]:
    return [
        token
        for token in "".join(ch if ch.isalnum() else " " for ch in question.lower()).split()
        if token
    ]


def _classify_task(question: str) -> str:
    tokens = _task_tokens(question)
    if len(tokens) >= _TASK_TOKEN_DEEP_THRESHOLD:
        return "deep"
    return "trivial"


def _looks_like_prompt_text(text: str) -> bool:
    """Return whether one command-trace text looks like a natural-language prompt."""

    cleaned = " ".join(str(text or "").split()).strip()
    if len(cleaned) < 24:
        return False
    if not any(character.isalpha() for character in cleaned):
        return False
    lowered = cleaned.lower()
    command_prefixes = ("pytest ", "git ", "make ", "uv ", "python ", "cargo ", "npm ")
    if lowered.startswith(command_prefixes):
        return False
    return "\nstdout:" not in lowered and "\nstderr:" not in lowered


def _dedupe_previews(previews: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for preview in previews:
        source = str(preview.get("source") or "").strip()
        text = str(preview.get("text") or "").strip()
        if not source or source in seen or not text:
            continue
        deduped.append({"source": source, "text": text})
        seen.add(source)
    return deduped


def _build_budgeted_message(
    *,
    reformulated_prompt: str,
    mediation_mode: str,
    rag_status: str,
    dspy_status: str,
    summary: str,
    sources: list[str],
    previews: list[dict[str, str]],
    warnings: list[str],
    prompt_family_id: str | None,
    family_artifact_selected: bool | None,
    budget_tokens: int,
    essentials_count: int,
) -> tuple[str, int]:
    summary_limit = max(96, min(240, budget_tokens))
    trimmed_summary = _truncate_text(summary, limit=summary_limit)
    trimmed_previews = _dedupe_previews(previews)[:1]
    trimmed_reformulated_prompt = _truncate_text(reformulated_prompt, limit=144)
    source_limit = max(1, min(2, essentials_count))
    lines = [
        "Repo mediation active.",
        (
            "Execution: reuse family artifact."
            if family_artifact_selected and dspy_status == "success"
            else "Execution: repo-grounded DSPy mediation."
            if dspy_status == "success"
            else "Execution: repo-grounded fallback."
        ),
    ]
    if prompt_family_id:
        lines.append(f"Family: {prompt_family_id}")
    lines.append(f"Mode: {mediation_mode}")
    if reformulated_prompt.strip():
        lines.append(f"Prompt: {trimmed_reformulated_prompt}")
    if trimmed_summary:
        lines.extend(["", "Summary:", trimmed_summary])

    def _candidate_text(extra_lines: list[str]) -> str:
        return "\n".join(lines + extra_lines).strip()

    if sources:
        section = ["", "Files:"]
        for source in sources[:source_limit]:
            trial = [*section, f"- {source}"]
            if _estimate_token_count(_candidate_text(trial)) > budget_tokens:
                break
            section = trial
        if len(section) > 2:
            lines.extend(section)

    if trimmed_previews:
        section = ["", "Evidence:"]
        for preview in trimmed_previews:
            candidate_line = (
                f"- {preview['source']}: "
                f"{_truncate_text(preview['text'], limit=max(80, budget_tokens // 2))}"
            )
            trial = [*section, candidate_line]
            if _estimate_token_count(_candidate_text(trial)) > budget_tokens:
                break
            section = trial
        if len(section) > 2:
            lines.extend(section)

    if warnings:
        section = ["", "Notes:"]
        for warning in warnings[:1]:
            candidate_line = f"- {_truncate_text(warning, limit=120)}"
            trial = [*section, candidate_line]
            if _estimate_token_count(_candidate_text(trial)) > budget_tokens:
                break
            section = trial
        if len(section) > 2:
            lines.extend(section)

    message = "\n".join(lines).strip()
    estimated_tokens = _estimate_token_count(message)
    if estimated_tokens > budget_tokens:
        message = "\n".join(
            [
                "Repo mediation active.",
                f"Mode: {mediation_mode}",
                *([f"Family: {prompt_family_id}"] if prompt_family_id else []),
                "Summary:",
                _truncate_text(trimmed_summary, limit=max(72, budget_tokens // 2)),
            ]
        ).strip()
        estimated_tokens = _estimate_token_count(message)
    return message, estimated_tokens


def _result_from_payload(payload: dict[str, object]) -> CodexMediationResult | None:
    try:
        raw_sources = payload.get("sources")
        sources = (
            [str(item).strip() for item in raw_sources if str(item).strip()]
            if isinstance(raw_sources, list)
            else []
        )
        raw_warnings = payload.get("warnings")
        warnings = (
            [str(item).strip() for item in raw_warnings if str(item).strip()]
            if isinstance(raw_warnings, list)
            else []
        )
        raw_evidence_previews = payload.get("evidence_previews")
        evidence_previews = (
            [
                {
                    "source": str(item.get("source") or ""),
                    "text": str(item.get("text") or ""),
                }
                for item in raw_evidence_previews
                if isinstance(item, dict)
                and str(item.get("source") or "").strip()
                and str(item.get("text") or "").strip()
            ]
            if isinstance(raw_evidence_previews, list)
            else []
        )
        raw_budget_tokens = payload.get("budget_tokens")
        budget_tokens = (
            int(raw_budget_tokens)
            if isinstance(raw_budget_tokens, (bool, int, float, str))
            else _DEFAULT_TOKEN_BUDGET
        )
        raw_estimated_tokens = payload.get("estimated_tokens")
        estimated_tokens = (
            int(raw_estimated_tokens)
            if isinstance(raw_estimated_tokens, (bool, int, float, str))
            else 0
        )
        family_feedback_count_value = payload.get("family_feedback_count")
        return CodexMediationResult(
            question=str(payload.get("question") or ""),
            original_prompt=str(payload.get("original_prompt") or ""),
            reformulated_prompt=str(payload.get("reformulated_prompt") or ""),
            reformulation_status=str(payload.get("reformulation_status") or "identity"),
            mediation_mode=str(payload.get("mediation_mode") or "heuristic"),
            rag_status=str(payload.get("rag_status") or "failed"),
            dspy_status=str(payload.get("dspy_status") or "disabled"),
            dspy_lm_model=(
                str(payload.get("dspy_lm_model")).strip()
                if payload.get("dspy_lm_model") is not None
                else None
            )
            or None,
            summary=str(payload.get("summary") or ""),
            retrieval_mode=str(payload.get("retrieval_mode") or "lexical"),
            sources=sources,
            warnings=warnings,
            bundle_version=(
                str(payload.get("bundle_version")).strip()
                if payload.get("bundle_version") is not None
                else None
            )
            or None,
            program_path=(
                str(payload.get("program_path")).strip()
                if payload.get("program_path") is not None
                else None
            )
            or None,
            evidence_previews=evidence_previews,
            developer_message=str(payload.get("developer_message") or ""),
            prompt_family_id=(
                str(payload.get("prompt_family_id")).strip()
                if payload.get("prompt_family_id") is not None
                else None
            )
            or None,
            prompt_family_similarity=_float_or_none(payload.get("prompt_family_similarity")) or 0.0,
            prompt_family_band=str(payload.get("prompt_family_band") or "new"),
            family_runtime_hit_rate=_float_or_none(payload.get("family_runtime_hit_rate")),
            family_artifact_hit_rate=_float_or_none(payload.get("family_artifact_hit_rate")),
            family_predicted_hit_rate=_float_or_none(payload.get("family_predicted_hit_rate")),
            family_predicted_hit_rate_lower_bound=_float_or_none(
                payload.get("family_predicted_hit_rate_lower_bound")
            ),
            family_prediction_uncertainty=_float_or_none(
                payload.get("family_prediction_uncertainty")
            ),
            family_feedback_count=(
                family_feedback_count_value
                if isinstance(family_feedback_count_value, int)
                and not isinstance(family_feedback_count_value, bool)
                else None
            ),
            family_artifact_selected=(
                bool(payload.get("family_artifact_selected"))
                if payload.get("family_artifact_selected") is not None
                else None
            ),
            family_exploration_selected=(
                bool(payload.get("family_exploration_selected"))
                if payload.get("family_exploration_selected") is not None
                else None
            ),
            task_classification=str(payload.get("task_classification") or "deep"),
            budget_tokens=budget_tokens,
            estimated_tokens=estimated_tokens,
            injected=bool(payload.get("injected", True)),
            cache_hit=bool(payload.get("cache_hit", False)),
        )
    except Exception:
        return None


def _extract_text_from_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n".join(parts).strip()


def _sanitize_bundle_token(name: str, *, default: str) -> str:
    """Return one filesystem-safe bundle token."""

    parts = [part for part in re.split(r"[^A-Za-z0-9._-]+", str(name).strip()) if part]
    if parts:
        return "-".join(parts)
    return default


def _strip_forwarded_discord_tail(text: str) -> str:
    """Remove forwarded Discord noise without dropping later user-authored lines."""

    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    filtered_lines: list[str] = []
    skipping_forwarded_followups = False
    for raw_line in cleaned.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if _FORWARDED_DISCORD_LINE_PATTERN.match(stripped):
            skipping_forwarded_followups = True
            continue
        if skipping_forwarded_followups and stripped.startswith(("Attachments:", "- ")):
            continue
        if stripped:
            skipping_forwarded_followups = False
        filtered_lines.append(line)
    stripped_text = "\n".join(filtered_lines).strip()
    return stripped_text or cleaned


def _strip_dataset_execution_envelope(text: str) -> str:
    """Remove dataset-specific execution scaffolding from one Codex user prompt."""

    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    if "\nEXECUTION CONTEXT:" in cleaned:
        cleaned = cleaned.split("\nEXECUTION CONTEXT:", 1)[0].rstrip()
    elif "\nAUTONOMOUS EXECUTION CONTRACT:" in cleaned:
        cleaned = cleaned.split("\nAUTONOMOUS EXECUTION CONTRACT:", 1)[0].rstrip()
    if "Messages with required reaction:" in cleaned:
        cleaned = cleaned.split("Messages with required reaction:", 1)[1].strip()
    elif "Messages aggregated:" in cleaned and "\n\n" in cleaned:
        cleaned = cleaned.split("\n\n", 1)[1].strip()
    normalized_lines: list[str] = []
    skip_attachment_lines = False
    for raw_line in cleaned.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            skip_attachment_lines = False
            if normalized_lines and normalized_lines[-1] != "":
                normalized_lines.append("")
            continue
        if stripped == "Attachment locations:":
            skip_attachment_lines = True
            continue
        if skip_attachment_lines and stripped.startswith("- "):
            continue
        if stripped.startswith("Discord channel:"):
            continue
        if stripped.startswith("Channel ID:"):
            continue
        if stripped.startswith("Queue label:"):
            continue
        if stripped.startswith("Messages aggregated:"):
            continue
        if stripped.startswith("Available repository:"):
            continue
        if stripped.startswith("Repository checkout:"):
            continue
        if stripped.startswith("Attachment mount:"):
            continue
        if stripped.startswith("Attachments saved for execution"):
            continue
        if stripped.startswith("Attachments:"):
            continue
        if stripped.startswith("[") and ") " in stripped:
            _prefix, _sep, remainder = stripped.partition(") ")
            if _sep and _prefix.startswith("["):
                stripped = remainder.strip()
        normalized_lines.append(stripped)
    while normalized_lines and normalized_lines[-1] == "":
        normalized_lines.pop()
    result = _strip_forwarded_discord_tail("\n".join(normalized_lines).strip())
    fallback = _strip_forwarded_discord_tail(str(text or "").strip())
    return result or fallback


def _command_trace_step(item: Mapping[str, object]) -> dict[str, str] | None:
    """Extract one compact command-trace step from a Responses input item."""

    step: dict[str, str] = {}
    item_type = str(item.get("type") or "").strip()
    role = str(item.get("role") or "").strip()
    if item_type:
        step["type"] = item_type
    if role:
        step["role"] = role
    text = _extract_text_from_content(item.get("content"))
    if text:
        step["text"] = text
    for key in ("name", "command", "tool_name", "call_id", "arguments", "output"):
        value = item.get(key)
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if cleaned:
            step[key] = cleaned
    return step or None


def extract_codex_turn_state(payload: Mapping[str, object]) -> dict[str, object]:
    """Extract the current outbound prompt plus its visible command-trace lineage."""

    raw_input = payload.get("input")
    if isinstance(raw_input, str):
        cleaned = _strip_dataset_execution_envelope(raw_input.strip())
        return {
            "original_prompt": cleaned,
            "command_trace": (
                [{"type": "message", "role": "user", "text": cleaned}] if cleaned else []
            ),
        }
    if not isinstance(raw_input, list):
        return {"original_prompt": "", "command_trace": []}

    user_messages: list[str] = []
    fallback_messages: list[str] = []
    command_trace: list[dict[str, str]] = []
    for item in raw_input:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role") or "").strip().lower()
        item_type = str(item.get("type") or "").strip().lower()
        step = _command_trace_step(item)
        text = step.get("text", "").strip() if isinstance(step, dict) else ""
        if role == "user" and text and isinstance(step, dict):
            step["text"] = _strip_dataset_execution_envelope(text)
            text = step["text"]
        if item_type == "message":
            if role == "user" and text:
                user_messages.append(text)
            elif role in {"developer", "system"} and text:
                fallback_messages.append(text)
        if role not in {"developer", "system"} and step is not None:
            command_trace.append(step)
    if user_messages:
        original_prompt = user_messages[-1]
    elif fallback_messages:
        original_prompt = fallback_messages[-1]
    else:
        original_prompt = ""
    original_prompt = _strip_dataset_execution_envelope(original_prompt)
    return {
        "original_prompt": original_prompt,
        "command_trace": command_trace,
    }


def extract_codex_task_text(payload: Mapping[str, object]) -> str:
    """Extract the latest user-facing task text from one Responses payload."""

    return str(extract_codex_turn_state(payload).get("original_prompt") or "").strip()


def reformulate_codex_prompt(
    original_prompt: str,
    *,
    lm_config: DSPyLMConfig | None,
) -> tuple[str, str]:
    """Return the reformulated DSPy helper prompt for one outbound Codex turn."""

    cleaned = " ".join(original_prompt.split()).strip()
    if not cleaned:
        return "", "empty"
    if lm_config is None or _dspy is None:
        return cleaned, "identity"
    try:
        assert _dspy is not None
        configure_dspy_lm(lm_config)

        class PromptReformulationSignature(_dspy.Signature):
            """Rewrite one software-agent prompt into a compact mediation query."""

            original_prompt = _dspy.InputField()
            reformulated_prompt = _dspy.OutputField(
                desc=(
                    "A concise reformulation for repository-grounded DSPy mediation. Preserve "
                    "the requested task, files, tests, commands, failures, and constraints. Do "
                    "not solve the task."
                )
            )

        reformulator = _dspy.Predict(PromptReformulationSignature)
        prediction = reformulator(original_prompt=cleaned)
        reformulated = " ".join(str(getattr(prediction, "reformulated_prompt", "")).split()).strip()
        if not reformulated:
            return cleaned, "identity"
        return reformulated, "dspy"
    except Exception:
        return cleaned, "identity"


def _resolve_family_state_path(repository_root: Path, bundle_root: Path) -> Path | None:
    """Resolve the family-state path used for prompt-family support lookups."""

    direct_candidates = [
        bundle_root.resolve() / DEFAULT_TRAINER_FAMILY_STATE_PATH,
        repository_root.resolve() / DEFAULT_TRAINER_FAMILY_STATE_PATH,
        bundle_root.resolve() / "artifacts" / "trainer" / "family-state.json",
        repository_root.resolve() / "artifacts" / "trainer" / "family-state.json",
    ]
    for candidate in direct_candidates:
        if candidate.is_file():
            return candidate
    legacy_candidates = [
        bundle_root.resolve() / "artifacts" / "trainer" / "champion-index.json",
        repository_root.resolve() / "artifacts" / "trainer" / "champion-index.json",
    ]
    for candidate in legacy_candidates:
        if candidate.is_file():
            return candidate
    for cache_root in (bundle_root.resolve(), repository_root.resolve()):
        remote_payload = fetch_remote_family_state(cache_root)
        if not isinstance(remote_payload, dict):
            continue
        family_state_path = str(remote_payload.get("family_state_path") or "").strip()
        if not family_state_path:
            continue
        resolved = cache_root / family_state_path
        if resolved.is_file():
            return resolved
    return None


def _available_staged_bundle_versions(bundle_root: Path) -> list[str]:
    """Return staged bundle versions discoverable from the local bundle mirror."""

    resolved_root = bundle_root.resolve()
    versions: set[str] = set()
    versions_dir = resolved_root / "versions"
    if versions_dir.is_dir():
        for candidate in versions_dir.iterdir():
            if not candidate.is_dir():
                continue
            if (candidate / "program.json").is_file() or (candidate / "bundle.json").is_file():
                versions.add(candidate.name)
    remote_dir = resolved_root / "artifacts" / "dspy" / "remote"
    if remote_dir.is_dir():
        for candidate in remote_dir.iterdir():
            if not candidate.is_dir():
                continue
            if (candidate / "program.json").is_file() or (candidate / "bundle.json").is_file():
                versions.add(candidate.name)
    return sorted(versions, reverse=True)


def _load_staged_bundle_manifest(
    *,
    bundle_root: Path,
    bundle_version: str | None,
) -> dict[str, object] | None:
    """Load one staged bundle manifest directly from the local mirror."""

    if bundle_version is None:
        return None
    resolved_root = bundle_root.resolve()
    candidates = (
        resolved_root / "versions" / bundle_version / "bundle.json",
        resolved_root / "artifacts" / "dspy" / "remote" / bundle_version / "bundle.json",
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            return load_bundle_manifest(candidate)
        except Exception:
            continue
    return None


def _resolve_bundle_version_hint(
    *,
    bundle_root: Path,
    bundle_version: str | None,
    bundle_channel: str,
) -> str | None:
    """Return the best-known bundle version for staged bundle-store lookups."""

    if bundle_version is not None:
        return bundle_version
    remote_channel_state = inspect_remote_bundle_channel(bundle_channel)
    if remote_channel_state is not None:
        resolved_bundle_version = str(
            remote_channel_state.get("current_bundle_version") or ""
        ).strip()
        return resolved_bundle_version or None
    channel_state = inspect_bundle_channel(bundle_root, channel=bundle_channel)
    resolved_bundle_version = str(channel_state.get("current_bundle_version") or "").strip()
    if resolved_bundle_version:
        return resolved_bundle_version
    staged_versions = _available_staged_bundle_versions(bundle_root)
    return staged_versions[0] if staged_versions else None


def _staged_bundle_program_candidates(
    *,
    bundle_root: Path,
    bundle_version: str | None,
) -> list[Path]:
    """Return canonical staged program.json candidates for one bundle version."""

    if bundle_version is None:
        return []
    resolved_root = bundle_root.resolve()
    return [
        resolved_root / "versions" / bundle_version / "program.json",
        resolved_root / "artifacts" / "dspy" / "remote" / bundle_version / "program.json",
    ]


def _staged_bundle_routing_index_candidates(
    *,
    bundle_root: Path,
    bundle_version: str | None,
) -> list[Path]:
    """Return canonical staged routing-index candidates for one bundle version."""

    if bundle_version is None:
        return []
    resolved_root = bundle_root.resolve()
    return [
        resolved_root / "versions" / bundle_version / "routing-index.sqlite3",
        resolved_root / "artifacts" / "dspy" / "remote" / bundle_version / "routing-index.sqlite3",
    ]


def _staged_family_program_candidates(
    *,
    bundle_root: Path,
    bundle_version: str | None,
    prompt_family_id: str | None,
) -> list[Path]:
    """Return canonical staged family program candidates for one bundle version."""

    if bundle_version is None or not prompt_family_id:
        return []
    resolved_root = bundle_root.resolve()
    safe_family_id = _sanitize_bundle_token(prompt_family_id, default="family")
    return [
        resolved_root / "versions" / bundle_version / "families" / safe_family_id / "program.json",
        resolved_root
        / "artifacts"
        / "dspy"
        / "remote"
        / bundle_version
        / "families"
        / safe_family_id
        / "program.json",
    ]


def _resolve_bundle_routing_index_path(
    *,
    bundle_root: Path,
    bundle_version: str | None,
    bundle_channel: str,
) -> Path | None:
    """Resolve one bundle-local routing index staged beside the runtime artifacts."""

    def _local_candidate_from_manifest(bundle_payload: Mapping[str, object] | None) -> Path | None:
        routing_index_path_text = (
            str(bundle_payload.get("routing_index_path") or "").strip()
            if isinstance(bundle_payload, Mapping)
            else ""
        )
        if not routing_index_path_text:
            return None
        candidate = Path(routing_index_path_text)
        if not candidate.is_absolute():
            candidate = (bundle_root / candidate).resolve()
        if candidate.is_file():
            return candidate.resolve()
        return None

    if bundle_version is not None:
        local_bundle: Mapping[str, object] | None
        try:
            _, local_bundle = resolve_bundle_manifest(bundle_root, bundle_version=bundle_version)
        except ValueError:
            local_bundle = _load_staged_bundle_manifest(
                bundle_root=bundle_root,
                bundle_version=bundle_version,
            )
        local_candidate = _local_candidate_from_manifest(local_bundle)
        if local_candidate is not None:
            return local_candidate
        for candidate in _staged_bundle_routing_index_candidates(
            bundle_root=bundle_root,
            bundle_version=bundle_version,
        ):
            if candidate.is_file():
                return candidate.resolve()
        try:
            remote_bundle = fetch_remote_bundle(
                bundle_root,
                bundle_version=bundle_version,
                channel=None,
                download_family_artifacts=False,
            )
        except Exception:
            remote_bundle = None
        remote_candidate = _local_candidate_from_manifest(remote_bundle)
        if remote_candidate is not None:
            return remote_candidate
        return None

    remote_channel_state = inspect_remote_bundle_channel(bundle_channel)
    if remote_channel_state is not None:
        staged_bundle_version = (
            str(remote_channel_state.get("current_bundle_version") or "").strip() or None
        )
        if staged_bundle_version is None:
            return None
        for candidate in _staged_bundle_routing_index_candidates(
            bundle_root=bundle_root,
            bundle_version=staged_bundle_version,
        ):
            if candidate.is_file():
                return candidate.resolve()
        try:
            remote_bundle = fetch_remote_bundle(
                bundle_root,
                bundle_version=staged_bundle_version,
                channel=None,
                download_family_artifacts=False,
            )
        except Exception:
            remote_bundle = None
        remote_candidate = _local_candidate_from_manifest(remote_bundle)
        if remote_candidate is not None:
            return remote_candidate
        return None

    channel_state = inspect_bundle_channel(bundle_root, channel=bundle_channel)
    current_bundle = (
        channel_state.get("current_bundle") if channel_state.get("channel_found") else None
    )
    local_candidate = _local_candidate_from_manifest(
        current_bundle if isinstance(current_bundle, Mapping) else None
    )
    if local_candidate is not None:
        return local_candidate
    staged_bundle_version = _resolve_bundle_version_hint(
        bundle_root=bundle_root,
        bundle_version=None,
        bundle_channel=bundle_channel,
    )
    if staged_bundle_version is not None:
        staged_bundle_payload = _load_staged_bundle_manifest(
            bundle_root=bundle_root,
            bundle_version=staged_bundle_version,
        )
        staged_candidate = _local_candidate_from_manifest(staged_bundle_payload)
        if staged_candidate is not None:
            return staged_candidate
        for candidate in _staged_bundle_routing_index_candidates(
            bundle_root=bundle_root,
            bundle_version=staged_bundle_version,
        ):
            if candidate.is_file():
                return candidate.resolve()
    try:
        remote_bundle = fetch_remote_bundle(
            bundle_root,
            bundle_version=None,
            channel=bundle_channel,
            download_family_artifacts=False,
        )
    except Exception:
        remote_bundle = None
    return _local_candidate_from_manifest(remote_bundle)


def _build_family_registry_from_state_path(
    *,
    repository_root: Path,
    family_state_path: Path,
) -> dict[str, object] | None:
    """Synthesize one bundle-style family registry from a persisted family-state file."""

    try:
        return build_bundle_family_registry(
            repository_root.resolve(),
            family_state_path=family_state_path.resolve(),
        )
    except Exception:
        return None


def _resolve_bundle_family_registry(
    *,
    bundle_root: Path,
    bundle_version: str | None,
    bundle_channel: str,
) -> dict[str, object] | None:
    """Resolve the monolithic bundle's internal family registry when available."""

    if bundle_version is not None:
        local_bundle: Mapping[str, object] | None
        try:
            _, local_bundle = resolve_bundle_manifest(
                bundle_root,
                bundle_version=bundle_version,
            )
        except ValueError:
            local_bundle = _load_staged_bundle_manifest(
                bundle_root=bundle_root,
                bundle_version=bundle_version,
            )
        family_registry = (
            local_bundle.get("family_registry") if isinstance(local_bundle, dict) else None
        )
        if isinstance(family_registry, Mapping):
            return dict(family_registry)
        try:
            remote_bundle = fetch_remote_bundle(
                bundle_root,
                bundle_version=bundle_version,
                channel=None,
                download_family_artifacts=False,
            )
        except Exception:
            remote_bundle = None
        remote_family_registry = (
            remote_bundle.get("family_registry") if isinstance(remote_bundle, dict) else None
        )
        if isinstance(remote_family_registry, Mapping):
            return dict(remote_family_registry)
        return None
    remote_channel_state = inspect_remote_bundle_channel(bundle_channel)
    if remote_channel_state is not None:
        staged_bundle_version = (
            str(remote_channel_state.get("current_bundle_version") or "").strip() or None
        )
        if staged_bundle_version is None:
            return None
        try:
            remote_bundle = fetch_remote_bundle(
                bundle_root,
                bundle_version=staged_bundle_version,
                channel=None,
                download_family_artifacts=False,
            )
        except Exception:
            remote_bundle = None
        remote_family_registry = (
            remote_bundle.get("family_registry") if isinstance(remote_bundle, dict) else None
        )
        if isinstance(remote_family_registry, Mapping):
            return dict(remote_family_registry)
        return None
    channel_state = inspect_bundle_channel(bundle_root, channel=bundle_channel)
    staged_bundle_version = _resolve_bundle_version_hint(
        bundle_root=bundle_root,
        bundle_version=None,
        bundle_channel=bundle_channel,
    )
    current_bundle = (
        channel_state.get("current_bundle") if channel_state.get("channel_found") else None
    )
    if isinstance(current_bundle, Mapping):
        family_registry = current_bundle.get("family_registry")
        if isinstance(family_registry, Mapping):
            return dict(family_registry)
    current_bundle_path = str(channel_state.get("current_bundle_path") or "").strip()
    if current_bundle_path:
        resolved_local_bundle_path = (bundle_root / current_bundle_path).resolve()
        if resolved_local_bundle_path.is_file():
            local_bundle_payload = load_bundle_manifest(resolved_local_bundle_path)
            family_registry = local_bundle_payload.get("family_registry")
            if isinstance(family_registry, Mapping):
                return dict(family_registry)
    if staged_bundle_version is not None:
        staged_bundle_payload = _load_staged_bundle_manifest(
            bundle_root=bundle_root,
            bundle_version=staged_bundle_version,
        )
        family_registry = (
            staged_bundle_payload.get("family_registry")
            if isinstance(staged_bundle_payload, Mapping)
            else None
        )
        if isinstance(family_registry, Mapping):
            return dict(family_registry)
    try:
        remote_bundle = fetch_remote_bundle(
            bundle_root,
            bundle_version=bundle_version,
            channel=None if bundle_version else bundle_channel,
            download_family_artifacts=False,
        )
    except Exception:
        remote_bundle = None
    if isinstance(remote_bundle, dict):
        remote_bundle_path = str(remote_bundle.get("bundle_path") or "").strip()
        if remote_bundle_path:
            resolved_remote_bundle_path = (bundle_root / remote_bundle_path).resolve()
            if resolved_remote_bundle_path.is_file():
                remote_bundle_payload = load_bundle_manifest(resolved_remote_bundle_path)
                family_registry = remote_bundle_payload.get("family_registry")
                if isinstance(family_registry, Mapping):
                    return dict(family_registry)
    return None


def _resolve_family_runtime_program_path(
    *,
    repository_root: Path,
    bundle_root: Path,
    family_registry: Mapping[str, object] | None,
    prompt_family_id: str | None,
    bundle_version: str | None,
) -> Path | None:
    """Resolve the matched family's runtime program path from the bundle registry."""

    if not prompt_family_id:
        return None
    raw_families = family_registry.get("families") if isinstance(family_registry, Mapping) else None
    if isinstance(raw_families, list):
        for family in raw_families:
            if not isinstance(family, Mapping):
                continue
            family_id = str(family.get("prompt_family_id") or "").strip()
            if family_id != prompt_family_id:
                continue
            runtime_artifact = family.get("runtime_artifact")
            if not isinstance(runtime_artifact, Mapping):
                break
            if not bool(runtime_artifact.get("artifact_ready")):
                break
            program_path_text = str(runtime_artifact.get("program_path") or "").strip()
            if not program_path_text:
                break
            resolved_program_path = Path(program_path_text)
            if not resolved_program_path.is_absolute():
                candidate_roots = []
                for candidate_root in (repository_root, bundle_root):
                    resolved_candidate_root = candidate_root.resolve()
                    if resolved_candidate_root not in candidate_roots:
                        candidate_roots.append(resolved_candidate_root)
                for candidate_root in candidate_roots:
                    candidate_program_path = candidate_root / resolved_program_path
                    if candidate_program_path.is_file():
                        return candidate_program_path.resolve()
            elif resolved_program_path.is_file():
                return resolved_program_path.resolve()
            break
    for candidate in _staged_family_program_candidates(
        bundle_root=bundle_root,
        bundle_version=bundle_version,
        prompt_family_id=prompt_family_id,
    ):
        if candidate.is_file():
            return candidate.resolve()
    if bundle_version is not None and prompt_family_id:
        try:
            remote_artifact = fetch_remote_bundle_family_artifact(
                bundle_root,
                bundle_version=bundle_version,
                prompt_family_id=prompt_family_id,
            )
        except Exception:
            remote_artifact = None
        program_path_text = (
            str(remote_artifact.get("program_path") or "").strip()
            if isinstance(remote_artifact, Mapping)
            else ""
        )
        if program_path_text:
            resolved_program_path = Path(program_path_text)
            if not resolved_program_path.is_absolute():
                resolved_program_path = (bundle_root / resolved_program_path).resolve()
            if resolved_program_path.is_file():
                return resolved_program_path.resolve()
    return None


def _resolve_family_entry_from_routing_index(
    *,
    routing_index_path: Path | None,
    prompt_family_id: str | None,
) -> dict[str, object] | None:
    """Load one thin family entry directly from the bundle-local routing index."""

    if routing_index_path is None or not prompt_family_id:
        return None
    resolved_index_path = routing_index_path.resolve()
    if not resolved_index_path.is_file():
        return None
    connection = sqlite3.connect(resolved_index_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT *
            FROM family_index_entries
            WHERE prompt_family_id = ?
            """,
            (prompt_family_id,),
        ).fetchone()
    except sqlite3.DatabaseError:
        return None
    finally:
        connection.close()
    if row is None:
        return None

    if "payload_json" in row.keys():
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            return None
        entry = {str(key): value for key, value in payload.items()}
        prompt_family_id = str(row["prompt_family_id"] or "").strip()
        if prompt_family_id and "prompt_family_id" not in entry:
            entry["prompt_family_id"] = prompt_family_id
        if "family_record_count" not in entry:
            entry["family_record_count"] = int(row["family_record_count"] or 0)
        return entry

    def _load_json_column(column_name: str, default: object) -> object:
        try:
            raw = str(row[column_name] or "")
        except Exception:
            return default
        if not raw.strip():
            return default
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return default
        return value

    feedback_metric = _load_json_column("family_feedback_metric_json", {})
    success_metric = _load_json_column("family_success_metric_json", {})
    prompt_terms = _load_json_column("prompt_terms_json", [])
    command_terms = _load_json_column("command_terms_json", [])
    constraint_terms = _load_json_column("constraint_terms_json", [])
    entry = {
        "prompt_family_id": str(row["prompt_family_id"] or "").strip(),
        "question": str(row["question"] or "").strip(),
        "family_record_count": int(row["family_record_count"] or 0),
        "family_father_similarity_mean": _float_or_none(row["family_father_similarity_mean"]),
        "family_runtime_score": _float_or_none(row["family_runtime_score"]),
        "family_metric_1_mean": _float_or_none(row["family_metric_1_mean"]),
        "family_feedback_metric": feedback_metric if isinstance(feedback_metric, Mapping) else {},
        "family_feedback_count": int(row["family_feedback_count"] or 0),
        "family_success_metric": success_metric if isinstance(success_metric, Mapping) else {},
        "family_prompt_profile_terms": prompt_terms if isinstance(prompt_terms, list) else [],
        "family_command_pattern_summary": command_terms
        if isinstance(command_terms, list)
        else [],
        "family_constraint_summary": constraint_terms if isinstance(constraint_terms, list) else [],
    }
    if "family_path" in row.keys():
        entry["family_path"] = str(row["family_path"] or "").strip()
    if "father_path" in row.keys():
        entry["father_path"] = str(row["father_path"] or "").strip()
    return entry
    return entry
def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _resolve_family_bundle_entry(
    *,
    family_registry: Mapping[str, object] | None,
    prompt_family_id: str | None,
) -> dict[str, object] | None:
    """Return the matched family entry from the bundle registry."""

    if not isinstance(family_registry, Mapping) or not prompt_family_id:
        return None
    raw_families = family_registry.get("families")
    if not isinstance(raw_families, list):
        return None
    for family in raw_families:
        if not isinstance(family, Mapping):
            continue
        family_id = str(family.get("prompt_family_id") or "").strip()
        if family_id == prompt_family_id:
            return {str(key): value for key, value in family.items()}
    return None


def _heuristic_sources(root: Path) -> list[Path]:
    candidates = [
        root / "README.md",
        root / "AGENTS.md",
        root / "pyproject.toml",
        root / "package.json",
        root / "Cargo.toml",
    ]
    if (root / "src").is_dir():
        for path in sorted((root / "src").rglob("*")):
            if path.is_file():
                candidates.append(path)
                if len(candidates) >= _DEFAULT_PREVIEW_COUNT + 5:
                    break
    return [path for path in candidates if path.is_file()]


def _build_heuristic_previews(root: Path) -> list[dict[str, str]]:
    previews: list[dict[str, str]] = []
    for path in _heuristic_sources(root)[:_DEFAULT_PREVIEW_COUNT]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        previews.append(
            {
                "source": path.relative_to(root).as_posix(),
                "text": _truncate_text(text),
            }
        )
    return previews


def _resolve_program_path_and_bundle_version(
    *,
    repository_root: Path,
    bundle_root: Path,
    bundle_version: str | None,
    bundle_channel: str,
) -> tuple[Path | None, str | None]:
    if bundle_version is not None:
        try:
            _, local_bundle = resolve_bundle_manifest(
                bundle_root,
                bundle_version=bundle_version,
            )
        except ValueError:
            local_bundle = None
        local_program_path_text = (
            local_bundle.get("program_path") if isinstance(local_bundle, dict) else None
        )
        if isinstance(local_program_path_text, str) and local_program_path_text.strip():
            local_program_path = (bundle_root / local_program_path_text).resolve()
            if local_program_path.is_file():
                return local_program_path, bundle_version
        for candidate in _staged_bundle_program_candidates(
            bundle_root=bundle_root,
            bundle_version=bundle_version,
        ):
            if candidate.is_file():
                return candidate.resolve(), bundle_version
    else:
        remote_channel_state = inspect_remote_bundle_channel(bundle_channel)
        if remote_channel_state is not None:
            resolved_bundle_version = (
                str(remote_channel_state.get("current_bundle_version") or "").strip() or None
            )
            if resolved_bundle_version is None:
                return None, None
            for candidate in _staged_bundle_program_candidates(
                bundle_root=bundle_root,
                bundle_version=resolved_bundle_version,
            ):
                if candidate.is_file():
                    return candidate.resolve(), resolved_bundle_version
            try:
                remote_bundle = fetch_remote_bundle(
                    bundle_root,
                    bundle_version=resolved_bundle_version,
                    channel=None,
                    download_family_artifacts=False,
                )
            except Exception:
                remote_bundle = None
            remote_program_path_text = (
                remote_bundle.get("program_path") if isinstance(remote_bundle, dict) else None
            )
            if isinstance(remote_program_path_text, str) and remote_program_path_text.strip():
                remote_program_path = (bundle_root / remote_program_path_text).resolve()
                if remote_program_path.is_file():
                    return remote_program_path, resolved_bundle_version
            return None, resolved_bundle_version
        channel_state = inspect_bundle_channel(bundle_root, channel=bundle_channel)
        resolved_bundle_version = (
            str(channel_state.get("current_bundle_version") or "").strip() or None
        )
        local_program_path_text = (
            channel_state.get("current_program_path")
            if channel_state.get("channel_found")
            else None
        )
        if isinstance(local_program_path_text, str) and local_program_path_text.strip():
            local_program_path = (bundle_root / local_program_path_text).resolve()
            if local_program_path.is_file():
                return local_program_path, resolved_bundle_version
        for candidate in _staged_bundle_program_candidates(
            bundle_root=bundle_root,
            bundle_version=resolved_bundle_version,
        ):
            if candidate.is_file():
                return candidate.resolve(), resolved_bundle_version
        if resolved_bundle_version is None:
            for staged_bundle_version in _available_staged_bundle_versions(bundle_root):
                for candidate in _staged_bundle_program_candidates(
                    bundle_root=bundle_root,
                    bundle_version=staged_bundle_version,
                ):
                    if candidate.is_file():
                        return candidate.resolve(), staged_bundle_version
    try:
        remote_bundle = fetch_remote_bundle(
            bundle_root,
            bundle_version=bundle_version,
            channel=None if bundle_version else bundle_channel,
            download_family_artifacts=False,
        )
    except Exception:
        remote_bundle = None
    if isinstance(remote_bundle, dict):
        program_path_text = remote_bundle.get("program_path")
        if isinstance(program_path_text, str) and program_path_text.strip():
            program_path = (bundle_root / program_path_text).resolve()
            if program_path.is_file():
                resolved_version = (
                    str(remote_bundle.get("bundle_version") or bundle_version or "").strip() or None
                )
                return program_path, resolved_version
    runner = RepositoryRAG(repository_root, top_k=4)
    runner_program_path: Path | None = runner.program_path
    if runner_program_path is None:
        return None, None
    return runner_program_path, resolve_bundle_version_for_program(bundle_root, runner_program_path)


def build_codex_mediation(
    question: str,
    *,
    command_trace: Sequence[Mapping[str, object]] = (),
    repository_root: Path,
    bundle_root: Path,
    prefer_dspy: bool = True,
    dspy_top_k: int = 4,
    bundle_channel: str = "stable",
    bundle_version: str | None = None,
    token_budget: int = _DEFAULT_TOKEN_BUDGET,
    trivial_token_budget: int = _DEFAULT_TRIVIAL_TOKEN_BUDGET,
    essentials_count: int = _DEFAULT_ESSENTIAL_COUNT,
    low_signal_min_sources: int = 1,
    family_exploration_rate: float = _DEFAULT_FAMILY_EXPLORATION_RATE,
    retrieval_mode: RetrievalMode | None = None,
) -> CodexMediationResult:
    """Build one combined repo-grounded mediation block for Codex."""

    resolved_root = repository_root.resolve()
    original_prompt = " ".join(question.split()).strip()
    task_classification = _classify_task(original_prompt)
    effective_budget = (
        max(120, trivial_token_budget)
        if task_classification == "trivial"
        else max(240, token_budget)
    )
    effective_essentials = 1 if task_classification == "trivial" else max(1, essentials_count)

    warnings: list[str] = []
    resolved_bundle_root = bundle_root.resolve()
    lm_config = resolve_dspy_lm_config() if prefer_dspy else None
    reformulated_prompt, reformulation_status = reformulate_codex_prompt(
        original_prompt,
        lm_config=lm_config,
    )
    active_prompt = reformulated_prompt or original_prompt
    family_lookup_prompt = original_prompt or active_prompt
    family_state_path: Path | None = None
    family_state_checked = False

    def _get_family_state_path() -> Path | None:
        nonlocal family_state_checked, family_state_path
        if not family_state_checked:
            family_state_path = _resolve_family_state_path(resolved_root, resolved_bundle_root)
            family_state_checked = True
        return family_state_path

    resolved_bundle_version: str | None = _resolve_bundle_version_hint(
        bundle_root=resolved_bundle_root,
        bundle_version=bundle_version,
        bundle_channel=bundle_channel,
    )
    bundle_routing_index_path = _resolve_bundle_routing_index_path(
        bundle_root=resolved_bundle_root,
        bundle_version=resolved_bundle_version,
        bundle_channel=bundle_channel,
    )
    family_registry: Mapping[str, object] | None = None
    family_entry: dict[str, object] | None = None
    prompt_family_id: str | None = None
    prompt_family_similarity = 0.0
    prompt_family_band = "new"
    family_runtime_hit_rate: float | None = None
    family_artifact_hit_rate: float | None = None
    family_predicted_hit_rate: float | None = None
    family_predicted_hit_rate_lower_bound: float | None = None
    family_prediction_uncertainty: float | None = None
    family_feedback_count: int | None = None
    family_artifact_selected: bool | None = None
    family_exploration_selected = False
    supported_family = False
    if bundle_routing_index_path is not None:
        support = resolve_prompt_family_support(family_lookup_prompt, bundle_routing_index_path)
        prompt_family_id = support.prompt_family_id
        prompt_family_similarity = support.similarity
        prompt_family_band = support.band
        supported_family = support.supported
        family_entry = _resolve_family_entry_from_routing_index(
            routing_index_path=bundle_routing_index_path,
            prompt_family_id=prompt_family_id,
        )
    else:
        family_registry = _resolve_bundle_family_registry(
            bundle_root=resolved_bundle_root,
            bundle_version=bundle_version,
            bundle_channel=bundle_channel,
        )
        if isinstance(family_registry, Mapping):
            support = resolve_prompt_family_support_from_payload(
                family_lookup_prompt,
                {"prompt_families": family_registry.get("families", [])},
            )
            prompt_family_id = support.prompt_family_id
            prompt_family_similarity = support.similarity
            prompt_family_band = support.band
            supported_family = support.supported
        else:
            family_state_path = _get_family_state_path()
            if family_state_path is not None:
                synthesized_family_registry = _build_family_registry_from_state_path(
                    repository_root=resolved_root,
                    family_state_path=family_state_path,
                )
                if isinstance(synthesized_family_registry, Mapping):
                    family_registry = synthesized_family_registry
                    support = resolve_prompt_family_support_from_payload(
                        family_lookup_prompt,
                        {"prompt_families": family_registry.get("families", [])},
                    )
                else:
                    support = resolve_prompt_family_support(family_lookup_prompt, family_state_path)
                prompt_family_id = support.prompt_family_id
                prompt_family_similarity = support.similarity
                prompt_family_band = support.band
                supported_family = support.supported
            else:
                warnings.append(
                    "Family state index was unavailable; request will pass through unchanged."
                )
    if prefer_dspy and supported_family and prompt_family_id is not None:
        family_state_path = _get_family_state_path()
        resolved_family_program_path = _resolve_family_runtime_program_path(
            repository_root=resolved_root,
            bundle_root=resolved_bundle_root,
            family_registry=family_registry,
            prompt_family_id=prompt_family_id,
            bundle_version=resolved_bundle_version,
        )
        if resolved_family_program_path is None and family_state_path is not None:
            synthesized_family_registry = _build_family_registry_from_state_path(
                repository_root=resolved_root,
                family_state_path=family_state_path,
            )
            if isinstance(synthesized_family_registry, Mapping):
                synthesized_support = resolve_prompt_family_support_from_payload(
                    family_lookup_prompt,
                    {"prompt_families": synthesized_family_registry.get("families", [])},
                )
                synthesized_family_program_path = _resolve_family_runtime_program_path(
                    repository_root=resolved_root,
                    bundle_root=resolved_bundle_root,
                    family_registry=synthesized_family_registry,
                    prompt_family_id=synthesized_support.prompt_family_id,
                    bundle_version=resolved_bundle_version,
                )
                if synthesized_support.supported and synthesized_family_program_path is not None:
                    family_registry = synthesized_family_registry
                    prompt_family_id = synthesized_support.prompt_family_id
                    prompt_family_similarity = synthesized_support.similarity
                    prompt_family_band = synthesized_support.band
                    supported_family = True
    if family_entry is None:
        family_entry = _resolve_family_bundle_entry(
            family_registry=family_registry,
            prompt_family_id=prompt_family_id,
        )
    if isinstance(family_entry, Mapping):
        runtime_metric = family_entry.get("family_runtime_metric")
        if isinstance(runtime_metric, Mapping):
            family_runtime_hit_rate = _float_or_none(runtime_metric.get("hit_rate"))
        feedback_metric = family_entry.get("family_feedback_metric")
        if family_runtime_hit_rate is None and isinstance(feedback_metric, Mapping):
            family_runtime_hit_rate = _float_or_none(feedback_metric.get("hit_rate"))
        if family_runtime_hit_rate is None:
            family_runtime_hit_rate = _float_or_none(family_entry.get("family_metric_1_mean"))
        family_artifact_hit_rate = _float_or_none(family_entry.get("family_runtime_score"))
        runtime_artifact = family_entry.get("runtime_artifact")
        if isinstance(runtime_artifact, Mapping):
            if family_artifact_hit_rate is None:
                family_artifact_hit_rate = _float_or_none(runtime_artifact.get("hit_rate"))
            family_predicted_hit_rate = _float_or_none(
                runtime_artifact.get("predicted_hit_rate")
            )
            family_predicted_hit_rate_lower_bound = _float_or_none(
                runtime_artifact.get("predicted_hit_rate_lower_bound")
            )
            family_prediction_uncertainty = _float_or_none(
                runtime_artifact.get("prediction_uncertainty")
            )
            feedback_count = runtime_artifact.get("feedback_count")
            if isinstance(feedback_count, int) and not isinstance(feedback_count, bool):
                family_feedback_count = feedback_count
        success_metric = family_entry.get("family_success_metric")
        if isinstance(success_metric, Mapping):
            if family_predicted_hit_rate is None:
                family_predicted_hit_rate = _float_or_none(success_metric.get("posterior_mean"))
            if family_predicted_hit_rate_lower_bound is None:
                family_predicted_hit_rate_lower_bound = _float_or_none(
                    success_metric.get("lower_bound")
                )
            if family_prediction_uncertainty is None:
                family_prediction_uncertainty = _float_or_none(
                    success_metric.get("uncertainty")
                )
        if family_feedback_count is None:
            feedback_count = family_entry.get("family_feedback_count")
            if isinstance(feedback_count, int) and not isinstance(feedback_count, bool):
                family_feedback_count = feedback_count

    if not supported_family:
        warnings.append(
            "No father-backed prompt-family support was found for the original prompt; "
            "the request will pass through unchanged."
        )
        return CodexMediationResult(
            question=active_prompt,
            original_prompt=original_prompt,
            reformulated_prompt=active_prompt,
            reformulation_status=reformulation_status,
            mediation_mode="passthrough",
            rag_status="skipped",
            dspy_status="skipped",
            dspy_lm_model=str(getattr(lm_config, "model", "") or "").strip() or None,
            summary=(
                "No father-backed prompt-family support was found for the original prompt, so "
                "the proxy did not inject DSPy mediation for this turn."
            ),
            retrieval_mode=str(retrieval_mode or "lexical"),
            sources=[],
            warnings=warnings,
            bundle_version=resolved_bundle_version,
            program_path=None,
            evidence_previews=[],
            developer_message="",
            prompt_family_id=prompt_family_id,
            prompt_family_similarity=prompt_family_similarity,
            prompt_family_band=prompt_family_band,
            family_runtime_hit_rate=family_runtime_hit_rate,
            family_artifact_hit_rate=family_artifact_hit_rate,
            family_predicted_hit_rate=family_predicted_hit_rate,
            family_predicted_hit_rate_lower_bound=family_predicted_hit_rate_lower_bound,
            family_prediction_uncertainty=family_prediction_uncertainty,
            family_feedback_count=family_feedback_count,
            family_artifact_selected=family_artifact_selected,
            family_exploration_selected=family_exploration_selected,
            task_classification=task_classification,
            budget_tokens=effective_budget,
            estimated_tokens=0,
            injected=False,
        )

    rag_answer = ask_repository(
        question=active_prompt,
        root=resolved_root,
        retrieval_mode=retrieval_mode,
    )
    warnings.extend(getattr(rag_answer, "retrieval_warnings", ()) or ())
    effective_retrieval_mode = str(getattr(rag_answer, "retrieval_mode", "lexical") or "lexical")
    previews: list[dict[str, str]] = []
    sources: list[str] = []
    if rag_answer.context:
        previews = _dedupe_previews(
            [
                {
                    "source": chunk.source.relative_to(resolved_root).as_posix()
                    if chunk.source.is_relative_to(resolved_root)
                    else chunk.source.as_posix(),
                    "text": _truncate_text(chunk.text),
                }
                for chunk in rag_answer.context[:_DEFAULT_PREVIEW_COUNT]
            ]
        )
        sources = [item["source"] for item in previews]
        rag_status = "success"
        rag_summary = rag_answer.summary.strip()
    else:
        previews = _build_heuristic_previews(resolved_root)
        sources = [item["source"] for item in previews]
        rag_status = "heuristic" if previews else "failed"
        rag_summary = (
            f"No lexical repo-RAG evidence matched the task {active_prompt!r}; "
            "fall back to the heuristic file shortlist."
        )
        if rag_status == "heuristic":
            warnings.append("Repo-RAG retrieval returned no chunks; using heuristic file previews.")
        else:
            warnings.append(
                "Repo-RAG retrieval returned no chunks and no heuristic previews were available."
            )

    dspy_status = "disabled"
    dspy_lm_model = str(getattr(lm_config, "model", "") or "").strip() or None
    summary = rag_summary
    program_path_text: str | None = None
    if prefer_dspy:
        try:
            if lm_config is None:
                raise RuntimeError("DSPy LM configuration is unavailable.")
            use_family_artifact = True
            baseline_hit_rate = (
                family_predicted_hit_rate_lower_bound
                if family_predicted_hit_rate_lower_bound is not None
                else family_predicted_hit_rate
                if family_predicted_hit_rate is not None
                else family_runtime_hit_rate
            )
            if (
                family_artifact_hit_rate is not None
                and baseline_hit_rate is not None
                and family_artifact_hit_rate < baseline_hit_rate
            ):
                use_family_artifact = False
                warnings.append(
                    "Matched family runtime artifact scored below the current family success "
                    "baseline, so the proxy fell back to fresh/global mediation for this turn."
                )
            normalized_exploration_rate = _clamp_probability(family_exploration_rate)
            if use_family_artifact and normalized_exploration_rate > 0.0:
                exploration_roll = _stable_fraction(
                    original_prompt,
                    active_prompt,
                    prompt_family_id,
                    resolved_bundle_version or bundle_version or "",
                )
                if exploration_roll < normalized_exploration_rate:
                    use_family_artifact = False
                    family_exploration_selected = True
                    warnings.append(
                        "Matched family runtime artifact was deterministically bypassed for "
                        "controlled exploration, so the proxy used the fresh/global mediation "
                        "path for this turn."
                    )
            family_program_path = (
                _resolve_family_runtime_program_path(
                    repository_root=resolved_root,
                    bundle_root=resolved_bundle_root,
                    family_registry=family_registry,
                    prompt_family_id=prompt_family_id,
                    bundle_version=resolved_bundle_version,
                )
                if use_family_artifact
                else None
            )
            global_program_path, resolved_bundle_version = _resolve_program_path_and_bundle_version(
                repository_root=resolved_root,
                bundle_root=resolved_bundle_root,
                bundle_version=bundle_version,
                bundle_channel=bundle_channel,
            )
            program_path = family_program_path or global_program_path
            family_artifact_selected = family_program_path is not None
            if program_path is None:
                raise FileNotFoundError("No compiled DSPy bundle is available.")
            if (
                family_program_path is None
                and use_family_artifact
                and isinstance(family_registry, Mapping)
            ):
                warnings.append(
                    "Family match resolved, but no ready family runtime artifact was available; "
                    "falling back to the global compiled program."
                )
            runner = RepositoryRAG(
                root=resolved_root,
                top_k=dspy_top_k,
                program_path=program_path,
                lm_config=lm_config,
                require_configured_lm=True,
                retrieval_mode=retrieval_mode,
            )
            runtime_question = original_prompt or active_prompt
            dspy_result = runner(
                runtime_question,
                original_prompt=original_prompt or None,
                reformulated_prompt=active_prompt or None,
                command_trace=command_trace,
            )
            if not dspy_result.answer.strip():
                raise RuntimeError("DSPy produced an empty answer.")
            dspy_status = "success"
            summary = dspy_result.answer.strip()
            effective_retrieval_mode = str(
                getattr(dspy_result, "retrieval_mode", effective_retrieval_mode)
                or effective_retrieval_mode
            )
            if program_path.is_relative_to(resolved_bundle_root):
                program_path_text = program_path.relative_to(resolved_bundle_root).as_posix()
            elif program_path.is_relative_to(resolved_root):
                program_path_text = program_path.relative_to(resolved_root).as_posix()
            else:
                program_path_text = str(program_path)
        except Exception as exc:
            dspy_status = "heuristic"
            warnings.append(
                f"DSPy mediation was unavailable; using heuristic synthesis instead. ({exc})"
            )

    mediation_mode = "dspy_rag"
    if dspy_status != "success" and rag_status != "success":
        mediation_mode = "heuristic"
    elif dspy_status != "success":
        mediation_mode = "rag_heuristic_dspy"
    elif rag_status != "success":
        mediation_mode = "heuristic_rag_dspy"

    low_signal = (
        len(sources) < max(0, low_signal_min_sources)
        and dspy_status != "success"
        and rag_status != "success"
    ) or (
        len(sources) < max(0, low_signal_min_sources)
        and dspy_status != "success"
        and (not summary.strip() or len(summary.strip()) < _LOW_SIGNAL_SUMMARY_LIMIT)
    )

    developer_message = ""
    estimated_tokens = 0
    injected = False
    if not low_signal:
        developer_message, estimated_tokens = _build_budgeted_message(
            reformulated_prompt=active_prompt,
            mediation_mode=mediation_mode,
            rag_status=rag_status,
            dspy_status=dspy_status,
            summary=summary,
            sources=sources,
            previews=previews,
            warnings=warnings,
            prompt_family_id=prompt_family_id,
            family_artifact_selected=family_artifact_selected,
            budget_tokens=effective_budget,
            essentials_count=effective_essentials,
        )
        injected = bool(developer_message)
    else:
        warnings.append(
            "Mediation block was suppressed because the repo-grounded signal was too weak."
        )

    return CodexMediationResult(
        question=active_prompt,
        original_prompt=original_prompt,
        reformulated_prompt=active_prompt,
        reformulation_status=reformulation_status,
        mediation_mode=mediation_mode,
        rag_status=rag_status,
        dspy_status=dspy_status,
        dspy_lm_model=dspy_lm_model,
        summary=summary,
        retrieval_mode=effective_retrieval_mode,
        sources=sources[: max(1, effective_essentials + 1)],
        warnings=warnings,
        bundle_version=resolved_bundle_version,
        program_path=program_path_text,
        evidence_previews=previews[: max(1, effective_essentials)],
        developer_message=developer_message,
        prompt_family_id=prompt_family_id,
        prompt_family_similarity=prompt_family_similarity,
        prompt_family_band=prompt_family_band,
        family_runtime_hit_rate=family_runtime_hit_rate,
        family_artifact_hit_rate=family_artifact_hit_rate,
        family_predicted_hit_rate=family_predicted_hit_rate,
        family_predicted_hit_rate_lower_bound=family_predicted_hit_rate_lower_bound,
        family_prediction_uncertainty=family_prediction_uncertainty,
        family_feedback_count=family_feedback_count,
        family_artifact_selected=family_artifact_selected,
        family_exploration_selected=family_exploration_selected,
        task_classification=task_classification,
        budget_tokens=effective_budget,
        estimated_tokens=estimated_tokens,
        injected=injected,
    )


def augment_responses_payload(
    payload: Mapping[str, object],
    *,
    developer_message: str,
) -> dict[str, object]:
    """Inject one mediation developer-message into a Responses payload."""

    updated = dict(payload)
    if not developer_message.strip():
        return updated
    raw_input = updated.get("input")
    message_block = {
        "type": "message",
        "role": "developer",
        "content": [{"type": "input_text", "text": developer_message}],
    }
    if isinstance(raw_input, str):
        updated["input"] = [
            message_block,
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": raw_input}],
            },
        ]
        return updated
    if isinstance(raw_input, list):
        items = list(raw_input)
        insert_at = 0
        while insert_at < len(items):
            item = items[insert_at]
            if not isinstance(item, dict) or item.get("type") != "message":
                break
            if str(item.get("role") or "").strip().lower() != "developer":
                break
            insert_at += 1
        items.insert(insert_at, message_block)
        updated["input"] = items
        return updated
    instructions = str(updated.get("instructions") or "").strip()
    updated["instructions"] = (
        f"{instructions}\n\n{developer_message}".strip() if instructions else developer_message
    )
    return updated


class _CodexProxyHandler(BaseHTTPRequestHandler):
    """Handle one Codex responses request."""

    protocol_version = "HTTP/1.1"

    @property
    def runtime(self) -> _CodexProxyRuntime:
        return self.server.runtime  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        if self.path.rstrip("/") != "/healthz":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        payload = {
            "status": "ok",
            "repository_root": str(self.runtime.config.repository_root),
            "bundle_root": str(self.runtime.config.bundle_root),
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        runtime = self.runtime
        split = urlsplit(self.path)
        if split.path.rstrip("/") != "/openai/responses":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        request_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(request_body.decode("utf-8"))
        except Exception:
            payload = None

        outbound_payload_bytes = request_body
        if isinstance(payload, dict):
            turn_state = extract_codex_turn_state(payload)
            original_prompt = str(turn_state.get("original_prompt") or "").strip()
            command_trace_value = turn_state.get("command_trace")
            if isinstance(command_trace_value, list):
                command_trace = [step for step in command_trace_value if isinstance(step, Mapping)]
            else:
                command_trace = []
            if original_prompt:
                mediation = runtime.build_mediation(original_prompt, command_trace)
                runtime.persist_status(mediation, command_trace=command_trace)
                runtime.persist_turn_trace(mediation, command_trace=command_trace)
                if mediation.injected and mediation.developer_message.strip():
                    payload = augment_responses_payload(
                        payload,
                        developer_message=mediation.developer_message,
                    )
                    outbound_payload_bytes = json.dumps(payload).encode("utf-8")
            else:
                runtime.persist_raw_status(
                    {
                        "mediation_mode": "passthrough",
                        "warnings": ["Could not extract a user task from the Codex request."],
                    }
                )

        upstream_query = list(parse_qsl(split.query, keep_blank_values=True))
        if not any(name == "api-version" for name, _ in upstream_query):
            upstream_query.append(("api-version", runtime.api_version))
        upstream_url = urlunsplit(
            (
                runtime.upstream_scheme,
                runtime.upstream_netloc,
                "/openai/responses",
                urlencode(upstream_query),
                "",
            )
        )
        headers = {
            "Authorization": f"Bearer {runtime.api_key}",
            "Accept": self.headers.get("Accept", "text/event-stream"),
            "Content-Type": "application/json",
        }
        try:
            with runtime.client.stream(
                "POST",
                upstream_url,
                headers=headers,
                content=outbound_payload_bytes,
            ) as response:
                self.send_response(response.status_code)
                self.send_header(
                    "Content-Type",
                    response.headers.get("content-type", "text/event-stream"),
                )
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                for chunk in response.iter_bytes():
                    if not chunk:
                        continue
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except Exception as exc:
            body = json.dumps({"error": {"message": str(exc)}}).encode("utf-8")
            self.send_response(HTTPStatus.BAD_GATEWAY)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


class _CodexProxyRuntime:
    """Mutable proxy runtime shared by one server instance."""

    def __init__(self, config: CodexProxyConfig) -> None:
        self.config = config
        self.status_path = config.artifact_dir / config.status_filename
        self.config.artifact_dir.mkdir(parents=True, exist_ok=True)
        runtime = resolve_azure_openai_runtime(dict(os.environ))
        split = urlsplit(runtime.endpoint)
        self.upstream_scheme = split.scheme
        self.upstream_netloc = split.netloc
        self.api_key = runtime.api_key
        self.api_version = runtime.api_version
        self.client = httpx.Client(timeout=None)
        self._mediation_cache: dict[str, CodexMediationResult] = {}
        self.turn_trace_batch_name = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        self.turn_trace_dir = (
            self.config.artifact_dir / "repo_rag_turn_traces" / self.turn_trace_batch_name
        )
        self.turn_trace_dir.mkdir(parents=True, exist_ok=True)
        self.turn_trace_manifest_path = self.turn_trace_dir / "manifest.json"
        self._turn_trace_entries: list[str] = []
        self._persisted_trace_keys: set[str] = set()
        self.cache_dir = (
            config.cache_dir.resolve()
            if config.cache_dir is not None
            else (config.artifact_dir.parent / ".repo_rag_cache").resolve()
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl_seconds = max(0, int(config.cache_ttl_seconds))
        self.corpus_manifest_path = self.cache_dir / "retrieval-corpus-manifest.json"
        self.corpus_manifest = build_corpus_manifest(self.config.repository_root)
        write_corpus_manifest(self.corpus_manifest_path, self.corpus_manifest)
        self.corpus_fingerprint = str(self.corpus_manifest.get("corpus_fingerprint") or "").strip()
        self.retrieval_profile_fingerprint = self._compute_retrieval_profile_fingerprint()

    def _compute_retrieval_profile_fingerprint(self) -> str:
        profile_path = self.config.repository_root / "config" / "retrieval-profile.json"
        if not profile_path.is_file():
            return "default-profile"
        try:
            return hashlib.sha256(profile_path.read_bytes()).hexdigest()
        except OSError:
            return "unreadable-profile"

    @property
    def turn_trace_entries(self) -> list[str]:
        """Return one defensive copy of the persisted turn-trace entry list."""

        return list(self._turn_trace_entries)

    def _cache_key(self, original_prompt: str, command_trace: list[Mapping[str, str]]) -> str:
        command_trace_token = json.dumps(
            command_trace,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        identity = "|".join(
            [
                str(self.config.repository_root),
                str(self.config.bundle_root),
                str(self.config.bundle_version or ""),
                str(self.config.bundle_channel),
                str(self.config.prefer_dspy),
                str(self.config.dspy_top_k),
                str(self.config.retrieval_mode or ""),
                str(self.config.token_budget),
                str(self.config.trivial_token_budget),
                self.corpus_fingerprint,
                self.retrieval_profile_fingerprint,
                original_prompt.strip(),
                command_trace_token,
            ]
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def _cache_path_for_key(self, cache_key: str) -> Path:
        return self.cache_dir / f"{cache_key}.json"

    def _load_cached_mediation(
        self,
        original_prompt: str,
        command_trace: list[Mapping[str, str]],
    ) -> CodexMediationResult | None:
        cache_path = self._cache_path_for_key(self._cache_key(original_prompt, command_trace))
        if not cache_path.is_file():
            return None
        if self.cache_ttl_seconds > 0:
            age_seconds = max(0.0, time.time() - cache_path.stat().st_mtime)
            if age_seconds > self.cache_ttl_seconds:
                return None
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        cached = _result_from_payload(payload.get("result", payload))
        if cached is None:
            return None
        return CodexMediationResult(
            question=cached.question,
            original_prompt=cached.original_prompt,
            reformulated_prompt=cached.reformulated_prompt,
            reformulation_status=cached.reformulation_status,
            mediation_mode=cached.mediation_mode,
            rag_status=cached.rag_status,
            dspy_status=cached.dspy_status,
            dspy_lm_model=cached.dspy_lm_model,
            summary=cached.summary,
            retrieval_mode=cached.retrieval_mode,
            sources=cached.sources,
            warnings=cached.warnings,
            bundle_version=cached.bundle_version,
            program_path=cached.program_path,
            evidence_previews=cached.evidence_previews,
            developer_message=cached.developer_message,
            prompt_family_id=cached.prompt_family_id,
            prompt_family_similarity=cached.prompt_family_similarity,
            prompt_family_band=cached.prompt_family_band,
            family_runtime_hit_rate=cached.family_runtime_hit_rate,
            family_artifact_hit_rate=cached.family_artifact_hit_rate,
            family_artifact_selected=cached.family_artifact_selected,
            task_classification=cached.task_classification,
            budget_tokens=cached.budget_tokens,
            estimated_tokens=cached.estimated_tokens,
            injected=cached.injected,
            cache_hit=True,
        )

    def _store_cached_mediation(
        self,
        original_prompt: str,
        command_trace: list[Mapping[str, str]],
        mediation: CodexMediationResult,
    ) -> None:
        cache_path = self._cache_path_for_key(self._cache_key(original_prompt, command_trace))
        temp_path = cache_path.with_suffix(".json.tmp")
        payload = {
            "schema_version": 1,
            "cached_at": int(time.time()),
            "result": mediation.to_payload(),
        }
        temp_path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")
        temp_path.replace(cache_path)

    def build_mediation(
        self,
        original_prompt: str,
        command_trace: list[Mapping[str, str]],
    ) -> CodexMediationResult:
        cache_key = self._cache_key(original_prompt, command_trace)
        cached = self._mediation_cache.get(cache_key)
        if cached is not None:
            return cached
        cached_disk = self._load_cached_mediation(original_prompt, command_trace)
        if cached_disk is not None:
            self._mediation_cache[cache_key] = cached_disk
            return cached_disk
        mediation = build_codex_mediation(
            original_prompt,
            command_trace=command_trace,
            repository_root=self.config.repository_root,
            bundle_root=self.config.bundle_root,
            prefer_dspy=self.config.prefer_dspy,
            dspy_top_k=self.config.dspy_top_k,
            bundle_channel=self.config.bundle_channel,
            bundle_version=self.config.bundle_version,
            token_budget=self.config.token_budget,
            trivial_token_budget=self.config.trivial_token_budget,
            essentials_count=self.config.essentials_count,
            low_signal_min_sources=self.config.low_signal_min_sources,
            family_exploration_rate=self.config.family_exploration_rate,
            retrieval_mode=self.config.retrieval_mode,
        )
        self._mediation_cache[cache_key] = mediation
        self._store_cached_mediation(original_prompt, command_trace, mediation)
        return mediation

    def _turn_trace_dedupe_key(self, mediation: CodexMediationResult) -> str:
        """Return one stable per-rollout key for same-prompt trace suppression."""

        identity = [
            mediation.original_prompt.strip(),
            mediation.reformulated_prompt.strip(),
            str(mediation.prompt_family_id or ""),
            mediation.prompt_family_band,
            mediation.dspy_status,
            str(bool(mediation.family_artifact_selected)),
            str(mediation.bundle_version or ""),
            str(mediation.program_path or ""),
        ]
        return hashlib.sha256(
            json.dumps(
                identity,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def _should_persist_turn_trace(self, mediation: CodexMediationResult) -> bool:
        """Return whether this mediation should become a trainer-facing trace."""

        dedupe_key = self._turn_trace_dedupe_key(mediation)
        if dedupe_key in self._persisted_trace_keys:
            return False
        self._persisted_trace_keys.add(dedupe_key)
        return True

    def _rewrite_turn_trace_manifest(self) -> None:
        """Persist the current local turn-trace manifest after one mutation."""

        if not self._turn_trace_entries:
            if self.turn_trace_manifest_path.exists():
                self.turn_trace_manifest_path.unlink()
            return
        manifest = {
            "schema_version": 1,
            "batch_kind": "repo-rag-codex-proxy-turn-trace-batch",
            "batch_name": self.turn_trace_batch_name,
            "trace_dir": self.turn_trace_dir.relative_to(self.config.artifact_dir).as_posix(),
            "trace_paths": list(self._turn_trace_entries),
        }
        self.turn_trace_manifest_path.write_text(
            f"{json.dumps(manifest, indent=2)}\n",
            encoding="utf-8",
        )

    def _persist_single_turn_trace(
        self,
        mediation: CodexMediationResult,
        *,
        command_trace: list[Mapping[str, str]],
        trace_role: str = "turn",
        trainer_signal_kind: str | None = None,
    ) -> Path | None:
        if not self._should_persist_turn_trace(mediation):
            return None
        metric_hits = 1 if mediation.dspy_status == "success" else 0
        metric_total = 1
        resolved_signal_kind = trainer_signal_kind or "full_trace"
        trainer_signal_reason = (
            "family-reuse"
            if resolved_signal_kind == "full_trace"
            and mediation.family_artifact_selected
            and mediation.dspy_status == "success"
            else "fresh-or-fallback"
        )
        trace_payload = {
            "command": "codex-proxy-turn-mediation",
            "command_status": "success",
            "answer": mediation.summary,
            "context": [],
            "retrieved_context": [
                {
                    "source": preview.get("source"),
                    "preview": preview.get("text"),
                    "text": preview.get("text"),
                }
                for preview in mediation.evidence_previews
            ],
            "trace_role": trace_role,
            "trace": build_runtime_trace(
                RuntimeTraceContext(
                    question=mediation.reformulated_prompt or mediation.question,
                    mode="codex-proxy-turn-mediation",
                    retrieval_mode=mediation.retrieval_mode,
                    sources=mediation.sources,
                    context_count=len(mediation.evidence_previews),
                    top_k=self.config.dspy_top_k,
                    provider="codex-proxy",
                    program_loaded=mediation.dspy_status == "success",
                    program_path=mediation.program_path,
                    bundle_version=mediation.bundle_version,
                    overlay_path=None,
                    mcp_candidate_count=0,
                    answer_length=len(mediation.summary),
                    context_field="evidence_previews",
                    evidence_items=mediation.evidence_previews,
                    command_trace=command_trace,
                    original_prompt=mediation.original_prompt,
                    reformulated_prompt=mediation.reformulated_prompt,
                    prompt_family_id=mediation.prompt_family_id,
                    prompt_family_similarity=mediation.prompt_family_similarity,
                    prompt_family_band=mediation.prompt_family_band,
                    family_runtime_hit_rate=mediation.family_runtime_hit_rate,
                    family_artifact_hit_rate=mediation.family_artifact_hit_rate,
                    family_predicted_hit_rate=mediation.family_predicted_hit_rate,
                    family_predicted_hit_rate_lower_bound=(
                        mediation.family_predicted_hit_rate_lower_bound
                    ),
                    family_prediction_uncertainty=mediation.family_prediction_uncertainty,
                    family_feedback_count=mediation.family_feedback_count,
                    family_artifact_selected=mediation.family_artifact_selected,
                    mediation_metric_hits=metric_hits,
                    mediation_metric_total=metric_total,
                    trainer_signal_kind=resolved_signal_kind,
                )
            ),
            "outcome": {
                "acceptance_status": "candidate",
                "accepted": None,
                "execution_status": "success",
                "method": "codex_proxy_mediation",
                "backend": "repo_rag_codex_proxy",
                "used_baseline_fallback": mediation.dspy_status != "success",
            },
            "mediation": mediation.to_payload(),
            "trainer_signal_reason": trainer_signal_reason,
        }
        trace_name = hashlib.sha256(
            json.dumps(
                [
                    trace_role,
                    mediation.original_prompt,
                    mediation.reformulated_prompt,
                    command_trace,
                    mediation.bundle_version,
                ],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]
        turn_index = len(self._turn_trace_entries)
        trace_path = self.turn_trace_dir / f"{turn_index}-{trace_name}.json"
        trace_path.write_text(f"{json.dumps(trace_payload, indent=2)}\n", encoding="utf-8")
        relative_path = trace_path.relative_to(self.config.artifact_dir).as_posix()
        if relative_path not in self._turn_trace_entries:
            self._turn_trace_entries.append(relative_path)
        self._rewrite_turn_trace_manifest()
        return trace_path

    def _lineage_prompts(
        self, mediation: CodexMediationResult, command_trace: list[Mapping[str, str]]
    ) -> list[tuple[str, str]]:
        """Return unique prompt-like lineage prompts derived from one turn."""

        lineage: list[tuple[str, str]] = []
        seen: set[str] = set()

        def _append(role: str, text: str) -> None:
            cleaned = " ".join(str(text or "").split()).strip()
            if not cleaned:
                return
            token = cleaned.casefold()
            if token in seen:
                return
            seen.add(token)
            lineage.append((role, cleaned))

        _append("original", mediation.original_prompt)
        if mediation.reformulated_prompt.strip() != mediation.original_prompt.strip():
            _append("reformulated", mediation.reformulated_prompt)
        for step in command_trace:
            role = str(step.get("role") or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue
            text = str(step.get("text") or "").strip()
            if _looks_like_prompt_text(text):
                _append("lineage", text)
        return lineage

    def persist_turn_trace(
        self,
        mediation: CodexMediationResult,
        *,
        command_trace: list[Mapping[str, str]],
    ) -> Path | None:
        primary_trace_path = self._persist_single_turn_trace(
            mediation,
            command_trace=command_trace,
            trace_role="turn",
            trainer_signal_kind="full_trace",
        )
        for trace_role, prompt_text in self._lineage_prompts(mediation, command_trace):
            if prompt_text == mediation.original_prompt.strip():
                continue
            lineage_mediation = self.build_mediation(prompt_text, [])
            self._persist_single_turn_trace(
                lineage_mediation,
                command_trace=[],
                trace_role=trace_role,
            )
        return primary_trace_path

    def persist_status(
        self,
        mediation: CodexMediationResult,
        *,
        command_trace: list[Mapping[str, str]] | None = None,
    ) -> None:
        payload = mediation.to_payload()
        if command_trace is not None:
            payload["command_trace"] = list(command_trace)
        self.persist_raw_status(payload)

    def persist_raw_status(self, payload: dict[str, object]) -> None:
        self.status_path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")

    def close(self) -> None:
        self.client.close()


CodexProxyRuntime = _CodexProxyRuntime


@contextmanager
def running_codex_proxy(config: CodexProxyConfig) -> Iterator[RunningCodexProxy]:
    """Run one local single-threaded HTTP server for Codex mediation."""

    runtime = _CodexProxyRuntime(config)
    server = HTTPServer((config.host, config.port), _CodexProxyHandler)
    server.runtime = runtime  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        host_text = host.decode("utf-8", errors="ignore") if isinstance(host, bytes) else str(host)
        yield RunningCodexProxy(
            server=server,
            thread=thread,
            base_url=f"http://{host_text}:{port}/openai",
            status_path=runtime.status_path,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        runtime.close()


def serve_codex_proxy(
    *,
    repository_root: Path,
    bundle_root: Path,
    artifact_dir: Path,
    host: str = "127.0.0.1",
    port: int = 0,
    prefer_dspy: bool = True,
    dspy_top_k: int = 4,
    bundle_channel: str = "stable",
    bundle_version: str | None = None,
    token_budget: int = _DEFAULT_TOKEN_BUDGET,
    trivial_token_budget: int = _DEFAULT_TRIVIAL_TOKEN_BUDGET,
    essentials_count: int = _DEFAULT_ESSENTIAL_COUNT,
    low_signal_min_sources: int = 1,
    family_exploration_rate: float = _DEFAULT_FAMILY_EXPLORATION_RATE,
    retrieval_mode: RetrievalMode | None = None,
    cache_dir: Path | None = None,
    cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
    ready_file: Path | None = None,
) -> int:
    """Serve the blocking Codex proxy process used by worker-side wrappers."""

    config = CodexProxyConfig(
        repository_root=repository_root.resolve(),
        bundle_root=bundle_root.resolve(),
        artifact_dir=artifact_dir.resolve(),
        host=host,
        port=port,
        prefer_dspy=prefer_dspy,
        dspy_top_k=dspy_top_k,
        bundle_channel=bundle_channel,
        bundle_version=bundle_version,
        token_budget=token_budget,
        trivial_token_budget=trivial_token_budget,
        essentials_count=essentials_count,
        low_signal_min_sources=low_signal_min_sources,
        family_exploration_rate=_clamp_probability(family_exploration_rate),
        retrieval_mode=retrieval_mode,
        cache_dir=cache_dir.resolve() if cache_dir is not None else None,
        cache_ttl_seconds=cache_ttl_seconds,
    )
    with running_codex_proxy(config) as running:
        if ready_file is not None:
            ready_file.parent.mkdir(parents=True, exist_ok=True)
            ready_file.write_text(
                json.dumps(
                    {
                        "base_url": running.base_url,
                        "status_path": str(running.status_path),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        try:
            running.thread.join()
        except KeyboardInterrupt:
            return 0
    return 0


__all__ = [
    "CodexMediationResult",
    "CodexProxyConfig",
    "RunningCodexProxy",
    "augment_responses_payload",
    "build_codex_mediation",
    "extract_codex_task_text",
    "extract_codex_turn_state",
    "running_codex_proxy",
    "serve_codex_proxy",
]
