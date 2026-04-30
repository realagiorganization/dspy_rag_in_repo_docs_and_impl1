UV ?= uv
QUESTION ?= What does this repository research?
QUERY ?= dspy training
MODEL_ID ?= sample-ft-model
DEPLOYMENT_NAME ?= repo-rag-ft
AZURE_ENDPOINT ?= https://example.services.ai.azure.com/models
DSPY_RUN_NAME ?= repository-rag-default
DSPY_TRAINING_PATH ?= samples/training/repository_training_examples.yaml
BUNDLE_RUN_NAME ?=
BUNDLE_VERSION ?=
BUNDLE_INSPECT_CHANNEL ?=
BUNDLE_CHANNEL ?= stable
BUNDLE_NOTE ?=
OVERLAY_NAME ?= default
TRACE_PAYLOAD_PATH ?=
TRACE_PATH ?=
TRACE_NAME ?=
TRACE_OUTCOME_PATH ?=
TRACE_QUEUE_NAME ?= default
TRACE_QUEUE_LIMIT ?=
TRACE_KEEP_QUEUED ?=
TRAINER_PROMOTE_CHANNEL ?=
TRAINER_NOTE ?=
TRAINER_MIN_BUNDLE_PASS_RATE ?=
TRAINER_SERVICE_POLL_INTERVAL ?= 60
TRAINER_SERVICE_MAX_CYCLES ?=
TRAINER_SERVICE_MAX_IDLE_CYCLES ?=
TRAINER_SERVICE_STATE_PATH ?=
TRAINER_SERVICE_HISTORY_DIR ?=
TRAINER_K8S_IMAGE ?= ghcr.io/realagiorganization/repo-rag-lab:latest
TRAINER_K8S_NAMESPACE ?= repo-rag
TRAINER_K8S_SERVICE_ACCOUNT_NAME ?= repo-rag-trainer
TRAINER_K8S_CONFIG_MAP_NAME ?= repo-rag-trainer-config
TRAINER_K8S_SECRET_NAME ?= repo-rag-trainer-secrets
TRAINER_K8S_PVC_NAME ?= repo-rag-trainer-artifacts
TRAINER_K8S_PVC_STORAGE_CLASS ?= azurefile-csi
TRAINER_K8S_PVC_SIZE ?= 10Gi
TRAINER_K8S_PVC_ACCESS_MODES ?= ReadWriteMany
TRAINER_K8S_OUTPUT_DIR ?= artifacts/kubernetes
TRAINER_K8S_CYCLE_SCHEDULE ?= */15 * * * *
TRAINER_CANDIDATES_OUTPUT_PATH ?=
TRAINER_CANDIDATES_SUMMARY_PATH ?=
TRAINER_CANDIDATE_STATUSES ?= accepted,candidate
TRAINER_RECOMPILE_RUN_NAME ?= trainer-auto
TRAINER_RECOMPILE_BASE_TRAINING_PATH ?= samples/training/repository_training_examples.yaml
TRAINER_RECOMPILE_CANDIDATES_PATH ?=
TRAINER_RECOMPILE_GENERATED_TRAINING_PATH ?=
TRAINER_RECOMPILE_GENERATED_TRAINING_SUMMARY_PATH ?=
TRAINER_RECOMPILE_OPTIMIZER ?= bootstrapfewshot
TRAINER_RECOMPILE_TOP_K ?= 4
TRAINER_RECOMPILE_MAX_BOOTSTRAPPED_DEMOS ?= 2
TRAINER_RECOMPILE_MAX_LABELED_DEMOS ?= 2
TRAINER_RECOMPILE_MIPRO_AUTO ?= light
TRAINER_RECOMPILE_NUM_THREADS ?= 4
TRAINER_RECOMPILE_MIPRO_NUM_TRIALS ?=
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
RETRIEVAL_MODE ?=
PYTEST_COV_ARGS ?= --cov=src/repo_rag_lab --cov-report=term-missing --cov-report=xml
GH_RUN_LIMIT ?= 10
RUN_ID ?=
GITHUB_PR_GATES_BRANCH ?= master
GITHUB_PR_GATES_REPO ?=
PAGES_SITE_BRANCH ?= master
PAGES_SITE_OUTPUT_DIR ?= artifacts/pages_docs
PAGES_SITE_REPO_URL ?=
NOTEBOOK_TIMEOUT ?= 600
REPO_TMPDIR ?= $(HOME)/.cache/repo-rag-lab-tmp
PYTEST_CACHE_DIR ?= $(HOME)/.cache/repo-rag-lab-pytest
COVERAGE_DIR ?= $(HOME)/.cache/repo-rag-lab-coverage
COVERAGE_FILE_PATH ?= $(COVERAGE_DIR)/.coverage

