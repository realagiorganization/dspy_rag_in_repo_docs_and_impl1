"""Azure OpenAI embedding-backed semantic retrieval helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from .azure_runtime import (
    embed_with_azure_openai,
    load_runtime_environment,
    resolve_azure_openai_embedding_runtime,
)

DEFAULT_SEMANTIC_INDEX_PATH = Path("artifacts/retrieval/semantic-index.json")
DEFAULT_EMBEDDING_BATCH_SIZE = 16
_INDEX_SCHEMA_VERSION = 1


def rank_semantic_chunks(
    question: str,
    *,
    root: Path,
    chunk_records: Sequence[tuple[str, str]],
    max_candidates: int | None = None,
) -> tuple[list[tuple[int, float]], list[str]]:
    """Return semantic rankings for ``chunk_records`` plus any fallback warnings."""

    if not chunk_records:
        return [], []

    env, _ = load_runtime_environment(root, load_env_file=False)
    try:
        runtime = resolve_azure_openai_embedding_runtime(env)
    except RuntimeError as exc:
        return [], [f"Semantic retrieval unavailable: {exc}"]

    try:
        document_vectors = _load_or_build_document_vectors(
            root=root,
            chunk_records=chunk_records,
            deployment_name=runtime.deployment_name,
            api_version=runtime.api_version,
        )
        query_vector = _normalize_vector(embed_with_azure_openai(runtime, inputs=[question])[0])
    except Exception as exc:
        return [], [f"Semantic retrieval failed: {exc}"]

    ranked = sorted(
        (
            (index, _cosine_similarity(query_vector, document_vector))
            for index, document_vector in enumerate(document_vectors)
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    if max_candidates is not None:
        ranked = ranked[: max(1, max_candidates)]
    return ranked, []


def _load_or_build_document_vectors(
    *,
    root: Path,
    chunk_records: Sequence[tuple[str, str]],
    deployment_name: str,
    api_version: str,
) -> list[list[float]]:
    index_path = root.resolve() / DEFAULT_SEMANTIC_INDEX_PATH
    existing_vectors = _load_existing_vectors(
        index_path=index_path,
        deployment_name=deployment_name,
        api_version=api_version,
    )
    current_records: list[dict[str, object]] = []
    document_vectors: list[list[float]] = []
    missing_inputs: list[str] = []
    missing_positions: list[int] = []

    for index, (source, text) in enumerate(chunk_records):
        text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        record_key = _record_key(source, text_sha256)
        vector = existing_vectors.get(record_key)
        current_record: dict[str, object] = {
            "source": source,
            "text_sha256": text_sha256,
            "vector": None,
        }
        current_records.append(current_record)
        if vector is None:
            missing_inputs.append(text)
            missing_positions.append(index)
            document_vectors.append([])
            continue
        current_record["vector"] = vector
        document_vectors.append(vector)

    if missing_inputs:
        env, _ = load_runtime_environment(root, load_env_file=False)
        runtime = resolve_azure_openai_embedding_runtime(env)
        embedded_vectors: list[list[float]] = []
        for start in range(0, len(missing_inputs), DEFAULT_EMBEDDING_BATCH_SIZE):
            batch = missing_inputs[start : start + DEFAULT_EMBEDDING_BATCH_SIZE]
            embedded_vectors.extend(embed_with_azure_openai(runtime, inputs=batch))
        for position, vector in zip(missing_positions, embedded_vectors, strict=True):
            normalized = _normalize_vector(vector)
            document_vectors[position] = normalized
            current_records[position]["vector"] = normalized
        _write_vector_index(
            index_path=index_path,
            deployment_name=deployment_name,
            api_version=api_version,
            records=current_records,
        )

    if any(not vector for vector in document_vectors):
        raise RuntimeError("Semantic retrieval index build left one or more chunk vectors empty.")
    return document_vectors


def _load_existing_vectors(
    *,
    index_path: Path,
    deployment_name: str,
    api_version: str,
) -> dict[str, list[float]]:
    if not index_path.is_file():
        return {}
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, Mapping):
        return {}
    if int(payload.get("schema_version", 0)) != _INDEX_SCHEMA_VERSION:
        return {}
    if str(payload.get("deployment_name") or "") != deployment_name:
        return {}
    if str(payload.get("api_version") or "") != api_version:
        return {}
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        return {}

    vectors: dict[str, list[float]] = {}
    for record in raw_records:
        if not isinstance(record, Mapping):
            continue
        source = str(record.get("source") or "").strip()
        text_sha256 = str(record.get("text_sha256") or "").strip()
        raw_vector = record.get("vector")
        if not source or not text_sha256 or not isinstance(raw_vector, list):
            continue
        try:
            vectors[_record_key(source, text_sha256)] = _normalize_vector(
                [float(value) for value in raw_vector]
            )
        except (TypeError, ValueError):
            continue
    return vectors


def _write_vector_index(
    *,
    index_path: Path,
    deployment_name: str,
    api_version: str,
    records: Sequence[Mapping[str, object]],
) -> None:
    serializable_records: list[dict[str, object]] = []
    for record in records:
        source = str(record.get("source") or "").strip()
        text_sha256 = str(record.get("text_sha256") or "").strip()
        raw_vector = record.get("vector")
        if not source or not text_sha256 or not isinstance(raw_vector, list):
            continue
        serializable_records.append(
            {
                "source": source,
                "text_sha256": text_sha256,
                "vector": [float(value) for value in raw_vector],
            }
        )
    payload = {
        "schema_version": _INDEX_SCHEMA_VERSION,
        "index_kind": "repo-rag-semantic-index",
        "deployment_name": deployment_name,
        "api_version": api_version,
        "record_count": len(serializable_records),
        "records": serializable_records,
    }
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")


def _record_key(source: str, text_sha256: str) -> str:
    return f"{source}\n{text_sha256}"


def _normalize_vector(vector: Sequence[float]) -> list[float]:
    magnitude = sum(value * value for value in vector) ** 0.5
    if magnitude <= 0:
        raise RuntimeError("Semantic retrieval received an empty embedding vector.")
    return [float(value) / magnitude for value in vector]


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise RuntimeError("Semantic retrieval vectors must share one common dimensionality.")
    return sum(
        left_value * right_value for left_value, right_value in zip(left, right, strict=True)
    )
