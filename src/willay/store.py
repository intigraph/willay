"""One shared host ledger: reserve before sending, retain ambiguous charges."""

from __future__ import annotations

import fcntl
import hashlib
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .spec import Refused

DAILY_CHARS = 20_000
DAILY_EFFECT_SECONDS = 30
DAILY_REQUESTS = 20


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if root.is_symlink():
            raise Refused("State directory may not be a symlink")
        self.db = sqlite3.connect(root / "usage.sqlite")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS takes (id TEXT PRIMARY KEY, day TEXT NOT NULL, "
            "chars INTEGER NOT NULL, seconds REAL NOT NULL, status TEXT NOT NULL, sha TEXT)"
        )
        self.db.commit()
        os.chmod(root / "usage.sqlite", 0o600)
        (root / "takes").mkdir(mode=0o700, exist_ok=True)

    @contextmanager
    def lock(self):
        fd = os.open(self.root / "render.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Refused(
                    "Another renderer holds the shared ledger; wait for its completion"
                ) from None
            yield
        finally:
            os.close(fd)

    def caps(self) -> tuple[int, int]:
        # Operator-controlled, day-scoped admission; scripts cannot set this in TOML.
        day = datetime.now(UTC).date().isoformat()
        if os.environ.get("WILLAY_CAP_OVERRIDE_DATE") != day:
            return DAILY_CHARS, DAILY_REQUESTS
        try:
            chars = int(os.environ.get("WILLAY_DAILY_CHARACTER_CAP", DAILY_CHARS))
            requests = int(os.environ.get("WILLAY_DAILY_REQUEST_CAP", DAILY_REQUESTS))
        except ValueError:
            raise Refused("Operator caps must be integers") from None
        if not 1 <= chars <= 60_000 or not 1 <= requests <= 60:
            raise Refused("Operator caps outside permitted character/request bounds")
        return chars, requests

    def usage(self) -> dict:
        day = datetime.now(UTC).date().isoformat()
        chars, seconds, requests = self.db.execute(
            "SELECT coalesce(sum(chars),0),coalesce(sum(seconds),0),count(*) "
            "FROM takes WHERE day=?",
            (day,),
        ).fetchone()
        chars_cap, requests_cap = self.caps()
        return {
            "day_utc": day,
            "reserved_characters": chars,
            "reserved_effect_seconds": seconds,
            "reserved_requests": requests,
            "character_cap": chars_cap,
            "effect_seconds_cap": DAILY_EFFECT_SECONDS,
            "request_cap": requests_cap,
        }

    def preflight(self, pieces):
        new = {}
        for piece in pieces:
            if piece.kind == "file":
                continue
            row = self.db.execute(
                "SELECT status,sha FROM takes WHERE id=?", (piece.cache_key,)
            ).fetchone()
            if row:
                path = self.root / "takes" / (piece.cache_key + ".mp3")
                if (
                    row[0] != "complete"
                    or not path.is_file()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != row[1]
                ):
                    raise Refused(
                        "Ambiguous or changed cached take; inspect before any provider call"
                    )
            else:
                new[piece.cache_key] = piece
        u = self.usage()
        if (
            u["reserved_characters"] + sum(p.chars for p in new.values()) > u["character_cap"]
            or u["reserved_effect_seconds"] + sum(p.effect_seconds for p in new.values())
            > DAILY_EFFECT_SECONDS
            or u["reserved_requests"] + len(new) > u["request_cap"]
        ):
            raise Refused(
                "Daily host character/effect/request budget would be exceeded; nothing sent"
            )
        return list(new.values())

    def take(self, piece, transport) -> Path:
        ident = piece.cache_key
        path = self.root / "takes" / (ident + ".mp3")
        row = self.db.execute("SELECT status,sha FROM takes WHERE id=?", (ident,)).fetchone()
        if row:
            if (
                row[0] == "complete"
                and path.is_file()
                and hashlib.sha256(path.read_bytes()).hexdigest() == row[1]
            ):
                return path
            raise Refused("Take is indeterminate or cached bytes changed; no automatic paid retry")
        self.preflight([piece])
        with self.db:
            self.db.execute(
                "INSERT INTO takes VALUES (?,?,?,?,?,NULL)",
                (
                    ident,
                    datetime.now(UTC).date().isoformat(),
                    piece.chars,
                    piece.effect_seconds,
                    "reserved",
                ),
            )
        audio = transport(piece.kind, piece.payload)
        if not isinstance(audio, bytes) or not audio:
            raise Refused("Empty or invalid audio; reservation retained")
        temporary = path.with_suffix(".pending")
        with temporary.open("xb") as f:
            os.chmod(temporary, 0o600)
            f.write(audio)
            f.flush()
            os.fsync(f.fileno())
        temporary.replace(path)
        with self.db:
            self.db.execute(
                "UPDATE takes SET status='complete',sha=? WHERE id=?",
                (hashlib.sha256(audio).hexdigest(), ident),
            )
        return path
