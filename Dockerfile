ARG PYTHON_BASE_IMAGE=python:3.11-slim-bookworm

FROM ${PYTHON_BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    REPO_RAG_PROJECT_ROOT=/workspace/repo-rag \
    DATASET_REPO_RAG_PROJECT_ROOT=/workspace/repo-rag \
    DATASET_REPO_RAG_COMMAND=repo-rag

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    cargo \
    ca-certificates \
    git \
    make \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip uv

WORKDIR /workspace/repo-rag

COPY AGENTS.md README.md Makefile pyproject.toml uv.lock ./
COPY config ./config
COPY data ./data
COPY docs ./docs
COPY publication ./publication
COPY rust-cli ./rust-cli
COPY samples/training ./samples/training
COPY src ./src
COPY utilities ./utilities

RUN python -m pip install -e ".[azure]"

RUN mkdir -p \
    artifacts/dspy \
    artifacts/kubernetes \
    artifacts/sqlite \
    artifacts/traces \
    artifacts/trainer

CMD ["repo-rag", "utility-summary"]
