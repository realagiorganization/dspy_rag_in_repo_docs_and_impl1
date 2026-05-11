from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, cast

import pytest

from repo_rag_lab.azure_artifacts import (
    AzureArtifactConfig,
    AzureArtifactStore,
    AzureQueueMessage,
    batched_trace_blob_name,
    bundle_blob_names,
    bundle_channel_blob_name,
    bundle_version_blob_prefix,
    decode_queue_message,
    failed_trace_blob_name,
    family_state_blob_names,
    family_state_current_blob_name,
    normalize_artifact_metadata_paths,
    processed_trace_blob_name,
    queued_trace_blob_name,
    repo_rag_bundle_container,
    repo_rag_family_state_container,
    repo_rag_trace_container,
    repo_rag_trace_queue_name,
)
from repo_rag_lab.runtime_artifacts import (
    drain_trace_queue,
    fetch_remote_bundle,
    fetch_remote_family_state,
    inspect_bundle_channel,
    inspect_pending_trainer_inputs,
    queue_trace_record,
    resolve_bundle_manifest,
    restore_processed_trace_records,
    upload_remote_bundle,
    upload_remote_family_state,
)


def _sample_trace_payload() -> dict[str, object]:
    return {
        "command": "ask",
        "command_status": "success",
        "root": "/tmp/target",
        "trace": {
            "schema_version": 1,
            "trace_kind": "repo-rag-runtime",
            "question": "How does the trainer ingest traces?",
            "mode": "baseline",
            "retrieval_mode": "idf-rerank",
            "sources": ["README.md"],
            "source_count": 1,
            "context_count": 1,
            "context_field": "context",
            "mcp_candidate_count": 0,
            "answer_length": 42,
            "bundle_version": "stable-42",
        },
    }


class _FakeAzureArtifactStore:
    def __init__(self) -> None:
        self.blobs: dict[tuple[str, str], str] = {}
        self.messages: list[AzureQueueMessage] = []
        self.deleted_messages: list[str] = []

    def upload_json(self, container_name: str, blob_name: str, payload: dict[str, object]) -> None:
        self.blobs[(container_name, blob_name)] = json.dumps(payload)

    def upload_text(self, container_name: str, blob_name: str, text: str) -> None:
        self.blobs[(container_name, blob_name)] = text

    def download_json(self, container_name: str, blob_name: str) -> dict[str, object]:
        return json.loads(self.blobs[(container_name, blob_name)])

    def download_text(self, container_name: str, blob_name: str) -> str:
        return self.blobs[(container_name, blob_name)]

    def send_queue_message(self, queue_name: str, payload: dict[str, object]) -> dict[str, object]:
        message = AzureQueueMessage(
            message_id=f"msg-{len(self.messages) + 1}",
            pop_receipt="receipt",
            content=json.dumps(payload),
            dequeue_count=1,
        )
        self.messages.append(message)
        return {"message_id": message.message_id}

    def receive_queue_messages(
        self,
        queue_name: str,
        *,
        limit: int | None = None,
        visibility_timeout: int = 30,
    ) -> list[AzureQueueMessage]:
        del queue_name, visibility_timeout
        if isinstance(limit, int) and limit > 0:
            return list(self.messages[:limit])
        return list(self.messages)

    def approximate_queue_message_count(self, queue_name: str) -> int:
        del queue_name
        return len(self.messages)

    def delete_queue_message(self, queue_name: str, message: AzureQueueMessage) -> None:
        del queue_name
        self.deleted_messages.append(message.message_id)
        self.messages = [
            candidate for candidate in self.messages if candidate.message_id != message.message_id
        ]

    def delete_blob(self, container_name: str, blob_name: str) -> None:
        self.blobs.pop((container_name, blob_name), None)

    def blob_exists(self, container_name: str, blob_name: str) -> bool:
        return (container_name, blob_name) in self.blobs

    def list_blobs(self, container_name: str, *, prefix: str) -> list[str]:
        return sorted(
            blob_name
            for (candidate_container, blob_name) in self.blobs
            if candidate_container == container_name and blob_name.startswith(prefix)
        )


class _FakeAzureExistsError(Exception):
    pass


class _FakeAzureNotFoundError(Exception):
    pass


@dataclass
class _FakeDownload:
    data: bytes

    def readall(self) -> bytes:
        return self.data


@dataclass
class _FakeBlobProperties:
    name: str


class _FakeBlobClient:
    def __init__(self, container: _FakeContainerClient, blob_name: str) -> None:
        self._container = container
        self._blob_name = blob_name

    def download_blob(self) -> _FakeDownload:
        if self._blob_name not in self._container.storage:
            raise _FakeAzureNotFoundError(self._blob_name)
        return _FakeDownload(self._container.storage[self._blob_name])

    def exists(self) -> bool:
        return self._blob_name in self._container.storage


class _FakeContainerClient:
    def __init__(self, service: _FakeBlobServiceClient, container_name: str) -> None:
        self._service = service
        self.container_name = container_name

    @property
    def storage(self) -> dict[str, bytes]:
        return self._service.containers.setdefault(self.container_name, {})

    def create_container(self) -> None:
        if self.container_name in self._service.created_containers:
            raise _FakeAzureExistsError(self.container_name)
        self._service.created_containers.add(self.container_name)
        self._service.containers.setdefault(self.container_name, {})

    def upload_blob(self, *, name: str, data: bytes, overwrite: bool) -> None:
        if not overwrite and name in self.storage:
            raise _FakeAzureExistsError(name)
        self.storage[name] = data

    def get_blob_client(self, blob_name: str) -> _FakeBlobClient:
        return _FakeBlobClient(self, blob_name)

    def delete_blob(self, blob_name: str) -> None:
        if blob_name not in self.storage:
            raise _FakeAzureNotFoundError(blob_name)
        del self.storage[blob_name]

    def list_blobs(self, *, name_starts_with: str) -> list[_FakeBlobProperties]:
        return [
            _FakeBlobProperties(name=name)
            for name in sorted(self.storage)
            if name.startswith(name_starts_with)
        ]


@dataclass
class _FakeQueueSendResponse:
    id: str
    inserted_on: str = "2026-04-29T00:00:00+00:00"
    expires_on: str = "2026-04-30T00:00:00+00:00"


@dataclass
class _FakeQueueSDKMessage:
    id: str
    pop_receipt: str
    content: str
    dequeue_count: int | None = 1


