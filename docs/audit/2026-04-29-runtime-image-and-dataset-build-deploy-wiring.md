# 2026-04-29 Runtime Image And Dataset Build/Deploy Wiring

## Summary

This audit records the new packaging and deployment layer that turns the repository from a purely
repo-local runtime into a containerized runtime that `../dataset` can build, ship, and deploy.

The key changes in this turn are:

- the repository now ships its own runtime image definition in the repository-root `Dockerfile`
- that image keeps an editable checkout under `/workspace/repo-rag`, so `repo-rag` can be
  preinstalled in worker and trainer containers without breaking path-sensitive features such as
  the Rust lookup wrapper
- `../dataset/build_and_push_images.sh` now builds and pushes `repo-rag-runtime` in addition to
  `prompt-executor` and `queue-initializer`
- `../dataset/docker/prompt-executor/Dockerfile` now accepts a `REPO_RAG_RUNTIME_IMAGE` base image
  and exports `DATASET_REPO_RAG_PROJECT_ROOT=/workspace/repo-rag` plus
  `DATASET_REPO_RAG_COMMAND=repo-rag`
- `../dataset/deploy_repo_rag_trainer.sh` now provides a concrete AKS deployment helper for the
  trainer-side workload
- `../dataset` now carries submodule metadata for:
  - `submodules/dspy_rag_in_repo_docs_and_impl1`
  - `submodules/dataset_website`

One important correction emerged during implementation: the remote
`realagiorganization/dspy_rag_in_repo_docs_and_impl1` repository currently does not expose
`main`. The `dataset_website` submodule tracks `main`, but the repo-RAG submodule now tracks
`develop` so the integration repository can point at the branch where the runtime-image and
trainer-deployment work actually lands.

## Code And Documentation Changes

Changes in this repository:

- added the runtime image definition in:
  - `Dockerfile`
  - `.dockerignore`
- updated trainer-side Kubernetes manifest generation in:
  - `src/repo_rag_lab/trainer_deployment.py`
  - `src/repo_rag_lab/utilities.py`
  - `src/repo_rag_lab/cli.py`
- added and updated runtime/deployment docs in:
  - `docs/operations/runtime-image.md`
  - `docs/operations/trainer-deployment.md`
  - `docs/architecture/research-narrative.md`
  - `README.md`
- updated regression coverage in:
  - `tests/test_utilities.py`
  - `tests/test_cli_and_dspy.py`

Changes in `../dataset`:

- updated the worker image definition in:
  - `docker/prompt-executor/Dockerfile`
- updated image build orchestration in:
  - `build_and_push_images.sh`
- added the trainer deployment helper in:
  - `deploy_repo_rag_trainer.sh`
- added submodule metadata in:
  - `.gitmodules`
- updated operator docs in:
  - `README.md`
  - `USAGE.md`
  - `agents.md`
  - `agents.md.d/roadmap.md`

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

- `uv run python -m compileall src tests`
- `cargo build --manifest-path rust-cli/Cargo.toml`
- `uv run pytest tests/test_utilities.py tests/test_cli_and_dspy.py tests/test_repository_rag_bdd.py`
- `uv run repo-rag smoke-test`
- `bash -n ../dataset/build_and_push_images.sh`
- `bash -n ../dataset/deploy_repo_rag_trainer.sh`
- `git -C ../dataset submodule status`
- `make files-sync`
- `make exploratorium-sync`
- `make verify-surfaces`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`

Observed results:

- `uv run python -m compileall src tests`:
  passed
- `cargo build --manifest-path rust-cli/Cargo.toml`:
  passed
- `uv run pytest tests/test_utilities.py tests/test_cli_and_dspy.py tests/test_repository_rag_bdd.py`:
  passed, `65 passed`
- `uv run repo-rag smoke-test`:
  passed with `command_status: "success"` and `answer_contains_repository: true`
- `bash -n ../dataset/build_and_push_images.sh`:
  passed
- `bash -n ../dataset/deploy_repo_rag_trainer.sh`:
  passed
- `git -C ../dataset submodule status`:
  passed; both submodule entries are present, with `dataset_website` initialized and the repo-RAG
  submodule staged for the repo-local integration branch
- `make files-sync`:
  passed
- `make exploratorium-sync`:
  passed
- `make verify-surfaces`:
  passed with `issue_count: 0`
- `uv run pytest tests/test_file_summaries.py tests/test_exploratorium_translation.py tests/test_project_surfaces.py`:
  passed, `28 passed`

Verification categories not executed in this turn:

- full Docker image builds for `repo-rag-runtime`, `prompt-executor`, or `queue-initializer`
- live `az acr build` or Docker pushes
- live AKS apply through `deploy_repo_rag_trainer.sh`
- standalone `make quality`
- standalone `make coverage`
- `../dataset` Python/unit suites beyond shell syntax and submodule wiring

## Status Impact

- The repo-RAG runtime is now packaged as a real container image source, not just as a Python CLI.
- `dataset` now has a first-class place to build and push that runtime image.
- Trainer deployment is no longer only a manifest generator inside this repository; `dataset` now
  also has a concrete AKS deployment helper for that workload.
- The worker container path now has a documented route to preinstalled `repo-rag` instead of
  relying only on sibling checkouts or launcher overrides.
- The repo-to-repo relationship is now visible in `dataset` through submodule metadata, with one
  explicit caveat: repo-RAG still does not expose `main`, so the submodule currently tracks
  `develop`.
