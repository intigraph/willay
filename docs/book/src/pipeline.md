# Rendering pipeline

Validate every host, turn and asset before generation. Consecutive turns form
dialogue chunks with at most 2,000 characters and ten unique voices. More hosts
can appear in later chunks; no turn is silently truncated.

The shared usage ledger reserves before each paid call. Content hashes bind
model, text, voice and output format; checked successful takes are reusable.
Ambiguous calls retain reservations and refuse automatic retry.

ffmpeg decodes originals, assembles ordered audio with transition crossfades,
loops and ducks a quiet bed, then performs two-pass EBU R128 normalization.
The encoded MP3 is measured again. `manifest.json` records actual duration,
loudness and hashes; `chapters.json` and `show-notes.md` accompany it.

Publishing verifies those hashes, uses a stable GUID and updates RSS atomically.
The authenticated reader supports byte ranges for podcast apps. Publication
does not create host routing or authorize making a private feed public.
