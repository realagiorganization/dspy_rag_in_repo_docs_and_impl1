"""Azure deployment manifest helpers for downstream release workflows."""

from __future__ import annotations

import json
from pathlib import Path


def _relative_path_text(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def write_deployment_manifest(
    root: Path, model_id: str, deployment_name: str, endpoint: str
) -> Path:
    """Write a small Azure deployment manifest under ``artifacts/azure``."""

    output_dir = root / "artifacts" / "azure"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "model_id": model_id,
        "deployment_name": deployment_name,
        "endpoint": endpoint,
        "notes": [
            "Provision the fine-tuned model in Azure AI Foundry or Azure OpenAI first.",
            (
                "Use this deployment name as the model selector when calling the Azure "
                "inference endpoint."
            ),
            "Keep endpoint, API version, and credentials outside source control.",
        ],
        "environment_variables": [
            "AZURE_INFERENCE_ENDPOINT",
            "AZURE_INFERENCE_CREDENTIAL",
            "AZURE_OPENAI_API_VERSION",
        ],
    }
    output_path = output_dir / f"{deployment_name}.json"
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output_path


def write_tuning_run_metadata(
    root: Path,
    run_name: str,
    training_data_path: Path,
    benchmark_summary: dict[str, object],
    deployment_name: str,
) -> Path:
    """Write notebook-oriented tuning metadata alongside Azure deployment manifests."""

    output_dir = root / "artifacts" / "azure" / "tuning"
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_name": run_name,
        "training_data_path": _relative_path_text(root, training_data_path),
        "recommended_deployment_name": deployment_name,
        "benchmark_summary": benchmark_summary,
        "notes": [
            "Capture benchmark results before promoting a tuned DSPy program.",
            "Keep Azure credentials and runtime endpoint configuration outside source control.",
            (
                "Store tuned-program metadata next to deployment manifests for "
                "notebook reproducibility."
            ),
        ],
    }
    output_path = output_dir / f"{run_name}.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path
