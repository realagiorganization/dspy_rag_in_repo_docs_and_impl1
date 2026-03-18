# Repository Research Narrative

This file is the overreaching narrative for the repository. It is meant to answer one question
that the other docs answer only in pieces: what research program is this repository actually
running, how do its parts connect, and what evidence currently supports that story?

Read this file as the top-level map. Then drop into the more specific docs:

- [README.md](README.md) for operator-facing entrypoints and repo layout.
- [README.DSPY.MD](README.DSPY.MD) for the DSPy-specific implementation and training path.
- [env.md](env.md) for environment and secret surfaces.
- [publication/README.md](publication/README.md) and
  [publication/repository-rag-lab-article.pdf](publication/repository-rag-lab-article.pdf) for
  the publication-style walkthrough.
- [docs/audit/README.md](docs/audit/README.md) and the newest dated audit note for current
  verification evidence.

## Thesis

The repository treats a software project itself as a research object: a codebase is both the
corpus and the laboratory. The same checked-in sources support:

1. baseline repository-grounded retrieval,
2. DSPy runtime answering and compiled-program development,
3. notebook-based experiment playbooks,
4. operational verification and CI evidence,
5. publication-style reporting, and
6. downstream deployment handoff metadata.

The core claim is not just that repository RAG can be demonstrated. The stronger claim is that the
entire workflow can be made self-describing and reproducible when notebooks, CLI surfaces, tests,
audit notes, CI logs, and publication outputs all point at the same package helpers under
[`src/repo_rag_lab/`](src/repo_rag_lab).

## Research Questions

The repository is currently organized around these questions:

- How well can a repository answer questions about itself using only checked-in text and a simple
  retriever?
- How far can DSPy push that baseline when the repository also provides structured training
  examples, retrieval benchmarks, and compiled-program persistence?
- Can notebook experimentation stay honest if the real logic lives in tested Python modules instead
  of ad hoc notebook cells?
- Can verification evidence become part of the research record rather than a side channel?
- Can publication and deployment-handoff artifacts be generated from the same workflow surfaces
  instead of from parallel undocumented scripts?

## Narrative Arc

### 1. The Repository Becomes A Corpus

The first move is to treat the repository as a bounded knowledge source rather than an external
dataset. That story starts in:

- [src/repo_rag_lab/corpus.py](src/repo_rag_lab/corpus.py)
- [src/repo_rag_lab/retrieval.py](src/repo_rag_lab/retrieval.py)
- [src/repo_rag_lab/workflow.py](src/repo_rag_lab/workflow.py)
- [notebooks/01_repo_rag_research.ipynb](notebooks/01_repo_rag_research.ipynb)

The repo loads its own text-like files, chunks them, ranks them lexically, and synthesizes a
baseline answer. This is the minimum honest system: before optimization, before benchmarking, and
before deployment, the repo must be able to explain itself from its own contents.

### 2. The Corpus Is Curated, Not Just Scraped

The second move is to acknowledge that not every file should count equally. Corpus planning is a
research activity in its own right, not an implementation detail. That story lives in:

- [samples/population/repository_population_candidates.yaml](samples/population/repository_population_candidates.yaml)
- [src/repo_rag_lab/population_samples.py](src/repo_rag_lab/population_samples.py)
- [notebooks/04_sample_population_lab.ipynb](notebooks/04_sample_population_lab.ipynb)

This stage turns the repository from a flat directory tree into a prioritized knowledge plan. The
repo can extend that plan automatically and rerank it from benchmark evidence, which is the first
step from static documentation toward adaptive system behavior.

### 3. MCP Discovery Broadens The Story

The repository does not only answer content questions. It also inspects its own MCP-adjacent
surfaces, so the research narrative includes operational structure as part of the corpus:

- [src/repo_rag_lab/mcp.py](src/repo_rag_lab/mcp.py)
- [documentation/mcp-discovery.md](documentation/mcp-discovery.md)
- [notebooks/01_repo_rag_research.ipynb](notebooks/01_repo_rag_research.ipynb)

That matters because the repo is not just modeling prose. It is modeling tooling shape,
integration affordances, and the agent-facing contract of the project.

