UV ?= uv
QUESTION ?= What does this repository research?
MODEL_ID ?= sample-ft-model
DEPLOYMENT_NAME ?= repo-rag-ft
AZURE_ENDPOINT ?= https://example.services.ai.azure.com/models

.PHONY: setup sync lock ask discover-mcp utility-summary smoke-test notebook bdd rust-cli-build rust-cli-run azure-manifest fmt test lint typecheck complexity quality build publish

setup:
	$(UV) sync --extra azure

sync:
	$(UV) sync --extra azure

lock:
	$(UV) lock

ask: sync
	$(UV) run repo-rag ask --question "$(QUESTION)"

discover-mcp: sync
	$(UV) run repo-rag discover-mcp

utility-summary: sync
	$(UV) run repo-rag utility-summary

smoke-test: sync
	$(UV) run repo-rag smoke-test

notebook: sync
	$(UV) run jupyter lab notebooks/01_repo_rag_research.ipynb

bdd: sync
	$(UV) run pytest tests -k repository_rag

test: sync
	$(UV) run pytest

lint: sync
	RUFF_CACHE_DIR=.ruff_cache $(UV) run ruff check src tests

typecheck: sync
	MYPY_CACHE_DIR=.mypy_cache $(UV) run mypy src

complexity: sync
	$(UV) run radon cc src/repo_rag_lab -s -n B

quality: lint typecheck complexity test

rust-cli-build:
	cargo build --manifest-path rust-cli/Cargo.toml

rust-cli-run:
	cargo run --manifest-path rust-cli/Cargo.toml -- ask --question "$(QUESTION)"

azure-manifest: sync
	$(UV) run repo-rag azure-manifest --model-id "$(MODEL_ID)" --deployment-name "$(DEPLOYMENT_NAME)" --endpoint "$(AZURE_ENDPOINT)"

fmt: sync
	$(UV) run ruff format src tests

build: sync
	$(UV) build

publish: build
	$(UV) publish

compile: sync
	$(UV) run python -m compileall src tests