class _FakeQueueClient:
    def __init__(self, service: _FakeQueueServiceClient, queue_name: str) -> None:
        self._service = service
        self.queue_name = queue_name

    @property
    def messages(self) -> list[_FakeQueueSDKMessage]:
        return self._service.queues.setdefault(self.queue_name, [])

    def create_queue(self) -> None:
        if self.queue_name in self._service.created_queues:
            raise _FakeAzureExistsError(self.queue_name)
        self._service.created_queues.add(self.queue_name)
        self._service.queues.setdefault(self.queue_name, [])

    def send_message(self, content: str) -> _FakeQueueSendResponse:
        message_id = f"message-{len(self.messages) + 1}"
        self.messages.append(
            _FakeQueueSDKMessage(
                id=message_id,
                pop_receipt=f"receipt-{message_id}",
                content=content,
            )
        )
        return _FakeQueueSendResponse(id=message_id)

    def receive_messages(
        self,
        *,
        messages_per_page: int,
        visibility_timeout: int,
    ) -> list[_FakeQueueSDKMessage]:
        del visibility_timeout
        return list(self.messages[:messages_per_page])

    def get_queue_properties(self) -> object:
        return type(
            "_FakeQueueProperties",
            (),
            {"approximate_message_count": len(self.messages)},
        )()

    def delete_message(self, message_id: str, pop_receipt: str) -> None:
        del pop_receipt
        self._service.queues[self.queue_name] = [
            message for message in self.messages if message.id != message_id
        ]


class _FakeBlobServiceClient:
    last_init: ClassVar[tuple[str, str | None] | None] = None
    last_connection_string: ClassVar[str | None] = None

    def __init__(self, *, account_url: str, credential: str | None) -> None:
        self.account_url = account_url
        self.credential = credential
        self.containers: dict[str, dict[str, bytes]] = {}
        self.created_containers: set[str] = set()
        _FakeBlobServiceClient.last_init = (account_url, credential)

    @classmethod
    def from_connection_string(cls, connection_string: str) -> _FakeBlobServiceClient:
        cls.last_connection_string = connection_string
        return cls(account_url="https://from-connection-string", credential=None)

    def get_container_client(self, container_name: str) -> _FakeContainerClient:
        return _FakeContainerClient(self, container_name)


class _FakeQueueServiceClient:
    last_init: ClassVar[tuple[str, str | None] | None] = None
    last_connection_string: ClassVar[str | None] = None

    def __init__(self, *, account_url: str, credential: str | None) -> None:
        self.account_url = account_url
        self.credential = credential
        self.queues: dict[str, list[_FakeQueueSDKMessage]] = {}
        self.created_queues: set[str] = set()
        _FakeQueueServiceClient.last_init = (account_url, credential)

    @classmethod
    def from_connection_string(cls, connection_string: str) -> _FakeQueueServiceClient:
        cls.last_connection_string = connection_string
        return cls(account_url="https://from-connection-string", credential=None)

    def get_queue_client(self, queue_name: str) -> _FakeQueueClient:
        return _FakeQueueClient(self, queue_name)


def _install_fake_azure_sdks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "repo_rag_lab.azure_artifacts._require_blob_sdk",
        lambda: (_FakeBlobServiceClient, _FakeAzureExistsError, _FakeAzureNotFoundError),
    )
    monkeypatch.setattr(
        "repo_rag_lab.azure_artifacts._require_queue_sdk",
        lambda: (_FakeQueueServiceClient, _FakeAzureExistsError, _FakeAzureNotFoundError),
    )


def test_queue_trace_record_and_drain_trace_queue_use_azure_blob_queue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeAzureArtifactStore()
    config = AzureArtifactConfig(
        account_name="acct",
        account_key="key",
        connection_string=None,
        trace_container="repo-rag-training-traces",
        bundle_container="repo-rag-bundles",
        champion_container="repo-rag-champions",
        queue_name="repo-rag-training",
    )

    def fake_resolve_azure_artifact_config(queue_name: str | None = None) -> AzureArtifactConfig:
        del queue_name
        return config

    def fake_azure_artifact_store(cfg: AzureArtifactConfig) -> _FakeAzureArtifactStore:
        del cfg
        return store

    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.resolve_azure_artifact_config",
        fake_resolve_azure_artifact_config,
    )
    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.AzureArtifactStore",
        fake_azure_artifact_store,
    )

    queued = queue_trace_record(
        tmp_path,
        _sample_trace_payload(),
        queue_name="dataset",
        trace_name="worker-demo",
        batch_name="20260508T223000Z",
        outcome={"acceptance_status": "accepted", "accepted": True, "execution_status": "success"},
    )

    assert queued["storage_backend"] == "azure-blob-queue"
    assert queued["trace_container"] == "repo-rag-training-traces"
    assert queued["batch_name"] == "20260508T223000Z"
    assert queued["batch_trace_path"] == batched_trace_blob_name(
        "20260508T223000Z",
        Path(str(queued["queue_item_path"])).name,
    )
    assert str(queued["queue_item_path"]).startswith("queued/repo-rag-training/")
    assert store.blob_exists(
        "repo-rag-training-traces",
        str(queued["batch_trace_path"]),
    )
    assert store.messages

    drained = drain_trace_queue(tmp_path, queue_name="dataset")

    assert drained["storage_backend"] == "azure-blob-queue"
    assert drained["drained_count"] == 1
    assert drained["failed_count"] == 0
    drained_items = drained["items"]
    assert isinstance(drained_items, list)
    assert drained_items
    first_drained_item = drained_items[0]
    assert isinstance(first_drained_item, dict)
    imported_record_path = first_drained_item["imported_trace_record_path"]
    assert isinstance(imported_record_path, str)
    imported_path = tmp_path / imported_record_path
    assert imported_path.exists()
    imported_payload = json.loads(imported_path.read_text(encoding="utf-8"))
    assert imported_payload["outcome"]["acceptance_status"] == "accepted"
    assert store.deleted_messages == ["msg-1"]


