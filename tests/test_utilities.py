# pyright: reportUnknownLambdaType=false

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from repo_rag_lab.azure_artifacts import AzureArtifactConfig
from repo_rag_lab.dspy_training import DSPyLMConfig
from repo_rag_lab.utilities import (
    run_azure_inference_probe,
    run_azure_openai_probe,
    run_bundle_fetch,
    run_bundle_inspection,
    run_bundle_promote,
    run_bundle_publish,
    run_bundle_rollback,
    run_dspy_artifacts,
    run_exploratorium_translation_sync,
    run_file_summary_sync,
    run_github_pr_gate_sync,
    run_notebook_report,
    run_overlay_init,
    run_pages_site_sync,
    run_retrieval_evaluation,
    run_smoke_test,
    run_surface_verification,
    run_todo_backlog_sync,
    run_trace_drain,
    run_trace_enqueue,
    run_trace_export,
    run_trace_import,
    run_trainer_candidates,
    run_trainer_cycle,
    run_trainer_k8s_manifest_generation,
    run_trainer_recompile,
    run_trainer_service,
    utility_summary,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
_RECOVERED_TRACES_DIR = Path("artifacts/trainer/recovered-imported-traces")


def _restore_processed_trace_records_stub(
    *,
    processed_count: int,
    restored_count: int,
    trace_paths: Sequence[str],
    failed_count: int = 0,
) -> Callable[..., dict[str, object]]:
    def _restore(
        root: Path,
        queue_name: str = "default",
        output_dir: Path = _RECOVERED_TRACES_DIR,
    ) -> dict[str, object]:
        del root
        return {
            "storage_backend": "azure-blob-queue",
            "queue_name": queue_name,
            "processed_count": processed_count,
            "restored_count": restored_count,
            "failed_count": failed_count,
            "trace_paths": list(trace_paths),
            "failures": [],
            "output_dir": str(output_dir),
        }

    return _restore


def _materialize_training_candidates_stub(
    *,
    candidate_count: int,
    new_candidate_count: int,
    prompt_family_count: int,
    context_group_count: int,
) -> Callable[..., dict[str, object]]:
    def _materialize(
        root: Path,
        trace_paths: Sequence[str],
        output_path: Path,
        summary_path: Path,
        include_statuses: tuple[str, ...] = ("accepted", "candidate"),
        seed_existing_output: bool = True,
    ) -> dict[str, object]:
        del root, trace_paths, output_path, summary_path, include_statuses, seed_existing_output
        return {
            "candidate_count": candidate_count,
            "new_candidate_count": new_candidate_count,
            "prompt_family_count": prompt_family_count,
            "context_group_count": context_group_count,
            "champion_index_path": "artifacts/trainer/champion-index.json",
            "output_path": "artifacts/trainer/training-candidates.yaml",
            "summary_path": "artifacts/trainer/training-candidates-summary.json",
        }

    return _materialize


def _write_bundle_manifest(
    root: Path,
    run_name: str,
    *,
    created_at: str = "2026-04-29T00:00:00+00:00",
    benchmark_status: str = "pass",
) -> Path:
    artifact_dir = root / "artifacts" / "dspy" / run_name
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "program.json").write_text('{"program": "demo"}\n', encoding="utf-8")
    (artifact_dir / "metadata.json").write_text('{"metadata": "demo"}\n', encoding="utf-8")
    bundle_path = artifact_dir / "bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "bundle_kind": "global",
                "run_name": run_name,
                "bundle_version": run_name,
                "bundle_status": "ready",
                "created_at": created_at,
                "artifact_dir": f"artifacts/dspy/{run_name}",
                "bundle_path": f"artifacts/dspy/{run_name}/bundle.json",
                "program_path": f"artifacts/dspy/{run_name}/program.json",
                "metadata_path": f"artifacts/dspy/{run_name}/metadata.json",
                "training_path": "samples/training/repository_training_examples.yaml",
                "top_k": 4,
                "retrieval_mode": "idf-rerank",
                "benchmark_status": benchmark_status,
                "benchmark_summary": {"pass_rate": 1.0},
                "compiled_program_summary": {"program_type": "RepositoryRAGProgram"},
                "lm": {"model": "azure/test"},
                "provenance": {
                    "source": "repo-rag",
                    "retrieval_profile_path": "config/retrieval-profile.json",
                    "question_bank_path": "data/questions/repository.yaml",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return bundle_path


def _write_demo_repo_for_exploratorium(tmp_path: Path) -> None:
    (tmp_path / "documentation").mkdir(parents=True)
    (tmp_path / "publication").mkdir(parents=True)
    (tmp_path / "src" / "repo_rag_lab").mkdir(parents=True)

    (tmp_path / "README.md").write_text(
        "# Demo Repo\n\nSee https://github.com/example/project and https://astral.sh/.\n",
        encoding="utf-8",
    )
    (tmp_path / "Makefile").write_text(".PHONY: setup\nsetup:\n\t@true\n", encoding="utf-8")
    (tmp_path / "documentation" / "azure-deployment.md").write_text(
        "# Azure Deployment\n\nCompanion note.\n",
        encoding="utf-8",
    )
    (tmp_path / "documentation" / "mcp-discovery.md").write_text(
        "# MCP Discovery\n\nCompanion note.\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "repo_rag_lab" / "example.py").write_text(
        '"""Example module."""\n\nVALUE = 1\n',
        encoding="utf-8",
    )
    (tmp_path / "publication" / "references.bib").write_text(
        "@misc{mcp2024,\n"
        "  title = {Model Context Protocol},\n"
        "  howpublished = {\\url{https://modelcontextprotocol.io/}}\n"
        "}\n\n"
        "@misc{azureinference2025,\n"
        "  title = {Azure AI Inference Documentation},\n"
        "  howpublished = {\\url{https://learn.microsoft.com/azure/ai-services/}}\n"
        "}\n",
        encoding="utf-8",
    )


def test_utility_summary_mentions_core_surfaces() -> None:
    summary = utility_summary(REPO_ROOT)
    assert "ask" in summary
    assert "lookup-first" in summary
    assert "ask-live" in summary
    assert "discover-mcp" in summary
    assert "serve-mcp" in summary
    assert "serve-codex-proxy" in summary
    assert "dspy-train" in summary
    assert "dspy-artifacts" in summary
    assert "bundle-inspect" in summary
    assert "bundle-publish" in summary
    assert "bundle-promote" in summary
    assert "bundle-rollback" in summary
    assert "bundle-fetch" in summary
    assert "overlay-init" in summary
    assert "trace-export" in summary
    assert "trace-import" in summary
    assert "trace-enqueue" in summary
    assert "trace-drain" in summary
    assert "trainer-cycle" in summary
    assert "trainer-service" in summary
    assert "trainer-k8s-manifests" in summary
    assert "trainer-recompile" in summary
    assert "azure-openai-probe" in summary
    assert "azure-inference-probe" in summary
    assert "files-sync" in summary
    assert "rust-lookup-index" in summary
    assert "rust-lookup" in summary
    assert "exploratorium-sync" in summary
    assert "github-pr-gates" in summary
    assert "pages-build" in summary
    assert "retrieval-eval" in summary
    assert "todo-sync" in summary
    assert "smoke-test" in summary
    assert "verify-surfaces" in summary
    assert "run-notebooks" in summary


def test_run_smoke_test_reports_expected_fields() -> None:
    payload = json.loads(run_smoke_test(REPO_ROOT))
    assert payload["command"] == "smoke-test"
    assert payload["command_status"] == "success"
    assert payload["warnings"] == []
    assert payload["answer_contains_repository"] is True
    assert payload["manifest_path"].startswith("artifacts/azure/")
    assert payload["artifact_metadata"]["generated_paths"] == [payload["manifest_path"]]
    assert isinstance(payload["mcp_candidate_count"], int)


def test_run_trainer_k8s_manifest_generation_writes_expected_manifests(tmp_path: Path) -> None:
    payload = json.loads(
        run_trainer_k8s_manifest_generation(
            tmp_path,
            image="ghcr.io/example/repo-rag:latest",
            namespace="repo-rag",
        )
    )

    assert payload["command"] == "trainer-k8s-manifests"
    assert payload["command_status"] == "success"
    assert payload["namespace"] == "repo-rag"
    assert payload["image"] == "ghcr.io/example/repo-rag:latest"
    assert payload["manifest_dir"] == "artifacts/kubernetes"
    assert payload["image_pull_secret_name"] == "acr-secret"
    assert payload["pvc_storage_class_name"] == "azurefile-csi"
    assert payload["pvc_size"] == "10Gi"
    assert payload["pvc_access_modes"] == ["ReadWriteMany"]
    assert len(payload["manifest_paths"]) == 6

    pvc_path = tmp_path / "artifacts" / "kubernetes" / "trainer-artifacts.pvc.yaml"
    deployment_path = tmp_path / "artifacts" / "kubernetes" / "trainer-service.deployment.yaml"
    cronjob_path = tmp_path / "artifacts" / "kubernetes" / "trainer-cycle.cronjob.yaml"
    config_map_path = tmp_path / "artifacts" / "kubernetes" / "trainer-configmap.yaml"
    secret_example_path = tmp_path / "artifacts" / "kubernetes" / "trainer-secret.example.yaml"

    pvc = yaml.safe_load(pvc_path.read_text(encoding="utf-8"))
    deployment = yaml.safe_load(deployment_path.read_text(encoding="utf-8"))
    cronjob = yaml.safe_load(cronjob_path.read_text(encoding="utf-8"))
    config_map = yaml.safe_load(config_map_path.read_text(encoding="utf-8"))
    secret_example = yaml.safe_load(secret_example_path.read_text(encoding="utf-8"))

    assert pvc["kind"] == "PersistentVolumeClaim"
    assert pvc["spec"]["storageClassName"] == "azurefile-csi"
    assert pvc["spec"]["accessModes"] == ["ReadWriteMany"]
    assert pvc["spec"]["resources"]["requests"]["storage"] == "10Gi"
    assert deployment["kind"] == "Deployment"
    deployment_spec = deployment["spec"]["template"]["spec"]
    assert deployment_spec["imagePullSecrets"] == [{"name": "acr-secret"}]
    assert deployment_spec["containers"][0]["command"][:4] == [
        "repo-rag",
        "trainer-service",
        "--root",
        "/workspace/repo-rag",
    ]
    assert "--max-idle-cycles" not in deployment_spec["containers"][0]["command"]
    assert "--minimum-pass-rate" not in deployment_spec["containers"][0]["command"]
    assert "--minimum-source-recall" not in deployment_spec["containers"][0]["command"]
    assert "--minimum-bundle-pass-rate" not in deployment_spec["containers"][0]["command"]
    min_new_index = deployment_spec["containers"][0]["command"].index(
        "--min-new-candidates-for-recompile"
    )
    assert deployment_spec["containers"][0]["command"][min_new_index + 1] == "1"
    assert "--recompile-run-name" not in deployment_spec["containers"][0]["command"]
    assert cronjob["kind"] == "CronJob"
    assert cronjob["spec"]["schedule"] == "*/15 * * * *"
    cronjob_spec = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    assert cronjob_spec["imagePullSecrets"] == [{"name": "acr-secret"}]
    assert cronjob_spec["containers"][0]["command"][:4] == [
        "repo-rag",
        "trainer-cycle",
        "--root",
        "/workspace/repo-rag",
    ]
    assert config_map["kind"] == "ConfigMap"
    assert config_map["data"]["TRAINER_RECOMPILE_RUN_NAME"] == ""
    assert config_map["data"]["TRAINER_MIN_BUNDLE_PASS_RATE"] == ""
    assert config_map["data"]["TRAINER_MIN_NEW_CANDIDATES_FOR_RECOMPILE"] == "1"
    assert config_map["data"]["TRAINER_SERVICE_MAX_IDLE_CYCLES"] == ""
    assert config_map["data"]["RETRIEVAL_MIN_PASS_RATE"] == ""
    assert config_map["data"]["RETRIEVAL_MIN_SOURCE_RECALL"] == ""
    assert config_map["data"]["TRAINER_PROMOTE_CHANNEL"] == "stable"
    assert secret_example["kind"] == "Secret"
    assert "AZURE_OPENAI_API_KEY" in secret_example["stringData"]


def test_run_retrieval_evaluation_reports_expected_fields() -> None:
    payload = json.loads(run_retrieval_evaluation(REPO_ROOT, top_k=4, top_k_sweep="1,4"))
    assert payload["command"] == "retrieval-eval"
    assert payload["command_status"] == "success"
    assert payload["root"] == str(REPO_ROOT)
    assert payload["retrieval_mode"] == "idf-rerank"
    assert payload["training_path"] == "samples/training/repository_training_examples.yaml"
    assert payload["benchmark_count"] >= 1
    assert payload["default_top_k"] == 4
    assert payload["default_summary"]["top_k"] == 4
    assert payload["default_summary"]["tag_summaries"]
    assert [summary["top_k"] for summary in payload["top_k_summaries"]] == [1, 4]
    assert "average_reciprocal_rank" in payload["default_summary"]
    assert payload["thresholds_enabled"] is False
    assert payload["thresholds"]["minimum_pass_rate"] is None
    assert payload["thresholds"]["minimum_source_recall"] is None
    assert payload["threshold_failures"] == []
    assert payload["status"] == "pass"
    assert payload["artifact_metadata"]["input_paths"] == [payload["training_path"]]


def test_run_retrieval_evaluation_reports_threshold_failures() -> None:
    payload = json.loads(
        run_retrieval_evaluation(
            REPO_ROOT,
            top_k=4,
            top_k_sweep="1,4",
            minimum_pass_rate=1.1,
            minimum_source_recall=1.1,
        )
    )

    assert payload["status"] == "fail"
    assert len(payload["threshold_failures"]) == 2
    assert payload["command_status"] == "fail"


def test_run_surface_verification_reports_expected_fields() -> None:
    payload = json.loads(run_surface_verification(REPO_ROOT))
    assert payload["command"] == "verify-surfaces"
    assert payload["command_status"] == "success"
    assert payload["issue_count"] == 0
    assert payload["checked_notebook_count"] >= 2


def test_run_dspy_artifacts_reports_expected_fields(tmp_path: Path) -> None:
    payload = json.loads(run_dspy_artifacts(tmp_path))
    assert payload["command"] == "dspy-artifacts"
    assert payload["command_status"] == "success"
    assert payload["root"] == str(tmp_path)
    assert payload["artifact_root"] == "artifacts/dspy"
    assert payload["run_count"] == 0
    assert payload["runs"] == []
    assert payload["warnings"] == ["No saved DSPy runs are available yet."]


def test_run_bundle_inspection_reports_empty_state(tmp_path: Path) -> None:
    payload = json.loads(run_bundle_inspection(tmp_path))

    assert payload["command"] == "bundle-inspect"
    assert payload["command_status"] == "success"
    assert payload["bundle_found"] is False
    assert payload["warnings"] == ["No saved DSPy bundles are available yet."]


def test_run_bundle_publish_creates_published_record(tmp_path: Path) -> None:
    _write_bundle_manifest(tmp_path, "sample-run")

    payload = json.loads(run_bundle_publish(tmp_path, run_name="sample-run"))

    assert payload["command"] == "bundle-publish"
    assert payload["command_status"] == "success"
    assert payload["bundle_version"] == "sample-run"
    assert payload["publish_status"] == "published"
    assert payload["publish_action"] == "created"
    published_path = tmp_path / payload["published_bundle_path"]
    assert published_path.exists()


def test_run_bundle_inspection_reads_promoted_channel_state(tmp_path: Path) -> None:
    _write_bundle_manifest(tmp_path, "stable-run")
    json.loads(run_bundle_promote(tmp_path, channel="stable", run_name="stable-run"))

    payload = json.loads(run_bundle_inspection(tmp_path, channel="stable"))

    assert payload["command"] == "bundle-inspect"
    assert payload["command_status"] == "success"
    assert payload["channel_found"] is True
    assert payload["bundle_found"] is True
    assert payload["channel_name"] == "stable"
    assert payload["current_bundle_version"] == "stable-run"


def test_run_bundle_inspection_prefers_remote_channel_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repo_rag_lab.utilities.inspect_remote_bundle_channel",
        lambda channel: {
            "channel_found": True,
            "channel_name": channel,
            "current_bundle_version": "remote-stable",
            "storage_backend": "azure-blob",
            "bundle_container": "repo-rag-bundles",
        },
    )

    payload = json.loads(run_bundle_inspection(tmp_path, channel="stable"))

    assert payload["command"] == "bundle-inspect"
    assert payload["channel_found"] is True
    assert payload["storage_backend"] == "azure-blob"
    assert payload["current_bundle_version"] == "remote-stable"


