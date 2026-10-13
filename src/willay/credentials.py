"""Credential ladder adapted from Steve Brown's cc-speaks client.

The runtime wrapper verifies file ownership/permissions before delegating here.
No model key is stored in a script specification or printed by this resolver.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

KEY_SHAPE = re.compile(r"[A-Za-z0-9_\-]{20,}")


class CredentialError(ValueError):
    pass


def _expand(candidate: str, env: Mapping[str, str]) -> Path:
    path = Path(candidate)
    if not candidate.startswith("~"):
        return path
    home = env.get("HOME")
    if not home:
        return path.expanduser()
    return Path(home) / candidate.lstrip("~").lstrip("/")


def _checked_key(value: str, _source: str) -> str:
    if KEY_SHAPE.fullmatch(value):
        return value
    raise CredentialError("Key is not shaped like a key; nothing sent")


def _resolve(value_env: str, file_env: str, default_file: str, env: Mapping[str, str]) -> str:
    env_val = (env.get(value_env) or "").strip()
    if env_val:
        return _checked_key(env_val, value_env)
    for candidate in (env.get(file_env), default_file):
        if not candidate:
            continue
        path = _expand(candidate, env)
        try:
            value = path.read_text().strip()
        except OSError:
            continue
        if value:
            return _checked_key(value, str(path))
    return ""


def resolve_key(env: Mapping[str, str]) -> str:
    return _resolve("ELEVENLABS_API_KEY", "ELEVENLABS_API_KEY_FILE", "", env)
