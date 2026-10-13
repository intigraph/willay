# willay

*willay* (Quechua): to tell, to announce, news.

Agents write the episode; willay performs it. You give it a script with any
number of hosts, sound effects and music cues, and it renders one finished
podcast episode, using ElevenLabs voices.

willay does not call a language model. The agent that uses it already is one.

## Episode spec (draft)

```yaml
title: What the crew shipped this week
hosts:                       # any number, 1..N
  - id: ana
    voice: <elevenlabs-voice-id>
    persona: curious, asks the questions
  - id: rafa
    voice: <elevenlabs-voice-id>
    persona: dry, knows the details
music:
  intro: assets/intro.mp3
  outro: assets/outro.mp3
  bed: { file: assets/bed.mp3, gain_db: -24 }   # optional under-speech bed
segments:
  - say: { host: ana, text: "[excited] Welcome back!" }
  - say: { host: rafa, text: "Three releases and one very stubborn alert." }
  - sfx: { file: assets/whoosh.wav }            # or { prompt: "soft whoosh" } via ElevenLabs sound effects
  - transition: { file: assets/sting.mp3, crossfade_ms: 400 }
  - say: { host: ana, text: "Let's start with the alert." }
```

## Pipeline

1. Validate the spec (hosts referenced exist, assets exist, character budget).
2. Group consecutive `say` turns into dialogue chunks within the API limit and
   render each with ElevenLabs Text to Dialogue (multi-speaker, expressive tags).
3. Render `sfx` from files or ElevenLabs sound-effect prompts; cache every render
   by content hash so re-runs only pay for what changed.
4. Assemble with ffmpeg: intro, segments, transitions with crossfades, music bed
   ducked under speech, outro; EBU R128 loudness normalisation.
5. Write `episode.mp3`, chapters and show notes, and optionally publish to a
   private RSS feed.

## Interfaces

- CLI: `willay render episode.yaml -o out/`, `willay voices`, `willay budget episode.yaml`
- Agent skill: how to write a good multi-host script for willay.
- MCP tool: later.

## Safety

- The ElevenLabs key comes from the environment, never from the spec or the repo.
- A per-day character cap and a dry-run budget check before any paid call.

## Status

Design only. See the issues for the build plan.