def test_drain_trace_queue_skips_stale_failed_blob_messages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeAzureArtifactStore()
    config = AzureArtifactConfig(
        account_name="acct",
        account_key="key",
        connection_string=None,
        trace_container="repo-rag-training-traces",
        bundle_container="repo-rag-bundles",
        champion_container="repo-rag-champions",
        queue_name="repo-rag-training",
    )

    def fake_resolve_azure_artifact_config(queue_name: str | None = None) -> AzureArtifactConfig:
        del queue_name
        return config

    def fake_azure_artifact_store(cfg: AzureArtifactConfig) -> _FakeAzureArtifactStore:
        del cfg
        return store

    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.resolve_azure_artifact_config",
        fake_resolve_azure_artifact_config,
    )
    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.AzureArtifactStore",
        fake_azure_artifact_store,
    )

    store.messages.append(
        AzureQueueMessage(
            message_id="msg-stale",
            pop_receipt="receipt-stale",
            content=json.dumps(
                {
                    "blob_name": "failed/repo-rag-training/stale-failure.json",
                    "queue_item_kind": "repo-rag-trace-queue-item",
                }
            ),
            dequeue_count=2,
        )
    )

    drained = drain_trace_queue(tmp_path, queue_name="dataset")

    assert drained["storage_backend"] == "azure-blob-queue"
    assert drained["drained_count"] == 0
    assert drained["failed_count"] == 0
    assert drained["skipped_count"] == 1
    assert drained["status"] == "success"
    skipped_items = drained["skipped_items"]
    assert isinstance(skipped_items, list)
    assert isinstance(skipped_items[0], dict)
    assert skipped_items[0]["skip_reason"] == "stale-failed-blob"
    assert store.deleted_messages == ["msg-stale"]


def test_drain_trace_queue_skips_stale_missing_queued_blob_messages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeAzureArtifactStore()
    config = AzureArtifactConfig(
        account_name="acct",
        account_key="key",
        connection_string=None,
        trace_container="repo-rag-training-traces",
        bundle_container="repo-rag-bundles",
        champion_container="repo-rag-champions",
        queue_name="repo-rag-training",
    )

    def fake_resolve_azure_artifact_config(queue_name: str | None = None) -> AzureArtifactConfig:
        del queue_name
        return config

    def fake_azure_artifact_store(cfg: AzureArtifactConfig) -> _FakeAzureArtifactStore:
        del cfg
        return store

    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.resolve_azure_artifact_config",
        fake_resolve_azure_artifact_config,
    )
    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.AzureArtifactStore",
        fake_azure_artifact_store,
    )

    store.messages.append(
        AzureQueueMessage(
            message_id="msg-stale-queued",
            pop_receipt="receipt-stale-queued",
            content=json.dumps(
                {
                    "blob_name": "queued/repo-rag-training/stale-queued.json",
                    "queue_item_kind": "repo-rag-trace-queue-item",
                }
            ),
            dequeue_count=2,
        )
    )

    drained = drain_trace_queue(tmp_path, queue_name="dataset")

    assert drained["storage_backend"] == "azure-blob-queue"
    assert drained["drained_count"] == 0
    assert drained["failed_count"] == 0
    assert drained["skipped_count"] == 1
    assert drained["status"] == "success"
    skipped_items = drained["skipped_items"]
    assert isinstance(skipped_items, list)
    assert isinstance(skipped_items[0], dict)
    assert skipped_items[0]["skip_reason"] == "stale-queue-blob"
    assert store.deleted_messages == ["msg-stale-queued"]


def test_restore_processed_trace_records_rebuilds_local_ledger_from_azure_processed_blobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeAzureArtifactStore()
    config = AzureArtifactConfig(
        account_name="acct",
        account_key="key",
        connection_string=None,
        trace_container="repo-rag-training-traces",
        bundle_container="repo-rag-bundles",
        champion_container="repo-rag-champions",
        queue_name="repo-rag-training",
    )

    def fake_resolve_azure_artifact_config(queue_name: str | None = None) -> AzureArtifactConfig:
        del queue_name
        return config

    def fake_azure_artifact_store(cfg: AzureArtifactConfig) -> _FakeAzureArtifactStore:
        del cfg
        return store

    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.resolve_azure_artifact_config",
        fake_resolve_azure_artifact_config,
    )
    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.AzureArtifactStore",
        fake_azure_artifact_store,
    )

    queue_item_name = "20260501T180000Z-worker-demo.json"
    store.upload_json(
        "repo-rag-training-traces",
        processed_trace_blob_name("repo-rag-training", queue_item_name),
        {
            "schema_version": 1,
            "queue_item_kind": "repo-rag-trace-queue-item",
            "queue_status": "imported",
            "queue_name": "repo-rag-training",
            "trace_name": "worker-demo",
            "trace_payload": _sample_trace_payload(),
            "outcome": {
                "acceptance_status": "accepted",
                "accepted": True,
                "execution_status": "success",
            },
        },
    )

    restored = restore_processed_trace_records(tmp_path, queue_name="dataset")

    assert restored["storage_backend"] == "azure-blob-queue"
    assert restored["processed_count"] == 1
    assert restored["restored_count"] == 1
    trace_paths = restored["trace_paths"]
    assert isinstance(trace_paths, list)
    assert trace_paths
    restored_path = tmp_path / str(trace_paths[0])
    assert restored_path.exists()
    restored_payload = json.loads(restored_path.read_text(encoding="utf-8"))
    assert restored_payload["trace_record_kind"] == "repo-rag-trace-record"
    assert restored_payload["question"] == "How does the trainer ingest traces?"
    assert restored_payload["outcome"]["acceptance_status"] == "accepted"

    restored_again = restore_processed_trace_records(tmp_path, queue_name="dataset")

    assert restored_again["processed_count"] == 1
    assert restored_again["restored_count"] == 0
    assert restored_again["trace_paths"] == []


def test_inspect_pending_trainer_inputs_reports_filesystem_queue_and_recovery(
    tmp_path: Path,
) -> None:
    first = inspect_pending_trainer_inputs(tmp_path, queue_name="dataset")
    assert first["storage_backend"] == "filesystem"
    assert first["queue_visible_count"] == 0
    assert first["recoverable_processed_count"] == 0
    assert first["current_cycle_input_detected"] is False

    queued = queue_trace_record(tmp_path, _sample_trace_payload(), queue_name="dataset")
    assert queued["storage_backend"] == "filesystem"

    second = inspect_pending_trainer_inputs(tmp_path, queue_name="dataset")
    assert second["queue_visible_count"] == 1
    assert second["current_cycle_input_detected"] is True

    drain_trace_queue(tmp_path, queue_name="dataset")
    third = inspect_pending_trainer_inputs(tmp_path, queue_name="dataset")
    assert third["queue_visible_count"] == 0
    assert third["recoverable_processed_count"] == 1
    assert third["current_cycle_input_detected"] is False

    restore_processed_trace_records(tmp_path, queue_name="dataset")
    fourth = inspect_pending_trainer_inputs(tmp_path, queue_name="dataset")
    assert fourth["queue_visible_count"] == 0
    assert fourth["recoverable_processed_count"] == 0
    assert fourth["current_cycle_input_detected"] is False