def test_run_bundle_promote_and_rollback_manage_channel_history(tmp_path: Path) -> None:
    _write_bundle_manifest(tmp_path, "older-run", created_at="2026-04-29T00:00:00+00:00")
    _write_bundle_manifest(tmp_path, "newer-run", created_at="2026-04-29T01:00:00+00:00")

    first = json.loads(run_bundle_promote(tmp_path, channel="stable", run_name="older-run"))
    second = json.loads(run_bundle_promote(tmp_path, channel="stable", run_name="newer-run"))
    rolled_back = json.loads(run_bundle_rollback(tmp_path, channel="stable"))

    assert first["command"] == "bundle-promote"
    assert first["channel_action"] == "promote"
    assert first["current_bundle_version"] == "older-run"
    assert second["current_bundle_version"] == "newer-run"
    assert second["history"][-1]["action"] == "promote"
    assert rolled_back["command"] == "bundle-rollback"
    assert rolled_back["channel_action"] == "rollback"
    assert rolled_back["current_bundle_version"] == "older-run"
    assert rolled_back["history"][-1]["action"] == "rollback"


def test_run_bundle_publish_promote_and_rollback_mirror_to_remote_blob_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote_blobs: dict[tuple[str, str], str] = {}
    config = AzureArtifactConfig(
        account_name="acct",
        account_key="key",
        connection_string=None,
        trace_container="repo-rag-training-traces",
        bundle_container="repo-rag-bundles",
        queue_name="repo-rag-training",
    )

    class FakeAzureArtifactStore:
        def __init__(self, cfg: AzureArtifactConfig) -> None:
            assert cfg == config

        def upload_json(
            self,
            container_name: str,
            blob_name: str,
            payload: dict[str, object],
        ) -> None:
            remote_blobs[(container_name, blob_name)] = json.dumps(payload)

        def upload_text(self, container_name: str, blob_name: str, text: str) -> None:
            remote_blobs[(container_name, blob_name)] = text

    monkeypatch.setattr("repo_rag_lab.utilities.resolve_azure_artifact_config", lambda: config)
    monkeypatch.setattr(
        "repo_rag_lab.runtime_artifacts.AzureArtifactStore",
        FakeAzureArtifactStore,
    )

    _write_bundle_manifest(tmp_path, "older-run", created_at="2026-04-29T00:00:00+00:00")
    _write_bundle_manifest(tmp_path, "newer-run", created_at="2026-04-29T01:00:00+00:00")

    published = json.loads(run_bundle_publish(tmp_path, run_name="older-run"))
    first_promote = json.loads(run_bundle_promote(tmp_path, channel="stable", run_name="older-run"))
    promoted = json.loads(run_bundle_promote(tmp_path, channel="stable", run_name="newer-run"))
    rolled_back = json.loads(run_bundle_rollback(tmp_path, channel="stable"))

    assert published["remote_publish"]["storage_backend"] == "azure-blob"
    assert first_promote["remote_channel"]["remote_channel_blob"] == "channels/stable.json"
    assert promoted["remote_publish"]["storage_backend"] == "azure-blob"
    assert promoted["remote_channel"]["remote_channel_blob"] == "channels/stable.json"
    assert rolled_back["remote_channel"]["remote_channel_blob"] == "channels/stable.json"

    assert ("repo-rag-bundles", "versions/older-run/bundle.json") in remote_blobs
    assert ("repo-rag-bundles", "versions/older-run/program.json") in remote_blobs
    assert ("repo-rag-bundles", "versions/older-run/metadata.json") in remote_blobs
    assert ("repo-rag-bundles", "versions/older-run/published.json") in remote_blobs
    assert ("repo-rag-bundles", "versions/newer-run/bundle.json") in remote_blobs
    assert ("repo-rag-bundles", "versions/newer-run/program.json") in remote_blobs
    assert ("repo-rag-bundles", "versions/newer-run/metadata.json") in remote_blobs
    assert ("repo-rag-bundles", "versions/newer-run/published.json") in remote_blobs
    stable_channel = json.loads(remote_blobs[("repo-rag-bundles", "channels/stable.json")])
    assert stable_channel["current_bundle_version"] == "older-run"


