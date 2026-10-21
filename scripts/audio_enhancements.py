"""Lightweight original audio-bed generation and YouTube chapter helpers.

The soundtrack is synthesised locally from simple chords and soft plucks. No
downloaded/copyrighted music or extra API key is required.
"""
from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import Iterable

import numpy as np

_CHORDS = (
    (130.81, 196.00, 261.63, 329.63),  # Cmaj7
    (110.00, 164.81, 220.00, 261.63),  # Am7
    (87.31, 174.61, 220.00, 261.63),   # Fmaj7
    (98.00, 196.00, 246.94, 293.66),   # G6
)
_MELODY = (392.00, 329.63, 293.66, 440.00, 392.00, 329.63, 261.63, 293.66)


def _pad(times: np.ndarray, frequencies: tuple[float, ...], detune: float = 0.0) -> np.ndarray:
    """A quiet warm pad with restrained upper harmonics."""
    result = np.zeros_like(times)
    for index, frequency in enumerate(frequencies):
        f = frequency + detune
        result += 0.205 * np.sin(2 * math.pi * f * times + index * 0.23)
        result += 0.035 * np.sin(2 * math.pi * (2 * f) * times + index * 0.41)
    return result * 0.024


def generate_music_bed(
    duration_seconds: float,
    output_path: str | Path,
    sample_rate: int = 24000,
) -> Path:
    """Write an original soft instrumental music bed as stereo PCM WAV."""
    duration_seconds = float(duration_seconds)
    sample_rate = int(sample_rate)
    if duration_seconds <= 0:
        raise ValueError("Music-bed duration must be positive.")
    if sample_rate < 8000 or sample_rate > 96000:
        raise ValueError("Sample rate must be between 8kHz and 96kHz.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    total_samples = max(1, int(round(duration_seconds * sample_rate)))
    chunk_samples = sample_rate * 2
    chord_seconds = 8.0
    transition_seconds = 1.15
    melody = np.asarray(_MELODY, dtype=np.float64)

    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)

        for offset in range(0, total_samples, chunk_samples):
            count = min(chunk_samples, total_samples - offset)
            times = (np.arange(offset, offset + count, dtype=np.float64) / sample_rate)
            chord_indices = (times / chord_seconds).astype(np.int64) % len(_CHORDS)
            position_in_chord = np.mod(times, chord_seconds)
            transition = np.clip(
                (position_in_chord - (chord_seconds - transition_seconds))
                / transition_seconds,
                0.0,
                1.0,
            )
            transition = transition * transition * (3.0 - 2.0 * transition)

            left = np.zeros(count, dtype=np.float64)
            right = np.zeros(count, dtype=np.float64)
            for chord_index, chord in enumerate(_CHORDS):
                mask = chord_indices == chord_index
                if not np.any(mask):
                    continue
                local_times = times[mask]
                blend = transition[mask]
                next_chord = _CHORDS[(chord_index + 1) % len(_CHORDS)]
                left[mask] = (
                    _pad(local_times, chord) * (1.0 - blend)
                    + _pad(local_times, next_chord) * blend
                )
                right[mask] = (
                    _pad(local_times, chord, detune=0.035) * (1.0 - blend)
                    + _pad(local_times, next_chord, detune=0.035) * blend
                )

            # Very soft notes add a little musical movement without competing with speech.
            bar_position = np.mod(times, 4.0)
            note_indices = (times / 4.0).astype(np.int64) % len(melody)
            note_frequencies = melody[note_indices]
            pluck = (
                np.sin(2.0 * math.pi * note_frequencies * bar_position)
                * np.exp(-3.4 * bar_position)
                * (bar_position < 0.95)
                * 0.0045
            )
            pan_right = np.where(note_indices % 2 == 0, 0.40, 0.85)
            pan_left = np.where(note_indices % 2 == 0, 0.85, 0.40)
            left += pluck * pan_left
            right += pluck * pan_right

            # Gentle movement and fades; keep the soundtrack safely below narration.
            swell = 0.88 + 0.12 * (0.5 + 0.5 * np.sin(2.0 * math.pi * times / 7.0))
            fade_in = np.clip(times / 1.6, 0.0, 1.0)
            fade_out = np.clip((duration_seconds - times) / 2.2, 0.0, 1.0)
            envelope = swell * fade_in * fade_out
            left *= envelope
            right *= envelope
            stereo = np.column_stack((left, right))
            pcm = np.clip(stereo * 32767.0, -32768, 32767).astype("<i2")
            wav.writeframes(pcm.tobytes())

    print(f"Created original soft music bed: {output} ({duration_seconds:.1f}s)")
    return output