def test_inspect_pending_trainer_inputs_reports_azure_queue_visibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeAzureArtifactStore()
    config = AzureArtifactConfig(
        account_name="acct",
        account_key="key",
        connection_string=None,
        trace_container="repo-rag-training-traces",
        bundle_container="repo-rag-bundles",
        champion_container="repo-rag-training-families",
        queue_name="repo-rag-training",
    )

    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.resolve_azure_artifact_config",
        lambda queue_name=None: config,
    )
    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.AzureArtifactStore",
        lambda cfg: store,
    )

    queued = queue_trace_record(tmp_path, _sample_trace_payload(), queue_name="dataset")
    assert queued["storage_backend"] == "azure-blob-queue"

    inspected = inspect_pending_trainer_inputs(tmp_path, queue_name="dataset")
    assert inspected["storage_backend"] == "azure-blob-queue"
    assert inspected["queue_visible_count"] == 1
    assert inspected["recoverable_processed_count"] == 0
    assert inspected["current_cycle_input_detected"] is True


def test_fetch_remote_bundle_downloads_bundle_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeAzureArtifactStore()
    config = AzureArtifactConfig(
        account_name="acct",
        account_key="key",
        connection_string=None,
        trace_container="repo-rag-training-traces",
        bundle_container="repo-rag-bundles",
        champion_container="repo-rag-champions",
        queue_name="repo-rag-training",
    )
    bundle_version = "stable-42"
    store.upload_json(
        "repo-rag-bundles",
        "channels/stable.json",
        {
            "schema_version": 1,
            "channel_kind": "bundle-channel",
            "channel_name": "stable",
            "current_bundle_version": bundle_version,
            "current_run_name": bundle_version,
            "current_bundle_path": f"versions/{bundle_version}/bundle.json",
            "current_program_path": f"versions/{bundle_version}/program.json",
            "current_metadata_path": f"versions/{bundle_version}/metadata.json",
            "current_published_bundle_path": f"versions/{bundle_version}/published.json",
            "current_bundle": {"bundle_version": bundle_version},
        },
    )
    store.upload_json(
        "repo-rag-bundles",
        f"versions/{bundle_version}/bundle.json",
        {
            "schema_version": 1,
            "bundle_kind": "global",
            "bundle_version": bundle_version,
            "run_name": bundle_version,
            "bundle_status": "ready",
            "benchmark_status": "pass",
            "family_registry": {
                "schema_version": 1,
                "registry_kind": "repo-rag-family-registry",
                "families": [
                    {
                        "prompt_family_id": "pf-demo",
                        "runtime_artifact": {
                            "artifact_kind": "compiled-family-program",
                            "artifact_ready": True,
                            "program_path": (
                                f"versions/{bundle_version}/families/pf-demo/program.json"
                            ),
                            "metadata_path": (
                                f"versions/{bundle_version}/families/pf-demo/metadata.json"
                            ),
                        },
                    }
                ],
            },
        },
    )
    store.upload_text(
        "repo-rag-bundles",
        f"versions/{bundle_version}/metadata.json",
        "{}\n",
    )
    store.upload_text(
        "repo-rag-bundles",
        f"versions/{bundle_version}/program.json",
        '{"program":"demo"}\n',
    )
    store.upload_json(
        "repo-rag-bundles",
        f"versions/{bundle_version}/published.json",
        {"publish_status": "published", "bundle_version": bundle_version},
    )
    store.upload_text(
        "repo-rag-bundles",
        f"versions/{bundle_version}/families/pf-demo/program.json",
        '{"program":"family-demo"}\n',
    )
    store.upload_text(
        "repo-rag-bundles",
        f"versions/{bundle_version}/families/pf-demo/metadata.json",
        '{"prompt_family_id":"pf-demo"}\n',
    )

    def fake_resolve_azure_artifact_config(queue_name: str | None = None) -> AzureArtifactConfig:
        del queue_name
        return config

    def fake_azure_artifact_store(cfg: AzureArtifactConfig) -> _FakeAzureArtifactStore:
        del cfg
        return store

    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.resolve_azure_artifact_config",
        fake_resolve_azure_artifact_config,
    )
    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.AzureArtifactStore",
        fake_azure_artifact_store,
    )

    payload = fetch_remote_bundle(tmp_path, channel="stable")

    assert payload is not None
    assert payload["bundle_version"] == bundle_version
    program_path = tmp_path / str(payload["program_path"])
    assert program_path.exists()
    assert program_path.read_text(encoding="utf-8") == '{"program":"demo"}\n'
    bundle_payload = json.loads(
        (tmp_path / str(payload["bundle_path"])).read_text(encoding="utf-8")
    )
    family_registry = bundle_payload["family_registry"]
    families = family_registry["families"]
    assert families[0]["prompt_family_id"] == "pf-demo"
    runtime_artifact = families[0]["runtime_artifact"]
    assert runtime_artifact["artifact_ready"] is True
    assert runtime_artifact["program_path"] == (
        f"artifacts/dspy/remote/{bundle_version}/families/pf-demo/program.json"
    )
    assert runtime_artifact["metadata_path"] == (
        f"artifacts/dspy/remote/{bundle_version}/families/pf-demo/metadata.json"
    )
    family_program_path = tmp_path / str(runtime_artifact["program_path"])
    assert family_program_path.exists()
    assert family_program_path.read_text(encoding="utf-8") == '{"program":"family-demo"}\n'


