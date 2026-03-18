# Publication Article

This directory contains a publication-style walkthrough of the repository.

## Files

- `repository-rag-lab-article.tex`: main article source
- `references.bib`: bibliography used by the article
- `todo-backlog-table.tex`: generated LaTeX include mirrored from `todo-backlog.yaml`
- `repository-rag-lab-article.pdf`: committed PDF output for stable linking
- `article-banner.png`: clipped banner image derived from the article's first page
- `Makefile`: local build helpers for the PDF and banner

## Local Build

```bash
make paper-build
```

That command first runs `make todo-sync` from the repository root so the Markdown backlog and the
generated `todo-backlog-table.tex` stay aligned, then calls the publication-local Makefile, runs
`pdflatex` and `bibtex`, writes the PDF, and crops the banner image from the rendered first page.

## Automation

The `Publication PDF` GitHub Actions workflow rebuilds the article on pushes that touch the
publication surface, restores cached LaTeX auxiliary files to speed repeated builds, uploads the
rendered PDF as a workflow artifact, and, when the `DISCORD_WEBHOOK` secret is configured,
attempts to post the artifact link, the commit-pinned PDF link, and the workflow run link to
Discord.
