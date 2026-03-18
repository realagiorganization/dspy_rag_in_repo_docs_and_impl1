UV ?= uv
QUESTION ?= What does this repository research?
QUERY ?= dspy training
MODEL_ID ?= sample-ft-model
DEPLOYMENT_NAME ?= repo-rag-ft
AZURE_ENDPOINT ?= https://example.services.ai.azure.com/models
DSPY_RUN_NAME ?= repository-rag-default
DSPY_TRAINING_PATH ?= samples/training/repository_training_examples.yaml
DSPY_MODEL ?=
DSPY_API_KEY ?=
DSPY_API_BASE ?=
DSPY_API_VERSION ?=
DSPY_MODEL_TYPE ?= chat
DSPY_TEMPERATURE ?=
DSPY_MAX_TOKENS ?=
DSPY_PROGRAM_PATH ?=
DSPY_OPTIMIZER ?= bootstrapfewshot
DSPY_TOP_K ?= 4
DSPY_MAX_BOOTSTRAPPED_DEMOS ?= 2
DSPY_MAX_LABELED_DEMOS ?= 2
DSPY_MIPRO_AUTO ?= light
DSPY_NUM_THREADS ?= 4
DSPY_MIPRO_NUM_TRIALS ?=
LIVE_PROVIDER ?= azure-openai
RUNTIME_LOAD_ENV_FILE ?= 1
RETRIEVAL_TRAINING_PATH ?= samples/training/repository_training_examples.yaml
RETRIEVAL_TOP_K ?= 4
RETRIEVAL_TOP_K_SWEEP ?= 1,2,4,8
RETRIEVAL_MIN_PASS_RATE ?= 1.0
RETRIEVAL_MIN_SOURCE_RECALL ?= 1.0
PYTEST_COV_ARGS ?= --cov=src/repo_rag_lab --cov-report=term-missing --cov-report=xml
GH_RUN_LIMIT ?= 10
RUN_ID ?=
NOTEBOOK_TIMEOUT ?= 600
REPO_TMPDIR ?= $(HOME)/.cache/repo-rag-lab-tmp
PYTEST_CACHE_DIR ?= $(HOME)/.cache/repo-rag-lab-pytest
COVERAGE_DIR ?= $(HOME)/.cache/repo-rag-lab-coverage
COVERAGE_FILE_PATH ?= $(COVERAGE_DIR)/.coverage

.PHONY: setup sync lock hooks-install hooks-run hooks-run-push ask ask-dspy ask-live dspy-train dspy-artifacts retrieval-eval discover-mcp utility-summary files-sync todo-sync exploratorium-sync exploratorium-build smoke-test azure-openai-probe azure-inference-probe verify-surfaces gh-runs gh-watch gh-failed-logs paper-build paper-clean notebook notebook-report bdd compile test coverage coverage-html lint lint-python typecheck complexity quality rust-fmt rust-lint rust-quality rust-cli-build rust-cli-run rust-lookup-index rust-lookup azure-manifest fmt build publish

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

ask-dspy: sync
	$(UV) run repo-rag ask --question "$(QUESTION)" --use-dspy \
		$(if $(strip $(DSPY_PROGRAM_PATH)),--dspy-program-path "$(DSPY_PROGRAM_PATH)",) \
		$(if $(strip $(DSPY_MODEL)),--dspy-model "$(DSPY_MODEL)",) \
		$(if $(strip $(DSPY_API_KEY)),--dspy-api-key "$(DSPY_API_KEY)",) \
		$(if $(strip $(DSPY_API_BASE)),--dspy-api-base "$(DSPY_API_BASE)",) \
		$(if $(strip $(DSPY_API_VERSION)),--dspy-api-version "$(DSPY_API_VERSION)",) \
		--dspy-model-type "$(DSPY_MODEL_TYPE)" \
		$(if $(strip $(DSPY_TEMPERATURE)),--dspy-temperature $(DSPY_TEMPERATURE),) \
		$(if $(strip $(DSPY_MAX_TOKENS)),--dspy-max-tokens $(DSPY_MAX_TOKENS),) \
		--dspy-top-k $(DSPY_TOP_K)

