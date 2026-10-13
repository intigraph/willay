# CLI

```sh
uv sync --locked
uv run --locked willay --version
uv run --locked willay budget examples/episode.toml
uv run --locked willay voices
uv run --locked willay render examples/episode.toml -o out/example
uv run --locked willay metrics
```

An already-approved private host can render and publish in one command:

```sh
willay render episode.toml -o out/episode \
  --feed-root /approved/feed --base-url https://podcasts.example.test
```

`willay publish` publishes an existing completed output. `willay serve` implements
the separate authenticated reader for a reviewed service host; it is not a
crew-session background launcher. The podcast skill is in `skills/podcast`.

Quality and documentation entry points are `just check`, `just build` and
`just docs`. Release wheels and source archives carry published checksums.
