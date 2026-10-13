from __future__ import annotations

import hashlib
import json
import wave
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from willay import feed, media, provider
from willay.cli import render
from willay.spec import Piece, Refused, load
from willay.store import DAILY_CHARS, Store


def script(root: Path, segments: str, extra: str = "") -> Path:
    path = root / "episode.toml"
    path.write_text(
        'title="Fixture episode"\n' + extra + '\n[[hosts]]\nid="a"\nvoice="voiceA"\n'
        '\n[[hosts]]\nid="b"\nvoice="voiceB"\n' + segments
    )
    return path


def tone(path: Path, seconds=0.8, frequency=440):
    media.run(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:duration={seconds}",
            "-c:a",
            "pcm_s16le",
            str(path),
        ]
    )


def test_toml_chunking_preserves_all_turns(tmp_path):
    turns = ["a" * 1400, "b" * 900, "c" * 800]
    path = script(
        tmp_path, "".join(f'\n[[segments]]\nsay={{host="a",text="{t}"}}\n' for t in turns)
    )
    episode = load(path)
    assert [p.chars for p in episode.pieces] == [1400, 1700]
    assert [t["text"] for p in episode.pieces for t in p.payload["inputs"]] == turns


def test_more_than_ten_hosts_split_without_losing_speakers(tmp_path):
    path = tmp_path / "episode.toml"
    path.write_text(
        'title="Panel"\n'
        + "".join(f'\n[[hosts]]\nid="h{i}"\nvoice="v{i}"\n' for i in range(12))
        + "".join(f'\n[[segments]]\nsay={{host="h{i}",text="hello"}}\n' for i in range(12))
    )
    pieces = load(path).pieces
    assert [len(p.payload["inputs"]) for p in pieces] == [10, 2]


@pytest.mark.parametrize(
    "segment",
    [
        'say={host="unknown",text="hello"}',
        'say={host="a",text=""}',
        'sfx={file="missing.wav"}',
        'transition={prompt="whoosh"}',
        'sfx={prompt="whoosh",duration_seconds=nan}',
        'say={host="a",text="hello"}\nsfx={prompt="whoosh"}',
    ],
)
def test_invalid_inputs_refuse_before_transport(tmp_path, segment):
    path = script(tmp_path, "\n[[segments]]\n" + segment + "\n")
    calls = []
    with pytest.raises(Refused):
        render(path, tmp_path / "out", Store(tmp_path / "state"), lambda *a: calls.append(a))
    assert calls == []


def test_spec_cannot_carry_credentials(tmp_path):
    path = script(tmp_path, '\n[[segments]]\nsay={host="a",text="hello"}', 'api_key="secret"')
    with pytest.raises(Refused):
        load(path)


def test_changed_asset_changes_episode_identity(tmp_path):
    tone(tmp_path / "sting.wav")
    path = script(
        tmp_path, '\n[[segments]]\nsay={host="a",text="hello"}', '[music]\nintro="sting.wav"'
    )
    before = load(path).source_hash
    tone(tmp_path / "sting.wav", frequency=880)
    assert load(path).source_hash != before


def piece(chars=40, value="x"):
    return Piece(
        "dialogue",
        {"model_id": "eleven_v3", "inputs": [{"text": value * chars, "voice_id": "v"}]},
        "Dialogue",
    )


def test_cache_reuses_bytes_without_spending_again(tmp_path):
    store = Store(tmp_path)
    calls = []
    with store.lock():
        path = store.take(piece(), lambda *a: calls.append(a) or b"fixture")
        assert store.take(piece(), lambda *a: pytest.fail("duplicate call")) == path
    assert len(calls) == 1
    assert store.usage()["reserved_characters"] == 40


def test_timeout_retains_charge_and_never_retries(tmp_path):
    store = Store(tmp_path)

    def fail(*_):
        raise TimeoutError

    with pytest.raises(TimeoutError):
        store.take(piece(), fail)
    assert Store(tmp_path).usage()["reserved_characters"] == 40
    with pytest.raises(Refused):
        store.take(piece(), lambda *a: pytest.fail("ambiguous retry"))
    with pytest.raises(Refused):
        store.preflight([piece()])


def test_budget_rejects_entire_batch_before_call(tmp_path):
    store = Store(tmp_path)
    with store.db:
        store.db.execute(
            "INSERT INTO takes VALUES (?,?,?,?,?,NULL)",
            ("earlier", store.usage()["day_utc"], DAILY_CHARS - 20, 0, "reserved"),
        )
    with pytest.raises(Refused):
        store.preflight([piece()])
    assert store.db.execute("SELECT count(*) FROM takes").fetchone()[0] == 1


