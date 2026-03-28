UV ?= uv
QUESTION ?= What does this repository research?
MODEL_ID ?= sample-ft-model
DEPLOYMENT_NAME ?= repo-rag-ft
AZURE_ENDPOINT ?= https://example.services.ai.azure.com/models

.PHONY: setup sync lock hooks-install hooks-run hooks-run-push ask discover-mcp utility-summary render-ui serve-ui smoke-test verify-surfaces notebook bdd compile test coverage coverage-html lint lint-python typecheck complexity quality rust-fmt rust-lint rust-quality rust-cli-build rust-cli-run azure-manifest fmt build publish

setup:
	$(UV) sync --extra azure

sync:
	$(UV) sync --extra azure

lock:
	$(UV) lock

hooks-install: sync
	PRE_COMMIT_HOME=.pre-commit-cache $(UV) run pre-commit install --hook-type pre-commit --hook-type pre-push

hooks-run: sync
	PRE_COMMIT_HOME=.pre-commit-cache $(UV) run pre-commit run --all-files

hooks-run-push: sync
	PRE_COMMIT_HOME=.pre-commit-cache $(UV) run pre-commit run --all-files --hook-stage pre-push

ask: sync
	$(UV) run repo-rag ask --question "$(QUESTION)"

discover-mcp: sync
	$(UV) run repo-rag discover-mcp

utility-summary: sync
	$(UV) run repo-rag utility-summary

render-ui: sync
	$(UV) run repo-rag render-ui --question "$(QUESTION)"

serve-ui: sync
	$(UV) run repo-rag serve-ui --question "$(QUESTION)"

smoke-test: sync
	$(UV) run repo-rag smoke-test

verify-surfaces: sync
	$(UV) run repo-rag verify-surfaces

notebook: sync
	$(UV) run jupyter lab notebooks/01_repo_rag_research.ipynb

bdd: sync
	$(UV) run pytest tests -k repository_rag

test: sync
	$(UV) run pytest
	$(UV) run coverage report --fail-under=85

coverage: sync
	$(UV) run pytest
	$(UV) run coverage report

coverage-html: sync
	$(UV) run pytest --cov-report=html
	$(UV) run coverage html

compile: sync
	$(UV) run python -m compileall src tests

lint-python: sync
	RUFF_CACHE_DIR=.ruff_cache $(UV) run ruff format --check src tests
	RUFF_CACHE_DIR=.ruff_cache $(UV) run ruff check src tests
	RUFF_CACHE_DIR=.ruff_cache $(UV) run nbqa ruff notebooks

lint: lint-python

typecheck: sync
	MYPY_CACHE_DIR=.mypy_cache $(UV) run mypy src tests
	$(UV) run basedpyright

complexity: sync
	$(UV) run radon cc src/repo_rag_lab -s -n B

quality: compile lint typecheck verify-surfaces complexity test

rust-fmt:
	cargo fmt --manifest-path rust-cli/Cargo.toml --check

rust-lint:
	cargo clippy --manifest-path rust-cli/Cargo.toml --all-targets -- -D warnings

rust-quality: rust-fmt rust-lint rust-cli-build rust-cli-run

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
