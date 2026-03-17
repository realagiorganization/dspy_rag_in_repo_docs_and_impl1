# TODO

## DSPy Training And Runtime

- Build the missing automated DSPy training path.
  - Add a dedicated module such as `src/repo_rag_lab/dspy_training.py`.
  - Configure the DSPy LM explicitly instead of requiring in-process setup outside the CLI.
  - Define a real `dspy.Module` and optimizer flow rather than stopping at the current DSPy-shaped runtime wrapper.
  - Persist compiled DSPy programs to a versioned path such as `artifacts/dspy/`.
  - Expose the training surface through both `src/repo_rag_lab/cli.py` and `Makefile`.
- Make the existing DSPy CLI path operational without custom bootstrap code.
  - Add LM-selection and credential/configuration flags or documented env handling for `--use-dspy`.
  - Add tests that verify CLI behavior for both the configured and unconfigured DSPy path.
- Extend the notebooks beyond summary-only DSPy preparation.
  - Let `notebooks/03_dspy_training_lab.ipynb` load and exercise a compiled DSPy program.
  - Keep `src/repo_rag_lab/notebook_scaffolding.py` aligned with any future compiled-artifact workflow.

## Retrieval, Corpus, And Evaluation

- Strengthen retrieval quality beyond the lexical baseline.
  - Replace lexical overlap scoring with embeddings or another stronger retrieval layer.
  - Compare direct file retrieval against MCP-powered retrieval services.
  - Keep retrieval improvements shared by both the baseline workflow and the DSPy workflow.
- Expand benchmark and training evidence.
  - Enrich more entries in `samples/training/repository_training_examples.yaml` with `expected_sources`.
  - Expand repository-specific benchmark questions and expected answers.
  - Add tests for regression metrics and artifact persistence once the training surface exists.
- Keep the benchmark corpus definition stable as the repository grows.
  - Review `src/repo_rag_lab/benchmarks.py` exclusions whenever new generated docs or artifacts are added.
  - Make sure benchmark assertions continue to measure the intended repository corpus instead of generated side outputs.
- Continue improving corpus planning.
  - Use benchmark hit data to drive `rerank_population_candidates(...)` more systematically.
  - Expand population-candidate discovery if submodules or additional documentation surfaces become important.

## Notebook And Documentation Surfaces

- Keep notebooks executable as research playbooks.
  - Add notebook execution checks in CI if notebook execution becomes part of the acceptance surface.
  - Preserve notebook cell IDs and repository-surface validation when scaffolding changes.
  - Keep notebook logging and tuning-metadata outputs documented under `artifacts/`.
- Keep the DSPy and utility documentation current.
  - Refresh `README.DSPY.MD` when the training or benchmark workflow changes.
  - Keep `utilities/README.md`, `README.md`, and notebook guidance aligned with the actual CLI and Make targets.

## Verification, CI, And Deployment

- Expand verification beyond the current smoke/BDD emphasis.
  - Add a live or mocked Azure inference integration test once deployment moves beyond manifest generation.
  - Split or explicitly label integration-oriented tests if the repository grows past the current smoke-test and BDD surface.
  - Add tests that cover the future DSPy training and artifact-loading paths.
- Keep CI current with platform changes.
  - Update GitHub Actions dependencies that still emit Node.js 20 deprecation warnings.
  - Keep the post-push `samples/logs/` evidence updated after every push.
- Keep packaging and publish surfaces healthy.
  - Re-check the `Publish` workflow when the repo starts producing versioned DSPy artifacts or release tags.

## Repo Hygiene And Workflow Policy

- Decide what to do with the recurring `rust-cli/Cargo.lock` artifact.
  - Commit it intentionally if the Rust wrapper should be treated like an application.
  - Ignore it or otherwise suppress regeneration if it is not meant to be versioned.
- Keep audit notes and backlog documents synchronized.
  - Update `docs/audit/` when verification status materially changes.
  - Refresh this file when roadmap items are completed or replaced.
