# Budgets and private feeds

Keys resolve at runtime from an already-held `ELEVENLABS_API_KEY` or an owner-only
`ELEVENLABS_API_KEY_FILE`. The public default is
`~/.config/willay/elevenlabs_api_key`; deployments can point at an existing vault
file. Keys never belong in TOML, source, subprocess arguments or output.

One shared rendering state directory enforces daily UTC ceilings of 20,000
dialogue characters, 30 generated-effect seconds and 20 paid calls. Every
attempt reserves first; failures and ambiguous timeouts are not automatically
refunded. This is a local reservation cap, not an account-global invoice meter.
`willay metrics` reports usage and ceilings without script text or secrets.

The feed requires private HTTPS routing and authentication. Its reader requires
Basic auth for RSS/media/HEAD, restricts served paths, refuses symlinks and supports
byte ranges. The feed root must already be private before publication. Verify
both unauthorized refusal and authenticated playback in the actual podcast app.

Personal listening is the intended use. Notes attribute generated voices to
ElevenLabs; output rights still depend on account/service terms. Keep private
sources and voices out of public repositories. Rollback disables the scoped
feed/skill while retaining originals and the quota ledger.
