# 2026-04-29 Trainer Kubernetes Deployment Surface

## Summary

This audit records the next deployment-oriented step after trainer-side bundle benchmark gates: the
repository now exposes a concrete Kubernetes packaging surface for the trainer runtime instead of
leaving AKS/CronJob deployment as an implied future wrapper.

- `repo-rag trainer-k8s-manifests` now materializes Kubernetes manifests for:
  - a ServiceAccount
  - a ConfigMap
  - an example Secret
  - a `trainer-service` Deployment
  - a `trainer-cycle` CronJob
- The generated manifests use one shared repo-RAG runtime image plus PVC-backed `artifacts/`
  storage, keeping worker and trainer roles separate without Docker-in-Docker.
- During verification a real repo-native bug surfaced: `make trainer-k8s-manifests` passed an
  empty `--service-max-idle-cycles` flag when the variable was unset. The Makefile was fixed in
  the same turn and the target now passes.
- The local shell still only exposed `AZURE_OPENAI_API_KEY`, so live trainer-side recompilation in
  a Kubernetes-like environment remained blocked on missing endpoint/deployment/API-version
  variables.

## Code And Documentation Changes

Changes landed in this repository:

- added Kubernetes manifest generation helpers in:
  - `src/repo_rag_lab/trainer_deployment.py`
- exposed the new surface in:
  - `src/repo_rag_lab/utilities.py`
  - `src/repo_rag_lab/cli.py`
  - `Makefile`
  - `src/repo_rag_lab/verification.py`
- added coverage for manifest generation and CLI wiring in:
  - `tests/test_utilities.py`
  - `tests/test_cli_and_dspy.py`
- added trainer deployment operations guidance in:
  - `docs/operations/trainer-deployment.md`
- updated operator, API, DSPy, narrative, planning, and Azure handoff docs in:
  - `README.md`
  - `docs/architecture/package-api.md`
  - `docs/architecture/dspy-rag-guide.md`
  - `docs/architecture/research-narrative.md`
  - `docs/planning/dataset-integration-plan.md`
  - `docs/operations/azure-deployment.md`
  - `docs/audit/README.md`

No `../dataset` runtime code changed in this turn. The work stayed in the repo-RAG repository and
extended the trainer-side deployment surface.

## Verification

Configured verification surfaces in this repository still include:

- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make files-sync`
- `make exploratorium-sync`
- `make verify-surfaces`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

Commands executed locally on `2026-04-29` for this turn:

- `env | rg '^(DSPY_|AZURE_OPENAI_|OPENAI_API_KEY)'`
- `uv run python -m compileall src tests`
- `uv run pytest tests/test_utilities.py tests/test_cli_and_dspy.py`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag trainer-k8s-manifests --root . --image ghcr.io/example/repo-rag:latest --output json`
- `make trainer-k8s-manifests TRAINER_K8S_IMAGE=ghcr.io/example/repo-rag:latest`
- `uv run repo-rag smoke-test`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `make files-sync`
- `make exploratorium-sync`
- `make verify-surfaces`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

Observed results:

- `env | rg '^(DSPY_|AZURE_OPENAI_|OPENAI_API_KEY)'`:
  showed only `AZURE_OPENAI_API_KEY`; no local endpoint, deployment-name, or API-version
  variables were present for a bounded live trainer-side recompilation run
- `uv run python -m compileall src tests`: passed
- `uv run pytest tests/test_utilities.py tests/test_cli_and_dspy.py`:
  passed, `60 passed`
- `uv run pytest tests/test_utilities.py tests/test_repository_rag_bdd.py`:
  passed, `33 passed`
- `uv run repo-rag trainer-k8s-manifests --root . --image ghcr.io/example/repo-rag:latest --output json`:
  passed with `command_status: "success"` and generated five manifests under
  `artifacts/kubernetes/`
- first `make trainer-k8s-manifests TRAINER_K8S_IMAGE=ghcr.io/example/repo-rag:latest` run:
  failed because an empty `--service-max-idle-cycles` flag was passed through the Makefile
- after the Makefile fix, `make trainer-k8s-manifests TRAINER_K8S_IMAGE=ghcr.io/example/repo-rag:latest`:
  passed and produced the same manifest set
- `uv run repo-rag smoke-test`:
  passed with `command_status: "success"` and `answer_contains_repository: true`
- `cargo build --manifest-path rust-cli/Cargo.toml`: passed
- `make files-sync`:
  passed and refreshed `FILES.md`, `FILES.csv`, and `AGENTS.md.d/FILES.md`
- `make exploratorium-sync`:
  passed and refreshed the exploratorium translation TeX, manifest, and PDF surfaces
- `make verify-surfaces`:
  passed with `issue_count: 0`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`:
  passed, `28 passed`

Verification categories not executed in this turn:

- no live Kubernetes deployment
- no live `repo-rag trainer-recompile` run because the local LM environment remained incomplete
- no `make quality` or `make coverage`
- no `../dataset` worker or AKS deployment run

## Status Impact

- Phase 5 of `docs/planning/dataset-integration-plan.md` is now materially closed except for
  central-inference strategy:
  - shared runtime image family: done
  - separate worker vs. trainer roles: done
  - shared-storage/PVC-backed artifact story: done
  - central inference placement: still pending
- The integration path is now documented and packaged well enough to move from local-only trainer
  loops toward Kubernetes worker pools, even though live AKS validation is still pending.
- The next practical work items are now:
  - decide whether the long-term inference layer stays external or becomes a shared internal
    service
  - add bounded live validation once the local shell exposes full Azure/OpenAI DSPy runtime
    metadata, not only an API key
