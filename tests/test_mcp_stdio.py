from __future__ import annotations

import io
from pathlib import Path

import repo_rag_lab.mcp_stdio as mcp_stdio


def test_mcp_stdio_main_dispatches_to_bounded_server(
    monkeypatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {}

    def fake_serve(root, *, input_stream, output_stream):
        observed["root"] = root
        observed["input_stream"] = input_stream
        observed["output_stream"] = output_stream
        return 17

    class _StdIn:
        buffer = io.BytesIO()

    class _StdOut:
        buffer = io.BytesIO()

    monkeypatch.setattr(mcp_stdio, "serve_repo_rag_mcp", fake_serve)
    monkeypatch.setattr(mcp_stdio.sys, "stdin", _StdIn())
    monkeypatch.setattr(mcp_stdio.sys, "stdout", _StdOut())

    exit_code = mcp_stdio.main(["--root", str(tmp_path)])

    assert exit_code == 17
    assert observed["root"] == tmp_path
