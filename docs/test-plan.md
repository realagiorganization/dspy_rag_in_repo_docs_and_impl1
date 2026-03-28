# Feature-Focused Test Plan

This test plan turns the repository feature set into explicit verification targets.

## Primary Features

- Repository-grounded `RAG` question answering through the Python workflow
- `DSPY`-shaped retrieval and answer flow when optional DSPy support is enabled
- `MCP` candidate discovery for repository-local tooling
- Static and served `UI` rendering for repository answers
- `AZURE` deployment manifest generation
- Generated `DOCS SITE` publication for test and verification guidance

## Test Layers

### Unit And Module Checks

- Retrieval scoring and chunk selection
- Corpus loading and file filtering
- Azure manifest generation
- CLI argument routing
- Notebook and Makefile surface verification helpers
- Docs-site generation helpers

### Behavior And BDD Checks

- Repository question answering returns repository evidence
- MCP discovery returns valid JSON
- Rendered answer UI includes the question, answer, and evidence
- Mock-backed app and HTTP response contracts remain stable

### Surface Verification

- `Makefile` exposes the required public targets
- Research notebooks include Markdown headings and short code cells
- The feature-focused test plan exists and includes the required sections

### Coverage And Quality Gates

- `ruff` formatting and linting
- `mypy` and `basedpyright`
- `radon` complexity threshold
- `pytest` with coverage threshold enforcement
- Rust formatting, linting, build, and wrapper execution when Rust is available

### CI And Publication Checks

- `CI` workflow blocks on Python, content/metadata, and Rust wrapper checks
- `GitHub Pages` builds the documentation site from repository sources
- `Publish` pushes package artifacts on version tags

## Core Commands

```bash
python3 -m compileall src tests
UV_CACHE_DIR=.uv-cache uv run pytest
UV_CACHE_DIR=.uv-cache uv run repo-rag smoke-test
UV_CACHE_DIR=.uv-cache uv run repo-rag verify-surfaces
UV_CACHE_DIR=.uv-cache uv run repo-rag docs-site
```

## Current Gaps

- Browser-driven UI automation is still absent in the local sandboxed workflow
- No live Azure endpoint validation exists yet
- No separately named external integration suite exists yet

## Exit Criteria

- The feature set is documented in the generated docs site
- Core repo-native checks pass locally
- The relevant workflows are wired into CI or Pages publication
- Audit notes stay aligned with the real verification surface
