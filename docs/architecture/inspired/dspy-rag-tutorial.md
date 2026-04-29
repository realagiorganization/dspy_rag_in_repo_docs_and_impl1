# DSPy Tutorial: Basic RAG

Source: https://dspy.ai/tutorials/rag/

This note captures the parts of the tutorial that map cleanly onto this repository's
repository-grounded workflow.

## Core Pattern

The tutorial demonstrates a compact DSPy RAG loop:

1. Configure a language model and a retriever.
2. Wrap retrieval and generation in a reusable DSPy module.
3. Evaluate against a task metric instead of relying on intuition.
4. Improve the program with a DSPy optimizer after the baseline is stable.

## What Carries Over To This Repository

- Retrieval should remain an explicit, swappable step.
- Evaluation should use a small repository-specific question-answer set.
- Compiled or tuned artifacts should be saved and treated as versioned outputs.
- Optimization only makes sense after the baseline corpus and retrieval behavior are credible.

## How The Current Scaffold Reflects That

- The package keeps retrieval, answer synthesis, utilities, and verification in separate modules.
- Example questions and training samples live in version control so notebooks, CLI runs, and tests share the same data.
- Azure deployment is treated as a downstream artifact step, not part of the baseline RAG execution path.

## Next Steps Suggested By The Tutorial

- Replace the lexical overlap retriever with embeddings or an MCP-backed retrieval surface.
- Expand the repository-specific evaluation set.
- Add DSPy optimizer experiments only after the baseline evidence improves.