def test_run_bundle_fetch_reports_remote_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repo_rag_lab.utilities.fetch_remote_bundle",
        lambda root, bundle_version=None, channel=None: {
            "bundle_found": True,
            "bundle_version": bundle_version or "stable-run",
            "requested_channel": channel,
            "storage_backend": "azure-blob",
            "cache_dir": "artifacts/dspy/remote/stable-run",
            "bundle_path": "artifacts/dspy/remote/stable-run/bundle.json",
            "metadata_path": "artifacts/dspy/remote/stable-run/metadata.json",
            "program_path": "artifacts/dspy/remote/stable-run/program.json",
            "published_bundle_path": "artifacts/dspy/remote/stable-run/published.json",
        },
    )

    payload = json.loads(run_bundle_fetch(tmp_path, channel="stable"))

    assert payload["command"] == "bundle-fetch"
    assert payload["command_status"] == "success"
    assert payload["storage_backend"] == "azure-blob"
    assert payload["bundle_found"] is True
    assert payload["requested_channel"] == "stable"


def test_run_overlay_init_writes_machine_readable_manifest(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "retrieval-profile.json").write_text(
        '{"retrieval_mode": "idf-rerank"}\n',
        encoding="utf-8",
    )

    payload = json.loads(
        run_overlay_init(
            tmp_path,
            overlay_name="worker overlay",
            bundle_version="bundle-v1",
        )
    )

    assert payload["command"] == "overlay-init"
    assert payload["command_status"] == "success"
    assert payload["overlay_kind"] == "local"
    assert payload["overlay_name"] == "worker-overlay"
    assert payload["bundle_version"] == "bundle-v1"
    assert payload["retrieval_mode"] == "idf-rerank"
    assert payload["overlay_path"] == "artifacts/overlays/worker-overlay/overlay.json"
    assert payload["artifact_metadata"]["generated_paths"] == [
        "artifacts/overlays/worker-overlay",
        "artifacts/overlays/worker-overlay/overlay.json",
    ]


def test_run_trace_export_persists_normalized_record(tmp_path: Path) -> None:
    payload_path = tmp_path / "ask.json"
    payload_path.write_text(
        json.dumps(
            {
                "command": "ask",
                "command_status": "success",
                "root": str(tmp_path),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "question": "What does this repository research?",
                "answer": "Repository answer",
                "response_text": "Question: ...",
                "sources": ["README.md"],
                "context": [
                    {
                        "source": "README.md",
                        "preview": "Context",
                        "text": "Context",
                    }
                ],
                "trace": {
                    "schema_version": 1,
                    "trace_kind": "repo-rag-runtime",
                    "question": "What does this repository research?",
                    "mode": "baseline",
                    "retrieval_mode": "idf-rerank",
                    "sources": ["README.md"],
                    "source_count": 1,
                    "context_count": 1,
                    "context_field": "context",
                    "mcp_candidate_count": 0,
                    "answer_length": 16,
                },
            }
        ),
        encoding="utf-8",
    )

    exported = json.loads(
        run_trace_export(
            tmp_path,
            payload_path=payload_path,
            trace_name="demo trace",
        )
    )

    assert exported["command"] == "trace-export"
    assert exported["command_status"] == "success"
    assert exported["trace_record_kind"] == "repo-rag-trace-record"
    assert exported["trace_storage_kind"] == "exported"
    assert exported["source_command"] == "ask"
    assert exported["question"] == "What does this repository research?"
    assert exported["artifact_metadata"]["input_paths"] == [str(payload_path)]
    trace_record_path = tmp_path / exported["trace_record_path"]
    assert trace_record_path.exists()
    trace_record = json.loads(trace_record_path.read_text(encoding="utf-8"))
    assert trace_record["trace"]["evidence_count"] == 1
    assert len(trace_record["trace"]["evidence_fingerprints"]) == 1


def test_run_trace_import_ingests_external_trace_record(tmp_path: Path) -> None:
    external_trace_path = tmp_path / "external-trace.json"
    outcome_path = tmp_path / "accepted-outcome.json"
    external_trace_path.write_text(
        json.dumps(
            {
                "trace_record_kind": "repo-rag-trace-record",
                "source_command": "ask",
                "source_command_status": "success",
                "question": "Where can you read MCP discovery notes?",
                "sources": ["docs/architecture/mcp-discovery.md"],
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "trace": {
                    "schema_version": 1,
                    "trace_kind": "repo-rag-runtime",
                    "question": "Where can you read MCP discovery notes?",
                    "mode": "baseline",
                    "retrieval_mode": "idf-rerank",
                    "sources": ["docs/architecture/mcp-discovery.md"],
                    "source_count": 1,
                    "context_count": 1,
                    "context_field": "context",
                    "mcp_candidate_count": 0,
                    "answer_length": 42,
                },
            }
        ),
        encoding="utf-8",
    )
    outcome_path.write_text(
        json.dumps(
            {
                "accepted": True,
                "acceptance_status": "accepted",
                "execution_status": "success",
                "method": "repo_rag_cli",
                "backend": "repo_rag_cli",
                "prompt_id": "demo-prompt",
            }
        ),
        encoding="utf-8",
    )

    imported = json.loads(
        run_trace_import(
            tmp_path,
            trace_path=external_trace_path,
            outcome_path=outcome_path,
        )
    )

    assert imported["command"] == "trace-import"
    assert imported["command_status"] == "success"
    assert imported["trace_record_kind"] == "repo-rag-trace-record"
    assert imported["trace_storage_kind"] == "imported"
    assert imported["source_command"] == "ask"
    assert imported["question"] == "Where can you read MCP discovery notes?"
    assert imported["artifact_metadata"]["input_paths"] == [
        str(external_trace_path),
        str(outcome_path),
    ]
    assert imported["outcome"]["accepted"] is True
    assert imported["outcome"]["acceptance_status"] == "accepted"
    imported_path = tmp_path / imported["trace_record_path"]
    assert imported_path.exists()
    assert "artifacts/traces/imported/" in imported["trace_record_path"]