def test_duplicate_payload_preflight_is_one_paid_request(tmp_path):
    assert len(Store(tmp_path).preflight([piece(), piece()])) == 1


def test_changed_cached_bytes_refuse(tmp_path):
    store = Store(tmp_path)
    p = store.take(piece(), lambda *_: b"good")
    p.write_bytes(b"drift")
    with pytest.raises(Refused):
        store.preflight([piece()])


def test_global_render_lock_excludes_second_renderer(tmp_path):
    first, second = Store(tmp_path), Store(tmp_path)
    with first.lock(), pytest.raises(Refused), second.lock():
        pytest.fail("second renderer entered")


def test_missing_key_reserves_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setenv("ELEVENLABS_API_KEY_FILE", str(tmp_path / "missing"))
    path = script(tmp_path, '\n[[segments]]\nsay={host="a",text="hello"}')
    store = Store(tmp_path / "state")
    with pytest.raises(Refused):
        render(path, tmp_path / "out", store)
    assert store.usage()["reserved_requests"] == 0


def test_key_file_permissions_and_symlink_refuse(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    path = tmp_path / "key"
    path.write_text("synthetic_token_1234567890")
    path.chmod(0o644)
    monkeypatch.setenv("ELEVENLABS_API_KEY_FILE", str(path))
    with pytest.raises(Refused):
        provider.key()
    path.chmod(0o600)
    assert provider.key() == "synthetic_token_1234567890"
    link = tmp_path / "link"
    link.symlink_to(path)
    monkeypatch.setenv("ELEVENLABS_API_KEY_FILE", str(link))
    with pytest.raises(OSError):
        provider.key()


def test_actual_ffmpeg_crossfade_duck_normalize_publish(tmp_path):
    for name, hz in [("intro", 220), ("sting", 600), ("bed", 110), ("voice", 440)]:
        tone(tmp_path / (name + ".wav"), frequency=hz)
    path = script(
        tmp_path,
        '\n[[segments]]\nchapter="First topic"\nsay={host="a",text="hello"}\n'
        '\n[[segments]]\ntransition={file="sting.wav",crossfade_ms=200}\n'
        '\n[[segments]]\nchapter="Second topic"\nsay={host="b",text="bye"}\n',
        '[music]\nintro="intro.wav"\noutro="intro.wav"\nbed={file="bed.wav",gain_db=-24}\n',
    )
    audio = (tmp_path / "voice.wav").read_bytes()
    store = Store(tmp_path / "state")
    calls = []
    out = tmp_path / "out"
    result = render(path, out, store, lambda *args: calls.append(args) or audio)
    assert len(calls) == 2
    assert abs(result["duration_seconds"] - 3.6) < 0.05
    assert (out / "episode.mp3").stat().st_size > 1000
    with wave.open(str(tmp_path / "voice.wav")) as w:
        assert w.getnframes() > 0
    chapter_data = json.loads((out / "chapters.json").read_text())
    assert {"First topic", "Second topic"} <= {c["title"] for c in chapter_data["chapters"]}
    assert render(path, out, store, lambda *_: pytest.fail("duplicate provider call")) == result
    feed_root = tmp_path / "feed"
    ident = feed.publish(out, feed_root, "https://podcasts.example.test/private")
    assert feed.publish(out, feed_root, "https://podcasts.example.test/private") == ident
    xml = ET.parse(feed_root / "feed.xml")
    assert len(xml.findall("./channel/item")) == 1
    enclosure = xml.find("./channel/item/enclosure")
    assert int(enclosure.attrib["length"]) == (out / "episode.mp3").stat().st_size
    assert (
        hashlib.sha256((feed_root / ident / "episode.mp3").read_bytes()).hexdigest()
        == result["files"]["episode.mp3"]
    )
    (out / "episode.mp3").write_bytes(b"drift")
    with pytest.raises(Refused):
        feed.publish(out, feed_root, "https://podcasts.example.test/private")


@pytest.mark.parametrize(
    "url", ["http://example.test", "https://u:p@example.test", "https://example.test?token=secret"]
)
def test_feed_url_refuses_insecure_or_embedded_credentials(tmp_path, url):
    with pytest.raises(Refused):
        feed.publish(tmp_path, tmp_path / "feed", url)
