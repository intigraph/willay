"""Bounded ffmpeg assembly with chapters and measured R128 normalization."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import imageio_ffmpeg

from .spec import Episode, Refused


def executable() -> str:
    return shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()


def run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            [executable(), "-hide_banner", "-nostdin", "-threads", "1", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise Refused("ffmpeg unavailable or timed out") from None
    if result.returncode:
        raise Refused("ffmpeg refused the audio or assembly; original takes retained")
    return result


def pcm(source: Path, target: Path) -> float:
    run(
        [
            "-y",
            "-i",
            str(source),
            "-t",
            "1801",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(target),
        ]
    )
    with wave.open(str(target)) as w:
        duration = w.getnframes() / w.getframerate()
    if not 0.05 <= duration <= 1800:
        raise Refused("Audio duration outside 0.05..1800 seconds")
    return duration


def validate_assets(episode: Episode):
    paths = {Path(p.payload["file"]) for p in episode.pieces if p.kind == "file"}
    if episode.bed:
        paths.add(episode.bed)
    with tempfile.TemporaryDirectory(prefix="willay-assets-") as tmp:
        for i, path in enumerate(sorted(paths)):
            pcm(path, Path(tmp) / f"{i}.wav")


def completed(episode: Episode, output: Path) -> dict | None:
    receipt = output / "manifest.json"
    if not receipt.exists():
        return None
    data = json.loads(receipt.read_text())
    if set(data["files"]) != {"episode.mp3", "chapters.json", "show-notes.md"}:
        raise Refused("Unexpected completed output files")
    if data["source_hash"] != episode.source_hash:
        raise Refused("Output already belongs to another script; choose a new output directory")
    for name, sha in data["files"].items():
        path = output / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise Refused("Completed output changed; inspect before replacing it")
    return data


def assemble(episode: Episode, takes: list[Path], output: Path) -> dict:
    prior = completed(episode, output)
    if prior:
        return prior
    if len(takes) != len(episode.pieces):
        raise Refused("Incomplete take coverage")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".willay-", dir=output) as tmp:
        root = Path(tmp)
        durations = [pcm(p, root / f"{i}.wav") for i, p in enumerate(takes)]
        total = 0.0
        chapters = []
        args = ["-y"]
        for i in range(len(takes)):
            args += ["-i", str(root / f"{i}.wav")]
        filters = []
        current = "0:a"
        for i, (piece, duration) in enumerate(zip(episode.pieces, durations, strict=True)):
            fade = 0.0
            if i:
                requested = piece.crossfade or episode.pieces[i - 1].crossfade
                fade = min(requested, duration / 2, durations[i - 1] / 2)
                nxt = f"join{i}"
                operation = (
                    f"acrossfade=d={fade:.6f}:c1=tri:c2=tri" if fade else "concat=n=2:v=0:a=1"
                )
                filters.append(f"[{current}][{i}:a]{operation}[{nxt}]")
                current = nxt
            start = max(0, total - fade)
            if not chapters or piece.label != chapters[-1]["title"]:
                chapters.append({"startTime": round(start, 3), "title": piece.label})
            total += duration - fade
        if total > 1800:
            raise Refused("Episode longer than 30 minutes; no silent truncation")
        if episode.bed:
            bed_index = len(takes)
            args += ["-stream_loop", "-1", "-i", str(episode.bed)]
            filters += [
                f"[{current}]asplit=2[speech][duckkey]",
                (
                    f"[{bed_index}:a]aresample=44100,aformat=channel_layouts=stereo,"
                    f"volume={episode.bed_gain}dB[quietbed]"
                ),
                (
                    "[quietbed][duckkey]sidechaincompress=threshold=0.015:ratio=8:"
                    "attack=20:release=250[ducked]"
                ),
                "[speech][ducked]amix=inputs=2:duration=first:normalize=0[withbed]",
            ]
            current = "withbed"
        if not filters:
            filters.append("[0:a]anull[joined]")
            current = "joined"
        mixed = root / "mixed.wav"
        run(
            [
                *args,
                "-filter_complex_threads",
                "1",
                "-filter_complex",
                ";".join(filters),
                "-map",
                f"[{current}]",
                "-t",
                f"{total:.6f}",
                "-c:a",
                "pcm_s16le",
                str(mixed),
            ]
        )
        analysis = run(
            [
                "-i",
                str(mixed),
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                "-f",
                "null",
                "-",
            ]
        )
        try:
            measured, _ = json.JSONDecoder().raw_decode(
                analysis.stderr[analysis.stderr.rfind("{") :]
            )
            values = [
                float(measured[k])
                for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
            ]
        except (ValueError, KeyError):
            raise Refused(
                "No valid R128 measurement; silence is not a normalized episode"
            ) from None
        if not all(math.isfinite(v) for v in values):
            raise Refused("R128 measurement is nonfinite; check silent takes")
        norm = (
            f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={values[0]}:"
            f"measured_TP={values[1]}:measured_LRA={values[2]}:measured_thresh={values[3]}:"
            f"offset={values[4]}:linear=true:print_format=json"
        )
        mp3 = root / "episode.mp3"
        run(
            [
                "-y",
                "-i",
                str(mixed),
                "-af",
                norm,
                "-ar",
                "44100",
                "-ac",
                "2",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "128k",
                "-metadata",
                f"title={episode.title}",
                str(mp3),
            ]
        )
        check = run(
            [
                "-i",
                str(mp3),
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                "-f",
                "null",
                "-",
            ]
        )
        observed, _ = json.JSONDecoder().raw_decode(check.stderr[check.stderr.rfind("{") :])
        loudness, peak = float(observed["input_i"]), float(observed["input_tp"])
        if not math.isfinite(loudness) or not math.isfinite(peak):
            raise Refused("Finished audio has no finite loudness measurement")
        chapter_path = root / "chapters.json"
        chapter_path.write_text(
            json.dumps({"version": "1.2.0", "chapters": chapters}, indent=2) + "\n"
        )
        notes = root / "show-notes.md"
        body = [
            f"# {episode.title}",
            "",
            episode.description,
            "",
            "AI-generated voices by ElevenLabs. Personal listening.",
        ]
        for p in episode.pieces:
            if p.kind == "dialogue":
                body += ["", *[f"- {t['text']}" for t in p.payload["inputs"]]]
        notes.write_text("\n".join(body) + "\n")
        files = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (mp3, chapter_path, notes)
        }
        data = {
            "source_hash": episode.source_hash,
            "duration_seconds": round(total, 3),
            "title": episode.title,
            "description": episode.description,
            "files": files,
            "normalization": {
                "target_lufs": -16,
                "target_true_peak_db": -1.5,
                "measured_output_lufs": loudness,
                "measured_output_true_peak_db": peak,
            },
            "scope": "actual assembly; provider provenance recorded separately in take ledger",
        }
        for name in files:
            (root / name).replace(output / name)
        # Completion receipt is last; a partial assembly never looks complete.
        (root / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
        (root / "manifest.json").replace(output / "manifest.json")
    return data
