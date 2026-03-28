from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path


@dataclass(frozen=True)
class SitePage:
    filename: str
    title: str
    source: Path


SITE_PAGES = [
    SitePage(
        filename="test-plan.html",
        title="Feature-Focused Test Plan",
        source=Path("docs/test-plan.md"),
    ),
    SitePage(
        filename="ui-and-integration-audit.html",
        title="UI And Integration Audit",
        source=Path("docs/audit/2026-03-27-ui-and-integration.md"),
    ),
]


def build_docs_site(root: Path, output_dir: Path | None = None) -> Path:
    destination = output_dir or (root / "artifacts" / "site")
    destination.mkdir(parents=True, exist_ok=True)

    page_summaries: list[tuple[str, str]] = []
    for page in SITE_PAGES:
        source_path = root / page.source
        html = render_markdown_page(
            title=page.title,
            markdown=source_path.read_text(encoding="utf-8"),
        )
        (destination / page.filename).write_text(html, encoding="utf-8")
        page_summaries.append((page.title, page.filename))

    index_html = render_index_page(page_summaries)
    (destination / "index.html").write_text(index_html, encoding="utf-8")
    return destination


def verify_docs_site_sources(root: Path) -> dict[str, object]:
    issues: list[dict[str, str]] = []
    test_plan = root / "docs" / "test-plan.md"
    if not test_plan.exists():
        issues.append({"path": str(test_plan), "message": "Missing feature-focused test plan."})
    else:
        text = test_plan.read_text(encoding="utf-8")
        for heading in ("# Feature-Focused Test Plan", "## Primary Features", "## Core Commands"):
            if heading not in text:
                issues.append({"path": str(test_plan), "message": f"Missing heading `{heading}`."})

    for page in SITE_PAGES:
        source_path = root / page.source
        if not source_path.exists():
            issues.append({"path": str(source_path), "message": "Missing docs-site source file."})

    return {
        "checked_page_count": len(SITE_PAGES),
        "issue_count": len(issues),
        "issues": issues,
    }


def render_index_page(page_summaries: list[tuple[str, str]]) -> str:
    links = "\n".join(
        (f'        <li><a href="{escape(filename)}">{escape(title)}</a></li>')
        for title, filename in page_summaries
    )
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "  <head>",
            '    <meta charset="utf-8">',
            '    <meta name="viewport" content="width=device-width, initial-scale=1">',
            "    <title>Repository Docs</title>",
            "    <style>",
            (
                "      body { margin: 0; font-family: Georgia, serif; background: #f5f2ea; "
                "color: #1f1b16; }"
            ),
            "      main { max-width: 56rem; margin: 0 auto; padding: 3rem 1.5rem 4rem; }",
            (
                "      .hero { background: linear-gradient(135deg, #e7d9b8, #d6ebe2); "
                "border-radius: 1.25rem; padding: 1.75rem; }"
            ),
            (
                "      .hero strong { display: block; font-size: 0.9rem; letter-spacing: "
                "0.08em; text-transform: uppercase; }"
            ),
            "      h1, h2 { line-height: 1.1; }",
            "      p, li { font-size: 1rem; line-height: 1.6; }",
            "      ul { padding-left: 1.25rem; }",
            "      a { color: #124c40; }",
            "    </style>",
            "  </head>",
            "  <body>",
            "    <main>",
            '      <section class="hero">',
            "        <strong>Generated Docs Site</strong>",
            "        <h1>Feature-Focused Test Plan</h1>",
            (
                "        <p>The test plan is the primary entrypoint on this site so verification, "
                "BDD coverage, docs publication, and CI expectations stay visible.</p>"
            ),
            '        <p><a href="test-plan.html">Open the test plan</a></p>',
            "      </section>",
            "      <section>",
            "        <h2>Documentation Pages</h2>",
            "        <ul>",
            f"{links}",
            "        </ul>",
            "      </section>",
            "    </main>",
            "  </body>",
            "</html>",
        ]
    )


def render_markdown_page(*, title: str, markdown: str) -> str:
    body = markdown_to_html(markdown)
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "  <head>",
            '    <meta charset="utf-8">',
            '    <meta name="viewport" content="width=device-width, initial-scale=1">',
            f"    <title>{escape(title)}</title>",
            "    <style>",
            (
                "      body { margin: 0; font-family: Georgia, serif; background: #fbf8f2; "
                "color: #201b17; }"
            ),
            "      main { max-width: 56rem; margin: 0 auto; padding: 3rem 1.5rem 4rem; }",
            "      nav { margin-bottom: 1.5rem; }",
            "      h1, h2, h3 { line-height: 1.15; }",
            "      p, li, pre, code { line-height: 1.6; }",
            (
                "      pre { overflow-x: auto; background: #efe7da; padding: 1rem; "
                "border-radius: 0.75rem; }"
            ),
            "      code { font-family: monospace; }",
            "      a { color: #124c40; }",
            "    </style>",
            "  </head>",
            "  <body>",
            "    <main>",
            '      <nav><a href="index.html">Back to docs index</a></nav>',
            f"{body}",
            "    </main>",
            "  </body>",
            "</html>",
        ]
    )


def markdown_to_html(markdown: str) -> str:
    blocks: list[str] = []
    paragraph_lines: list[str] = []
    list_items: list[str] = []
    in_code = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_lines:
            text = " ".join(line.strip() for line in paragraph_lines)
            blocks.append(f"<p>{escape(text)}</p>")
            paragraph_lines.clear()

    def flush_list() -> None:
        if list_items:
            joined = "\n".join(f"  <li>{escape(item)}</li>" for item in list_items)
            blocks.append(f"<ul>\n{joined}\n</ul>")
            list_items.clear()

    def flush_code() -> None:
        if code_lines:
            blocks.append(f"<pre><code>{escape(chr(10).join(code_lines))}</code></pre>")
            code_lines.clear()

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            flush_paragraph()
            flush_list()
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not line.strip():
            flush_paragraph()
            flush_list()
            continue
        if line.startswith("### "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h3>{escape(line[4:])}</h3>")
            continue
        if line.startswith("## "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h2>{escape(line[3:])}</h2>")
            continue
        if line.startswith("# "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h1>{escape(line[2:])}</h1>")
            continue
        if line.startswith("- "):
            flush_paragraph()
            list_items.append(line[2:].strip())
            continue
        paragraph_lines.append(line)

    flush_paragraph()
    flush_list()
    flush_code()
    return "\n".join(blocks)
