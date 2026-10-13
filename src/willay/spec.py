"""Validate the entire TOML episode before any paid generation."""

from __future__ import annotations

import hashlib
import json
import math
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

MAX_CHARS = 12_000
CHUNK_CHARS = 2_000


class Refused(ValueError):
    pass


def text(value: object, field: str, maximum: int = 2_000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise Refused(f"{field}: expected nonempty text, at most {maximum} characters")
    return value


def number(value: object, field: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Refused(f"{field}: expected a number")
    if not math.isfinite(value) or not low <= value <= high:
        raise Refused(f"{field}: outside {low}..{high}")
    return float(value)


def fields(value: object, allowed: set[str], required: set[str]) -> dict:
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - allowed:
        raise Refused("Unrecognized or missing fields in episode")
    return value


def asset(value: object, root: Path) -> Path:
    name = text(value, "asset", 512)
    path = (root / name).resolve()
    if not path.is_file() or path.stat().st_size > 100 * 1024 * 1024:
        raise Refused("Asset missing, not a regular file, or larger than 100 MiB")
    return path


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class Piece:
    kind: str
    payload: dict
    label: str
    crossfade: float = 0

    @property
    def chars(self) -> int:
        return sum(len(x["text"]) for x in self.payload["inputs"]) if self.kind == "dialogue" else 0

    @property
    def effect_seconds(self) -> float:
        return self.payload["duration_seconds"] if self.kind == "effect" else 0

    @property
    def cache_key(self) -> str:
        return digest({"kind": self.kind, "payload": self.payload, "format": "mp3_44100_128"})


@dataclass(frozen=True)
class Episode:
    title: str
    description: str
    pieces: tuple[Piece, ...]
    bed: Path | None
    bed_gain: float
    source_hash: str

    def budget(self) -> dict:
        return {
            "dialogue_characters": sum(p.chars for p in self.pieces),
            "generated_effect_seconds": sum(p.effect_seconds for p in self.pieces),
            "paid_requests": sum(p.kind != "file" for p in self.pieces),
            "pieces": len(self.pieces),
        }


def load(path: Path) -> Episode:
    raw = path.read_bytes()
    if len(raw) > 1_000_000:
        raise Refused("Spec larger than 1 MB")
    data = tomllib.loads(raw.decode())
    fields(
        data,
        {"title", "description", "hosts", "music", "segments", "model"},
        {"title", "hosts", "segments"},
    )
    title = text(data["title"], "title", 200)
    description = data.get("description", "")
    if not isinstance(description, str) or len(description) > 4_000:
        raise Refused("Invalid description")
    model = data.get("model", "eleven_v3")
    if model not in {"eleven_v3", "eleven_v4"}:
        raise Refused("Dialogue model must be eleven_v3 or eleven_v4")
    hosts = data["hosts"]
    if not isinstance(hosts, list) or not 1 <= len(hosts) <= 200:
        raise Refused("Expected 1..200 hosts")
    voices = {}
    for h in hosts:
        fields(h, {"id", "voice", "persona"}, {"id", "voice"})
        name = text(h["id"], "host id", 64)
        voice = text(h["voice"], "voice", 64)
        if name in voices or not re.fullmatch(r"[A-Za-z0-9_-]+", voice):
            raise Refused("Duplicate host or invalid voice ID")
        voices[name] = voice
    music = fields(data.get("music", {}), {"intro", "outro", "bed"}, set())
    root = path.resolve().parent
    pieces: list[Piece] = []
    turns: list[dict] = []

    def flush():
        if turns:
            pieces.append(Piece("dialogue", {"inputs": list(turns), "model_id": model}, "Dialogue"))
            turns.clear()

    if "intro" in music:
        pieces.append(Piece("file", {"file": str(asset(music["intro"], root))}, "Intro"))
    segments = data["segments"]
    if not isinstance(segments, list) or not 1 <= len(segments) <= 200:
        raise Refused("Expected 1..200 segments")
    for s in segments:
        fields(s, {"say", "sfx", "transition", "chapter"}, set())
        kinds = set(s) - {"chapter"}
        if len(kinds) != 1:
            raise Refused("Each segment must contain exactly one say/sfx/transition")
        kind = kinds.pop()
        label = text(
            s.get("chapter", "Dialogue" if kind == "say" else kind.title()), "chapter", 200
        )
        if "chapter" in s:
            flush()
        if kind == "say":
            v = fields(s[kind], {"host", "text"}, {"host", "text"})
            if v["host"] not in voices:
                raise Refused("Unknown host")
            said = text(v["text"], "turn")
            if (
                sum(len(t["text"]) for t in turns) + len(said) > CHUNK_CHARS
                or len({t["voice_id"] for t in turns} | {voices[v["host"]]}) > 10
            ):
                flush()
            turns.append({"text": said, "voice_id": voices[v["host"]]})
            if "chapter" in s:
                # Retain chapter title on the next flushed group.
                pieces.append(Piece("marker", {}, label))
        else:
            flush()
            v = fields(s[kind], {"file", "prompt", "duration_seconds", "crossfade_ms"}, set())
            if ("file" in v) == ("prompt" in v) or (kind == "transition" and "file" not in v):
                raise Refused("Choose one file or sfx prompt; transitions require a file")
            fade = number(v.get("crossfade_ms", 0), "crossfade_ms", 0, 2_000) / 1_000
            if "file" in v:
                pieces.append(Piece("file", {"file": str(asset(v["file"], root))}, label, fade))
            else:
                prompt = text(v["prompt"], "effect prompt", 300)
                duration = number(v.get("duration_seconds", 2), "effect duration", 0.5, 10)
                pieces.append(
                    Piece(
                        "effect",
                        {
                            "text": prompt,
                            "duration_seconds": duration,
                            "model_id": "eleven_text_to_sound_v2",
                        },
                        label,
                    )
                )
    flush()
    if "outro" in music:
        pieces.append(Piece("file", {"file": str(asset(music["outro"], root))}, "Outro"))
    # Fold zero-length chapter markers into their following dialogue chunk.
    folded = []
    pending = None
    for piece in pieces:
        if piece.kind == "marker":
            pending = piece.label
        else:
            folded.append(Piece(piece.kind, piece.payload, pending or piece.label, piece.crossfade))
            pending = None
    if not any(p.kind == "dialogue" for p in folded):
        raise Refused("Episode needs spoken dialogue")
    bed = None
    gain = -24.0
    if "bed" in music:
        v = fields(music["bed"], {"file", "gain_db"}, {"file"})
        bed = asset(v["file"], root)
        gain = number(v.get("gain_db", -24), "bed gain", -60, -12)
    assets = {p.payload["file"] for p in folded if p.kind == "file"}
    if bed:
        assets.add(str(bed))
    identity = digest(
        {
            "script_sha256": hashlib.sha256(raw).hexdigest(),
            "assets": {
                name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in sorted(assets)
            },
        }
    )
    episode = Episode(title, description, tuple(folded), bed, gain, identity)
    if episode.budget()["dialogue_characters"] > MAX_CHARS:
        raise Refused("Episode exceeds 12,000 dialogue characters")
    return episode
