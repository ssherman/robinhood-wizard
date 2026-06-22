"""A one-shot localhost HTTP server that catches the OAuth redirect.

The browser is sent to Robinhood's authorize URL with our ``redirect_uri`` pointing
here; after consent it redirects back with ``?code=...&state=...`` (or ``?error=...``),
which this server captures and hands back to the login flow.
"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pydantic


class CallbackResult(pydantic.BaseModel):
    code: str | None = None
    state: str | None = None
    error: str | None = None


class OAuthCallbackServer:
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._requested_port = port
        self._result: CallbackResult | None = None
        self._httpd: HTTPServer | None = None
        self._bound_port: int | None = None
        self._listening = threading.Event()

    @property
    def redirect_uri(self) -> str:
        port = self._bound_port or self._requested_port
        return f"http://{self._host}:{port}/callback"

    def wait_until_listening(self, timeout: float) -> int:
        if not self._listening.wait(timeout):
            raise TimeoutError("callback server did not start listening")
        assert self._bound_port is not None
        return self._bound_port

    def wait_for_code(self, timeout: float) -> CallbackResult:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 (stdlib API name)
                qs = parse_qs(urlparse(self.path).query)
                server._result = CallbackResult(
                    code=(qs.get("code") or [None])[0],
                    state=(qs.get("state") or [None])[0],
                    error=(qs.get("error") or [None])[0],
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Robinhood Wizard: you may close this tab.")

            def log_message(self, *args) -> None:  # silence stdlib logging
                pass

        self._httpd = HTTPServer((self._host, self._requested_port), Handler)
        self._bound_port = self._httpd.server_address[1]
        self._listening.set()

        deadline = time.monotonic() + timeout
        while self._result is None and time.monotonic() < deadline:
            self._httpd.handle_request()
        self._httpd.server_close()
        return self._result or CallbackResult(error="timeout")