.PHONY: setup sync lock hooks-install hooks-run hooks-run-push ask ask-dspy ask-live dspy-train dspy-artifacts bundle-inspect bundle-fetch bundle-publish bundle-promote bundle-rollback overlay-init trace-export trace-import trace-enqueue trace-drain trainer-cycle trainer-service trainer-k8s-manifests trainer-candidates trainer-recompile retrieval-eval discover-mcp serve-mcp utility-summary files-sync todo-sync exploratorium-sync exploratorium-build github-pr-gates pages-sync pages-build pages-serve smoke-test azure-openai-probe azure-inference-probe verify-surfaces gh-runs gh-watch gh-failed-logs paper-build paper-clean notebook notebook-report bdd compile test coverage coverage-html lint lint-python typecheck complexity quality rust-fmt rust-lint rust-quality rust-cli-build rust-cli-run rust-lookup-index rust-lookup azure-manifest fmt build publish

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
	$(UV) run repo-rag ask --question "$(QUESTION)" \
		$(if $(strip $(RETRIEVAL_MODE)),--retrieval-mode "$(RETRIEVAL_MODE)",)

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
		--dspy-top-k $(DSPY_TOP_K) \
		$(if $(strip $(RETRIEVAL_MODE)),--retrieval-mode "$(RETRIEVAL_MODE)",)

ask-live: sync
	$(UV) run repo-rag ask-live --question "$(QUESTION)" --provider "$(LIVE_PROVIDER)" \
		$(if $(strip $(RETRIEVAL_MODE)),--retrieval-mode "$(RETRIEVAL_MODE)",) \
		$(if $(filter 1 true yes,$(RUNTIME_LOAD_ENV_FILE)),--load-env-file,)

dspy-train: sync
	$(UV) run repo-rag dspy-train --root . --training-path "$(DSPY_TRAINING_PATH)" \
		--run-name "$(DSPY_RUN_NAME)" --optimizer "$(DSPY_OPTIMIZER)" \
		--dspy-top-k $(DSPY_TOP_K) \
		$(if $(strip $(RETRIEVAL_MODE)),--retrieval-mode "$(RETRIEVAL_MODE)",) \
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

bundle-inspect: sync
	$(UV) run repo-rag bundle-inspect --root . \
		$(if $(strip $(BUNDLE_RUN_NAME)),--run-name "$(BUNDLE_RUN_NAME)",) \
		$(if $(strip $(BUNDLE_VERSION)),--bundle-version "$(BUNDLE_VERSION)",) \
		$(if $(strip $(BUNDLE_INSPECT_CHANNEL)),--channel "$(BUNDLE_INSPECT_CHANNEL)",)

bundle-fetch: sync
	$(UV) run repo-rag bundle-fetch --root . \
		$(if $(strip $(BUNDLE_VERSION)),--bundle-version "$(BUNDLE_VERSION)",) \
		$(if $(strip $(BUNDLE_INSPECT_CHANNEL)),--channel "$(BUNDLE_INSPECT_CHANNEL)",)

bundle-publish: sync
	$(UV) run repo-rag bundle-publish --root . \
		$(if $(strip $(BUNDLE_RUN_NAME)),--run-name "$(BUNDLE_RUN_NAME)",) \
		$(if $(strip $(BUNDLE_VERSION)),--bundle-version "$(BUNDLE_VERSION)",) \
		$(if $(strip $(BUNDLE_NOTE)),--note "$(BUNDLE_NOTE)",)