def test_fetch_remote_bundle_tolerates_missing_legacy_published_blob(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeAzureArtifactStore()
    config = AzureArtifactConfig(
        account_name="acct",
        account_key="key",
        connection_string=None,
        trace_container="repo-rag-training-traces",
        bundle_container="repo-rag-bundles",
        champion_container="repo-rag-champions",
        queue_name="repo-rag-training",
    )
    bundle_version = "stable-legacy"
    store.upload_json(
        "repo-rag-bundles",
        "channels/stable.json",
        {
            "schema_version": 1,
            "channel_kind": "bundle-channel",
            "channel_name": "stable",
            "current_bundle_version": bundle_version,
            "current_run_name": bundle_version,
            "current_bundle_path": f"versions/{bundle_version}/bundle.json",
            "current_program_path": f"versions/{bundle_version}/program.json",
            "current_metadata_path": f"versions/{bundle_version}/metadata.json",
            "current_bundle": {"bundle_version": bundle_version},
        },
    )
    store.upload_json(
        "repo-rag-bundles",
        f"versions/{bundle_version}/bundle.json",
        {
            "schema_version": 1,
            "bundle_kind": "global",
            "bundle_version": bundle_version,
            "run_name": bundle_version,
            "bundle_status": "ready",
            "benchmark_status": "pass",
        },
    )
    store.upload_text(
        "repo-rag-bundles",
        f"versions/{bundle_version}/metadata.json",
        "{}\n",
    )
    store.upload_text(
        "repo-rag-bundles",
        f"versions/{bundle_version}/program.json",
        '{"program":"demo"}\n',
    )

    def fake_resolve_azure_artifact_config(queue_name: str | None = None) -> AzureArtifactConfig:
        del queue_name
        return config

    def fake_azure_artifact_store(cfg: AzureArtifactConfig) -> _FakeAzureArtifactStore:
        del cfg
        return store

    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.resolve_azure_artifact_config",
        fake_resolve_azure_artifact_config,
    )
    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.AzureArtifactStore",
        fake_azure_artifact_store,
    )

    payload = fetch_remote_bundle(tmp_path, channel="stable")

    assert payload is not None
    assert payload["bundle_version"] == bundle_version
    assert payload["publish_status"] is None
    assert "published_bundle_path" not in payload
    assert (tmp_path / str(payload["program_path"])).is_file()


def test_fetch_remote_bundle_falls_back_to_latest_remote_version_when_channel_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeAzureArtifactStore()
    config = AzureArtifactConfig(
        account_name="acct",
        account_key="key",
        connection_string=None,
        trace_container="repo-rag-training-traces",
        bundle_container="repo-rag-bundles",
        champion_container="repo-rag-champions",
        queue_name="repo-rag-training",
    )
    bundle_version = "20260510T170500Z"
    store.upload_json(
        "repo-rag-bundles",
        f"versions/{bundle_version}/bundle.json",
        {
            "schema_version": 1,
            "bundle_kind": "global",
            "bundle_version": bundle_version,
            "run_name": bundle_version,
            "bundle_status": "ready",
            "benchmark_status": "pass",
        },
    )
    store.upload_text(
        "repo-rag-bundles",
        f"versions/{bundle_version}/metadata.json",
        "{}\n",
    )
    store.upload_text(
        "repo-rag-bundles",
        f"versions/{bundle_version}/program.json",
        '{"program":"latest-demo"}\n',
    )

    def fake_resolve_azure_artifact_config(queue_name: str | None = None) -> AzureArtifactConfig:
        del queue_name
        return config

    def fake_azure_artifact_store(cfg: AzureArtifactConfig) -> _FakeAzureArtifactStore:
        del cfg
        return store

    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.resolve_azure_artifact_config",
        fake_resolve_azure_artifact_config,
    )
    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.AzureArtifactStore",
        fake_azure_artifact_store,
    )

    payload = fetch_remote_bundle(tmp_path, channel="stable")

    assert payload is not None
    assert payload["bundle_version"] == bundle_version
    assert payload["resolved_from"] == "latest-remote-version"
    assert (tmp_path / str(payload["program_path"])).read_text(encoding="utf-8") == (
        '{"program":"latest-demo"}\n'
    )


def test_upload_remote_bundle_uploads_family_runtime_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeAzureArtifactStore()
    config = AzureArtifactConfig(
        account_name="acct",
        account_key="key",
        connection_string=None,
        trace_container="repo-rag-training-traces",
        bundle_container="repo-rag-bundles",
        champion_container="repo-rag-champions",
        queue_name="repo-rag-training",
    )
    bundle_dir = tmp_path / "artifacts" / "dspy" / "sample-run"
    family_dir = bundle_dir / "families" / "pf-demo"
    family_dir.mkdir(parents=True)
    bundle_path = bundle_dir / "bundle.json"
    metadata_path = bundle_dir / "metadata.json"
    program_path = bundle_dir / "program.json"
    family_program_path = family_dir / "program.json"
    family_metadata_path = family_dir / "metadata.json"
    bundle_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "bundle_kind": "global",
                "bundle_version": "stable-42",
                "run_name": "sample-run",
                "bundle_status": "ready",
                "program_path": "artifacts/dspy/sample-run/program.json",
                "metadata_path": "artifacts/dspy/sample-run/metadata.json",
                "family_registry": {
                    "schema_version": 1,
                    "registry_kind": "repo-rag-family-registry",
                    "families": [
                        {
                            "prompt_family_id": "pf-demo",
                            "runtime_artifact": {
                                "artifact_kind": "compiled-family-program",
                                "artifact_ready": True,
                                "program_path": (
                                    "artifacts/dspy/sample-run/families/pf-demo/program.json"
                                ),
                                "metadata_path": (
                                    "artifacts/dspy/sample-run/families/pf-demo/metadata.json"
                                ),
                            },
                        }
                    ],
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    metadata_path.write_text('{"run_name":"sample-run"}\n', encoding="utf-8")
    program_path.write_text('{"program":"global"}\n', encoding="utf-8")
    family_program_path.write_text('{"program":"family"}\n', encoding="utf-8")
    family_metadata_path.write_text('{"prompt_family_id":"pf-demo"}\n', encoding="utf-8")

    def fake_azure_artifact_store(cfg: AzureArtifactConfig) -> _FakeAzureArtifactStore:
        del cfg
        return store

    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.AzureArtifactStore",
        fake_azure_artifact_store,
    )

    payload = upload_remote_bundle(
        tmp_path,
        published_record={
            "bundle_version": "stable-42",
            "bundle_path": "artifacts/dspy/sample-run/bundle.json",
            "metadata_path": "artifacts/dspy/sample-run/metadata.json",
            "program_path": "artifacts/dspy/sample-run/program.json",
        },
        config=config,
    )

    remote_family_blobs = payload["remote_family_artifact_blobs"]
    assert remote_family_blobs == {
        "pf-demo": {
            "program": "versions/stable-42/families/pf-demo/program.json",
            "metadata": "versions/stable-42/families/pf-demo/metadata.json",
        }
    }
    assert (
        store.download_text(
            "repo-rag-bundles",
            "versions/stable-42/families/pf-demo/program.json",
        )
        == '{"program":"family"}\n'
    )
    assert (
        store.download_text(
            "repo-rag-bundles",
            "versions/stable-42/families/pf-demo/metadata.json",
        )
        == '{"prompt_family_id":"pf-demo"}\n'
    )


