"""Bounded ElevenLabs calls; secrets and error bodies never enter output."""

from __future__ import annotations

import http.client
import json
import os
import re
import stat
import urllib.error
import urllib.request
from pathlib import Path

from . import credentials
from .spec import Refused


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def key() -> str:
    value = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not value:
        path = Path(
            os.environ.get("ELEVENLABS_API_KEY_FILE", "~/.config/willay/elevenlabs_api_key")
        ).expanduser()
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd) as f:
                info = os.fstat(f.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_mode & 0o077
                    or info.st_uid != os.getuid()
                ):
                    raise Refused("ElevenLabs key file must be owner-only and owned by this user")
                value = f.read(512).strip()
        except FileNotFoundError:
            raise Refused(
                "ElevenLabs key missing; Stiwi must provision it once from his vault"
            ) from None
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,256}", value):
        raise Refused("ElevenLabs key is invalid; nothing sent")
    try:
        return credentials.resolve_key({"ELEVENLABS_API_KEY": value})
    except credentials.CredentialError:
        raise Refused("ElevenLabs key resolution refused; nothing sent") from None


def call(kind: str, payload: dict, secret: str) -> bytes:
    endpoint = {"dialogue": "text-to-dialogue", "effect": "sound-generation"}[kind]
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/{endpoint}?output_format=mp3_44100_128",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"xi-api-key": secret, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=90) as response:
            if response.status != 200 or "audio" not in response.headers.get("Content-Type", ""):
                raise Refused("Provider returned an unexpected response; charge remains reserved")
            audio = response.read(25 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        raise Refused(
            f"Provider HTTP {exc.code}; charge remains reserved; no automatic retry"
        ) from None
    except (OSError, TimeoutError, http.client.HTTPException):
        raise Refused(
            "Provider result indeterminate; charge reserved; inspect before any retry"
        ) from None
    if not audio or len(audio) > 25 * 1024 * 1024:
        raise Refused("Provider audio empty/oversized; charge remains reserved")
    return audio


def voices() -> list[dict]:
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key()}
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as r:
            result = json.loads(r.read(1_000_001))
    except urllib.error.HTTPError as exc:
        raise Refused(f"Voice-list HTTP {exc.code}; no audio generated") from None
    except (OSError, ValueError):
        raise Refused("Could not read available voices") from None
    return [{"id": v["voice_id"], "name": v["name"]} for v in result["voices"]]
