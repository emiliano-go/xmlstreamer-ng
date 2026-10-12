import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class _FeedRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append({
            "path": self.path,
            "headers": {k.lower(): v for k, v in self.headers.items()},
        })
        route = self.server.routes.get(self.path)
        if route is None:
            self.send_response(404)
            self.end_headers()
            return
        body, content_type, delay, truncate_after = route
        if delay:
            time.sleep(delay)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if truncate_after is not None:
            # Send a partial body and drop the connection abruptly.
            self.wfile.write(body[:truncate_after])
            self.wfile.flush()
            self.connection.close()
            return
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


class LocalFeedServer:
    def __init__(self, server: ThreadingHTTPServer):
        self._server = server
        self.requests = server.requests

    def serve(
        self,
        path: str,
        body: bytes,
        content_type: str = "application/xml",
        delay: float = 0.0,
        truncate_after: int = None,
    ) -> str:
        """Register a route and return its full URL."""
        self._server.routes[path] = (body, content_type, delay, truncate_after)
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}{path}"

    def last_headers(self) -> dict:
        """Headers (lowercased keys) of the last request received."""
        return self.requests[-1]["headers"]


@pytest.fixture()
def http_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FeedRequestHandler)
    server.routes = {}
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield LocalFeedServer(server)
    finally:
        server.shutdown()
        server.server_close()