def test_upload_and_fetch_remote_family_state_prefer_family_state_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeAzureArtifactStore()
    config = AzureArtifactConfig(
        account_name="acct",
        account_key="key",
        connection_string=None,
        trace_container="repo-rag-training-traces",
        bundle_container="repo-rag-bundles",
        champion_container="repo-rag-champions",
        queue_name="repo-rag-training",
        family_state_container="repo-rag-training-families",
    )
    family_state_path = tmp_path / "artifacts" / "trainer" / "family-state.json"
    family_state_path.parent.mkdir(parents=True)
    runtime_program_path = tmp_path / "artifacts" / "dspy" / "family-demo" / "program.json"
    runtime_metadata_path = tmp_path / "artifacts" / "dspy" / "family-demo" / "metadata.json"
    runtime_program_path.parent.mkdir(parents=True)
    runtime_program_path.write_text('{"program":"family-demo"}\n', encoding="utf-8")
    runtime_metadata_path.write_text(
        json.dumps({"prompt_family_id": "pf-demo"}, indent=2) + "\n",
        encoding="utf-8",
    )
    family_state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "family_state_kind": "repo-rag-trainer-family-state",
                "prompt_families": [
                    {
                        "prompt_family_id": "pf-demo",
                        "family_father_record": {
                            "question": "Inspect whether the README already embeds a demo GIF.",
                            "exact_snapshot_id": "ts-father",
                            "metric_hits": 1,
                            "metric_total": 1,
                            "metric_ratio": 1.0,
                        },
                        "family_records": [
                            {
                                "question": "Inspect whether the README already embeds a demo GIF.",
                                "original_prompt": "Add a demo GIF to README",
                                "reformulated_prompt": (
                                    "Inspect whether the README already embeds a demo GIF."
                                ),
                                "command_trace": [
                                    {
                                        "type": "message",
                                        "role": "assistant",
                                        "text": "inspect README",
                                    }
                                ],
                                "exact_snapshot_id": "ts-demo",
                                "metric_hits": 1,
                                "metric_total": 1,
                                "metric_ratio": 1.0,
                            }
                        ],
                        "family_runtime_artifact": {
                            "artifact_kind": "compiled-family-program",
                            "artifact_ready": True,
                            "program_path": "artifacts/dspy/family-demo/program.json",
                            "metadata_path": "artifacts/dspy/family-demo/metadata.json",
                            "hit_rate": 1.0,
                        },
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_resolve_azure_artifact_config(queue_name: str | None = None) -> AzureArtifactConfig:
        del queue_name
        return config

    def fake_azure_artifact_store(cfg: AzureArtifactConfig) -> _FakeAzureArtifactStore:
        del cfg
        return store

    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.resolve_azure_artifact_config",
        fake_resolve_azure_artifact_config,
    )
    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.AzureArtifactStore",
        fake_azure_artifact_store,
    )
    store.upload_text("repo-rag-training-families", "family-state.json", "{}")
    store.upload_json("repo-rag-training-families", "families/pf-demo/family.json", {"old": True})
    store.upload_json("repo-rag-training-families", "families/pf-demo/father.json", {"old": True})
    store.upload_json(
        "repo-rag-training-families",
        "families/pf-demo/records/ts-demo.json",
        {"old": True},
    )

    uploaded = upload_remote_family_state(tmp_path, family_state_path=family_state_path)

    assert uploaded is not None
    assert uploaded["family_state_container"] == "repo-rag-training-families"
    assert uploaded["family_state_path"] == "artifacts/trainer/family-state.json"
    blob_map = cast(dict[str, str], uploaded["remote_family_state_blobs"])
    assert blob_map == family_state_blob_names(str(uploaded["family_state_version"]))
    assert uploaded["remote_family_member_blobs"] == {
        "pf-demo": {
            "family": f"versions/{uploaded['family_state_version']}/families/pf-demo/family.json",
            "father": f"versions/{uploaded['family_state_version']}/families/pf-demo/father.json",
            "record_blobs": {
                "ts-demo": (
                    f"versions/{uploaded['family_state_version']}/families/pf-demo/records/ts-demo.json"
                ),
                "ts-father": (
                    f"versions/{uploaded['family_state_version']}/families/pf-demo/records/ts-father.json"
                ),
            },
            "runtime_artifact_blobs": {
                "program": (
                    f"versions/{uploaded['family_state_version']}/families/pf-demo/"
                    "runtime-artifact/program.json"
                ),
                "metadata": (
                    f"versions/{uploaded['family_state_version']}/families/pf-demo/"
                    "runtime-artifact/metadata.json"
                ),
            },
        }
    }
    assert store.blob_exists("repo-rag-training-families", blob_map["family_state"])
    assert store.blob_exists("repo-rag-training-families", family_state_current_blob_name())
    current_payload = json.loads(
        store.download_text("repo-rag-training-families", family_state_current_blob_name())
    )
    assert "champion_state_kind" not in current_payload
    assert "current_champion_index_blob" not in current_payload
    assert "current_family_state_alias_blob" not in current_payload
    assert store.blob_exists(
        "repo-rag-training-families",
        f"versions/{uploaded['family_state_version']}/families/pf-demo/family.json",
    )
    assert store.blob_exists(
        "repo-rag-training-families",
        f"versions/{uploaded['family_state_version']}/families/pf-demo/father.json",
    )
    assert store.blob_exists(
        "repo-rag-training-families",
        f"versions/{uploaded['family_state_version']}/families/pf-demo/records/ts-demo.json",
    )
    assert store.blob_exists(
        "repo-rag-training-families",
        (
            f"versions/{uploaded['family_state_version']}/families/pf-demo/"
            "runtime-artifact/program.json"
        ),
    )
    assert store.blob_exists(
        "repo-rag-training-families",
        (
            f"versions/{uploaded['family_state_version']}/families/pf-demo/"
            "runtime-artifact/metadata.json"
        ),
    )
    assert not store.blob_exists("repo-rag-training-families", "family-state.json")
    assert not store.blob_exists("repo-rag-training-families", "families/pf-demo/family.json")
    assert not store.blob_exists("repo-rag-training-families", "families/pf-demo/father.json")
    assert not store.blob_exists(
        "repo-rag-training-families",
        "families/pf-demo/records/ts-demo.json",
    )

    fetched = fetch_remote_family_state(tmp_path)

    assert fetched is not None
    assert fetched["family_state_container"] == "repo-rag-training-families"
    assert fetched["family_state_blob"] == blob_map["family_state"]
    assert fetched["cache_dir"] == (
        f"artifacts/trainer/remote-family-state/{uploaded['family_state_version']}"
    )
    assert fetched["remote_family_member_blobs"] == uploaded["remote_family_member_blobs"]
    cached_family_state = tmp_path / str(fetched["family_state_path"])
    cached_family_paths = cast(dict[str, str], fetched["cached_family_paths"])
    cached_family_member = tmp_path / cached_family_paths["pf-demo"]
    cached_family_member_paths = cast(dict[str, object], fetched["cached_family_member_paths"])
    cached_family_detail = cached_family_member_paths["pf-demo"]
    assert isinstance(cached_family_detail, dict)
    cached_father_path = tmp_path / str(cached_family_detail["father"])
    cached_record_paths = [tmp_path / str(path) for path in cached_family_detail["record_paths"]]
    cached_runtime_paths = cast(dict[str, str], cached_family_detail["runtime_artifact"])
    cached_runtime_program_path = tmp_path / cached_runtime_paths["program"]
    cached_runtime_metadata_path = tmp_path / cached_runtime_paths["metadata"]
    assert cached_family_state.exists()
    assert cached_family_member.exists()
    assert cached_father_path.exists()
    assert len(cached_record_paths) == 2
    assert all(path.exists() for path in cached_record_paths)
    assert cached_runtime_program_path.exists()
    assert cached_runtime_metadata_path.exists()
    cached_family_payload = json.loads(cached_family_member.read_text(encoding="utf-8"))
    assert cached_family_payload["prompt_family_id"] == "pf-demo"
    assert cached_family_payload["family_runtime_artifact"]["program_path"] == str(
        cached_runtime_paths["program"]
    )
    cached_family_state_payload = json.loads(cached_family_state.read_text(encoding="utf-8"))
    assert (
        cached_family_state_payload["prompt_families"][0]["family_runtime_artifact"]["program_path"]
        == str(cached_runtime_paths["program"])
    )
    cached_father_payload = json.loads(cached_father_path.read_text(encoding="utf-8"))
    assert cached_father_payload["exact_snapshot_id"] == "ts-father"


