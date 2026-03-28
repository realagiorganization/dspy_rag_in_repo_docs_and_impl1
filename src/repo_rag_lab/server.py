from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .app import RepositoryApp


@dataclass(frozen=True)
class UIResponse:
    status: HTTPStatus
    body: bytes
    content_type: str = "text/html; charset=utf-8"


def build_ui_server(
    *,
    root: Path,
    question: str,
    host: str = "127.0.0.1",
    port: int = 8000,
    app: RepositoryApp | None = None,
) -> ThreadingHTTPServer:
    repository_app = app or RepositoryApp()

    class RepositoryUIHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            response = build_ui_response(
                request_target=self.path,
                root=root,
                question=question,
                app=repository_app,
            )
            if response.status != HTTPStatus.OK:
                self.send_error(response.status, response.body.decode("utf-8"))
                return

            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            self.wfile.write(response.body)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    return ThreadingHTTPServer((host, port), RepositoryUIHandler)


def serve_ui(
    *,
    root: Path,
    question: str,
    host: str = "127.0.0.1",
    port: int = 8000,
    once: bool = False,
    announce: Callable[[str], None] = print,
) -> int:
    server = build_ui_server(root=root, question=question, host=host, port=port)
    address = f"http://{server.server_name}:{server.server_port}/"
    announce(address)
    try:
        if once:
            server.handle_request()
        else:
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


def build_ui_response(
    *,
    request_target: str,
    root: Path,
    question: str,
    app: RepositoryApp | None = None,
) -> UIResponse:
    parsed = urlparse(request_target)
    if parsed.path != "/":
        return UIResponse(status=HTTPStatus.NOT_FOUND, body=b"Path not found.")

    repository_app = app or RepositoryApp()
    page_question = _resolve_question(parsed.query, question)
    body = repository_app.render_question_page(page_question, root).encode("utf-8")
    return UIResponse(status=HTTPStatus.OK, body=body)


def _resolve_question(query: str, fallback: str) -> str:
    params = parse_qs(query)
    candidate = params.get("question", [fallback])[0].strip()
    return candidate or fallback
