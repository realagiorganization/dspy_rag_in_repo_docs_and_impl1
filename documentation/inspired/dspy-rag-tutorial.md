# DSPy Tutorial: Basic RAG

Source: https://dspy.ai/tutorials/rag/

## What It Demonstrates

The tutorial presents a compact DSPy RAG pipeline over a factual QA dataset. The important pattern is not the specific dataset, but the program shape:

1. Configure a language model and a retriever.
2. Wrap retrieval and generation inside a `dspy.Module`.
3. Evaluate using a task metric instead of intuition alone.
4. Improve the program with a DSPy optimizer rather than manually rewriting prompts.

## Portable Ideas For This Repository

- Keep retrieval as an explicit step in the module interface so repository context can be swapped independently from generation.
- Model quality should be measured against a small repository-specific QA set before trying optimization.
- DSPy compilation is useful only after a stable retrieval baseline exists.
- Saving compiled programs and evaluation data matters as much as the model prompt itself.

## How It Informs This Scaffold

- The repository workflow keeps retrieval and response synthesis separate.
- Example questions belong in version control so notebook, CLI, and tests use the same data.
- A tuned variant should be treated as an artifact that can later be deployed to Azure.

## Practical Gaps To Fill Here

- Replace the tutorial dataset with repository-grounded questions.
- Upgrade the simple lexical retriever to a vector or MCP-backed retriever when repo-local services exist.
- Add DSPy optimizer experiments once the corpus and evaluation set are credible.