bundle-promote: sync
	$(UV) run repo-rag bundle-promote --root . --channel "$(BUNDLE_CHANNEL)" \
		$(if $(strip $(BUNDLE_RUN_NAME)),--run-name "$(BUNDLE_RUN_NAME)",) \
		$(if $(strip $(BUNDLE_VERSION)),--bundle-version "$(BUNDLE_VERSION)",) \
		$(if $(strip $(BUNDLE_NOTE)),--note "$(BUNDLE_NOTE)",)

bundle-rollback: sync
	$(UV) run repo-rag bundle-rollback --root . --channel "$(BUNDLE_CHANNEL)" \
		$(if $(strip $(BUNDLE_VERSION)),--bundle-version "$(BUNDLE_VERSION)",) \
		$(if $(strip $(BUNDLE_NOTE)),--note "$(BUNDLE_NOTE)",)

overlay-init: sync
	$(UV) run repo-rag overlay-init --root . --overlay-name "$(OVERLAY_NAME)" \
		$(if $(strip $(BUNDLE_VERSION)),--bundle-version "$(BUNDLE_VERSION)",) \
		$(if $(strip $(RETRIEVAL_MODE)),--retrieval-mode "$(RETRIEVAL_MODE)",)

trace-export: sync
	$(UV) run repo-rag trace-export --root . \
		$(if $(strip $(TRACE_PAYLOAD_PATH)),--payload-path "$(TRACE_PAYLOAD_PATH)",) \
		$(if $(strip $(TRACE_NAME)),--trace-name "$(TRACE_NAME)",)

trace-import: sync
	$(UV) run repo-rag trace-import --root . --trace-path "$(TRACE_PATH)" \
		$(if $(strip $(TRACE_NAME)),--trace-name "$(TRACE_NAME)",) \
		$(if $(strip $(TRACE_OUTCOME_PATH)),--outcome-path "$(TRACE_OUTCOME_PATH)",)

trace-enqueue: sync
	$(UV) run repo-rag trace-enqueue --root . --trace-path "$(TRACE_PATH)" \
		--queue-name "$(TRACE_QUEUE_NAME)" \
		$(if $(strip $(TRACE_NAME)),--trace-name "$(TRACE_NAME)",) \
		$(if $(strip $(TRACE_OUTCOME_PATH)),--outcome-path "$(TRACE_OUTCOME_PATH)",)

trace-drain: sync
	$(UV) run repo-rag trace-drain --root . --queue-name "$(TRACE_QUEUE_NAME)" \
		$(if $(strip $(TRACE_QUEUE_LIMIT)),--limit $(TRACE_QUEUE_LIMIT),) \
		$(if $(filter 1 true yes,$(TRACE_KEEP_QUEUED)),--keep-queued,)