### 4. Training Examples Turn Narrative Into Measurable Work

The next stage formalizes what “good answers” should look like:

- [samples/training/repository_training_examples.yaml](samples/training/repository_training_examples.yaml)
- [src/repo_rag_lab/training_samples.py](src/repo_rag_lab/training_samples.py)
- [src/repo_rag_lab/benchmarks.py](src/repo_rag_lab/benchmarks.py)
- [notebooks/03_dspy_training_lab.ipynb](notebooks/03_dspy_training_lab.ipynb)

Training examples and expected sources convert repository self-description into a measurable
benchmark surface. This is the point where the project stops being a demo and becomes a research
instrument. The benchmark layer is now also a user-facing evaluation surface through
`make retrieval-eval`, which reports top-k sweeps and richer retrieval-quality metrics instead of
leaving benchmark inspection buried in notebook helpers.

### 5. DSPy Moves The Repo From Prompted Runtime To Compiled Program

The repo now has two DSPy layers:

- a runtime answer path through [src/repo_rag_lab/dspy_workflow.py](src/repo_rag_lab/dspy_workflow.py)
- a compile-save-reload path through [src/repo_rag_lab/dspy_training.py](src/repo_rag_lab/dspy_training.py)

These are exposed through:

- [src/repo_rag_lab/cli.py](src/repo_rag_lab/cli.py)
- [Makefile](Makefile)
- [README.DSPY.MD](README.DSPY.MD)

This is the current center of gravity of the repository. The project no longer stops at “use DSPy
at runtime if available.” It can now compile a repository-grounded program, persist it under
`artifacts/dspy/`, and reuse that program for later questions.

### 6. Notebooks Become Playbooks, Not Logic Dumps

The notebooks are part of the research narrative because they show how humans are expected to
interrogate the system. But they are intentionally thin:

- [src/repo_rag_lab/notebook_support.py](src/repo_rag_lab/notebook_support.py)
- [src/repo_rag_lab/notebook_scaffolding.py](src/repo_rag_lab/notebook_scaffolding.py)
- [src/repo_rag_lab/notebook_runner.py](src/repo_rag_lab/notebook_runner.py)
- [notebooks/](notebooks/)

Their role is to expose the experiment flow, not to hide untested logic in cells. The monitored
notebook runner and notebook logs under `artifacts/notebook_runs/` and
`artifacts/notebook_logs/` make notebook execution itself part of the observable research record.

### 7. Verification Evidence Is Part Of The Research Output

The repository treats verification as first-class evidence, not just build hygiene. That story is
captured in:

- [docs/audit/](docs/audit/)
- [samples/logs/](samples/logs/)
- [src/repo_rag_lab/verification.py](src/repo_rag_lab/verification.py)
- [tests/](tests/)

Audit notes capture local verification runs. GitHub Actions logs capture post-push CI status. The
combination creates a chain of evidence from local claims to remote execution.

### 8. Publication And Deployment Are Explicit Downstream Consumers

The repository does not blur experimentation with deployment. Instead it keeps the handoffs
explicit:

- [publication/](publication/)
- [src/repo_rag_lab/azure.py](src/repo_rag_lab/azure.py)
- [documentation/azure-deployment.md](documentation/azure-deployment.md)

The publication surface turns the technical work into a readable article. The Azure manifest and
tuning metadata surfaces turn experimental outputs into deployment-oriented metadata without
pretending that deployment itself happens inside this repo.

The publication bundle now also includes a bilingual exploratorium subdocument that inventories the
state of referenced papers and documentation, summarizes all tracked files, and summarizes every
authored explicit URL in English and Russian. That turns repository self-inventory into a
publication surface rather than leaving it as hidden maintenance glue.

## Current State

At the time of this document:

- baseline repository-grounded RAG is implemented and exposed through `make ask`
- live Azure-backed repository answering is implemented and exposed through `make ask-live`
- Azure runtime contract probes are implemented and exposed through
  `make azure-openai-probe` and `make azure-inference-probe`
