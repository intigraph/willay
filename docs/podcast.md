# Rendering and private feeds

Python 3.12+ and uv are required. The optional packaged ffmpeg binary avoids a
system-wide tool install; a system ffmpeg takes precedence. The dependency lock
pins both runtime and development dependencies. From the checkout:

```sh
uv sync --locked
uv run --locked willay budget examples/episode.toml
uv run --locked willay voices
uv run --locked willay render examples/episode.toml -o out/example
```

To install the reviewed package in an approved source environment, build the
wheel with `uv build --wheel` and use the reviewed wheel/dependency hashes in
the normal host deployment lane. A local development checkout is not the
installed host artifact.

`ELEVENLABS_API_KEY` may already be held by the process. Otherwise Willay reads
`ELEVENLABS_API_KEY_FILE`, defaulting to the existing owner-only
`~/.config/willay/elevenlabs_api_key`. Stiwi provisions his key from the vault once.
The runtime reads it without printing/logging or passing it in a subprocess
argument. Do not export it from a crew launcher: session snapshots can retain
environment values. The credential resolver is reused from the pinned
[cc-speaks source](cc-speaks-provenance.md); the resolver is adapted to the public configuration contract.
The original summary TTS endpoint and local playback function are not used.

The CLI validates the whole TOML script, resolves every asset and validates
local audio before paid generation. It groups speech by turns into at most
2,000 text characters and ten voices per dialogue call. An episode can have
more hosts across multiple chunks. More than 12,000 spoken characters refuses
rather than truncating. Models are `eleven_v3` (default) or `eleven_v4`.

Local effects use `sfx = { file = "assets/whoosh.wav" }`. Generated effects use
`sfx = { prompt = "soft whoosh", duration_seconds = 2 }`. Transitions accept a
local file and `crossfade_ms`, up to 2,000; the overlap is clipped to half each
neighbor's duration. `[music]` supports intro/outro files and
`bed = { file = "assets/bed.mp3", gain_db = -24 }`; the bed loops and ducks under
the assembled foreground. The two-pass EBU R128 target is -16 LUFS and -1.5 dB
true peak. The final encoded MP3 is measured again; observed values and duration
are in `manifest.json`, with file hashes, chapters and show notes.

One renderer holds a nonblocking host-wide state lock. The default shared
directory is `~/.local/state/willay`, overridable only as an installation choice
with `WILLAY_STATE_DIR`. Use the same directory for every renderer on that host.
Daily UTC ceilings are 20,000 dialogue characters, 30 generated-effect seconds
and 20 paid calls. These are conservative local reservations, not an invoice
or an account-global limit across other products/hosts. SFX billing is distinct
from text length. Every attempted call reserves quota first, including refusals
and ambiguous timeouts; reservations are not refunded automatically. A changed
voice/model/text is a new take. Successful unchanged takes reuse checked bytes;
changed cache bytes or ambiguous takes refuse any automatic paid retry.

`willay metrics` emits reserved usage and ceilings as Prometheus text, without
episode text or credentials. Install its collector on the actual rendering
host through the reviewed schedule; metrics on another state directory do not
prove that renderer's cap is live. Quota-ledger removal is not normal cleanup.

## Private feed host

The feed is an existing reviewed LAN web-host deployment, separate from a crew
session. `willay serve --feed-root /approved/feed --password-file /private/file`
is the reader implementation, not an instruction to start a daemon on a crew
host. Its default bind is loopback. A host role provides a scoped router mapping
and TLS, and selects the private password file for its serving user. Basic auth
is required for RSS, media and HEAD requests. The reader supports byte ranges,
allows only feed/media/chapter/show-note paths, refuses symlinks and suppresses
access logs. Four connections and a 15-second socket timeout bound the reader.
Use it behind HTTPS; plain LAN HTTP is not a private subscription transport.

Publish a completed output in one command on the admitted rendering/feed host:

```sh
willay render episode.toml -o out/episode \
  --feed-root /approved/feed --base-url https://podcasts.example.test
```

Or use `willay publish` for an already-rendered output. Publishing checks exact
completed-file hashes, updates feed artifacts atomically and keeps the same
episode GUID on repeated publication. It does not create DNS, TLS or access
control. The supplied feed root must already be private; an HTTPS URL alone
does not establish authentication. Feed credentials remain outside URLs/TOML.
Stiwi subscribes to `/feed.xml` and enters the feed login in his podcast app.
Actual app compatibility/playback needs a witnessed acceptance, not a local
RSS parser assertion.

Rollback disables the scoped feed service/route and removes the skill from
provisioning while retaining takes, published originals, encryption/access
secrets and the usage ledger. No general volume prune or shared-service restart.

## Tests and limits

```sh
uv run --locked pytest -q
uv run --locked ruff check src tests
uv run --locked ty check src
```

Credential semantics are covered by key-resolution tests; typing/lint cover all modules.
Offline fixtures use real ffmpeg and synthetic tones with a mocked voice
transport, and exercise the real auth/range handler without launching a daemon.
These checks do not prove provider voice availability, good generated speech,
host installation or playback in Stiwi's app. No MCP or crew job bridge is
installed by this CLI.

Current primary API guidance: [dialogue endpoint](https://elevenlabs.io/docs/api-reference/text-to-dialogue/convert),
[sound effects](https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert)
and [output rights](https://help.elevenlabs.io/hc/en-us/articles/13313564601361-Can-I-publish-the-content-I-generate-on-the-platform).
Personal listening is the requested use. Free-plan shared output needs ElevenLabs
attribution; commercial rights depend on the paid-plan/service-specific terms,
and beta services have separate restrictions. The show notes attribute generated
voices. Do not assume a commercial or beta-output license from API availability.

Provider generation has a bounded 300-second timeout. Transport failures report
only the exception class and elapsed time; charges remain reserved and are not
retried automatically. An operator can authorize a UTC-day-scoped budget via
`WILLAY_CAP_OVERRIDE_DATE=YYYY-MM-DD`, `WILLAY_DAILY_CHARACTER_CAP`, and
`WILLAY_DAILY_REQUEST_CAP` (maximum 60,000 and 60). Without a matching current
UTC date, the normal 20,000/20 defaults apply. The effect-seconds cap is unchanged.
This configuration requires the operator's explicit quota approval; never use it
to evade a refusal, and never reset the ledger.
