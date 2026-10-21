<h1 align="center">willay</h1>

<p align="center"><em>Agents write the episode. Willay performs it.</em></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="Apache-2.0"/></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/Python-3.12%2B-blue.svg" alt="Python 3.12+"/></a>
  <a href="https://github.com/intigraph/willay/actions/workflows/check.yml"><img src="https://github.com/intigraph/willay/actions/workflows/check.yml/badge.svg" alt="CI"/></a>
  <a href="docs/book/src/SUMMARY.md"><img src="https://img.shields.io/badge/docs-mdBook-green.svg" alt="Documentation"/></a>
</p>

*Willay* means “to tell / announce news” in Quechua. Give it an agent-written TOML
script with a configurable panel of hosts, ElevenLabs voices, effects and music
cues. It produces a finished MP3 with measured loudness, chapters and show notes,
and can publish it to an already-private podcast feed.

Willay does not call a language model. The agent writing the script already is one.

## See it in action

```sh
uv sync --locked
uv run --locked willay budget examples/episode.toml
uv run --locked willay render examples/episode.toml -o out/example
```

Budgeting needs no key and makes no network request. Rendering reads the key at
runtime from `ELEVENLABS_API_KEY_FILE` (or an already-held `ELEVENLABS_API_KEY`).
The default owner-only file is `~/.config/willay/elevenlabs_api_key`; deployments
may point at their existing vault-provisioned file. No key belongs in TOML or logs.

## What it does

- **Configurable hosts:** named voices and expressive turns, split at the API's
  2,000-character/ten-voice request boundary.
- **Effects and music:** local or generated sound effects, intro/outro files,
  transition crossfades and a quiet music bed ducked beneath the foreground.
- **Reusable takes:** content-addressed checked audio; changed model/text/voice
  creates a new take, ambiguous generation refuses automatic paid retry.
- **Finished episodes:** two-pass EBU R128 normalization, encoded MP3 measurements,
  actual duration, chapters, show notes and completion hashes.
- **Private subscriptions:** atomic RSS publishing, stable GUIDs and an authenticated
  reader with byte ranges for podcast apps, behind reviewed HTTPS routing.
- **Bounded usage:** shared host ledger, daily dialogue/effect/request ceilings,
  one renderer and Prometheus-format usage metrics.

## Episode spec

```toml
title = "A useful briefing"

[[hosts]]
id = "ana"
voice = "JBFqnCBsd6RMkjVDRZzb"

[[hosts]]
id = "rafa"
voice = "Aw4FAjKCGjjNkVhN1Xmq"

[[segments]]
chapter = "Welcome"
say = { host = "ana", text = "[curious] What changed?" }

[[segments]]
say = { host = "rafa", text = "Let's start with what was measured." }
```

Add `[music]` for intro/outro and a bed. Use `sfx` for a local file or generated
prompt, and `transition` for a local sting with crossfade. The whole spec and all
assets validate before any paid call. See [the format and commands](docs/podcast.md).

## CLI

```text
willay budget episode.toml
willay voices
willay render episode.toml -o out/episode
willay render episode.toml -o out/episode --feed-root /approved/feed --base-url https://podcasts.example.test
willay publish out/episode --feed-root /approved/feed --base-url https://podcasts.example.test
willay metrics
```

The feed reader is a separate reviewed service-host deployment; publishing files
alone does not create DNS, TLS or authentication. The [podcast skill](skills/podcast/SKILL.md)
helps agents write sourced episodes and verify actual listening results.

## Development and releases

```sh
just setup
just check
just build
just docs
```

Python/uv keep the existing credential client and tested subprocess pipeline
reusable. Release-please is the Python release-PR equivalent of release-plz;
release artifacts are built from the exact tag in the same workflow that creates
the release, with checksums. mdBook/Pages, quality entry points and licensing
follow the related stack repository conventions. See [the design decision](docs/design.md).

Source checks use synthetic tones and mocked provider calls, with real ffmpeg
assembly and actual authentication/range-handler controls. They do not certify
live provider speech, an installed feed or playback in a listener's app.
Personal listening is the intended use; generated voices are attributed to
ElevenLabs and output rights follow the account/service terms.
