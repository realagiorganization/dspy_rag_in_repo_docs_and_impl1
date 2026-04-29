# Runtime Image Notes

This repository now ships its own runtime image definition in the repository-root
[Dockerfile](../../Dockerfile). The image is intended to serve two roles:

- a lightweight trainer/runtime image for `trainer-service`, `trainer-cycle`, and
  `trainer-recompile`
- a reusable base layer for downstream worker images that need a preinstalled `repo-rag` CLI

## Packaging Model

- The image keeps a full editable checkout at `/workspace/repo-rag`.
- `repo-rag-lab` is installed in editable mode, so path-sensitive features such as
  `src/repo_rag_lab/rust_lookup.py` can still find `rust-cli/Cargo.toml`.
- The image exports:
  - `REPO_RAG_PROJECT_ROOT=/workspace/repo-rag`
  - `DATASET_REPO_RAG_PROJECT_ROOT=/workspace/repo-rag`
  - `DATASET_REPO_RAG_COMMAND=repo-rag`

Those defaults let `../dataset` call `repo-rag` as a preinstalled package while still preserving
the repo-root assumptions that parts of the runtime use internally.

## Build Context

This repository does not build or push the image by itself. The intended build orchestrator is the
`../dataset` repository:

- `../dataset/build_and_push_images.sh` now builds and pushes `repo-rag-runtime`
- it prefers the `dataset` submodule path `submodules/dspy_rag_in_repo_docs_and_impl1`
- when that submodule is absent locally, it can fall back to the sibling checkout
  `../dspy_rag_in_repo_docs_and_impl1`

That keeps `dataset` as the place where image tags and ACR pushes are coordinated, while this
repository remains the source of truth for the runtime image contents.

## Trainer Use

The generated Kubernetes trainer manifests expect the image to contain the repo checkout at
`/workspace/repo-rag` and the `repo-rag` CLI on `PATH`. They now invoke direct commands such as:

- `repo-rag trainer-service ...`
- `repo-rag trainer-cycle ...`

instead of `make trainer-service` inside the pod. That avoids runtime `uv sync` churn and keeps
the container behavior closer to an immutable runtime image model.
