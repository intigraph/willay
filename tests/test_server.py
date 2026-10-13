"""Exercise the real HTTP handler without starting a daemon or listener."""

import base64
import io

import pytest

from willay.server import handler
from willay.spec import Piece, Refused
from willay.store import Store


def request(root, path="/feed.xml", auth=True, range_header=None, head=False):
    cls = handler(root, b"podcast:synthetic_fixture_password")

    class Probe(cls):
        def send_response(self, code, message=None):
            self.status = code

        def send_header(self, name, value):
            self.response[name] = value

        def end_headers(self):
            pass

        def send_error(self, code, message=None, explain=None):
            self.status = code

    p = Probe.__new__(Probe)
    p.path = path
    p.headers = {}
    if auth:
        p.headers["Authorization"] = (
            "Basic " + base64.b64encode(b"podcast:synthetic_fixture_password").decode()
        )
    if range_header:
        p.headers["Range"] = range_header
    p.response = {}
    p.wfile = io.BytesIO()
    p.read_file(head)
    return p.status, p.response, p.wfile.getvalue()


def test_private_feed_requires_auth_even_on_head(tmp_path):
    (tmp_path / "feed.xml").write_bytes(b"private feed")
    assert request(tmp_path, auth=False)[0] == 401
    assert request(tmp_path, auth=False, head=True)[0] == 401
    status, headers, body = request(tmp_path)
    assert status == 200 and body == b"private feed"
    assert headers["Cache-Control"].startswith("private")


def test_phone_media_ranges_and_head(tmp_path):
    ident = "a" * 64
    (tmp_path / ident).mkdir()
    (tmp_path / ident / "episode.mp3").write_bytes(b"0123456789")
    status, headers, body = request(tmp_path, f"/{ident}/episode.mp3", range_header="bytes=2-5")
    assert (status, body) == (206, b"2345")
    assert headers["Content-Range"] == "bytes 2-5/10"
    assert request(tmp_path, f"/{ident}/episode.mp3", range_header="bytes=-3")[2] == b"789"
    assert request(tmp_path, f"/{ident}/episode.mp3", head=True)[2] == b""
    assert request(tmp_path, f"/{ident}/episode.mp3", range_header="bytes=100-")[0] == 416


@pytest.mark.parametrize(
    "path", ["/../secret", "/%2e%2e/secret", "/.publish.lock", "/episodes.json"]
)
def test_reader_never_exposes_state_or_traversal(tmp_path, path):
    assert request(tmp_path, path)[0] == 404


def test_reader_refuses_symlink(tmp_path):
    private = tmp_path / "secret"
    private.write_text("private")
    (tmp_path / "feed.xml").symlink_to(private)
    assert request(tmp_path)[0] == 404


def test_effect_budget_is_distinct_from_text_characters(tmp_path):
    store = Store(tmp_path)
    piece = Piece("effect", {"text": "soft whoosh", "duration_seconds": 10}, "Effect")
    store.take(piece, lambda *_: b"fixture")
    assert store.usage()["reserved_effect_seconds"] == 10
    assert store.usage()["reserved_characters"] == 0
    other = [Piece("effect", {"text": str(i), "duration_seconds": 10}, "Effect") for i in range(3)]
    with pytest.raises(Refused):
        store.preflight(other)
