"""Kubernetes manifest helpers for trainer-side repo-RAG deployment surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .dspy_training import DEFAULT_TRAINING_PATH

DEFAULT_TRAINER_K8S_OUTPUT_DIR = Path("artifacts/kubernetes")
DEFAULT_TRAINER_K8S_NAMESPACE = "repo-rag"
DEFAULT_TRAINER_K8S_SERVICE_ACCOUNT_NAME = "repo-rag-trainer"
DEFAULT_TRAINER_K8S_CONFIG_MAP_NAME = "repo-rag-trainer-config"
DEFAULT_TRAINER_K8S_SECRET_NAME = "repo-rag-trainer-secrets"
DEFAULT_TRAINER_K8S_PVC_NAME = "repo-rag-trainer-artifacts"
DEFAULT_TRAINER_K8S_PVC_STORAGE_CLASS = "azurefile-csi"
DEFAULT_TRAINER_K8S_PVC_SIZE = "10Gi"
DEFAULT_TRAINER_K8S_PVC_ACCESS_MODES = ("ReadWriteMany",)
DEFAULT_TRAINER_K8S_SERVICE_NAME = "repo-rag-trainer-service"
DEFAULT_TRAINER_K8S_CYCLE_NAME = "repo-rag-trainer-cycle"
DEFAULT_TRAINER_K8S_ARTIFACT_MOUNT_PATH = "/workspace/repo-rag/artifacts"
DEFAULT_TRAINER_K8S_REPO_ROOT = "/workspace/repo-rag"
DEFAULT_TRAINER_K8S_IMAGE = "ghcr.io/realagiorganization/repo-rag-lab:latest"
DEFAULT_TRAINER_K8S_IMAGE_PULL_POLICY = "IfNotPresent"
DEFAULT_TRAINER_K8S_IMAGE_PULL_SECRET_NAME = "acr-secret"
DEFAULT_TRAINER_K8S_CYCLE_SCHEDULE = "*/15 * * * *"
DEFAULT_TRAINER_K8S_QUEUE_NAME = "dataset"
DEFAULT_TRAINER_K8S_PROMOTE_CHANNEL: str | None = "stable"
DEFAULT_TRAINER_K8S_SERVICE_POLL_INTERVAL_SECONDS = 60.0
DEFAULT_TRAINER_K8S_SERVICE_MAX_IDLE_CYCLES: int | None = None
DEFAULT_TRAINER_K8S_RETRIEVAL_TOP_K = 4
DEFAULT_TRAINER_K8S_RETRIEVAL_TOP_K_SWEEP = "1,2,4,8"
DEFAULT_TRAINER_K8S_MINIMUM_PASS_RATE: float | None = None
DEFAULT_TRAINER_K8S_MINIMUM_SOURCE_RECALL: float | None = None
DEFAULT_TRAINER_K8S_MINIMUM_BUNDLE_PASS_RATE: float | None = None
DEFAULT_TRAINER_K8S_RECOMPILE_RUN_NAME: str | None = None
DEFAULT_TRAINER_K8S_MIN_NEW_CANDIDATES_FOR_RECOMPILE = 1


def _relative_path_text(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _write_yaml_document(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


@dataclass(frozen=True)
class TrainerK8sConfig:
    """Configuration for materializing trainer-side Kubernetes manifests."""

    image: str = DEFAULT_TRAINER_K8S_IMAGE
    namespace: str = DEFAULT_TRAINER_K8S_NAMESPACE
    service_account_name: str = DEFAULT_TRAINER_K8S_SERVICE_ACCOUNT_NAME
    config_map_name: str = DEFAULT_TRAINER_K8S_CONFIG_MAP_NAME
    secret_name: str = DEFAULT_TRAINER_K8S_SECRET_NAME
    pvc_name: str = DEFAULT_TRAINER_K8S_PVC_NAME
    pvc_storage_class_name: str | None = DEFAULT_TRAINER_K8S_PVC_STORAGE_CLASS
    pvc_size: str = DEFAULT_TRAINER_K8S_PVC_SIZE
    pvc_access_modes: tuple[str, ...] = DEFAULT_TRAINER_K8S_PVC_ACCESS_MODES
    deployment_name: str = DEFAULT_TRAINER_K8S_SERVICE_NAME
    cronjob_name: str = DEFAULT_TRAINER_K8S_CYCLE_NAME
    output_dir: Path = DEFAULT_TRAINER_K8S_OUTPUT_DIR
    artifact_mount_path: str = DEFAULT_TRAINER_K8S_ARTIFACT_MOUNT_PATH
    repo_root: str = DEFAULT_TRAINER_K8S_REPO_ROOT
    image_pull_policy: str = DEFAULT_TRAINER_K8S_IMAGE_PULL_POLICY
    image_pull_secret_name: str | None = DEFAULT_TRAINER_K8S_IMAGE_PULL_SECRET_NAME
    queue_name: str = DEFAULT_TRAINER_K8S_QUEUE_NAME
    cycle_schedule: str = DEFAULT_TRAINER_K8S_CYCLE_SCHEDULE
    poll_interval_seconds: float = DEFAULT_TRAINER_K8S_SERVICE_POLL_INTERVAL_SECONDS
    service_max_idle_cycles: int | None = DEFAULT_TRAINER_K8S_SERVICE_MAX_IDLE_CYCLES
    promote_channel: str | None = DEFAULT_TRAINER_K8S_PROMOTE_CHANNEL
    retrieval_training_path: str = str(DEFAULT_TRAINING_PATH)
    retrieval_top_k: int = DEFAULT_TRAINER_K8S_RETRIEVAL_TOP_K
    retrieval_top_k_sweep: str = DEFAULT_TRAINER_K8S_RETRIEVAL_TOP_K_SWEEP
    retrieval_mode: str | None = None
    minimum_pass_rate: float | None = DEFAULT_TRAINER_K8S_MINIMUM_PASS_RATE
    minimum_source_recall: float | None = DEFAULT_TRAINER_K8S_MINIMUM_SOURCE_RECALL
    minimum_bundle_pass_rate: float | None = DEFAULT_TRAINER_K8S_MINIMUM_BUNDLE_PASS_RATE
    trace_queue_limit: int | None = None
    trace_keep_queued: bool = False
    recompile_run_name: str | None = DEFAULT_TRAINER_K8S_RECOMPILE_RUN_NAME
    min_new_candidates_for_recompile: int = (
        DEFAULT_TRAINER_K8S_MIN_NEW_CANDIDATES_FOR_RECOMPILE
    )
    recompile_base_training_path: str = str(DEFAULT_TRAINING_PATH)
    recompile_optimizer: str = "bootstrapfewshot"
    recompile_top_k: int = 4
    recompile_max_bootstrapped_demos: int = 2
    recompile_max_labeled_demos: int = 2
    recompile_mipro_auto: str = "light"
    recompile_num_threads: int = 4
    recompile_mipro_num_trials: int | None = None


def _labels(config: TrainerK8sConfig, role: str) -> dict[str, str]:
    return {
        "app.kubernetes.io/name": "repo-rag-trainer",
        "app.kubernetes.io/component": role,
        "app.kubernetes.io/part-of": "repo-rag",
    }


def _config_map_payload(config: TrainerK8sConfig) -> dict[str, object]:
    data = {
        "TRACE_QUEUE_NAME": config.queue_name,
        "TRACE_QUEUE_LIMIT": str(config.trace_queue_limit or ""),
        "TRACE_KEEP_QUEUED": "1" if config.trace_keep_queued else "",
        "TRAINER_PROMOTE_CHANNEL": config.promote_channel or "",
        "TRAINER_SERVICE_POLL_INTERVAL": str(config.poll_interval_seconds),
        "TRAINER_SERVICE_MAX_IDLE_CYCLES": (
            str(config.service_max_idle_cycles) if config.service_max_idle_cycles is not None else ""
        ),
        "RETRIEVAL_TRAINING_PATH": config.retrieval_training_path,
        "RETRIEVAL_TOP_K": str(config.retrieval_top_k),
        "RETRIEVAL_TOP_K_SWEEP": config.retrieval_top_k_sweep,
        "RETRIEVAL_MODE": config.retrieval_mode or "",
        "RETRIEVAL_MIN_PASS_RATE": (
            str(config.minimum_pass_rate) if config.minimum_pass_rate is not None else ""
        ),
        "RETRIEVAL_MIN_SOURCE_RECALL": (
            str(config.minimum_source_recall)
            if config.minimum_source_recall is not None
            else ""
        ),
        "TRAINER_MIN_BUNDLE_PASS_RATE": (
            str(config.minimum_bundle_pass_rate)
            if config.minimum_bundle_pass_rate is not None
            else ""
        ),
        "TRAINER_MIN_NEW_CANDIDATES_FOR_RECOMPILE": str(
            max(1, int(config.min_new_candidates_for_recompile))
        ),
        "TRAINER_RECOMPILE_RUN_NAME": config.recompile_run_name or "",
        "TRAINER_RECOMPILE_BASE_TRAINING_PATH": config.recompile_base_training_path,
        "TRAINER_RECOMPILE_OPTIMIZER": config.recompile_optimizer,
        "TRAINER_RECOMPILE_TOP_K": str(config.recompile_top_k),
        "TRAINER_RECOMPILE_MAX_BOOTSTRAPPED_DEMOS": str(config.recompile_max_bootstrapped_demos),
        "TRAINER_RECOMPILE_MAX_LABELED_DEMOS": str(config.recompile_max_labeled_demos),
        "TRAINER_RECOMPILE_MIPRO_AUTO": config.recompile_mipro_auto,
        "TRAINER_RECOMPILE_NUM_THREADS": str(config.recompile_num_threads),
        "TRAINER_RECOMPILE_MIPRO_NUM_TRIALS": str(config.recompile_mipro_num_trials or ""),
        "DSPY_MODEL_TYPE": "chat",
        "DSPY_TEMPERATURE": "",
        "DSPY_MAX_TOKENS": "",
    }
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": config.config_map_name,
            "namespace": config.namespace,
            "labels": _labels(config, "config"),
        },
        "data": data,
    }


def _secret_example_payload(config: TrainerK8sConfig) -> dict[str, object]:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": config.secret_name,
            "namespace": config.namespace,
            "labels": _labels(config, "secret-example"),
        },
        "type": "Opaque",
        "stringData": {
            "AZURE_OPENAI_API_KEY": "<set-me>",
            "AZURE_OPENAI_ENDPOINT": "https://<resource>.openai.azure.com",
            "AZURE_OPENAI_DEPLOYMENT_NAME": "<deployment-name>",
            "AZURE_OPENAI_API_VERSION": "<api-version>",
            "AZURE_OPENAI_MODEL_NAME": "<model-name>",
            "AZURE_STORAGE_ACCOUNT": "<storage-account>",
            "AZURE_STORAGE_KEY": "<storage-key>",
            "DATASET_REPO_RAG_TRACE_CONTAINER": "repo-rag-training-traces",
            "DATASET_REPO_RAG_BUNDLE_CONTAINER": "repo-rag-bundles",
            "DATASET_REPO_RAG_TRACE_QUEUE_NAME": config.queue_name,
        },
    }


def _service_account_payload(config: TrainerK8sConfig) -> dict[str, object]:
    return {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {
            "name": config.service_account_name,
            "namespace": config.namespace,
            "labels": _labels(config, "service-account"),
        },
    }


def _pvc_payload(config: TrainerK8sConfig) -> dict[str, object]:
    spec: dict[str, object] = {
        "accessModes": list(config.pvc_access_modes),
        "resources": {"requests": {"storage": config.pvc_size}},
    }
    pvc_spec: dict[str, object] = {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {
            "name": config.pvc_name,
            "namespace": config.namespace,
            "labels": _labels(config, "artifacts"),
        },
        "spec": spec,
    }
    if config.pvc_storage_class_name:
        spec["storageClassName"] = config.pvc_storage_class_name
    return pvc_spec


def _trainer_command(config: TrainerK8sConfig, *, role: str) -> list[str]:
    command = [
        "repo-rag",
        "trainer-service" if role == "service" else "trainer-cycle",
        "--root",
        config.repo_root,
        "--queue-name",
        config.queue_name,
        "--training-path",
        config.retrieval_training_path,
        "--top-k",
        str(config.retrieval_top_k),
        "--top-k-sweep",
        config.retrieval_top_k_sweep,
        "--recompile-base-training-path",
        config.recompile_base_training_path,
        "--recompile-optimizer",
        config.recompile_optimizer,
        "--recompile-top-k",
        str(config.recompile_top_k),
        "--recompile-max-bootstrapped-demos",
        str(config.recompile_max_bootstrapped_demos),
        "--recompile-max-labeled-demos",
        str(config.recompile_max_labeled_demos),
        "--recompile-mipro-auto",
        config.recompile_mipro_auto,
        "--recompile-num-threads",
        str(config.recompile_num_threads),
        "--output",
        "json",
    ]
    if config.trace_queue_limit is not None:
        command.extend(["--limit", str(config.trace_queue_limit)])
    if config.trace_keep_queued:
        command.append("--keep-queued")
    if config.minimum_pass_rate is not None:
        command.extend(["--minimum-pass-rate", str(config.minimum_pass_rate)])
    if config.minimum_source_recall is not None:
        command.extend(["--minimum-source-recall", str(config.minimum_source_recall)])
    if config.minimum_bundle_pass_rate is not None:
        command.extend(["--minimum-bundle-pass-rate", str(config.minimum_bundle_pass_rate)])
    command.extend(
        [
            "--min-new-candidates-for-recompile",
            str(max(1, int(config.min_new_candidates_for_recompile))),
        ]
    )
    if config.recompile_run_name:
        command.extend(["--recompile-run-name", config.recompile_run_name])
    if config.promote_channel:
        command.extend(["--promote-channel", config.promote_channel])
    if config.retrieval_mode:
        command.extend(["--retrieval-mode", config.retrieval_mode])
    if config.recompile_mipro_num_trials is not None:
        command.extend(["--recompile-mipro-num-trials", str(config.recompile_mipro_num_trials)])
    if role == "service":
        command.extend(["--poll-interval-seconds", str(config.poll_interval_seconds)])
        if config.service_max_idle_cycles is not None:
            command.extend(["--max-idle-cycles", str(config.service_max_idle_cycles)])
    return command


def _image_pull_secrets(config: TrainerK8sConfig) -> list[dict[str, str]]:
    if not config.image_pull_secret_name:
        return []
    return [{"name": config.image_pull_secret_name}]


def _container_spec(config: TrainerK8sConfig, *, role: str) -> dict[str, object]:
    return {
        "name": f"repo-rag-{role}",
        "image": config.image,
        "imagePullPolicy": config.image_pull_policy,
        "workingDir": config.repo_root,
        "command": _trainer_command(config, role=role),
        "envFrom": [
            {"configMapRef": {"name": config.config_map_name}},
            {"secretRef": {"name": config.secret_name, "optional": True}},
        ],
        "volumeMounts": [
            {
                "name": "trainer-artifacts",
                "mountPath": config.artifact_mount_path,
            }
        ],
    }


def _volume_spec(config: TrainerK8sConfig) -> list[dict[str, object]]:
    return [
        {
            "name": "trainer-artifacts",
            "persistentVolumeClaim": {"claimName": config.pvc_name},
        }
    ]


def _deployment_payload(config: TrainerK8sConfig) -> dict[str, object]:
    labels = _labels(config, "service")
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": config.deployment_name,
            "namespace": config.namespace,
            "labels": labels,
        },
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": labels},
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "serviceAccountName": config.service_account_name,
                    "imagePullSecrets": _image_pull_secrets(config),
                    "containers": [_container_spec(config, role="service")],
                    "volumes": _volume_spec(config),
                },
            },
        },
    }


def _cronjob_payload(config: TrainerK8sConfig) -> dict[str, object]:
    labels = _labels(config, "cycle")
    return {
        "apiVersion": "batch/v1",
        "kind": "CronJob",
        "metadata": {
            "name": config.cronjob_name,
            "namespace": config.namespace,
            "labels": labels,
        },
        "spec": {
            "schedule": config.cycle_schedule,
            "concurrencyPolicy": "Forbid",
            "successfulJobsHistoryLimit": 3,
            "failedJobsHistoryLimit": 3,
            "jobTemplate": {
                "spec": {
                    "template": {
                        "metadata": {"labels": labels},
                        "spec": {
                            "serviceAccountName": config.service_account_name,
                            "imagePullSecrets": _image_pull_secrets(config),
                            "restartPolicy": "OnFailure",
                            "containers": [_container_spec(config, role="cycle")],
                            "volumes": _volume_spec(config),
                        },
                    }
                }
            },
        },
    }


def write_trainer_k8s_manifests(root: Path, *, config: TrainerK8sConfig) -> dict[str, object]:
    """Materialize Kubernetes manifests for the trainer service and cycle roles."""

    resolved_root = root.resolve()
    output_dir = config.output_dir
    if not output_dir.is_absolute():
        output_dir = resolved_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    service_account_path = output_dir / "trainer-serviceaccount.yaml"
    config_map_path = output_dir / "trainer-configmap.yaml"
    secret_example_path = output_dir / "trainer-secret.example.yaml"
    pvc_path = output_dir / "trainer-artifacts.pvc.yaml"
    deployment_path = output_dir / "trainer-service.deployment.yaml"
    cronjob_path = output_dir / "trainer-cycle.cronjob.yaml"

    _write_yaml_document(service_account_path, _service_account_payload(config))
    _write_yaml_document(config_map_path, _config_map_payload(config))
    _write_yaml_document(secret_example_path, _secret_example_payload(config))
    _write_yaml_document(pvc_path, _pvc_payload(config))
    _write_yaml_document(deployment_path, _deployment_payload(config))
    _write_yaml_document(cronjob_path, _cronjob_payload(config))

    return {
        "namespace": config.namespace,
        "image": config.image,
        "service_account_name": config.service_account_name,
        "config_map_name": config.config_map_name,
        "secret_name": config.secret_name,
        "pvc_name": config.pvc_name,
        "pvc_storage_class_name": config.pvc_storage_class_name,
        "pvc_size": config.pvc_size,
        "pvc_access_modes": list(config.pvc_access_modes),
        "image_pull_secret_name": config.image_pull_secret_name,
        "artifact_mount_path": config.artifact_mount_path,
        "repo_root": config.repo_root,
        "queue_name": config.queue_name,
        "cycle_schedule": config.cycle_schedule,
        "promote_channel": config.promote_channel,
        "minimum_bundle_pass_rate": config.minimum_bundle_pass_rate,
        "min_new_candidates_for_recompile": max(
            1, int(config.min_new_candidates_for_recompile)
        ),
        "manifest_dir": _relative_path_text(resolved_root, output_dir),
        "manifest_paths": [
            _relative_path_text(resolved_root, service_account_path),
            _relative_path_text(resolved_root, config_map_path),
            _relative_path_text(resolved_root, secret_example_path),
            _relative_path_text(resolved_root, pvc_path),
            _relative_path_text(resolved_root, deployment_path),
            _relative_path_text(resolved_root, cronjob_path),
        ],
    }