trainer-cycle: sync
	$(UV) run repo-rag trainer-cycle --root . --queue-name "$(TRACE_QUEUE_NAME)" \
		$(if $(strip $(TRACE_QUEUE_LIMIT)),--limit $(TRACE_QUEUE_LIMIT),) \
		$(if $(filter 1 true yes,$(TRACE_KEEP_QUEUED)),--keep-queued,) \
		$(if $(strip $(BUNDLE_RUN_NAME)),--run-name "$(BUNDLE_RUN_NAME)",) \
		$(if $(strip $(BUNDLE_VERSION)),--bundle-version "$(BUNDLE_VERSION)",) \
		$(if $(strip $(TRAINER_PROMOTE_CHANNEL)),--promote-channel "$(TRAINER_PROMOTE_CHANNEL)",) \
		$(if $(strip $(TRAINER_NOTE)),--note "$(TRAINER_NOTE)",) \
		--training-path "$(RETRIEVAL_TRAINING_PATH)" \
		--top-k $(RETRIEVAL_TOP_K) --top-k-sweep "$(RETRIEVAL_TOP_K_SWEEP)" \
		$(if $(strip $(RETRIEVAL_MODE)),--retrieval-mode "$(RETRIEVAL_MODE)",) \
		$(if $(strip $(RETRIEVAL_MIN_PASS_RATE)),--minimum-pass-rate $(RETRIEVAL_MIN_PASS_RATE),) \
		$(if $(strip $(RETRIEVAL_MIN_SOURCE_RECALL)),--minimum-source-recall $(RETRIEVAL_MIN_SOURCE_RECALL),) \
		$(if $(strip $(TRAINER_MIN_BUNDLE_PASS_RATE)),--minimum-bundle-pass-rate $(TRAINER_MIN_BUNDLE_PASS_RATE),) \
		$(if $(strip $(TRAINER_RECOMPILE_RUN_NAME)),--recompile-run-name "$(TRAINER_RECOMPILE_RUN_NAME)",) \
		--recompile-base-training-path "$(TRAINER_RECOMPILE_BASE_TRAINING_PATH)" \
		$(if $(strip $(TRAINER_RECOMPILE_CANDIDATES_PATH)),--recompile-candidates-path "$(TRAINER_RECOMPILE_CANDIDATES_PATH)",) \
		$(if $(strip $(TRAINER_RECOMPILE_GENERATED_TRAINING_PATH)),--recompile-generated-training-path "$(TRAINER_RECOMPILE_GENERATED_TRAINING_PATH)",) \
		$(if $(strip $(TRAINER_RECOMPILE_GENERATED_TRAINING_SUMMARY_PATH)),--recompile-generated-training-summary-path "$(TRAINER_RECOMPILE_GENERATED_TRAINING_SUMMARY_PATH)",) \
		--recompile-optimizer "$(TRAINER_RECOMPILE_OPTIMIZER)" \
		--recompile-top-k $(TRAINER_RECOMPILE_TOP_K) \
		--recompile-max-bootstrapped-demos $(TRAINER_RECOMPILE_MAX_BOOTSTRAPPED_DEMOS) \
		--recompile-max-labeled-demos $(TRAINER_RECOMPILE_MAX_LABELED_DEMOS) \
		--recompile-mipro-auto "$(TRAINER_RECOMPILE_MIPRO_AUTO)" \
		--recompile-num-threads $(TRAINER_RECOMPILE_NUM_THREADS) \
		$(if $(strip $(TRAINER_RECOMPILE_MIPRO_NUM_TRIALS)),--recompile-mipro-num-trials $(TRAINER_RECOMPILE_MIPRO_NUM_TRIALS),) \
		$(if $(strip $(DSPY_MODEL)),--dspy-model "$(DSPY_MODEL)",) \
		$(if $(strip $(DSPY_API_KEY)),--dspy-api-key "$(DSPY_API_KEY)",) \
		$(if $(strip $(DSPY_API_BASE)),--dspy-api-base "$(DSPY_API_BASE)",) \
		$(if $(strip $(DSPY_API_VERSION)),--dspy-api-version "$(DSPY_API_VERSION)",) \
		--dspy-model-type "$(DSPY_MODEL_TYPE)" \
		$(if $(strip $(DSPY_TEMPERATURE)),--dspy-temperature $(DSPY_TEMPERATURE),) \
		$(if $(strip $(DSPY_MAX_TOKENS)),--dspy-max-tokens $(DSPY_MAX_TOKENS),)

