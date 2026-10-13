# Episode specification

The format is TOML. Host IDs reference voice IDs chosen from `willay voices`.
Each segment contains exactly one `say`, `sfx` or `transition`. A chapter title
on a segment introduces a topic boundary. The whole spec validates before any
paid call, including all local assets.

```toml
title = "An evidence briefing"
description = "Source links and listening context go here."

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

`[music]` accepts intro/outro file paths and
`bed = { file = "assets/bed.mp3", gain_db = -24 }`. A transition accepts
`{ file = "assets/sting.mp3", crossfade_ms = 400 }`. Effects accept a local
`file` or a generated `prompt` plus bounded `duration_seconds`. Asset paths
are relative to the spec. Use only assets you have listening rights for.
Models are `eleven_v3` or `eleven_v4`; expressiveness tags stay in turn text.
