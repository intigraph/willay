#!/usr/bin/env bash
set -euo pipefail
printf '%s
' 'Base: 7471d8f49671a7af48893b4bc7722883f893657a (design only)'
if git cat-file -e 7471d8f49671a7af48893b4bc7722883f893657a:pyproject.toml 2>/dev/null; then
  printf '%s
' 'Unexpected executable package on base'; exit 1
else
  printf '%s
' 'Observed: no executable package on base'
fi
printf '%s
' 'Candidate CLI; no provider calls:' 'uv run --locked willay --version'
uv run --locked willay --version
printf '%s
' 'uv run --locked willay budget examples/episode.toml'
uv run --locked willay budget examples/episode.toml
printf '%s
' 'Negative control: unknown host refuses before provider I/O'
uv run --locked python - <<'CHECK'
import tempfile
from pathlib import Path
from willay.spec import Refused, load
with tempfile.TemporaryDirectory() as directory:
    target=Path(directory)/'bad.toml'
    target.write_text('title="Negative control"\n[[hosts]]\nid="a"\nvoice="example"\n[[segments]]\nsay={host="unknown",text="hello"}\n')
    try:
        load(target)
    except Refused as error:
        print('REFUSED:',error)
    else:
        raise SystemExit('Refusal control failed')
CHECK