def test_run_trace_enqueue_and_drain_round_trip(tmp_path: Path) -> None:
    external_trace_path = tmp_path / "external-trace.json"
    outcome_path = tmp_path / "accepted-outcome.json"
    external_trace_path.write_text(
        json.dumps(
            {
                "trace_record_kind": "repo-rag-trace-record",
                "source_command": "ask",
                "source_command_status": "success",
                "question": "How do worker traces reach the trainer queue?",
                "sources": ["docs/planning/dataset-integration-plan.md"],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "trace": {
                    "schema_version": 1,
                    "trace_kind": "repo-rag-runtime",
                    "question": "How do worker traces reach the trainer queue?",
                    "mode": "baseline",
                    "retrieval_mode": "idf-rerank",
                    "sources": ["docs/planning/dataset-integration-plan.md"],
                    "source_count": 1,
                    "context_count": 1,
                    "context_field": "context",
                    "mcp_candidate_count": 0,
                    "answer_length": 37,
                },
            }
        ),
        encoding="utf-8",
    )
    outcome_path.write_text(
        json.dumps(
            {
                "acceptance_status": "accepted",
                "accepted": True,
                "execution_status": "success",
            }
        ),
        encoding="utf-8",
    )

    queued = json.loads(
        run_trace_enqueue(
            tmp_path,
            trace_path=external_trace_path,
            outcome_path=outcome_path,
            queue_name="dataset",
            trace_name="worker-demo",
        )
    )

    assert queued["command"] == "trace-enqueue"
    assert queued["command_status"] == "success"
    assert queued["queue_status"] == "queued"
    assert queued["queue_name"] == "dataset"
    queue_item_path = tmp_path / queued["queue_item_path"]
    assert queue_item_path.exists()

    drained = json.loads(run_trace_drain(tmp_path, queue_name="dataset"))

    assert drained["command"] == "trace-drain"
    assert drained["command_status"] == "success"
    assert drained["drained_count"] == 1
    assert drained["failed_count"] == 0
    assert drained["remaining_count"] == 0
    imported_path = tmp_path / drained["items"][0]["imported_trace_record_path"]
    assert imported_path.exists()
    imported_payload = json.loads(imported_path.read_text(encoding="utf-8"))
    assert imported_payload["outcome"]["acceptance_status"] == "accepted"
    processed_item_path = tmp_path / drained["items"][0]["processed_queue_item_path"]
    assert processed_item_path.exists()


def test_versioned_training_run_name_returns_high_resolution_timestamp_only() -> None:
    from repo_rag_lab.utilities import _versioned_training_run_name

    resolved = _versioned_training_run_name(
        "trainer auto",
        recorded_at=datetime(2026, 5, 1, 17, 0, 0, 123456, tzinfo=UTC),
    )

    assert resolved == "20260501T170000123456Z"


