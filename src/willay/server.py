"""Private feed reader for a reviewed host behind the LAN HTTPS router.

# arming: library -- CLI serve is installed/started through the scoped host role.
"""

from __future__ import annotations

import base64
import hmac
import os
import re
import stat
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .spec import Refused


def credential(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise Refused("Feed password file must be owner-only and owned by the serving user")
        password = f.read(512).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", password):
        raise Refused("Feed password must be 32..256 random token characters")
    return ("podcast:" + password).encode()


def handler(root: Path, expected: bytes):
    class FeedHandler(BaseHTTPRequestHandler):
        server_version = "willay"

        def setup(self):
            self.connection.settimeout(15)
            super().setup()

        def log_message(self, format, *args):
            # No access URL, Authorization header, password or transcript logging.
            pass

        def do_GET(self):
            self.read_file(False)

        def do_HEAD(self):
            self.read_file(True)

        def read_file(self, head: bool):
            auth = self.headers.get("Authorization", "")
            try:
                supplied = base64.b64decode(auth.removeprefix("Basic "), validate=True)
            except ValueError:
                supplied = b""
            if not auth.startswith("Basic ") or not hmac.compare_digest(supplied, expected):
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="Private podcasts"')
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            name = unquote(urlsplit(self.path).path).lstrip("/")
            if not re.fullmatch(
                r"feed\.xml|[0-9a-f]{64}/(episode\.mp3|chapters\.json|show-notes\.md)", name
            ):
                self.send_error(404)
                return
            path = root / name
            if any(p.is_symlink() for p in [path, path.parent]) or not path.is_file():
                self.send_error(404)
                return
            size = path.stat().st_size
            start, end = 0, size - 1
            status = 200
            request_range = self.headers.get("Range")
            if request_range:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", request_range)
                if match and any(match.groups()):
                    first, last = match.groups()
                    if first:
                        start = int(first)
                        end = min(int(last), size - 1) if last else size - 1
                    else:
                        start = max(0, size - int(last))
                    status = 206
                else:
                    start = size
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
            self.send_response(status)
            self.send_header(
                "Content-Type",
                {
                    ".xml": "application/rss+xml",
                    ".mp3": "audio/mpeg",
                    ".json": "application/json",
                    ".md": "text/markdown",
                }[path.suffix],
            )
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "private, max-age=300")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if not head:
                with path.open("rb") as f:
                    f.seek(start)
                    remaining = end - start + 1
                    while remaining:
                        data = f.read(min(remaining, 64 * 1024))
                        if not data:
                            break
                        self.wfile.write(data)
                        remaining -= len(data)

    return FeedHandler


def serve(root: Path, password_file: Path, bind: str, port: int):
    expected = credential(password_file)

    class BoundedServer(ThreadingHTTPServer):
        slots = threading.BoundedSemaphore(4)

        def process_request(self, request, client_address):
            if not self.slots.acquire(blocking=False):
                self.shutdown_request(request)
                return
            try:
                super().process_request(request, client_address)
            except Exception:
                self.slots.release()
                raise

        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                self.slots.release()

    server = BoundedServer((bind, port), handler(root.resolve(), expected))
    server.daemon_threads = True
    server.timeout = 15
    server.serve_forever()
