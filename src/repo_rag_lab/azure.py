from __future__ import annotations

import json
from pathlib import Path


def write_deployment_manifest(
    root: Path, model_id: str, deployment_name: str, endpoint: str
) -> Path:
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