- tracked-file inventory sync is implemented and exposed through `make files-sync`
- retrieval-quality evaluation is implemented and exposed through `make retrieval-eval`
- DSPy runtime answering is implemented and exposed through `make ask-dspy`
- DSPy compile-save-reload is implemented and exposed through `make dspy-train`
- notebook batch execution and reporting are implemented and exposed through
  `make notebook-report`
- TODO and publication backlog synchronization are implemented and exposed through
  `make todo-sync`
- bilingual file, link, and fetch-state publication sync is implemented and exposed through
  `make exploratorium-sync`
- verification and CI logging are part of the repository contract, not optional cleanup

The main bottlenecks are now quality and coverage of retrieval, training examples, and benchmark
signal, not the lack of a DSPy or notebook execution surface.

## Evidence Surfaces

Use these files when you need to defend the current repository story quickly:

| Question | Best starting point | Supporting surfaces |
| --- | --- | --- |
| What is the repo for? | [README.md](README.md) | [publication/repository-rag-lab-article.pdf](publication/repository-rag-lab-article.pdf) |
| How is retrieval quality measured? | [README.DSPY.MD](README.DSPY.MD) | [src/repo_rag_lab/benchmarks.py](src/repo_rag_lab/benchmarks.py), [docs/audit/2026-03-18-retrieval-evaluation-suite.md](docs/audit/2026-03-18-retrieval-evaluation-suite.md) |
| How are live Azure runtime calls validated? | [documentation/azure-deployment.md](documentation/azure-deployment.md) | [src/repo_rag_lab/azure_runtime.py](src/repo_rag_lab/azure_runtime.py), [docs/audit/2026-03-18-azure-runtime-surfaces.md](docs/audit/2026-03-18-azure-runtime-surfaces.md) |
| How does DSPy work here? | [README.DSPY.MD](README.DSPY.MD) | [src/repo_rag_lab/dspy_training.py](src/repo_rag_lab/dspy_training.py), [src/repo_rag_lab/dspy_workflow.py](src/repo_rag_lab/dspy_workflow.py) |
| How do notebooks fit in? | [notebooks/](notebooks/) | [src/repo_rag_lab/notebook_scaffolding.py](src/repo_rag_lab/notebook_scaffolding.py), [src/repo_rag_lab/notebook_runner.py](src/repo_rag_lab/notebook_runner.py) |
| How is the repository inventory summarized? | [FILES.md](FILES.md) | [FILES.csv](FILES.csv), [src/repo_rag_lab/file_summaries.py](src/repo_rag_lab/file_summaries.py), [AGENTS.md.d/FILES.md](AGENTS.md.d/FILES.md) |
| What currently passes? | [docs/audit/README.md](docs/audit/README.md) | newest dated note in [docs/audit/](docs/audit/), plus [samples/logs/](samples/logs/) |
| What environment is required? | [env.md](env.md) | [documentation/azure-deployment.md](documentation/azure-deployment.md) |
| How does the publication relate? | [publication/README.md](publication/README.md) | [publication/repository-rag-lab-article.pdf](publication/repository-rag-lab-article.pdf), [publication/exploratorium_translation/exploratorium_translation.pdf](publication/exploratorium_translation/exploratorium_translation.pdf) |

## Tensions And Open Work

The narrative is coherent, but not complete. The main open tensions are:

- retrieval is still relatively simple compared with the sophistication of the DSPy training path
- notebook execution is well observed, but notebook conclusions still depend on the quality of the
  underlying corpus and benchmarks
- deployment handoff is documented, but live remote deployment is intentionally outside repo scope
- verification evidence is strong, but the index docs must be kept synchronized so the narrative
  does not drift behind the latest audit and CI state

## Maintenance Contract

This file is supposed to move as the repository moves. Update it whenever a turn materially
changes any of these:

- the central research question or thesis
- the narrative stages of the workflow
- the repo-native surfaces in `README.md` or `Makefile`
- DSPy training/runtime capabilities
- notebook responsibilities or observability
- verification evidence expectations
- publication or deployment-handoff scope

If a turn changes one of those and does not update this file, the repository narrative is drifting.