def _chapter_timestamp(seconds: float) -> str:
    value = max(0, int(seconds))
    hours, remainder = divmod(value, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def build_chapters(turns: Iterable[dict], duration_seconds: float) -> list[str]:
    """Create concise YouTube chapters from generated dialogue section markers."""
    candidates: list[tuple[float, str]] = [(0.0, "Hook and today's question")]
    labels_by_type = (
        ({"question", "follow_up", "story"}, "Real conversation and examples"),
        ({"language_tip"}, "Useful phrases explained"),
        ({"practice"}, "Speaking practice"),
        ({"recap"}, "Review and next step"),
    )
    seen = set()

    for turn in turns:
        turn_type = str(turn.get("turn_type", "reaction")).lower()
        start = float(turn.get("start", 0.0) or 0.0)
        if start < 0 or start >= float(duration_seconds):
            continue
        for accepted_types, label in labels_by_type:
            if turn_type in accepted_types and label not in seen:
                if start >= 12.0:
                    candidates.append((start, label))
                    seen.add(label)
                break

    candidates.sort(key=lambda item: item[0])
    accepted: list[tuple[float, str]] = []
    for start, label in candidates:
        if accepted and start - accepted[-1][0] < 10.0:
            continue
        accepted.append((start, label))

    return [f"{_chapter_timestamp(start)} {label}" for start, label in accepted]

def select_short_windows(
    segments: Iterable[dict],
    duration_seconds: float,
    max_clips: int = 3,
    target_seconds: float = 30.0,
    min_seconds: float = 18.0,
    max_seconds: float = 35.0,
    min_gap_seconds: float = 35.0,
) -> list[dict]:
    """Choose short-video excerpts that start/end on spoken segment boundaries."""
    duration_seconds = float(duration_seconds)
    if duration_seconds <= 0 or max_clips <= 0:
        return []

    valid_segments = []
    for item in segments:
        try:
            start = float(item.get("start", 0))
            end = float(item.get("end", 0))
            turn_index = int(item.get("turn_index", -1))
        except (TypeError, ValueError):
            continue
        if turn_index < 0 or start < 0 or end <= start or start >= duration_seconds:
            continue
        valid_segments.append({
            **item,
            "start": start,
            "end": min(end, duration_seconds),
            "turn_index": turn_index,
            "turn_type": str(item.get("turn_type", "reaction")).lower(),
            "text": str(item.get("text", "")).strip(),
        })

    if not valid_segments:
        return []

    turns: dict[int, dict] = {}
    for item in valid_segments:
        turn_id = item["turn_index"]
        if turn_id not in turns:
            turns[turn_id] = {
                "start": item["start"],
                "end": item["end"],
                "turn_type": item["turn_type"],
                "text": item["text"],
            }
        else:
            turns[turn_id]["start"] = min(turns[turn_id]["start"], item["start"])
            turns[turn_id]["end"] = max(turns[turn_id]["end"], item["end"])
            if item["text"]:
                turns[turn_id]["text"] += " " + item["text"]

    priorities = ("hook", "language_tip", "practice", "story", "question", "follow_up")
    selected = []

    def candidate_for(anchor: dict) -> dict | None:
        start = float(anchor["start"])
        limit = min(duration_seconds, start + max_seconds)
        ends = sorted({
            float(item["end"])
            for item in valid_segments
            if float(item["start"]) >= start - 0.02
            and float(item["end"]) > start
            and float(item["end"]) <= limit + 0.02
        })
        viable = [end for end in ends if min_seconds <= end - start <= max_seconds]
        if not viable:
            return None
        end = min(viable, key=lambda value: abs((value - start) - target_seconds))
        return {
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "turn_type": str(anchor["turn_type"]),
            "hook_text": str(anchor["text"])[:300],
        }

    ordered_turns = sorted(turns.values(), key=lambda item: item["start"])
    for turn_type in priorities:
        if len(selected) >= max_clips:
            break
        for anchor in ordered_turns:
            if anchor["turn_type"] != turn_type:
                continue
            candidate = candidate_for(anchor)
            if candidate is None:
                continue
            if any(
                abs(candidate["start"] - existing["start"]) < min_gap_seconds
                for existing in selected
            ):
                continue
            selected.append(candidate)
            break

    # If the draft has fewer named beats than expected, find other clean
    # excerpts instead of silently producing fewer usable short-video assets.
    if len(selected) < max_clips:
        for anchor in ordered_turns:
            candidate = candidate_for(anchor)
            if candidate is None:
                continue
            if any(
                abs(candidate["start"] - existing["start"]) < min_gap_seconds
                for existing in selected
            ):
                continue
            selected.append(candidate)
            if len(selected) >= max_clips:
                break

    selected.sort(key=lambda item: item["start"])
    return selected[:max_clips]