trainer-service: sync
	$(UV) run repo-rag trainer-service --root . --queue-name "$(TRACE_QUEUE_NAME)" \
		$(if $(strip $(TRACE_QUEUE_LIMIT)),--limit $(TRACE_QUEUE_LIMIT),) \
		$(if $(filter 1 true yes,$(TRACE_KEEP_QUEUED)),--keep-queued,) \
		$(if $(strip $(BUNDLE_RUN_NAME)),--run-name "$(BUNDLE_RUN_NAME)",) \
		$(if $(strip $(BUNDLE_VERSION)),--bundle-version "$(BUNDLE_VERSION)",) \
		$(if $(strip $(TRAINER_PROMOTE_CHANNEL)),--promote-channel "$(TRAINER_PROMOTE_CHANNEL)",) \
		$(if $(strip $(TRAINER_NOTE)),--note "$(TRAINER_NOTE)",) \
		--training-path "$(RETRIEVAL_TRAINING_PATH)" \
		--top-k $(RETRIEVAL_TOP_K) --top-k-sweep "$(RETRIEVAL_TOP_K_SWEEP)" \
		$(if $(strip $(RETRIEVAL_MODE)),--retrieval-mode "$(RETRIEVAL_MODE)",) \
		$(if $(strip $(RETRIEVAL_MIN_PASS_RATE)),--minimum-pass-rate $(RETRIEVAL_MIN_PASS_RATE),) \
		$(if $(strip $(RETRIEVAL_MIN_SOURCE_RECALL)),--minimum-source-recall $(RETRIEVAL_MIN_SOURCE_RECALL),) \
		$(if $(strip $(TRAINER_MIN_BUNDLE_PASS_RATE)),--minimum-bundle-pass-rate $(TRAINER_MIN_BUNDLE_PASS_RATE),) \
		--poll-interval-seconds $(TRAINER_SERVICE_POLL_INTERVAL) \
		$(if $(strip $(TRAINER_SERVICE_MAX_CYCLES)),--max-cycles $(TRAINER_SERVICE_MAX_CYCLES),) \
		$(if $(strip $(TRAINER_SERVICE_MAX_IDLE_CYCLES)),--max-idle-cycles $(TRAINER_SERVICE_MAX_IDLE_CYCLES),) \
		$(if $(strip $(TRAINER_SERVICE_STATE_PATH)),--state-path "$(TRAINER_SERVICE_STATE_PATH)",) \
		$(if $(strip $(TRAINER_SERVICE_HISTORY_DIR)),--history-dir "$(TRAINER_SERVICE_HISTORY_DIR)",) \
		$(if $(strip $(TRAINER_RECOMPILE_RUN_NAME)),--recompile-run-name "$(TRAINER_RECOMPILE_RUN_NAME)",) \
		--recompile-base-training-path "$(TRAINER_RECOMPILE_BASE_TRAINING_PATH)" \
		$(if $(strip $(TRAINER_RECOMPILE_CANDIDATES_PATH)),--recompile-candidates-path "$(TRAINER_RECOMPILE_CANDIDATES_PATH)",) \
		$(if $(strip $(TRAINER_RECOMPILE_GENERATED_TRAINING_PATH)),--recompile-generated-training-path "$(TRAINER_RECOMPILE_GENERATED_TRAINING_PATH)",) \
		$(if $(strip $(TRAINER_RECOMPILE_GENERATED_TRAINING_SUMMARY_PATH)),--recompile-generated-training-summary-path "$(TRAINER_RECOMPILE_GENERATED_TRAINING_SUMMARY_PATH)",) \
		--recompile-optimizer "$(TRAINER_RECOMPILE_OPTIMIZER)" \
		--recompile-top-k $(TRAINER_RECOMPILE_TOP_K) \
		--recompile-max-bootstrapped-demos $(TRAINER_RECOMPILE_MAX_BOOTSTRAPPED_DEMOS) \
		--recompile-max-labeled-demos $(TRAINER_RECOMPILE_MAX_LABELED_DEMOS) \
		--recompile-mipro-auto "$(TRAINER_RECOMPILE_MIPRO_AUTO)" \
		--recompile-num-threads $(TRAINER_RECOMPILE_NUM_THREADS) \
		$(if $(strip $(TRAINER_RECOMPILE_MIPRO_NUM_TRIALS)),--recompile-mipro-num-trials $(TRAINER_RECOMPILE_MIPRO_NUM_TRIALS),) \
		$(if $(strip $(DSPY_MODEL)),--dspy-model "$(DSPY_MODEL)",) \
		$(if $(strip $(DSPY_API_KEY)),--dspy-api-key "$(DSPY_API_KEY)",) \
		$(if $(strip $(DSPY_API_BASE)),--dspy-api-base "$(DSPY_API_BASE)",) \
		$(if $(strip $(DSPY_API_VERSION)),--dspy-api-version "$(DSPY_API_VERSION)",) \
		--dspy-model-type "$(DSPY_MODEL_TYPE)" \
		$(if $(strip $(DSPY_TEMPERATURE)),--dspy-temperature $(DSPY_TEMPERATURE),) \
		$(if $(strip $(DSPY_MAX_TOKENS)),--dspy-max-tokens $(DSPY_MAX_TOKENS),)

