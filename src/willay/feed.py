"""Atomically publish only completed episodes into an already-private web root."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlsplit

from .spec import Refused


def publish(output: Path, root: Path, base_url: str) -> str:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise Refused("Private feed needs an HTTPS base URL without embedded credentials/query")
    manifest = json.loads((output / "manifest.json").read_text())
    ident = manifest["source_hash"]
    if len(ident) != 64 or any(c not in "0123456789abcdef" for c in ident):
        raise Refused("Invalid completed episode identity")
    for name in ["episode.mp3", "chapters.json", "show-notes.md"]:
        if hashlib.sha256((output / name).read_bytes()).hexdigest() != manifest["files"].get(name):
            raise Refused("Output checksum mismatch; nothing published")
    root.mkdir(parents=True, exist_ok=True, mode=0o750)
    with (root / ".publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        index = root / "episodes.json"
        entries = json.loads(index.read_text()) if index.exists() else []
        target = root / ident
        if not target.exists():
            with tempfile.TemporaryDirectory(prefix=".publish-", dir=root) as tmp:
                staging = Path(tmp) / ident
                staging.mkdir(mode=0o750)
                for name in ["episode.mp3", "chapters.json", "show-notes.md"]:
                    shutil.copyfile(output / name, staging / name)
                    os.chmod(staging / name, 0o640)
                staging.rename(target)
        else:
            for name in manifest["files"]:
                if (
                    hashlib.sha256((target / name).read_bytes()).hexdigest()
                    != manifest["files"][name]
                ):
                    raise Refused("Published episode identity drift; refusing replacement")
        if not any(e["id"] == ident for e in entries):
            entries.append(
                {
                    "id": ident,
                    "title": manifest["title"],
                    "description": manifest["description"],
                    "published": format_datetime(datetime.now(UTC)),
                    "length": (output / "episode.mp3").stat().st_size,
                }
            )
        rss = ET.Element("rss", {"version": "2.0"})
        channel = ET.SubElement(rss, "channel")
        for name, value in [
            ("title", "Crew podcasts"),
            ("link", base_url),
            ("description", "Private agent-written episodes; AI voices by ElevenLabs"),
        ]:
            ET.SubElement(channel, name).text = value
        for entry in reversed(entries):
            item = ET.SubElement(channel, "item")
            for name, value in [
                ("title", entry["title"]),
                ("description", entry["description"]),
                ("pubDate", entry["published"]),
                ("guid", entry["id"]),
            ]:
                ET.SubElement(item, name).text = value
            ET.SubElement(
                item,
                "enclosure",
                {
                    "url": f"{base_url.rstrip('/')}/{entry['id']}/episode.mp3",
                    "type": "audio/mpeg",
                    "length": str(entry["length"]),
                },
            )
        for name, content in [
            ("episodes.json", json.dumps(entries, indent=2).encode()),
            ("feed.xml", ET.tostring(rss, encoding="utf-8", xml_declaration=True)),
        ]:
            fd, temp = tempfile.mkstemp(prefix=".feed-", dir=root)
            with os.fdopen(fd, "wb") as f:
                os.chmod(temp, 0o640)
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            Path(temp).replace(root / name)
    return ident
