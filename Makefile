PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PYTHON_BIN := $(VENV)/bin/python
QUESTION ?= What does this repository research?
MODEL_ID ?= sample-ft-model
DEPLOYMENT_NAME ?= repo-rag-ft
AZURE_ENDPOINT ?= https://example.services.ai.azure.com/models

.PHONY: setup ask discover-mcp utility-summary smoke-test notebook bdd rust-cli-build rust-cli-run azure-manifest fmt test

setup:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e .[dev]

ask:
	$(PYTHON_BIN) -m repo_rag_lab.cli ask --question "$(QUESTION)"

discover-mcp:
	$(PYTHON_BIN) -m repo_rag_lab.cli discover-mcp

utility-summary:
	$(PYTHON_BIN) -m repo_rag_lab.cli utility-summary

smoke-test:
	$(PYTHON_BIN) -m repo_rag_lab.cli smoke-test

notebook:
	$(PYTHON_BIN) -m jupyter lab notebooks/01_repo_rag_research.ipynb

bdd:
	$(PYTHON_BIN) -m pytest tests -k repository_rag

test:
	$(PYTHON_BIN) -m pytest

rust-cli-build:
	cargo build --manifest-path rust-cli/Cargo.toml

rust-cli-run:
	cargo run --manifest-path rust-cli/Cargo.toml -- ask --question "$(QUESTION)"

azure-manifest:
	$(PYTHON_BIN) -m repo_rag_lab.cli azure-manifest --model-id "$(MODEL_ID)" --deployment-name "$(DEPLOYMENT_NAME)" --endpoint "$(AZURE_ENDPOINT)"

fmt:
	$(PYTHON_BIN) -m compileall src tests
