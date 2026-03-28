from __future__ import annotations

from html import escape

from .workflow import RAGAnswer


def render_answer_page(answer: RAGAnswer) -> str:
    evidence_items = "\n".join(
        (
            "        <li>"
            f"<strong>{escape(str(chunk.source))}</strong>: {escape(_preview(chunk.text))}"
            "</li>"
        )
        for chunk in answer.context
    )
    mcp_items = "\n".join(
        (f"        <li><strong>{escape(server['path'])}</strong>: {escape(server['hint'])}</li>")
        for server in answer.mcp_servers
    )
    evidence_section = (
        "      <section>\n"
        "        <h2>Evidence</h2>\n"
        "        <ul>\n"
        f"{evidence_items}\n"
        "        </ul>\n"
        "      </section>"
        if evidence_items
        else "      <section><h2>Evidence</h2><p>No repository evidence was found.</p></section>"
    )
    mcp_section = (
        "      <section>\n"
        "        <h2>MCP Candidates</h2>\n"
        "        <ul>\n"
        f"{mcp_items}\n"
        "        </ul>\n"
        "      </section>"
        if mcp_items
        else ""
    )
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "  <head>",
            '    <meta charset="utf-8">',
            '    <meta name="viewport" content="width=device-width, initial-scale=1">',
            f"    <title>{escape(answer.question)}</title>",
            "    <style>",
            "      :root { color-scheme: light; }",
            (
                "      body { font-family: Georgia, serif; margin: 0; background: #f4efe6; "
                "color: #1d1a17; }"
            ),
            "      main { max-width: 52rem; margin: 0 auto; padding: 3rem 1.5rem 4rem; }",
            (
                "      .hero { background: linear-gradient(135deg, #efe3cf, #d7e7dd); "
                "border-radius: 1.25rem; padding: 1.5rem; box-shadow: 0 18px 40px "
                "rgba(29, 26, 23, 0.08); }"
            ),
            "      h1, h2 { line-height: 1.1; }",
            "      p, li { font-size: 1rem; line-height: 1.6; }",
            "      section { margin-top: 1.5rem; }",
            "      ul { padding-left: 1.25rem; }",
            (
                "      code { background: rgba(29, 26, 23, 0.08); padding: 0.1rem 0.3rem; "
                "border-radius: 0.3rem; }"
            ),
            "    </style>",
            "  </head>",
            "  <body>",
            "    <main>",
            '      <section class="hero">',
            "        <p>Repository RAG UI</p>",
            f"        <h1>{escape(answer.question)}</h1>",
            f"        <p>{escape(answer.answer)}</p>",
            "      </section>",
            evidence_section,
            mcp_section,
            "    </main>",
            "  </body>",
            "</html>",
        ]
    )


def _preview(text: str, limit: int = 240) -> str:
    compact = " ".join(text.split())
    return compact[:limit]
