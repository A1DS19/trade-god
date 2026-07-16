"""Health check HTTP server — GET /health returns JSON with last heartbeat."""

import json
import logging
import socketserver
import threading
from http.server import BaseHTTPRequestHandler

from app.bot.heartbeat import get as heartbeat_get

log = logging.getLogger(__name__)


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            beat = heartbeat_get()
            body = json.dumps(
                {
                    "status": "ok",
                    "last_heartbeat": beat.isoformat() if beat else None,
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # suppress default HTTP request logs


class _ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def start_health_server(port: int = 8080) -> None:
    server = _ReusableTCPServer(("", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log.info("Health check listening on :%d", port)
