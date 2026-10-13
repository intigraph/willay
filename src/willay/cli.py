"""Agent-written TOML -> voices -> finished podcast; no language-model calls."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, feed, media, provider, server
from .spec import Refused, load
from .store import Store


def state() -> Path:
    return Path(os.environ.get("WILLAY_STATE_DIR", "~/.local/state/willay")).expanduser()


def render(spec: Path, output: Path, store: Store, transport=None) -> dict:
    episode = load(spec)
    prior = media.completed(episode, output)
    if prior:
        return prior
    media.validate_assets(episode)
    with store.lock():
        pending = store.preflight(episode.pieces)
        if transport is None and pending:
            secret = provider.key()

            def transport(kind, payload):
                return provider.call(kind, payload, secret)

        takes = [
            Path(p.payload["file"]) if p.kind == "file" else store.take(p, transport)
            for p in episode.pieces
        ]
        return media.assemble(episode, takes, output)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="willay")
    parser.add_argument("--version", action="version", version=f"willay {__version__}")
    sub = parser.add_subparsers(dest="verb", required=True)
    for verb in ["budget", "render"]:
        p = sub.add_parser(verb)
        p.add_argument("spec", type=Path)
        if verb == "render":
            p.add_argument("-o", "--output", type=Path, required=True)
            p.add_argument("--feed-root", type=Path)
            p.add_argument("--base-url")
    sub.add_parser("voices")
    sub.add_parser("metrics")
    p = sub.add_parser("publish")
    p.add_argument("output", type=Path)
    p.add_argument("--feed-root", type=Path, required=True)
    p.add_argument("--base-url", required=True)
    p = sub.add_parser("serve", help="Reader only; use the reviewed HTTPS/auth host lane")
    p.add_argument("--feed-root", type=Path, required=True)
    p.add_argument("--password-file", type=Path, required=True)
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8082)
    args = parser.parse_args(argv)
    try:
        if args.verb == "budget":
            result = load(args.spec).budget()
        elif args.verb == "voices":
            result = provider.voices()
        elif args.verb == "publish":
            result = {
                "episode_id": feed.publish(args.output, args.feed_root, args.base_url),
                "hosting": "Requires the already-reviewed private HTTPS/auth web root",
            }
        elif args.verb == "serve":
            server.serve(args.feed_root, args.password_file, args.bind, args.port)
            return 0
        else:
            store = Store(state())
            if args.verb == "metrics":
                u = store.usage()
                for name in [
                    "reserved_characters",
                    "reserved_effect_seconds",
                    "reserved_requests",
                    "character_cap",
                    "effect_seconds_cap",
                    "request_cap",
                ]:
                    print(f"willay_daily_{name} {u[name]}")
                return 0
            if bool(args.feed_root) != bool(args.base_url):
                raise Refused("Publishing needs both --feed-root and --base-url")
            result = render(args.spec, args.output, store)
            if args.feed_root:
                feed.publish(args.output, args.feed_root, args.base_url)
        print(json.dumps(result, indent=2))
        return 0
    except (Refused, OSError, ValueError, KeyError) as exc:
        # No provider exception bodies or key values reach this surface.
        print(f"willay: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