trainer-k8s-manifests: sync
	$(UV) run repo-rag trainer-k8s-manifests --root . \
		--image "$(TRAINER_K8S_IMAGE)" \
		--namespace "$(TRAINER_K8S_NAMESPACE)" \
		--service-account-name "$(TRAINER_K8S_SERVICE_ACCOUNT_NAME)" \
		--config-map-name "$(TRAINER_K8S_CONFIG_MAP_NAME)" \
		--secret-name "$(TRAINER_K8S_SECRET_NAME)" \
		--pvc-name "$(TRAINER_K8S_PVC_NAME)" \
		--pvc-storage-class "$(TRAINER_K8S_PVC_STORAGE_CLASS)" \
		--pvc-size "$(TRAINER_K8S_PVC_SIZE)" \
		--pvc-access-modes "$(TRAINER_K8S_PVC_ACCESS_MODES)" \
		--output-dir "$(TRAINER_K8S_OUTPUT_DIR)" \
		--queue-name "$(TRACE_QUEUE_NAME)" \
		--cycle-schedule "$(TRAINER_K8S_CYCLE_SCHEDULE)" \
		--poll-interval-seconds $(TRAINER_SERVICE_POLL_INTERVAL) \
		$(if $(strip $(TRAINER_SERVICE_MAX_IDLE_CYCLES)),--service-max-idle-cycles $(TRAINER_SERVICE_MAX_IDLE_CYCLES),) \
		$(if $(strip $(TRAINER_PROMOTE_CHANNEL)),--promote-channel "$(TRAINER_PROMOTE_CHANNEL)",) \
		--training-path "$(RETRIEVAL_TRAINING_PATH)" \
		--top-k $(RETRIEVAL_TOP_K) \
		--top-k-sweep "$(RETRIEVAL_TOP_K_SWEEP)" \
		$(if $(strip $(RETRIEVAL_MODE)),--retrieval-mode "$(RETRIEVAL_MODE)",) \
		--minimum-pass-rate $(RETRIEVAL_MIN_PASS_RATE) \
		--minimum-source-recall $(RETRIEVAL_MIN_SOURCE_RECALL) \
		$(if $(strip $(TRAINER_MIN_BUNDLE_PASS_RATE)),--minimum-bundle-pass-rate $(TRAINER_MIN_BUNDLE_PASS_RATE),) \
		--recompile-run-name "$(TRAINER_RECOMPILE_RUN_NAME)" \
		--recompile-base-training-path "$(TRAINER_RECOMPILE_BASE_TRAINING_PATH)"

trainer-candidates: sync
	$(UV) run repo-rag trainer-candidates --root . \
		$(if $(strip $(TRACE_PATH)),--trace-path "$(TRACE_PATH)",) \
		$(if $(strip $(TRAINER_CANDIDATES_OUTPUT_PATH)),--output-path "$(TRAINER_CANDIDATES_OUTPUT_PATH)",) \
		$(if $(strip $(TRAINER_CANDIDATES_SUMMARY_PATH)),--summary-path "$(TRAINER_CANDIDATES_SUMMARY_PATH)",) \
		--include-statuses "$(TRAINER_CANDIDATE_STATUSES)"

