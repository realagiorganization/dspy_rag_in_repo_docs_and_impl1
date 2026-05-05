"""Local streaming proxy that injects repo-RAG + DSPy mediation for Codex."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from .azure_runtime import resolve_azure_openai_runtime
from .corpus import build_corpus_manifest, write_corpus_manifest
from .dspy_training import resolve_dspy_lm_config
from .dspy_workflow import RepositoryRAG
from .retrieval import RetrievalMode
from .runtime_artifacts import (
    fetch_remote_bundle,
    inspect_bundle_channel,
    resolve_bundle_manifest,
    resolve_bundle_version_for_program,
)
from .workflow import ask_repository

_DEFAULT_SNIPPET_LIMIT = 280
_DEFAULT_PREVIEW_COUNT = 4
_DEFAULT_ESSENTIAL_COUNT = 3
_DEFAULT_TOKEN_BUDGET = 700
_DEFAULT_TRIVIAL_TOKEN_BUDGET = 280
_DEFAULT_CACHE_TTL_SECONDS = 3600
_TASK_TOKEN_DEEP_THRESHOLD = 10
_LOW_SIGNAL_SUMMARY_LIMIT = 40
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
    mediation_mode: str
    rag_status: str
    dspy_status: str
    summary: str
    retrieval_mode: str
    sources: list[str]
    warnings: list[str]
    bundle_version: str | None
    program_path: str | None
    evidence_previews: list[dict[str, str]]
    developer_message: str
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
    retrieval_mode: RetrievalMode | None = None
    cache_dir: Path | None = None
    cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS


@dataclass(frozen=True)
class RunningCodexProxy:
    """One running local Codex proxy instance."""

    server: ThreadingHTTPServer
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
    if any(token in _REPO_GROUNDING_HINTS for token in tokens):
        return "deep"
    return "trivial"


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
    mediation_mode: str,
    rag_status: str,
    dspy_status: str,
    task_classification: str,
    summary: str,
    sources: list[str],
    previews: list[dict[str, str]],
    warnings: list[str],
    budget_tokens: int,
    essentials_count: int,
) -> tuple[str, int]:
    summary_limit = max(120, min(520, budget_tokens * 3))
    trimmed_summary = _truncate_text(summary, limit=summary_limit)
    trimmed_previews = _dedupe_previews(previews)[: max(1, essentials_count)]
    lines = [
        "Repo mediation active.",
        f"Mode: {mediation_mode}",
        f"Task class: {task_classification}",
        f"RAG: {rag_status}",
        f"DSPy: {dspy_status}",
        "",
        "Summary:",
        trimmed_summary,
    ]

    def _candidate_text(extra_lines: list[str]) -> str:
        return "\n".join(lines + extra_lines).strip()

    if sources:
        section = ["", "Inspect first:"]
        for source in sources[: max(1, essentials_count + 1)]:
            trial = [*section, f"- {source}"]
            if _estimate_token_count(_candidate_text(trial)) > budget_tokens:
                break
            section = trial
        if len(section) > 2:
            lines.extend(section)

    if trimmed_previews:
        section = ["", "Evidence:"]
        for preview in trimmed_previews:
            candidate_line = f"- {preview['source']}: {preview['text']}"
            trial = [*section, candidate_line]
            if _estimate_token_count(_candidate_text(trial)) > budget_tokens:
                break
            section = trial
        if len(section) > 2:
            lines.extend(section)

    if warnings:
        section = ["", "Notes:"]
        for warning in warnings[:2]:
            candidate_line = f"- {_truncate_text(warning, limit=160)}"
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
                f"Task class: {task_classification}",
                "",
                "Summary:",
                _truncate_text(trimmed_summary, limit=max(96, budget_tokens * 2)),
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
        return CodexMediationResult(
            question=str(payload.get("question") or ""),
            mediation_mode=str(payload.get("mediation_mode") or "heuristic"),
            rag_status=str(payload.get("rag_status") or "failed"),
            dspy_status=str(payload.get("dspy_status") or "disabled"),
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


def extract_codex_task_text(payload: Mapping[str, object]) -> str:
    """Extract the latest user-facing task text from one Responses payload."""

    raw_input = payload.get("input")
    if isinstance(raw_input, str):
        return raw_input.strip()
    if not isinstance(raw_input, list):
        return ""

    user_messages: list[str] = []
    fallback_messages: list[str] = []
    for item in raw_input:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if item.get("type") != "message":
            continue
        text = _extract_text_from_content(item.get("content"))
        if not text:
            continue
        if role == "user":
            user_messages.append(text)
        elif role in {"developer", "system", "assistant"}:
            fallback_messages.append(text)
    if user_messages:
        return user_messages[-1]
    if fallback_messages:
        return fallback_messages[-1]
    return ""


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
    remote_bundle = fetch_remote_bundle(
        bundle_root,
        bundle_version=bundle_version,
        channel=None if bundle_version else bundle_channel,
    )
    if isinstance(remote_bundle, dict):
        program_path_text = remote_bundle.get("program_path")
        if isinstance(program_path_text, str) and program_path_text.strip():
            program_path = (bundle_root / program_path_text).resolve()
            resolved_version = (
                str(remote_bundle.get("bundle_version") or bundle_version or "").strip() or None
            )
            return program_path, resolved_version
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
    else:
        channel_state = inspect_bundle_channel(bundle_root, channel=bundle_channel)
        local_program_path_text = (
            channel_state.get("current_program_path")
            if channel_state.get("channel_found")
            else None
        )
        if isinstance(local_program_path_text, str) and local_program_path_text.strip():
            local_program_path = (bundle_root / local_program_path_text).resolve()
            if local_program_path.is_file():
                resolved_version = (
                    str(channel_state.get("current_bundle_version") or "").strip() or None
                )
                return local_program_path, resolved_version
    runner = RepositoryRAG(repository_root, top_k=4)
    runner_program_path: Path | None = runner.program_path
    if runner_program_path is None:
        return None, None
    return runner_program_path, resolve_bundle_version_for_program(bundle_root, runner_program_path)


def build_codex_mediation(
    question: str,
    *,
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
    retrieval_mode: RetrievalMode | None = None,
) -> CodexMediationResult:
    """Build one combined repo-grounded mediation block for Codex."""

    resolved_root = repository_root.resolve()
    task_classification = _classify_task(question)
    effective_budget = (
        max(120, trivial_token_budget)
        if task_classification == "trivial"
        else max(240, token_budget)
    )
    effective_essentials = 1 if task_classification == "trivial" else max(1, essentials_count)

    warnings: list[str] = []
    rag_answer = ask_repository(
        question=question,
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
            f"No lexical repo-RAG evidence matched the task {question!r}; "
            "fall back to the heuristic file shortlist."
        )
        if rag_status == "heuristic":
            warnings.append("Repo-RAG retrieval returned no chunks; using heuristic file previews.")
        else:
            warnings.append(
                "Repo-RAG retrieval returned no chunks and no heuristic previews were available."
            )

    dspy_status = "disabled"
    summary = rag_summary
    program_path_text: str | None = None
    resolved_bundle_version: str | None = bundle_version
    if prefer_dspy:
        try:
            lm_config = resolve_dspy_lm_config()
            if lm_config is None:
                raise RuntimeError("DSPy LM configuration is unavailable.")
            program_path, resolved_bundle_version = _resolve_program_path_and_bundle_version(
                repository_root=resolved_root,
                bundle_root=bundle_root.resolve(),
                bundle_version=bundle_version,
                bundle_channel=bundle_channel,
            )
            if program_path is None:
                raise FileNotFoundError("No compiled DSPy bundle is available.")
            runner = RepositoryRAG(
                root=resolved_root,
                top_k=dspy_top_k,
                program_path=program_path,
                lm_config=lm_config,
                require_configured_lm=True,
                retrieval_mode=retrieval_mode,
            )
            dspy_result = runner(question)
            if not dspy_result.answer.strip():
                raise RuntimeError("DSPy produced an empty answer.")
            dspy_status = "success"
            summary = dspy_result.answer.strip()
            effective_retrieval_mode = str(
                getattr(dspy_result, "retrieval_mode", effective_retrieval_mode)
                or effective_retrieval_mode
            )
            program_path_text = (
                program_path.relative_to(bundle_root.resolve()).as_posix()
                if program_path.is_relative_to(bundle_root.resolve())
                else str(program_path)
            )
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
            mediation_mode=mediation_mode,
            rag_status=rag_status,
            dspy_status=dspy_status,
            task_classification=task_classification,
            summary=summary,
            sources=sources,
            previews=previews,
            warnings=warnings,
            budget_tokens=effective_budget,
            essentials_count=effective_essentials,
        )
        injected = bool(developer_message)
    else:
        warnings.append(
            "Mediation block was suppressed because the repo-grounded signal was too weak."
        )

    return CodexMediationResult(
        question=question,
        mediation_mode=mediation_mode,
        rag_status=rag_status,
        dspy_status=dspy_status,
        summary=summary,
        retrieval_mode=effective_retrieval_mode,
        sources=sources[: max(1, effective_essentials + 1)],
        warnings=warnings,
        bundle_version=resolved_bundle_version,
        program_path=program_path_text,
        evidence_previews=previews[: max(1, effective_essentials)],
        developer_message=developer_message,
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
            task = extract_codex_task_text(payload)
            if task:
                mediation = runtime.build_mediation(task)
                runtime.persist_status(mediation)
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

    def _cache_key(self, task: str) -> str:
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
                task.strip(),
            ]
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def _cache_path_for_key(self, cache_key: str) -> Path:
        return self.cache_dir / f"{cache_key}.json"

    def _load_cached_mediation(self, task: str) -> CodexMediationResult | None:
        cache_path = self._cache_path_for_key(self._cache_key(task))
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
            mediation_mode=cached.mediation_mode,
            rag_status=cached.rag_status,
            dspy_status=cached.dspy_status,
            summary=cached.summary,
            retrieval_mode=cached.retrieval_mode,
            sources=cached.sources,
            warnings=cached.warnings,
            bundle_version=cached.bundle_version,
            program_path=cached.program_path,
            evidence_previews=cached.evidence_previews,
            developer_message=cached.developer_message,
            task_classification=cached.task_classification,
            budget_tokens=cached.budget_tokens,
            estimated_tokens=cached.estimated_tokens,
            injected=cached.injected,
            cache_hit=True,
        )

    def _store_cached_mediation(self, task: str, mediation: CodexMediationResult) -> None:
        cache_path = self._cache_path_for_key(self._cache_key(task))
        temp_path = cache_path.with_suffix(".json.tmp")
        payload = {
            "schema_version": 1,
            "cached_at": int(time.time()),
            "result": mediation.to_payload(),
        }
        temp_path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")
        temp_path.replace(cache_path)

    def build_mediation(self, task: str) -> CodexMediationResult:
        cached = self._mediation_cache.get(task)
        if cached is not None:
            return cached
        cached_disk = self._load_cached_mediation(task)
        if cached_disk is not None:
            self._mediation_cache[task] = cached_disk
            return cached_disk
        mediation = build_codex_mediation(
            task,
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
            retrieval_mode=self.config.retrieval_mode,
        )
        self._mediation_cache[task] = mediation
        self._store_cached_mediation(task, mediation)
        return mediation

    def persist_status(self, mediation: CodexMediationResult) -> None:
        self.persist_raw_status(mediation.to_payload())

    def persist_raw_status(self, payload: dict[str, object]) -> None:
        self.status_path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")

    def close(self) -> None:
        self.client.close()


@contextmanager
def running_codex_proxy(config: CodexProxyConfig) -> Iterator[RunningCodexProxy]:
    """Run one local ThreadingHTTPServer that mediates Codex responses requests."""

    runtime = _CodexProxyRuntime(config)
    server = ThreadingHTTPServer((config.host, config.port), _CodexProxyHandler)
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
    "running_codex_proxy",
    "serve_codex_proxy",
]