ask-live: sync
	$(UV) run repo-rag ask-live --question "$(QUESTION)" --provider "$(LIVE_PROVIDER)" \
		$(if $(filter 1 true yes,$(RUNTIME_LOAD_ENV_FILE)),--load-env-file,)

dspy-train: sync
	$(UV) run repo-rag dspy-train --root . --training-path "$(DSPY_TRAINING_PATH)" \
		--run-name "$(DSPY_RUN_NAME)" --optimizer "$(DSPY_OPTIMIZER)" \
		--dspy-top-k $(DSPY_TOP_K) \
		--max-bootstrapped-demos $(DSPY_MAX_BOOTSTRAPPED_DEMOS) \
		--max-labeled-demos $(DSPY_MAX_LABELED_DEMOS) \
		--mipro-auto "$(DSPY_MIPRO_AUTO)" --num-threads $(DSPY_NUM_THREADS) \
		$(if $(strip $(DSPY_MIPRO_NUM_TRIALS)),--mipro-num-trials $(DSPY_MIPRO_NUM_TRIALS),) \
		$(if $(strip $(DSPY_MODEL)),--dspy-model "$(DSPY_MODEL)",) \
		$(if $(strip $(DSPY_API_KEY)),--dspy-api-key "$(DSPY_API_KEY)",) \
		$(if $(strip $(DSPY_API_BASE)),--dspy-api-base "$(DSPY_API_BASE)",) \
		$(if $(strip $(DSPY_API_VERSION)),--dspy-api-version "$(DSPY_API_VERSION)",) \
		--dspy-model-type "$(DSPY_MODEL_TYPE)" \
		$(if $(strip $(DSPY_TEMPERATURE)),--dspy-temperature $(DSPY_TEMPERATURE),) \
		$(if $(strip $(DSPY_MAX_TOKENS)),--dspy-max-tokens $(DSPY_MAX_TOKENS),)

dspy-artifacts: sync
	$(UV) run repo-rag dspy-artifacts --root .

retrieval-eval: sync
	$(UV) run repo-rag retrieval-eval --root . --training-path "$(RETRIEVAL_TRAINING_PATH)" \
		--top-k $(RETRIEVAL_TOP_K) --top-k-sweep "$(RETRIEVAL_TOP_K_SWEEP)" \
		$(if $(strip $(RETRIEVAL_MIN_PASS_RATE)),--minimum-pass-rate $(RETRIEVAL_MIN_PASS_RATE),) \
		$(if $(strip $(RETRIEVAL_MIN_SOURCE_RECALL)),--minimum-source-recall $(RETRIEVAL_MIN_SOURCE_RECALL),)

discover-mcp: sync
	$(UV) run repo-rag discover-mcp

utility-summary: sync
	$(UV) run repo-rag utility-summary

files-sync: sync
	$(UV) run repo-rag sync-file-summaries --root .

todo-sync: sync
	$(UV) run repo-rag sync-todo-backlog

exploratorium-sync: sync
	$(UV) run repo-rag sync-exploratorium-translation --root .

exploratorium-build: exploratorium-sync
	$(MAKE) -C publication/exploratorium_translation build

smoke-test: sync
	$(UV) run repo-rag smoke-test

azure-openai-probe: sync
	$(UV) run repo-rag azure-openai-probe \
		$(if $(filter 1 true yes,$(RUNTIME_LOAD_ENV_FILE)),--load-env-file,)

azure-inference-probe: sync
	$(UV) run repo-rag azure-inference-probe \
		$(if $(filter 1 true yes,$(RUNTIME_LOAD_ENV_FILE)),--load-env-file,)

verify-surfaces: sync
	$(UV) run repo-rag verify-surfaces

gh-runs:
	gh run list --limit $(GH_RUN_LIMIT)

gh-watch:
	@run_id="$(RUN_ID)"; \
	if [ -z "$$run_id" ]; then \
		run_id="$$(gh run list --limit 1 --json databaseId --jq '.[0].databaseId')"; \
	fi; \
	test -n "$$run_id"; \
	gh run watch "$$run_id" --exit-status

