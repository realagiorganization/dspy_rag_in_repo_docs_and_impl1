"""Azure Blob + Queue helpers for trainer-side traces and global bundle storage."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from azure.storage.blob import BlobClient as AzureBlobClient
    from azure.storage.blob import BlobProperties as AzureBlobProperties
    from azure.storage.blob import BlobServiceClient as AzureBlobServiceClient
    from azure.storage.blob import ContainerClient as AzureContainerClient
    from azure.storage.queue import QueueClient as AzureQueueClient
    from azure.storage.queue import QueueMessage as AzureQueueSDKMessage
    from azure.storage.queue import QueueServiceClient as AzureQueueServiceClient
else:  # pragma: no cover - typing-only aliases
    AzureBlobClient = object
    AzureBlobProperties = object
    AzureBlobServiceClient = object
    AzureContainerClient = object
    AzureQueueClient = object
    AzureQueueSDKMessage = object
    AzureQueueServiceClient = object


def _first_non_empty(*values: object) -> str | None:
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return None


def _require_blob_sdk() -> tuple[type[AzureBlobServiceClient], type[Exception], type[Exception]]:
    try:
        from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
        from azure.storage.blob import BlobServiceClient
    except ImportError as exc:  # pragma: no cover - depends on optional azure extra
        raise RuntimeError(
            "Azure Blob support requires the optional azure runtime dependencies. "
            "Install repo-rag-lab with the `[azure]` extra."
        ) from exc
    return BlobServiceClient, ResourceExistsError, ResourceNotFoundError


def _require_queue_sdk() -> tuple[type[AzureQueueServiceClient], type[Exception], type[Exception]]:
    try:
        from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
        from azure.storage.queue import QueueServiceClient
    except ImportError as exc:  # pragma: no cover - depends on optional azure extra
        raise RuntimeError(
            "Azure Queue support requires the optional azure runtime dependencies. "
            "Install repo-rag-lab with the `[azure]` extra."
        ) from exc
    return QueueServiceClient, ResourceExistsError, ResourceNotFoundError


@dataclass(frozen=True)
class AzureArtifactConfig:
    """Resolved Azure Storage configuration for traces and bundle distribution."""

    account_name: str | None
    account_key: str | None
    connection_string: str | None
    trace_container: str | None
    bundle_container: str | None
    champion_container: str | None
    queue_name: str | None
    family_state_container: str | None = None

    @classmethod
    def from_env(cls, *, queue_name: str | None = None) -> AzureArtifactConfig:
        """Resolve one configuration from the supported environment variables."""

        family_state_container = _first_non_empty(
            os.getenv("REPO_RAG_FAMILY_STATE_CONTAINER"),
            os.getenv("DATASET_REPO_RAG_FAMILY_STATE_CONTAINER"),
            "repo-rag-training-families",
        )
        return cls(
            account_name=_first_non_empty(
                os.getenv("REPO_RAG_AZURE_STORAGE_ACCOUNT"),
                os.getenv("AZURE_STORAGE_ACCOUNT"),
            ),
            account_key=_first_non_empty(
                os.getenv("REPO_RAG_AZURE_STORAGE_KEY"),
                os.getenv("AZURE_STORAGE_KEY"),
            ),
            connection_string=_first_non_empty(
                os.getenv("REPO_RAG_AZURE_STORAGE_CONNECTION_STRING"),
                os.getenv("AZURE_STORAGE_CONNECTION_STRING"),
            ),
            trace_container=_first_non_empty(
                os.getenv("REPO_RAG_TRACE_CONTAINER"),
                os.getenv("DATASET_REPO_RAG_TRACE_CONTAINER"),
            ),
            bundle_container=_first_non_empty(
                os.getenv("REPO_RAG_BUNDLE_CONTAINER"),
                os.getenv("DATASET_REPO_RAG_BUNDLE_CONTAINER"),
            ),
            family_state_container=family_state_container,
            champion_container=family_state_container,
            queue_name=_first_non_empty(
                queue_name,
                os.getenv("REPO_RAG_TRACE_QUEUE"),
                os.getenv("DATASET_REPO_RAG_TRACE_QUEUE_NAME"),
            ),
        )

    @property
    def configured(self) -> bool:
        return bool(self.connection_string or (self.account_name and self.account_key))

    @property
    def traces_enabled(self) -> bool:
        return self.configured and bool(self.trace_container)

    @property
    def bundles_enabled(self) -> bool:
        return self.configured and bool(self.bundle_container)

    @property
    def family_state_enabled(self) -> bool:
        return self.configured and bool(
            _first_non_empty(self.family_state_container, self.champion_container)
        )

    @property
    def champions_enabled(self) -> bool:
        return self.family_state_enabled

    @property
    def queue_enabled(self) -> bool:
        return self.traces_enabled and bool(self.queue_name)

    @property
    def account_url(self) -> str:
        if not self.account_name:
            raise RuntimeError("Azure Storage account name is not configured.")
        return f"https://{self.account_name}.blob.core.windows.net"

    @property
    def queue_account_url(self) -> str:
        if not self.account_name:
            raise RuntimeError("Azure Storage account name is not configured.")
        return f"https://{self.account_name}.queue.core.windows.net"


@dataclass(frozen=True)
class AzureQueueMessage:
    """Small normalized queue-message payload used by the trainer loop."""

    message_id: str
    pop_receipt: str
    content: str
    dequeue_count: int | None


class AzureArtifactStore:
    """Thin wrapper around Azure Blob + Queue for repo-rag artifacts."""

    def __init__(self, config: AzureArtifactConfig) -> None:
        if not config.configured:
            raise RuntimeError("Azure Storage credentials are not configured.")
        self.config = config
        self._blob_service_client: AzureBlobServiceClient | None = None
        self._queue_service_client: AzureQueueServiceClient | None = None

    @classmethod
    def from_env(cls, *, queue_name: str | None = None) -> AzureArtifactStore | None:
        config = AzureArtifactConfig.from_env(queue_name=queue_name)
        if not config.configured:
            return None
        return cls(config)

    def _blob_service(self) -> AzureBlobServiceClient:
        if self._blob_service_client is None:
            blob_service_client_cls, _, _ = _require_blob_sdk()
            if self.config.connection_string:
                self._blob_service_client = blob_service_client_cls.from_connection_string(
                    self.config.connection_string
                )
            else:
                self._blob_service_client = blob_service_client_cls(
                    account_url=self.config.account_url,
                    credential=self.config.account_key,
                )
        return self._blob_service_client

    def _queue_service(self) -> AzureQueueServiceClient:
        if self._queue_service_client is None:
            queue_service_client_cls, _, _ = _require_queue_sdk()
            if self.config.connection_string:
                self._queue_service_client = queue_service_client_cls.from_connection_string(
                    self.config.connection_string
                )
            else:
                self._queue_service_client = queue_service_client_cls(
                    account_url=self.config.queue_account_url,
                    credential=self.config.account_key,
                )
        return self._queue_service_client

    def ensure_container(self, container_name: str) -> None:
        service = self._blob_service()
        _, resource_exists_error, _ = _require_blob_sdk()
        container_client: AzureContainerClient = service.get_container_client(container_name)
        try:
            container_client.create_container()
        except resource_exists_error:
            return

    def ensure_queue(self, queue_name: str) -> None:
        service = self._queue_service()
        _, resource_exists_error, _ = _require_queue_sdk()
        queue_client: AzureQueueClient = service.get_queue_client(queue_name)
        try:
            queue_client.create_queue()
        except resource_exists_error:
            return

    def upload_json(
        self, container_name: str, blob_name: str, payload: Mapping[str, object]
    ) -> None:
        self.upload_text(container_name, blob_name, f"{json.dumps(dict(payload), indent=2)}\n")

    def upload_text(self, container_name: str, blob_name: str, text: str) -> None:
        self.ensure_container(container_name)
        container_client: AzureContainerClient = self._blob_service().get_container_client(
            container_name
        )
        container_client.upload_blob(name=blob_name, data=text.encode("utf-8"), overwrite=True)

    def upload_bytes(self, container_name: str, blob_name: str, payload: bytes) -> None:
        self.ensure_container(container_name)
        container_client: AzureContainerClient = self._blob_service().get_container_client(
            container_name
        )
        container_client.upload_blob(name=blob_name, data=payload, overwrite=True)

    def download_json(self, container_name: str, blob_name: str) -> dict[str, object]:
        payload = json.loads(self.download_text(container_name, blob_name))
        if not isinstance(payload, dict):
            raise ValueError(
                f"Azure blob payload must decode to one JSON object: {container_name}/{blob_name}"
            )
        return payload

    def download_text(self, container_name: str, blob_name: str) -> str:
        return self.download_bytes(container_name, blob_name).decode("utf-8")

    def download_bytes(self, container_name: str, blob_name: str) -> bytes:
        container_client: AzureContainerClient = self._blob_service().get_container_client(
            container_name
        )
        blob_client: AzureBlobClient = container_client.get_blob_client(blob_name)
        return blob_client.download_blob().readall()

    def blob_exists(self, container_name: str, blob_name: str) -> bool:
        container_client: AzureContainerClient = self._blob_service().get_container_client(
            container_name
        )
        blob_client: AzureBlobClient = container_client.get_blob_client(blob_name)
        try:
            return bool(blob_client.exists())
        except Exception:
            return False

    def delete_blob(self, container_name: str, blob_name: str) -> None:
        container_client: AzureContainerClient = self._blob_service().get_container_client(
            container_name
        )
        _, _, resource_not_found_error = _require_blob_sdk()
        try:
            container_client.delete_blob(blob_name)
        except resource_not_found_error:
            return

    def send_queue_message(
        self, queue_name: str, payload: Mapping[str, object]
    ) -> dict[str, object]:
        self.ensure_queue(queue_name)
        queue_client: AzureQueueClient = self._queue_service().get_queue_client(queue_name)
        content = json.dumps(dict(payload))
        response = queue_client.send_message(content)
        return {
            "message_id": getattr(response, "id", None),
            "inserted_on": str(getattr(response, "inserted_on", "") or ""),
            "expires_on": str(getattr(response, "expires_on", "") or ""),
        }

    def receive_queue_messages(
        self,
        queue_name: str,
        *,
        limit: int | None = None,
        visibility_timeout: int = 30,
    ) -> list[AzureQueueMessage]:
        self.ensure_queue(queue_name)
        queue_client: AzureQueueClient = self._queue_service().get_queue_client(queue_name)
        max_messages = limit if isinstance(limit, int) and limit > 0 else 32
        raw_messages = list(
            queue_client.receive_messages(
                messages_per_page=max_messages,
                visibility_timeout=visibility_timeout,
            )
        )
        messages: list[AzureQueueMessage] = []
        for message in raw_messages:
            typed_message: AzureQueueSDKMessage = message
            messages.append(
                AzureQueueMessage(
                    message_id=str(getattr(typed_message, "id", "") or ""),
                    pop_receipt=str(getattr(typed_message, "pop_receipt", "") or ""),
                    content=str(getattr(typed_message, "content", "") or ""),
                    dequeue_count=getattr(typed_message, "dequeue_count", None),
                )
            )
        return messages

    def approximate_queue_message_count(self, queue_name: str) -> int:
        """Return the provider-reported approximate visible message count for one queue."""

        self.ensure_queue(queue_name)
        queue_client: AzureQueueClient = self._queue_service().get_queue_client(queue_name)
        properties = queue_client.get_queue_properties()
        approximate = getattr(properties, "approximate_message_count", 0)
        try:
            return max(0, int(approximate or 0))
        except (TypeError, ValueError):
            return 0

    def delete_queue_message(self, queue_name: str, message: AzureQueueMessage) -> None:
        queue_client: AzureQueueClient = self._queue_service().get_queue_client(queue_name)
        queue_client.delete_message(message.message_id, message.pop_receipt)

    def list_blobs(self, container_name: str, *, prefix: str) -> list[str]:
        container_client: AzureContainerClient = self._blob_service().get_container_client(
            container_name
        )
        names: list[str] = []
        for blob in container_client.list_blobs(name_starts_with=prefix):
            typed_blob: AzureBlobProperties = blob
            name = getattr(typed_blob, "name", None)
            if isinstance(name, str) and name.strip():
                names.append(name)
        return names


def repo_rag_trace_container(config: AzureArtifactConfig) -> str:
    container = config.trace_container
    if not container:
        raise RuntimeError("Trace container is not configured.")
    return container


def repo_rag_bundle_container(config: AzureArtifactConfig) -> str:
    container = config.bundle_container
    if not container:
        raise RuntimeError("Bundle container is not configured.")
    return container


def repo_rag_family_state_container(config: AzureArtifactConfig) -> str:
    container = _first_non_empty(config.family_state_container, config.champion_container)
    if not container:
        raise RuntimeError("Family-state container is not configured.")
    return container


def repo_rag_trace_queue_name(config: AzureArtifactConfig, *, fallback: str) -> str:
    return _first_non_empty(config.queue_name, fallback) or fallback


def bundle_version_blob_prefix(bundle_version: str) -> str:
    return f"versions/{bundle_version}"


def bundle_channel_blob_name(channel: str) -> str:
    return f"channels/{channel}.json"


def bundle_blob_names(bundle_version: str) -> dict[str, str]:
    prefix = bundle_version_blob_prefix(bundle_version)
    return {
        "bundle": f"{prefix}/bundle.json",
        "metadata": f"{prefix}/metadata.json",
        "program": f"{prefix}/program.json",
        "routing_index": f"{prefix}/routing-index.sqlite3",
        "published": f"{prefix}/published.json",
    }


def family_state_version_blob_prefix(family_state_version: str) -> str:
    return f"versions/{family_state_version}"


def family_state_current_blob_name() -> str:
    return "current.json"


def family_state_blob_names(family_state_version: str) -> dict[str, str]:
    prefix = family_state_version_blob_prefix(family_state_version)
    return {
        "family_state": f"{prefix}/family-index.sqlite3",
        "current": family_state_current_blob_name(),
    }


def queued_trace_blob_name(queue_name: str, file_name: str) -> str:
    return f"queued/{queue_name}/{file_name}"


def processed_trace_blob_name(queue_name: str, file_name: str) -> str:
    return f"processed/{queue_name}/{file_name}"


def failed_trace_blob_name(queue_name: str, file_name: str) -> str:
    return f"failed/{queue_name}/{file_name}"


def batched_trace_blob_name(batch_name: str, file_name: str) -> str:
    return f"batches/{batch_name}/{file_name}"


def decode_queue_message(payload: str) -> dict[str, object]:
    message = json.loads(payload)
    if not isinstance(message, dict):
        raise ValueError("Azure queue message must decode to one JSON object.")
    return {str(key): value for key, value in message.items()}


def normalize_artifact_metadata_paths(paths: Sequence[str | None]) -> list[str]:
    normalized: list[str] = []
    for path in paths:
        if not isinstance(path, str):
            continue
        cleaned = path.strip()
        if cleaned:
            normalized.append(cleaned)
    return normalized
