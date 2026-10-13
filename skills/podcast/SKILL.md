---
name: podcast
description: Write an agent-authored multi-host podcast from supplied sources and render it with Willay, ElevenLabs voices, effects and a private feed. Use for podcast episodes and spoken crew briefings, not short task-completion speech.
---

The agent writes the episode; Willay performs it. Do not call another language
model or install NotebookLM software. Use the repository's TOML format and
`willay budget`, `willay voices`, `willay render` and optional feed arguments.
See [the runnable example](../../examples/episode.toml) and
[the rendering guide](../../docs/podcast.md).

Read the actual sources before scripting. Preserve the distinction between
proposed, reviewed, merged, installed and observed results. State uncertainty
in the dialogue where it matters. Put attribution and relevant links in the
description/show notes; remove credentials, raw private records and unnecessary
host identifiers. A private feed does not authorize publishing it publicly.

For a five-to-ten-minute episode, aim for roughly 700–1,400 spoken words, then
use the rendered duration rather than claiming a word-count estimate is timing.
Give hosts distinct roles, let questions move the story, and explain technical
terms once. Keep each turn below 2,000 characters. Use expressive bracket tags
sparingly. Do not invent quotes, conversations or speaker identity claims.
`[[hosts]]` configures any needed panel; calls split at ten unique voices.

Use `chapter` on a segment to mark topic boundaries. Intro/outro, transition
stings and a quiet ducked bed are optional local assets with listening rights.
An `sfx.prompt` incurs another paid request and effect-duration budget. Generated
effects and successful voice takes are content-addressed; retain originals.
Automatic music generation and language-model scripting are not part of Willay.

Run `willay budget episode.toml` before generation. Use the single approved
shared state directory for the rendering host. Key resolution happens at runtime
from the vault-provisioned owner-only file or an already-held environment value;
never print, paste, export from a crew launcher or place the key in TOML.
If a take is ambiguous, stop and retain its charge/receipt; do not delete the
ledger, change state directories or regenerate around the refusal.

Render with `willay render episode.toml -o episode-output/`. Publishing in the
same command needs both `--feed-root` and `--base-url` for an already-reviewed
private HTTPS/auth feed host. Do not start a service on a crew host. Listen to
the actual output, check loudness/duration and show notes, then verify the
authenticated feed and podcast-app playback. Synthetic tones establish pipeline
behavior, not successful ElevenLabs speech or phone playback.
