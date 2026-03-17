# Publication Article

This directory contains a publication-style walkthrough of the repository.

## Files

- `repository-rag-lab-article.tex`: main article source
- `references.bib`: bibliography used by the article
- `repository-rag-lab-article.pdf`: committed PDF output for stable linking
- `article-banner.png`: clipped banner image derived from the article's first page
- `Makefile`: local build helpers for the PDF and banner

## Local Build

```bash
make paper-build
```

That command calls the publication-local Makefile, runs `pdflatex` and `bibtex`, writes the PDF,
and crops the banner image from the rendered first page.