def test_run_trainer_cycle_drains_queue_and_promotes_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repo_rag_lab.utilities._versioned_training_run_name",
        lambda run_family, recorded_at=None: "20260501T170000Z",
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.drain_trace_queue",
        lambda root, queue_name="default", limit=None, keep_queued=False: {
            "queue_name": queue_name,
            "queue_found": True,
            "queued_count_before": 1,
            "selected_count": 1,
            "drained_count": 1,
            "failed_count": 0,
            "remaining_count": 0,
            "keep_queued": keep_queued,
            "status": "success",
            "items": [
                {
                    "imported_trace_record_path": "artifacts/traces/imported/demo.json",
                }
            ],
            "failures": [],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.restore_processed_trace_records",
        _restore_processed_trace_records_stub(
            processed_count=1,
            restored_count=1,
            trace_paths=["artifacts/trainer/recovered-imported-traces/demo.json"],
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.load_training_examples",
        lambda path: ["example"],
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.build_retrieval_benchmarks",
        lambda examples: [{"question": "demo"}],
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.evaluate_retrieval_quality_suite",
        lambda root, benchmarks, top_k, top_k_values, retrieval_mode=None: {
            "retrieval_mode": "idf-rerank",
            "default_top_k": 4,
            "default_summary": {
                "top_k": 4,
                "pass_rate": 1.0,
                "source_recall": 1.0,
                "tag_summaries": [],
            },
            "top_k_summaries": [{"top_k": 4, "pass_rate": 1.0, "source_recall": 1.0}],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.check_retrieval_quality_thresholds",
        lambda summary, minimum_pass_rate=None, minimum_source_recall=None: [],
    )

    def fake_materialize_training_candidates(
        root: Path,
        trace_paths: list[Path],
        output_path: Path,
        summary_path: Path,
        include_statuses: tuple[str, ...] = ("accepted", "candidate"),
        seed_existing_output: bool = True,
    ) -> dict[str, object]:
        del root, output_path, summary_path, include_statuses
        assert trace_paths == [Path("artifacts/trainer/recovered-imported-traces/demo.json")]
        assert seed_existing_output is True
        return {
            "candidate_count": 1,
            "new_candidate_count": 1,
            "prompt_family_count": 1,
            "context_group_count": 1,
            "champion_index_path": "artifacts/trainer/champion-index.json",
            "output_path": "artifacts/trainer/training-candidates.yaml",
            "summary_path": "artifacts/trainer/training-candidates-summary.json",
        }

    monkeypatch.setattr(
        "repo_rag_lab.utilities.materialize_training_candidates",
        fake_materialize_training_candidates,
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities._trainer_recompile_payload",
        lambda *args, **kwargs: {
            "recompile_status": "compiled",
            "generated_training": {
                "output_path": "artifacts/trainer/generated-training.yaml",
                "summary_path": "artifacts/trainer/generated-training-summary.json",
            },
            "training_result": {
                "run_name": "20260501T170000Z",
                "bundle_version": "20260501T170000Z",
                "metadata_path": "artifacts/dspy/20260501T170000Z/metadata.json",
                "bundle_path": "artifacts/dspy/20260501T170000Z/bundle.json",
                "benchmark_summary": {"pass_rate": 1.0},
            },
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.resolve_bundle_manifest",
        lambda root, run_name=None, bundle_version=None: (
            root / "artifacts" / "dspy" / (run_name or "demo-run") / "bundle.json",
            {
                "run_name": run_name or "demo-run",
                "bundle_version": bundle_version or run_name or "demo-run",
                "bundle_path": f"artifacts/dspy/{run_name or 'demo-run'}/bundle.json",
                "metadata_path": f"artifacts/dspy/{run_name or 'demo-run'}/metadata.json",
                "benchmark_status": "pass",
                "benchmark_summary": {"pass_rate": 1.0},
            },
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.publish_bundle",
        lambda root, run_name=None, bundle_version=None, note=None: {
            "published_bundle_path": "artifacts/dspy/published/demo.json",
            "bundle_version": run_name or bundle_version or "demo",
            "publish_status": "published",
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.promote_bundle",
        lambda root, channel, run_name=None, bundle_version=None, note=None: {
            "channel_path": f"artifacts/dspy/channels/{channel}.json",
            "current_bundle_version": run_name or bundle_version or "demo",
            "channel_name": channel,
        },
    )

    payload = json.loads(
        run_trainer_cycle(
            tmp_path,
            queue_name="dataset",
            recompile_run_name="trainer-auto",
            promote_channel="stable",
        )
    )

    assert payload["command"] == "trainer-cycle"
    assert payload["command_status"] == "success"
    assert payload["queue_name"] == "dataset"
    assert payload["queue_drain"]["drained_count"] == 1
    assert payload["durable_trace_recovery"]["restored_count"] == 1
    assert payload["training_candidates"]["candidate_count"] == 1
    assert payload["gate_passed"] is True
    assert payload["recompile"]["requested_run_name"] == "trainer-auto"
    assert payload["recompile"]["resolved_run_name"] == "20260501T170000Z"
    assert payload["publish"]["publish_status"] == "published"
    assert payload["promotion_status"] == "promoted"
    assert payload["promotion"]["channel_name"] == "stable"


def test_run_trace_drain_reports_queue_missing_and_failed_item_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repo_rag_lab.utilities.drain_trace_queue",
        lambda root, queue_name="default", limit=None, keep_queued=False: {
            "queue_name": queue_name,
            "queue_found": False,
            "queued_count_before": 1,
            "selected_count": 1,
            "drained_count": 0,
            "failed_count": 1,
            "remaining_count": 1,
            "keep_queued": keep_queued,
            "status": "fail",
            "items": [],
            "failures": [{"path": "artifacts/traces/queued/demo.json"}],
        },
    )

    payload = json.loads(run_trace_drain(tmp_path, queue_name="dataset"))

    assert payload["command"] == "trace-drain"
    assert payload["command_status"] == "fail"
    assert payload["warnings"] == [
        "No queued trace items were available for the requested queue.",
        "One or more queued trace items failed during drain.",
    ]


def test_run_trainer_cycle_blocks_promotion_when_gate_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repo_rag_lab.utilities.drain_trace_queue",
        lambda root, queue_name="default", limit=None, keep_queued=False: {
            "queue_name": queue_name,
            "queue_found": True,
            "queued_count_before": 0,
            "selected_count": 0,
            "drained_count": 0,
            "failed_count": 0,
            "remaining_count": 0,
            "keep_queued": keep_queued,
            "status": "success",
            "items": [],
            "failures": [],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.restore_processed_trace_records",
        _restore_processed_trace_records_stub(
            processed_count=0,
            restored_count=0,
            trace_paths=[],
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.load_training_examples",
        lambda path: ["example"],
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.build_retrieval_benchmarks",
        lambda examples: [{"question": "demo"}],
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.evaluate_retrieval_quality_suite",
        lambda root, benchmarks, top_k, top_k_values, retrieval_mode=None: {
            "retrieval_mode": "idf-rerank",
            "default_top_k": 4,
            "default_summary": {
                "top_k": 4,
                "pass_rate": 0.5,
                "source_recall": 0.5,
                "tag_summaries": [],
            },
            "top_k_summaries": [{"top_k": 4, "pass_rate": 0.5, "source_recall": 0.5}],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.check_retrieval_quality_thresholds",
        lambda summary, minimum_pass_rate=None, minimum_source_recall=None: [
            "minimum_pass_rate not met"
        ],
    )

    def fake_materialize_training_candidates(
        root: Path,
        trace_paths: list[Path],
        output_path: Path,
        summary_path: Path,
        include_statuses: tuple[str, ...] = ("accepted", "candidate"),
        seed_existing_output: bool = True,
    ) -> dict[str, object]:
        del root, trace_paths, output_path, summary_path, include_statuses, seed_existing_output
        return {
            "candidate_count": 0,
            "new_candidate_count": 0,
            "prompt_family_count": 0,
            "context_group_count": 0,
            "champion_index_path": "artifacts/trainer/champion-index.json",
            "output_path": "artifacts/trainer/training-candidates.yaml",
            "summary_path": "artifacts/trainer/training-candidates-summary.json",
        }

    monkeypatch.setattr(
        "repo_rag_lab.utilities.materialize_training_candidates",
        fake_materialize_training_candidates,
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.resolve_bundle_manifest",
        lambda root, run_name=None, bundle_version=None: (
            root / "artifacts" / "dspy" / "demo-run" / "bundle.json",
            {
                "run_name": run_name or "demo-run",
                "bundle_version": bundle_version or run_name or "demo-run",
                "bundle_path": "artifacts/dspy/demo-run/bundle.json",
                "metadata_path": "artifacts/dspy/demo-run/metadata.json",
                "benchmark_status": "pass",
                "benchmark_summary": {"pass_rate": 1.0},
            },
        ),
    )

    payload = json.loads(
        run_trainer_cycle(
            tmp_path,
            queue_name="dataset",
            run_name="demo-run",
            promote_channel="stable",
        )
    )

    assert payload["command"] == "trainer-cycle"
    assert payload["command_status"] == "fail"
    assert payload["gate_passed"] is False
    assert payload["promotion_status"] == "blocked"
    assert payload["promotion"] is None


def test_run_trainer_cycle_blocks_publish_when_bundle_benchmark_gate_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repo_rag_lab.utilities.drain_trace_queue",
        lambda root, queue_name="default", limit=None, keep_queued=False: {
            "queue_name": queue_name,
            "queue_found": True,
            "queued_count_before": 1,
            "selected_count": 1,
            "drained_count": 1,
            "failed_count": 0,
            "remaining_count": 0,
            "keep_queued": keep_queued,
            "status": "success",
            "items": [{"imported_trace_record_path": "artifacts/traces/imported/one.json"}],
            "failures": [],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities._summarize_imported_trace_records", lambda root, paths: {}
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.restore_processed_trace_records",
        _restore_processed_trace_records_stub(
            processed_count=1,
            restored_count=1,
            trace_paths=["artifacts/trainer/recovered-imported-traces/one.json"],
        ),
    )
    monkeypatch.setattr("repo_rag_lab.utilities.load_training_examples", lambda path: ["example"])
    monkeypatch.setattr(
        "repo_rag_lab.utilities.build_retrieval_benchmarks",
        lambda examples: [{"question": "demo"}],
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.evaluate_retrieval_quality_suite",
        lambda root, benchmarks, top_k, top_k_values, retrieval_mode=None: {
            "retrieval_mode": "idf-rerank",
            "default_top_k": 4,
            "default_summary": {
                "top_k": 4,
                "pass_rate": 1.0,
                "source_recall": 1.0,
                "tag_summaries": [],
            },
            "top_k_summaries": [{"top_k": 4, "pass_rate": 1.0, "source_recall": 1.0}],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.check_retrieval_quality_thresholds",
        lambda summary, minimum_pass_rate=None, minimum_source_recall=None: [],
    )

    def fake_materialize_training_candidates(
        root: Path,
        trace_paths: list[Path],
        output_path: Path,
        summary_path: Path,
        include_statuses: tuple[str, ...] = ("accepted", "candidate"),
        seed_existing_output: bool = True,
    ) -> dict[str, object]:
        del root, trace_paths, output_path, summary_path, include_statuses, seed_existing_output
        return {
            "candidate_count": 1,
            "new_candidate_count": 1,
            "prompt_family_count": 1,
            "context_group_count": 1,
            "champion_index_path": "artifacts/trainer/champion-index.json",
            "output_path": "artifacts/trainer/training-candidates.yaml",
            "summary_path": "artifacts/trainer/training-candidates-summary.json",
        }

    monkeypatch.setattr(
        "repo_rag_lab.utilities.materialize_training_candidates",
        fake_materialize_training_candidates,
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities._trainer_recompile_payload",
        lambda *args, **kwargs: {
            "recompile_status": "compiled",
            "generated_training": {
                "output_path": "artifacts/trainer/generated-training.yaml",
                "summary_path": "artifacts/trainer/generated-training-summary.json",
            },
            "training_result": {
                "run_name": "trainer-auto",
                "metadata_path": "artifacts/dspy/trainer-auto/metadata.json",
                "bundle_path": "artifacts/dspy/trainer-auto/bundle.json",
                "benchmark_summary": {"pass_rate": 0.5},
            },
        },
    )

    payload = json.loads(
        run_trainer_cycle(
            tmp_path,
            queue_name="dataset",
            recompile_run_name="trainer-auto",
        )
    )

    assert payload["command"] == "trainer-cycle"
    assert payload["command_status"] == "fail"
    assert payload["gate_passed"] is True
    assert payload["bundle_gate_passed"] is False
    assert payload["bundle_gate"]["status"] == "fail"
    assert payload["publish"] is None
    assert "benchmark gates" in " ".join(payload["warnings"])


def test_run_trainer_cycle_skips_recompile_and_publish_without_new_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repo_rag_lab.utilities.drain_trace_queue",
        lambda root, queue_name="default", limit=None, keep_queued=False: {
            "queue_name": queue_name,
            "queue_found": True,
            "queued_count_before": 0,
            "selected_count": 0,
            "drained_count": 0,
            "failed_count": 0,
            "remaining_count": 0,
            "keep_queued": keep_queued,
            "status": "success",
            "items": [],
            "failures": [],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.restore_processed_trace_records",
        _restore_processed_trace_records_stub(
            processed_count=0,
            restored_count=0,
            trace_paths=[],
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.load_training_examples",
        lambda path: ["example"],
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.build_retrieval_benchmarks",
        lambda examples: [{"question": "demo"}],
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.evaluate_retrieval_quality_suite",
        lambda root, benchmarks, top_k, top_k_values, retrieval_mode=None: {
            "retrieval_mode": "idf-rerank",
            "default_top_k": 4,
            "default_summary": {
                "top_k": 4,
                "pass_rate": 1.0,
                "source_recall": 1.0,
                "tag_summaries": [],
            },
            "top_k_summaries": [{"top_k": 4, "pass_rate": 1.0, "source_recall": 1.0}],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.check_retrieval_quality_thresholds",
        lambda summary, minimum_pass_rate=None, minimum_source_recall=None: [],
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.materialize_training_candidates",
        _materialize_training_candidates_stub(
            candidate_count=1,
            new_candidate_count=0,
            prompt_family_count=1,
            context_group_count=2,
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities._trainer_recompile_payload",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("trainer recompile should not run without new candidates")
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.publish_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("bundle publish should not run without new candidates")
        ),
    )

    payload = json.loads(
        run_trainer_cycle(
            tmp_path,
            queue_name="dataset",
            recompile_run_name="trainer-auto",
        )
    )

    assert payload["command"] == "trainer-cycle"
    assert payload["command_status"] == "success"
    assert payload["training_candidates"]["new_candidate_count"] == 0
    assert payload["recompile"]["recompile_status"] == "skipped-no-new-candidates"
    assert payload["publish_requested"] is False
    assert payload["publish"] is None
    assert payload["bundle_gate"]["status"] == "not-requested"
    assert any("no new training candidates" in warning for warning in payload["warnings"])


def test_run_trainer_cycle_does_not_fail_promotion_without_new_bundle_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repo_rag_lab.utilities.drain_trace_queue",
        lambda root, queue_name="default", limit=None, keep_queued=False: {
            "queue_name": queue_name,
            "queue_found": True,
            "queued_count_before": 0,
            "selected_count": 0,
            "drained_count": 0,
            "failed_count": 0,
            "remaining_count": 0,
            "keep_queued": keep_queued,
            "status": "success",
            "items": [],
            "failures": [],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.restore_processed_trace_records",
        _restore_processed_trace_records_stub(
            processed_count=0,
            restored_count=0,
            trace_paths=[],
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.load_training_examples",
        lambda path: ["example"],
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.build_retrieval_benchmarks",
        lambda examples: [{"question": "demo"}],
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.evaluate_retrieval_quality_suite",
        lambda root, benchmarks, top_k, top_k_values, retrieval_mode=None: {
            "retrieval_mode": "idf-rerank",
            "default_top_k": 4,
            "default_summary": {
                "top_k": 4,
                "pass_rate": 0.5,
                "source_recall": 0.5,
                "tag_summaries": [],
            },
            "top_k_summaries": [{"top_k": 4, "pass_rate": 0.5, "source_recall": 0.5}],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.check_retrieval_quality_thresholds",
        lambda summary, minimum_pass_rate=None, minimum_source_recall=None: ["below-threshold"],
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.materialize_training_candidates",
        _materialize_training_candidates_stub(
            candidate_count=1,
            new_candidate_count=0,
            prompt_family_count=1,
            context_group_count=1,
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities._trainer_recompile_payload",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("trainer recompile should not run without new candidates")
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.publish_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("bundle publish should not run without new candidates")
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.promote_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("bundle promotion should not run without a publish candidate")
        ),
    )

    payload = json.loads(
        run_trainer_cycle(
            tmp_path,
            queue_name="dataset",
            recompile_run_name="trainer-auto",
            promote_channel="stable",
            minimum_pass_rate=1.0,
            minimum_source_recall=1.0,
        )
    )

    assert payload["command_status"] == "success"
    assert payload["gate_passed"] is False
    assert payload["publish_requested"] is False
    assert payload["promotion_requested"] is False
    assert payload["promotion_status"] == "not-requested"
    assert payload["bundle_gate"]["status"] == "not-requested"
    assert not any(
        "Promotion to `stable` was blocked" in warning for warning in payload["warnings"]
    )


def test_run_trainer_cycle_skips_recompile_below_new_candidate_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repo_rag_lab.utilities.drain_trace_queue",
        lambda root, queue_name="default", limit=None, keep_queued=False: {
            "queue_name": queue_name,
            "queue_found": True,
            "queued_count_before": 1,
            "selected_count": 1,
            "drained_count": 1,
            "failed_count": 0,
            "remaining_count": 0,
            "keep_queued": keep_queued,
            "status": "success",
            "items": [{"imported_trace_record_path": "artifacts/traces/imported/one.json"}],
            "failures": [],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.restore_processed_trace_records",
        _restore_processed_trace_records_stub(
            processed_count=1,
            restored_count=1,
            trace_paths=["artifacts/trainer/recovered-imported-traces/one.json"],
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.load_training_examples",
        lambda path: ["example"],
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.build_retrieval_benchmarks",
        lambda examples: [{"question": "demo"}],
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.evaluate_retrieval_quality_suite",
        lambda root, benchmarks, top_k, top_k_values, retrieval_mode=None: {
            "retrieval_mode": "idf-rerank",
            "default_top_k": 4,
            "default_summary": {
                "top_k": 4,
                "pass_rate": 1.0,
                "source_recall": 1.0,
                "tag_summaries": [],
            },
            "top_k_summaries": [{"top_k": 4, "pass_rate": 1.0, "source_recall": 1.0}],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.check_retrieval_quality_thresholds",
        lambda summary, minimum_pass_rate=None, minimum_source_recall=None: [],
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.materialize_training_candidates",
        _materialize_training_candidates_stub(
            candidate_count=2,
            new_candidate_count=1,
            prompt_family_count=1,
            context_group_count=2,
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities._trainer_recompile_payload",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("trainer recompile should not run below the candidate threshold")
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.publish_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("bundle publish should not run below the candidate threshold")
        ),
    )

    payload = json.loads(
        run_trainer_cycle(
            tmp_path,
            queue_name="dataset",
            recompile_run_name="trainer-auto",
            min_new_candidates_for_recompile=2,
        )
    )

    assert payload["command"] == "trainer-cycle"
    assert payload["command_status"] == "success"
    assert payload["training_candidates"]["new_candidate_count"] == 1
    assert payload["min_new_candidates_for_recompile"] == 2
    assert payload["recompile_threshold_met"] is False
    assert payload["recompile"]["recompile_status"] == "skipped-below-new-candidate-threshold"
    assert payload["publish_requested"] is False
    assert payload["publish"] is None
    assert any("minimum threshold" in warning for warning in payload["warnings"])


def test_run_trainer_cycle_uploads_remote_bundle_when_publish_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repo_rag_lab.utilities._versioned_training_run_name",
        lambda run_family, recorded_at=None: "20260501T170100Z",
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.drain_trace_queue",
        lambda root, queue_name="default", limit=None, keep_queued=False: {
            "queue_name": queue_name,
            "queue_found": True,
            "queued_count_before": 1,
            "selected_count": 1,
            "drained_count": 1,
            "failed_count": 0,
            "remaining_count": 0,
            "keep_queued": keep_queued,
            "status": "success",
            "items": [{"imported_trace_record_path": "artifacts/traces/imported/one.json"}],
            "failures": [],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities._summarize_imported_trace_records",
        lambda root, paths: {},
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.restore_processed_trace_records",
        _restore_processed_trace_records_stub(
            processed_count=1,
            restored_count=1,
            trace_paths=["artifacts/trainer/recovered-imported-traces/one.json"],
        ),
    )
    monkeypatch.setattr("repo_rag_lab.utilities.load_training_examples", lambda path: ["example"])
    monkeypatch.setattr(
        "repo_rag_lab.utilities.build_retrieval_benchmarks",
        lambda examples: [{"question": "demo"}],
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.evaluate_retrieval_quality_suite",
        lambda root, benchmarks, top_k, top_k_values, retrieval_mode=None: {
            "retrieval_mode": "idf-rerank",
            "default_top_k": 4,
            "default_summary": {
                "top_k": 4,
                "pass_rate": 1.0,
                "source_recall": 1.0,
                "tag_summaries": [],
            },
            "top_k_summaries": [{"top_k": 4, "pass_rate": 1.0, "source_recall": 1.0}],
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.check_retrieval_quality_thresholds",
        lambda summary, minimum_pass_rate=None, minimum_source_recall=None: [],
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.materialize_training_candidates",
        _materialize_training_candidates_stub(
            candidate_count=1,
            new_candidate_count=1,
            prompt_family_count=1,
            context_group_count=1,
        ),
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities._trainer_recompile_payload",
        lambda *args, **kwargs: {
            "recompile_status": "compiled",
            "generated_training": {
                "output_path": "artifacts/trainer/generated-training.yaml",
                "summary_path": "artifacts/trainer/generated-training-summary.json",
            },
            "training_result": {
                "run_name": "20260501T170100Z",
                "bundle_version": "20260501T170100Z",
                "metadata_path": "artifacts/dspy/20260501T170100Z/metadata.json",
                "bundle_path": "artifacts/dspy/20260501T170100Z/bundle.json",
                "benchmark_summary": {"pass_rate": 1.0},
            },
        },
    )

    monkeypatch.setattr(
        "repo_rag_lab.utilities.publish_bundle",
        lambda *args, **kwargs: {
            "bundle_version": "20260501T170100Z",
            "run_name": "20260501T170100Z",
            "published_bundle_path": "artifacts/dspy/published/20260501T170100Z.json",
            "bundle_path": "artifacts/dspy/20260501T170100Z/bundle.json",
            "metadata_path": "artifacts/dspy/20260501T170100Z/metadata.json",
            "program_path": "artifacts/dspy/20260501T170100Z/program.json",
            "publish_status": "published",
        },
    )
    monkeypatch.setattr(
        "repo_rag_lab.utilities.resolve_azure_artifact_config",
        lambda: AzureArtifactConfig(
            account_name="storage",
            account_key="secret",
            connection_string=None,
            trace_container="repo-rag-training-traces",
            bundle_container="repo-rag-bundles",
            queue_name="repo-rag-training",
        ),
    )

    upload_calls: list[dict[str, object]] = []

    def fake_upload_remote_bundle(
        root: Path,
        *,
        published_record: dict[str, object],
        config: AzureArtifactConfig,
    ) -> dict[str, object]:
        upload_calls.append(
            {
                "root": str(root),
                "bundle_version": published_record["bundle_version"],
                "bundle_container": config.bundle_container,
            }
        )
        return {
            "storage_backend": "azure-blob",
            "bundle_container": config.bundle_container,
            "remote_bundle_blobs": {
                "bundle": "versions/20260501T170100Z/bundle.json",
                "metadata": "versions/20260501T170100Z/metadata.json",
                "program": "versions/20260501T170100Z/program.json",
                "published": "versions/20260501T170100Z/published.json",
            },
        }

    monkeypatch.setattr(
        "repo_rag_lab.utilities.upload_remote_bundle",
        fake_upload_remote_bundle,
    )

    payload = json.loads(
        run_trainer_cycle(
            tmp_path,
            queue_name="dataset",
            recompile_run_name="trainer-auto",
        )
    )

    assert payload["command"] == "trainer-cycle"
    assert payload["command_status"] == "success"
    assert payload["publish_requested"] is True
    assert payload["durable_trace_recovery"]["restored_count"] == 1
    assert payload["recompile"]["requested_run_name"] == "trainer-auto"
    assert payload["recompile"]["resolved_run_name"] == "20260501T170100Z"
    assert payload["publish"]["bundle_version"] == "20260501T170100Z"
    assert payload["publish"]["remote_publish"]["storage_backend"] == "azure-blob"
    assert upload_calls == [
        {
            "root": str(tmp_path),
            "bundle_version": "20260501T170100Z",
            "bundle_container": "repo-rag-bundles",
        }
    ]


def test_run_trainer_candidates_materializes_yaml_from_imported_traces(tmp_path: Path) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    trace_record_path = imported_dir / "accepted-trace.json"
    trace_record_path.write_text(
        json.dumps(
            {
                "trace_record_kind": "repo-rag-trace-record",
                "trace_record_path": "artifacts/traces/imported/accepted-trace.json",
                "source_command": "ask",
                "question": "How do you build the publication PDF locally?",
                "answer": "Run make paper-build.",
                "sources": ["README.md", "publication/README.md"],
                "trace": {
                    "schema_version": 1,
                    "trace_kind": "repo-rag-runtime",
                    "recorded_at": "2026-04-29T00:00:00+00:00",
                    "question": "How do you build the publication PDF locally?",
                    "mode": "baseline",
                    "retrieval_mode": "idf-rerank",
                    "bundle_version": "stable-v1",
                    "overlay_path": "artifacts/overlays/default/overlay.json",
                    "sources": ["README.md", "publication/README.md"],
                    "source_count": 2,
                    "context_count": 2,
                    "context_field": "context",
                    "mcp_candidate_count": 0,
                    "answer_length": 20,
                },
                "outcome": {
                    "acceptance_status": "accepted",
                    "accepted": True,
                    "execution_status": "success",
                    "method": "dspy",
                    "backend": "repo_rag_cli",
                    "used_baseline_fallback": False,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = json.loads(run_trainer_candidates(tmp_path))

    assert payload["command"] == "trainer-candidates"
    assert payload["command_status"] == "success"
    assert payload["candidate_count"] == 1
    assert payload["new_candidate_count"] == 1
    output_path = tmp_path / payload["output_path"]
    summary_path = tmp_path / payload["summary_path"]
    champion_index_path = tmp_path / payload["champion_index_path"]
    assert output_path.exists()
    assert summary_path.exists()
    assert champion_index_path.exists()
    materialized = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    assert materialized[0]["question"] == "How do you build the publication PDF locally?"
    assert materialized[0]["expected_sources"] == []
    assert materialized[0]["candidate_status"] == "accepted"
    assert materialized[0]["provenance"]["observed_sources"] == [
        "README.md",
        "publication/README.md",
    ]
    champion_index = json.loads(champion_index_path.read_text(encoding="utf-8"))
    assert champion_index["record_kind"] == "repo-rag-trainer-champion-index"


def test_run_trainer_recompile_merges_candidates_and_reports_training_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repo_rag_lab.utilities.materialize_combined_training_examples",
        lambda root, base_training_path, candidates_path, output_path, summary_path: {
            "base_example_count": 8,
            "candidate_example_count": 2,
            "combined_example_count": 10,
            "new_candidate_count": 2,
            "duplicate_candidate_count": 0,
            "base_training_path": str(base_training_path),
            "candidates_path": str(candidates_path),
            "output_path": str(output_path),
            "summary_path": str(summary_path),
        },
    )

    class FakeTrainingResult:
        def to_payload(self) -> dict[str, object]:
            return {
                "run_name": "trainer-auto",
                "program_path": "artifacts/dspy/trainer-auto/program.json",
                "metadata_path": "artifacts/dspy/trainer-auto/metadata.json",
                "bundle_path": "artifacts/dspy/trainer-auto/bundle.json",
            }

    monkeypatch.setattr(
        "repo_rag_lab.utilities.train_repository_program",
        lambda root, training_config, lm_config: FakeTrainingResult(),
    )

    payload = json.loads(
        run_trainer_recompile(
            tmp_path,
            run_name="trainer-auto",
            lm_config=DSPyLMConfig(model="openai/test"),
        )
    )

    assert payload["command"] == "trainer-recompile"
    assert payload["command_status"] == "success"
    assert payload["recompile_status"] == "compiled"
    assert payload["generated_training"]["combined_example_count"] == 10
    assert payload["training_result"]["run_name"] == "trainer-auto"


def test_run_trainer_service_writes_state_and_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle_payloads = iter(
        [
            {
                "command": "trainer-cycle",
                "command_status": "success",
                "root": str(tmp_path),
                "warnings": [],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "queue_name": "dataset",
                "queue_drain": {
                    "drained_count": 1,
                    "failed_count": 0,
                    "items": [{"imported_trace_record_path": "artifacts/traces/imported/one.json"}],
                },
                "ingestion_summary": {
                    "acceptance_status_counts": {"accepted": 1},
                    "execution_status_counts": {"success": 1},
                    "retrieval_mode_counts": {"idf-rerank": 1},
                    "bundle_version_counts": {"stable-v1": 1},
                    "missing_source_count": 0,
                    "missing_context_count": 0,
                    "source_error_count": 0,
                    "used_baseline_fallback_count": 1,
                    "invalid_record_count": 0,
                },
                "gate_passed": True,
                "bundle_gate_passed": True,
                "training_candidates": {
                    "candidate_count": 1,
                    "new_candidate_count": 1,
                    "prompt_family_count": 1,
                    "context_group_count": 2,
                    "champion_index_path": "artifacts/trainer/champion-index.json",
                },
                "publish": {"published_bundle_path": "artifacts/dspy/published/demo.json"},
                "promotion": {"channel_path": "artifacts/dspy/channels/stable.json"},
            },
            {
                "command": "trainer-cycle",
                "command_status": "success",
                "root": str(tmp_path),
                "warnings": ["No queued trace items were available for this trainer cycle."],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "queue_name": "dataset",
                "queue_drain": {
                    "drained_count": 0,
                    "failed_count": 0,
                    "items": [],
                },
                "ingestion_summary": {
                    "acceptance_status_counts": {},
                    "execution_status_counts": {},
                    "retrieval_mode_counts": {},
                    "bundle_version_counts": {},
                    "missing_source_count": 1,
                    "missing_context_count": 1,
                    "source_error_count": 0,
                    "used_baseline_fallback_count": 0,
                    "invalid_record_count": 0,
                },
                "gate_passed": True,
                "bundle_gate_passed": True,
                "training_candidates": {
                    "candidate_count": 1,
                    "new_candidate_count": 0,
                    "prompt_family_count": 1,
                    "context_group_count": 2,
                    "champion_index_path": "artifacts/trainer/champion-index.json",
                },
                "publish": None,
                "promotion": None,
            },
        ]
    )

    monkeypatch.setattr(
        "repo_rag_lab.utilities.run_trainer_cycle",
        lambda *args, **kwargs: json.dumps(next(cycle_payloads)),
    )

    payload = json.loads(
        run_trainer_service(
            tmp_path,
            queue_name="dataset",
            poll_interval_seconds=0,
            max_idle_cycles=1,
        )
    )

    assert payload["command"] == "trainer-service"
    assert payload["command_status"] == "success"
    assert payload["stop_reason"] == "max-idle-cycles"
    assert payload["cycles_executed"] == 2
    assert payload["total_drained_count"] == 1
    assert payload["total_publish_count"] == 1
    assert payload["total_promotion_count"] == 1
    assert payload["bundle_gate_failure_count"] == 0
    assert payload["total_prompt_family_count"] == 1
    assert payload["total_context_group_count"] == 2
    assert payload["acceptance_status_totals"] == {"accepted": 1}
    assert payload["execution_status_totals"] == {"success": 1}
    assert payload["used_baseline_fallback_count"] == 1
    assert payload["missing_source_count"] == 1
    assert payload["missing_context_count"] == 1
    assert payload["state_path"] == "artifacts/trainer/service-state.json"
    assert payload["history_dir"] == "artifacts/trainer/history"
    assert payload["latest_cycle_record_path"] is not None
    assert (tmp_path / payload["state_path"]).exists()
    history_files = sorted((tmp_path / payload["history_dir"]).glob("*.json"))
    assert len(history_files) == 2
    state_payload = json.loads((tmp_path / payload["state_path"]).read_text(encoding="utf-8"))
    assert state_payload["cycles_executed"] == 2
    assert state_payload["last_cycle_command_status"] == "success"
    assert state_payload["total_prompt_family_count"] == 1
    assert state_payload["total_context_group_count"] == 2


def test_run_trainer_service_reports_failed_cycles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repo_rag_lab.utilities.run_trainer_cycle",
        lambda *args, **kwargs: json.dumps(
            {
                "command": "trainer-cycle",
                "command_status": "fail",
                "root": str(tmp_path),
                "warnings": ["Bundle promotion failed during trainer cycle."],
                "artifact_metadata": {
                    "input_paths": [],
                    "generated_paths": [],
                    "related_paths": [],
                },
                "queue_name": "dataset",
                "queue_drain": {
                    "drained_count": 1,
                    "failed_count": 1,
                    "items": [],
                },
                "gate_passed": False,
                "bundle_gate_passed": False,
                "publish": None,
                "promotion": None,
            }
        ),
    )

    payload = json.loads(
        run_trainer_service(
            tmp_path,
            queue_name="dataset",
            poll_interval_seconds=0,
            max_cycles=1,
        )
    )

    assert payload["command"] == "trainer-service"
    assert payload["command_status"] == "fail"
    assert payload["failed_cycle_count"] == 1
    assert payload["gate_failure_count"] == 1
    assert payload["bundle_gate_failure_count"] == 1
    assert "One or more trainer cycles failed during service execution." in payload["warnings"]


def test_run_todo_backlog_sync_reports_expected_fields() -> None:
    payload = json.loads(run_todo_backlog_sync(REPO_ROOT))
    assert payload["command"] == "sync-todo-backlog"
    assert payload["command_status"] == "success"
    assert payload["source_path"] == "todo-backlog.yaml"
    assert payload["markdown_path"] == "TODO.MD"
    assert payload["latex_path"] == "publication/todo-backlog-table.tex"
    assert payload["item_count"] >= 10


def test_run_azure_openai_probe_returns_machine_readable_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_probe(root: Path, *, load_env_file: bool = False) -> dict[str, object]:
        return {
            "provider": "azure-openai",
            "root": str(root),
            "load_env_file": load_env_file,
            "reply": "OPENAI_OK",
        }

    monkeypatch.setattr("repo_rag_lab.utilities.probe_azure_openai", fake_probe)
    payload = json.loads(run_azure_openai_probe(REPO_ROOT, load_env_file=True))
    assert payload["command"] == "azure-openai-probe"
    assert payload["command_status"] == "success"
    assert payload["provider"] == "azure-openai"
    assert payload["load_env_file"] is True
    assert payload["reply"] == "OPENAI_OK"


def test_run_azure_inference_probe_returns_machine_readable_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_probe(root: Path, *, load_env_file: bool = False) -> dict[str, object]:
        return {
            "provider": "azure-inference",
            "root": str(root),
            "load_env_file": load_env_file,
            "reply": "INFERENCE_OK",
        }

    monkeypatch.setattr("repo_rag_lab.utilities.probe_azure_inference", fake_probe)
    payload = json.loads(run_azure_inference_probe(REPO_ROOT, load_env_file=True))
    assert payload["command"] == "azure-inference-probe"
    assert payload["command_status"] == "success"
    assert payload["provider"] == "azure-inference"
    assert payload["load_env_file"] is True
    assert payload["reply"] == "INFERENCE_OK"


def test_run_file_summary_sync_reports_expected_fields() -> None:
    markdown_path = REPO_ROOT / "FILES.md"
    csv_path = REPO_ROOT / "FILES.csv"
    original_markdown = markdown_path.read_text(encoding="utf-8")
    original_csv = csv_path.read_text(encoding="utf-8")

    try:
        payload = json.loads(run_file_summary_sync(REPO_ROOT))
        assert payload["command"] == "sync-file-summaries"
        assert payload["command_status"] == "success"
        assert payload["markdown_path"] == "FILES.md"
        assert payload["csv_path"] == "FILES.csv"
        assert payload["guide_path"] == "AGENTS.md.d/FILES.md"
        assert payload["tracked_file_count"] >= 10
    finally:
        markdown_path.write_text(original_markdown, encoding="utf-8")
        csv_path.write_text(original_csv, encoding="utf-8")


def test_run_exploratorium_translation_sync_reports_expected_fields(tmp_path: Path) -> None:
    _write_demo_repo_for_exploratorium(tmp_path)

    payload = json.loads(run_exploratorium_translation_sync(tmp_path))
    assert payload["command"] == "sync-exploratorium-translation"
    assert payload["command_status"] == "success"
    assert (
        payload["tex_path"]
        == "publication/exploratorium_translation/generated/exploratorium-content.tex"
    )
    assert (
        payload["manifest_path"]
        == "publication/exploratorium_translation/generated/exploratorium-manifest.json"
    )
    assert (
        payload["main_tex_path"]
        == "publication/exploratorium_translation/exploratorium_translation.tex"
    )
    assert (
        payload["pdf_path"] == "publication/exploratorium_translation/exploratorium_translation.pdf"
    )
    assert payload["summarized_file_count"] >= 5


def test_run_github_pr_gate_sync_returns_machine_readable_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_sync_github_pr_gates(
        root: Path,
        *,
        branch: str = "master",
        repo: str | None = None,
        apply: bool = False,
    ) -> dict[str, object]:
        return {
            "repo": repo or "realagiorganization/dspy_rag_in_repo_docs_and_impl1",
            "branch": branch,
            "mode": "apply" if apply else "dry-run",
            "required_checks": [
                "Python Quality, Tests, And Build",
                "Rust Wrapper",
                "Build Publication PDF",
                "Hushwheel Fixture Quality",
            ],
            "root": str(root),
        }

    monkeypatch.setattr("repo_rag_lab.utilities.sync_github_pr_gates", fake_sync_github_pr_gates)
    payload = json.loads(
        run_github_pr_gate_sync(
            REPO_ROOT,
            branch="master",
            repo="realagiorganization/dspy_rag_in_repo_docs_and_impl1",
            apply=True,
        )
    )
    assert payload["command"] == "sync-github-pr-gates"
    assert payload["command_status"] == "success"
    assert payload["repo"] == "realagiorganization/dspy_rag_in_repo_docs_and_impl1"
    assert payload["branch"] == "master"
    assert payload["mode"] == "apply"
    assert payload["required_checks"] == [
        "Python Quality, Tests, And Build",
        "Rust Wrapper",
        "Build Publication PDF",
        "Hushwheel Fixture Quality",
    ]


def test_run_pages_site_sync_returns_machine_readable_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_sync_pages_site(
        root: Path,
        *,
        output_dir: Path,
        branch: str = "master",
        repo_url: str | None = None,
    ) -> dict[str, object]:
        return {
            "output_dir": str(output_dir),
            "page_count": 12,
            "branch": branch,
            "repo_url": repo_url,
            "root": str(root),
        }

    monkeypatch.setattr("repo_rag_lab.utilities.sync_pages_site", fake_sync_pages_site)
    payload = json.loads(
        run_pages_site_sync(
            REPO_ROOT,
            output_dir=Path("artifacts/pages_docs"),
            branch="master",
            repo_url="https://github.com/example/demo",
        )
    )
    assert payload["command"] == "sync-pages-site"
    assert payload["command_status"] == "success"
    assert payload["output_dir"] == "artifacts/pages_docs"
    assert payload["page_count"] == 12
    assert payload["branch"] == "master"
    assert payload["repo_url"] == "https://github.com/example/demo"


def test_run_notebook_report_returns_machine_readable_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_notebooks(root: Path, **_: object) -> dict[str, object]:
        return {
            "root": str(root),
            "run_id": "sample",
            "status": "success",
            "failure_count": 0,
            "notebook_count": 1,
            "notebooks": [],
        }

    monkeypatch.setattr("repo_rag_lab.utilities.run_notebooks", fake_run_notebooks)
    payload = json.loads(run_notebook_report(REPO_ROOT))
    assert payload["command"] == "run-notebooks"
    assert payload["command_status"] == "success"
    assert payload["status"] == "success"
    assert payload["failure_count"] == 0