trainer-recompile: sync
	$(UV) run repo-rag trainer-recompile --root . --run-name "$(TRAINER_RECOMPILE_RUN_NAME)" \
		--base-training-path "$(TRAINER_RECOMPILE_BASE_TRAINING_PATH)" \
		$(if $(strip $(TRAINER_RECOMPILE_CANDIDATES_PATH)),--candidates-path "$(TRAINER_RECOMPILE_CANDIDATES_PATH)",) \
		$(if $(strip $(TRAINER_RECOMPILE_GENERATED_TRAINING_PATH)),--generated-training-path "$(TRAINER_RECOMPILE_GENERATED_TRAINING_PATH)",) \
		$(if $(strip $(TRAINER_RECOMPILE_GENERATED_TRAINING_SUMMARY_PATH)),--generated-training-summary-path "$(TRAINER_RECOMPILE_GENERATED_TRAINING_SUMMARY_PATH)",) \
		--optimizer "$(TRAINER_RECOMPILE_OPTIMIZER)" \
		--dspy-top-k $(TRAINER_RECOMPILE_TOP_K) \
		$(if $(strip $(RETRIEVAL_MODE)),--retrieval-mode "$(RETRIEVAL_MODE)",) \
		--max-bootstrapped-demos $(TRAINER_RECOMPILE_MAX_BOOTSTRAPPED_DEMOS) \
		--max-labeled-demos $(TRAINER_RECOMPILE_MAX_LABELED_DEMOS) \
		--mipro-auto "$(TRAINER_RECOMPILE_MIPRO_AUTO)" \
		--num-threads $(TRAINER_RECOMPILE_NUM_THREADS) \
		$(if $(strip $(TRAINER_RECOMPILE_MIPRO_NUM_TRIALS)),--mipro-num-trials $(TRAINER_RECOMPILE_MIPRO_NUM_TRIALS),) \
		$(if $(strip $(DSPY_MODEL)),--dspy-model "$(DSPY_MODEL)",) \
		$(if $(strip $(DSPY_API_KEY)),--dspy-api-key "$(DSPY_API_KEY)",) \
		$(if $(strip $(DSPY_API_BASE)),--dspy-api-base "$(DSPY_API_BASE)",) \
		$(if $(strip $(DSPY_API_VERSION)),--dspy-api-version "$(DSPY_API_VERSION)",) \
		--dspy-model-type "$(DSPY_MODEL_TYPE)" \
		$(if $(strip $(DSPY_TEMPERATURE)),--dspy-temperature $(DSPY_TEMPERATURE),) \
		$(if $(strip $(DSPY_MAX_TOKENS)),--dspy-max-tokens $(DSPY_MAX_TOKENS),)

retrieval-eval: sync
	$(UV) run repo-rag retrieval-eval --root . --training-path "$(RETRIEVAL_TRAINING_PATH)" \
		--top-k $(RETRIEVAL_TOP_K) --top-k-sweep "$(RETRIEVAL_TOP_K_SWEEP)" \
		$(if $(strip $(RETRIEVAL_MODE)),--retrieval-mode "$(RETRIEVAL_MODE)",) \
		$(if $(strip $(RETRIEVAL_MIN_PASS_RATE)),--minimum-pass-rate $(RETRIEVAL_MIN_PASS_RATE),) \
		$(if $(strip $(RETRIEVAL_MIN_SOURCE_RECALL)),--minimum-source-recall $(RETRIEVAL_MIN_SOURCE_RECALL),)

discover-mcp: sync
	$(UV) run repo-rag discover-mcp

serve-mcp: sync
	$(UV) run repo-rag serve-mcp --root .

serve-codex-proxy: sync
	$(UV) run repo-rag serve-codex-proxy --root . --bundle-root . \
		--artifact-dir artifacts/codex_proxy \
		--host 127.0.0.1 --port 8088

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

github-pr-gates: sync
	$(UV) run repo-rag sync-github-pr-gates --root . --branch "$(GITHUB_PR_GATES_BRANCH)" --apply \
		$(if $(strip $(GITHUB_PR_GATES_REPO)),--repo "$(GITHUB_PR_GATES_REPO)",)

pages-sync: sync
	$(UV) run repo-rag sync-pages-site --root . --output-dir "$(PAGES_SITE_OUTPUT_DIR)" \
		--branch "$(PAGES_SITE_BRANCH)" \
		$(if $(strip $(PAGES_SITE_REPO_URL)),--repo-url "$(PAGES_SITE_REPO_URL)",)

pages-build: pages-sync
	$(UV) run mkdocs build --strict

pages-serve: pages-sync
	$(UV) run mkdocs serve

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