def test_inspect_bundle_channel_supports_staged_worker_bundle_store_layout(
    tmp_path: Path,
) -> None:
    channel_path = tmp_path / "channels" / "stable.json"
    channel_path.parent.mkdir(parents=True)
    channel_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "channel_kind": "bundle-channel",
                "channel_name": "stable",
                "current_bundle_version": "stable-77",
                "current_program_path": "versions/stable-77/program.json",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    state = inspect_bundle_channel(tmp_path, channel="stable")

    assert state["channel_found"] is True
    assert state["channel_path"] == "channels/stable.json"
    assert state["current_bundle_version"] == "stable-77"
    assert state["current_program_path"] == "versions/stable-77/program.json"


def test_resolve_bundle_manifest_supports_staged_worker_bundle_store_layout(
    tmp_path: Path,
) -> None:
    bundle_dir = tmp_path / "versions" / "stable-77"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "bundle.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "bundle_kind": "global",
                "bundle_version": "stable-77",
                "run_name": "stable-77",
                "created_at": "2026-05-03T09:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    bundle_path, payload = resolve_bundle_manifest(tmp_path, bundle_version="stable-77")

    assert bundle_path == (bundle_dir / "bundle.json").resolve()
    assert payload["bundle_version"] == "stable-77"


def test_azure_artifact_store_supports_connection_string_and_queue_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_azure_sdks(monkeypatch)
    monkeypatch.setenv("REPO_RAG_AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    monkeypatch.setenv("REPO_RAG_TRACE_CONTAINER", "repo-rag-training-traces")
    monkeypatch.setenv("REPO_RAG_BUNDLE_CONTAINER", "repo-rag-bundles")
    monkeypatch.setenv("REPO_RAG_TRACE_QUEUE", "repo-rag-training")

    config = AzureArtifactConfig.from_env()
    assert config.configured is True
    assert config.traces_enabled is True
    assert config.bundles_enabled is True
    assert config.queue_enabled is True

    store = AzureArtifactStore.from_env()
    assert store is not None

    store.upload_json("repo-rag-bundles", "versions/stable-42/bundle.json", {"bundle": "demo"})
    store.upload_text("repo-rag-bundles", "versions/stable-42/program.json", '{"program":"demo"}')
    assert store.download_json("repo-rag-bundles", "versions/stable-42/bundle.json") == {
        "bundle": "demo"
    }
    assert store.download_text("repo-rag-bundles", "versions/stable-42/program.json") == (
        '{"program":"demo"}'
    )
    assert store.blob_exists("repo-rag-bundles", "versions/stable-42/program.json") is True
    assert store.list_blobs("repo-rag-bundles", prefix="versions/stable-42/") == [
        "versions/stable-42/bundle.json",
        "versions/stable-42/program.json",
    ]

    send_response = store.send_queue_message("repo-rag-training", {"blob_name": "queued/item.json"})
    assert send_response["message_id"] == "message-1"
    received = store.receive_queue_messages("repo-rag-training")
    assert len(received) == 1
    assert json.loads(received[0].content)["blob_name"] == "queued/item.json"
    store.delete_queue_message("repo-rag-training", received[0])
    assert store.receive_queue_messages("repo-rag-training") == []

    store.delete_blob("repo-rag-bundles", "versions/stable-42/program.json")
    assert store.blob_exists("repo-rag-bundles", "versions/stable-42/program.json") is False

    assert _FakeBlobServiceClient.last_connection_string == "UseDevelopmentStorage=true"
    assert _FakeQueueServiceClient.last_connection_string == "UseDevelopmentStorage=true"


def test_azure_artifact_store_supports_account_url_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_azure_sdks(monkeypatch)
    config = AzureArtifactConfig(
        account_name="realagistorage",
        account_key="secret-key",
        connection_string=None,
        trace_container="repo-rag-training-traces",
        bundle_container="repo-rag-bundles",
        champion_container="repo-rag-champions",
        queue_name="repo-rag-training",
    )
    store = AzureArtifactStore(config)

    store.ensure_container("repo-rag-bundles")
    store.ensure_container("repo-rag-bundles")
    store.ensure_queue("repo-rag-training")
    store.ensure_queue("repo-rag-training")

    assert _FakeBlobServiceClient.last_init == (
        "https://realagistorage.blob.core.windows.net",
        "secret-key",
    )
    assert _FakeQueueServiceClient.last_init == (
        "https://realagistorage.queue.core.windows.net",
        "secret-key",
    )


def test_azure_artifact_config_prefers_family_state_container_envs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPO_RAG_AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    monkeypatch.setenv("REPO_RAG_FAMILY_STATE_CONTAINER", "repo-rag-training-families")
    monkeypatch.setenv("REPO_RAG_CHAMPION_CONTAINER", "repo-rag-champions-legacy")

    config = AzureArtifactConfig.from_env()

    assert config.family_state_container == "repo-rag-training-families"
    assert config.champion_container == "repo-rag-training-families"
    assert config.family_state_enabled is True
    assert config.champions_enabled is True
    assert repo_rag_family_state_container(config) == "repo-rag-training-families"


def test_azure_artifact_config_ignores_champion_container_envs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPO_RAG_AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    monkeypatch.delenv("REPO_RAG_FAMILY_STATE_CONTAINER", raising=False)
    monkeypatch.delenv("DATASET_REPO_RAG_FAMILY_STATE_CONTAINER", raising=False)
    monkeypatch.setenv("REPO_RAG_CHAMPION_CONTAINER", "repo-rag-champions-legacy")
    monkeypatch.setenv("DATASET_REPO_RAG_CHAMPION_CONTAINER", "repo-rag-champions-dataset")

    config = AzureArtifactConfig.from_env()

    assert config.family_state_container == "repo-rag-training-families"
    assert config.champion_container == "repo-rag-training-families"
    assert repo_rag_family_state_container(config) == "repo-rag-training-families"


def test_azure_artifact_helper_and_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_azure_sdks(monkeypatch)
    config = AzureArtifactConfig(
        account_name="realagistorage",
        account_key="secret-key",
        connection_string=None,
        trace_container="repo-rag-training-traces",
        bundle_container="repo-rag-bundles",
        champion_container="repo-rag-champions",
        queue_name=None,
    )
    store = AzureArtifactStore(config)
    store.upload_text("repo-rag-bundles", "versions/stable-42/not-json.txt", "[]")
    with pytest.raises(ValueError, match="must decode to one JSON object"):
        store.download_json("repo-rag-bundles", "versions/stable-42/not-json.txt")

    def fake_exists(self: _FakeBlobClient) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(_FakeBlobClient, "exists", fake_exists)
    assert store.blob_exists("repo-rag-bundles", "versions/stable-42/not-json.txt") is False
    store.delete_blob("repo-rag-bundles", "versions/stable-42/missing.json")

    config_without_names = AzureArtifactConfig(
        account_name=None,
        account_key=None,
        connection_string="UseDevelopmentStorage=true",
        trace_container=None,
        bundle_container=None,
        champion_container=None,
        queue_name=None,
    )
    with pytest.raises(RuntimeError):
        _ = config_without_names.account_url
    with pytest.raises(RuntimeError):
        _ = config_without_names.queue_account_url
    with pytest.raises(RuntimeError):
        AzureArtifactStore(
            AzureArtifactConfig(
                account_name=None,
                account_key=None,
                connection_string=None,
                trace_container=None,
                bundle_container=None,
                champion_container=None,
                queue_name=None,
            )
        )

    monkeypatch.delenv("REPO_RAG_AZURE_STORAGE_ACCOUNT", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT", raising=False)
    monkeypatch.delenv("REPO_RAG_AZURE_STORAGE_KEY", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_KEY", raising=False)
    monkeypatch.delenv("REPO_RAG_AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("REPO_RAG_FAMILY_STATE_CONTAINER", raising=False)
    monkeypatch.delenv("DATASET_REPO_RAG_FAMILY_STATE_CONTAINER", raising=False)
    monkeypatch.delenv("REPO_RAG_CHAMPION_CONTAINER", raising=False)
    monkeypatch.delenv("DATASET_REPO_RAG_CHAMPION_CONTAINER", raising=False)
    assert AzureArtifactStore.from_env() is None

    assert repo_rag_trace_container(config) == "repo-rag-training-traces"
    assert repo_rag_bundle_container(config) == "repo-rag-bundles"
    assert repo_rag_family_state_container(config) == "repo-rag-champions"
    assert repo_rag_trace_queue_name(config, fallback="dataset") == "dataset"
    assert bundle_version_blob_prefix("stable-42") == "versions/stable-42"
    assert bundle_channel_blob_name("stable") == "channels/stable.json"
    assert bundle_blob_names("stable-42") == {
        "bundle": "versions/stable-42/bundle.json",
        "metadata": "versions/stable-42/metadata.json",
        "program": "versions/stable-42/program.json",
        "published": "versions/stable-42/published.json",
    }
    assert family_state_blob_names("stable-42") == {
        "family_state": "versions/stable-42/family-state.json",
        "current": "current.json",
    }
    assert queued_trace_blob_name("dataset", "trace.json") == "queued/dataset/trace.json"
    assert processed_trace_blob_name("dataset", "trace.json") == "processed/dataset/trace.json"
    assert failed_trace_blob_name("dataset", "trace.json") == "failed/dataset/trace.json"
    assert decode_queue_message('{"blob_name":"queued/dataset/trace.json"}') == {
        "blob_name": "queued/dataset/trace.json"
    }
    with pytest.raises(ValueError, match="must decode to one JSON object"):
        decode_queue_message("[]")
    assert normalize_artifact_metadata_paths([" one ", None, "", "two"]) == ["one", "two"]

    with pytest.raises(RuntimeError):
        repo_rag_trace_container(
            AzureArtifactConfig(
                account_name="acct",
                account_key="key",
                connection_string=None,
                trace_container=None,
                bundle_container="repo-rag-bundles",
                champion_container="repo-rag-champions",
                queue_name="repo-rag-training",
            )
        )
    with pytest.raises(RuntimeError):
        repo_rag_bundle_container(
            AzureArtifactConfig(
                account_name="acct",
                account_key="key",
                connection_string=None,
                trace_container="repo-rag-training-traces",
                bundle_container=None,
                champion_container="repo-rag-champions",
                queue_name="repo-rag-training",
            )
        )