gh-failed-logs:
	@run_id="$(RUN_ID)"; \
	if [ -z "$$run_id" ]; then \
		run_id="$$(gh run list --limit 1 --json databaseId --jq '.[0].databaseId')"; \
	fi; \
	test -n "$$run_id"; \
	gh run view "$$run_id" --log-failed

paper-build: todo-sync exploratorium-sync
	$(MAKE) -C publication build

paper-clean:
	$(MAKE) -C publication clean

notebook: sync
	$(UV) run jupyter lab notebooks/01_repo_rag_research.ipynb

notebook-report: sync
	$(UV) run repo-rag run-notebooks --root . --timeout-seconds "$(NOTEBOOK_TIMEOUT)" --load-env-file

bdd: sync
	mkdir -p $(REPO_TMPDIR) $(PYTEST_CACHE_DIR)
	TMPDIR=$(REPO_TMPDIR) $(UV) run pytest -o cache_dir=$(PYTEST_CACHE_DIR) tests -k repository_rag

test: sync
	mkdir -p $(REPO_TMPDIR) $(PYTEST_CACHE_DIR) $(COVERAGE_DIR)
	rm -f $(COVERAGE_FILE_PATH) $(COVERAGE_FILE_PATH).*
	COVERAGE_FILE=$(COVERAGE_FILE_PATH) TMPDIR=$(REPO_TMPDIR) \
		$(UV) run pytest -o cache_dir=$(PYTEST_CACHE_DIR) $(PYTEST_COV_ARGS)
	COVERAGE_FILE=$(COVERAGE_FILE_PATH) $(UV) run coverage report --fail-under=85

coverage: sync
	mkdir -p $(REPO_TMPDIR) $(PYTEST_CACHE_DIR) $(COVERAGE_DIR)
	rm -f $(COVERAGE_FILE_PATH) $(COVERAGE_FILE_PATH).*
	COVERAGE_FILE=$(COVERAGE_FILE_PATH) TMPDIR=$(REPO_TMPDIR) \
		$(UV) run pytest -o cache_dir=$(PYTEST_CACHE_DIR) $(PYTEST_COV_ARGS)
	COVERAGE_FILE=$(COVERAGE_FILE_PATH) $(UV) run coverage report

coverage-html: sync
	mkdir -p $(REPO_TMPDIR) $(PYTEST_CACHE_DIR) $(COVERAGE_DIR)
	rm -f $(COVERAGE_FILE_PATH) $(COVERAGE_FILE_PATH).*
	COVERAGE_FILE=$(COVERAGE_FILE_PATH) TMPDIR=$(REPO_TMPDIR) \
		$(UV) run pytest -o cache_dir=$(PYTEST_CACHE_DIR) $(PYTEST_COV_ARGS) --cov-report=html
	COVERAGE_FILE=$(COVERAGE_FILE_PATH) $(UV) run coverage html

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

quality: compile lint typecheck verify-surfaces retrieval-eval complexity test

rust-fmt:
	cargo fmt --manifest-path rust-cli/Cargo.toml --check

rust-lint:
	cargo clippy --manifest-path rust-cli/Cargo.toml --all-targets -- -D warnings

rust-quality: rust-fmt rust-lint rust-cli-build rust-lookup-index rust-lookup rust-cli-run

rust-cli-build:
	cargo build --manifest-path rust-cli/Cargo.toml

rust-cli-run:
	cargo run --manifest-path rust-cli/Cargo.toml -- ask --question "$(QUESTION)"

rust-lookup-index:
	cargo run --manifest-path rust-cli/Cargo.toml -- index

rust-lookup:
	cargo run --manifest-path rust-cli/Cargo.toml -- lookup "$(QUERY)"

azure-manifest: sync
	$(UV) run repo-rag azure-manifest --model-id "$(MODEL_ID)" --deployment-name "$(DEPLOYMENT_NAME)" --endpoint "$(AZURE_ENDPOINT)"

fmt: sync
	$(UV) run ruff format src tests

build: sync
	$(UV) build

publish: build
	$(UV) publish
