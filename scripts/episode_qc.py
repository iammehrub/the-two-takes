"""Free, local quality checks for a finished Two Takes episode.

Uses only Python's standard library plus ffprobe/ffmpeg already installed by CI.
The report is written before upload; hard failures stop a broken render from
being published, while editorial targets are reported as warnings.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def _probe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,channels,sample_rate",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _duration(data: dict) -> float:
    try:
        return float(data.get("format", {}).get("duration", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _volume(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(path),
            "-vn", "-af", "volumedetect", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    log = (result.stderr or "") + "\n" + (result.stdout or "")
    mean_match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", log)
    peak_match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", log)
    return {
        "mean_volume_db": float(mean_match.group(1)) if mean_match else None,
        "peak_volume_db": float(peak_match.group(1)) if peak_match else None,
    }


def create_report(root, script, voice_path, video_path, subtitle_path) -> dict:
    root = Path(root)
    work = root / "work"
    warnings = []
    errors = []

    voice_path = Path(voice_path)
    video_path = Path(video_path)
    subtitle_path = Path(subtitle_path)
    required_files = {
        "voice": voice_path,
        "final_video": video_path,
        "captions": subtitle_path,
        "chapters": work / "chapters.txt",
        "metadata": work / "youtube_metadata.json",
    }
    for label, path in required_files.items():
        if not path.exists() or path.stat().st_size == 0:
            errors.append(f"Missing or empty {label} file: {path}")

    lines = [line.strip() for line in str(script).splitlines() if line.strip()]
    dialogue_lines = [
        line for line in lines if re.match(r"^(Himel|Niha):\s*.+", line, re.I)
    ]
    word_count = len(re.findall(r"\b[\w’'-]+\b", str(script)))
    host_counts = {
        host: sum(1 for line in dialogue_lines if line.lower().startswith(host.lower() + ":"))
        for host in ("Himel", "Niha")
    }
    host_total = sum(host_counts.values())
    host_balance = (
        round(min(host_counts.values()) / max(host_counts.values()), 3)
        if max(host_counts.values()) else 0.0
    )

    voice_info = _probe(voice_path) if voice_path.exists() and voice_path.stat().st_size else {}
    video_info = _probe(video_path) if video_path.exists() and video_path.stat().st_size else {}
    voice_seconds = _duration(voice_info)
    video_seconds = _duration(video_info)
    video_streams = [s for s in video_info.get("streams", []) if s.get("codec_type") == "video"]
    audio_streams = [s for s in video_info.get("streams", []) if s.get("codec_type") == "audio"]
    voice_streams = [s for s in voice_info.get("streams", []) if s.get("codec_type") == "audio"]

    video_stream = video_streams[0] if video_streams else {}
    audio_stream = audio_streams[0] if audio_streams else {}
    duration_difference = round(abs(video_seconds - voice_seconds), 3)

    if not video_streams:
        errors.append("Final video has no video stream.")
    elif (
        int(video_stream.get("width", 0) or 0) < 1920
        or int(video_stream.get("height", 0) or 0) < 1080
        or video_stream.get("codec_name") != "h264"
    ):
        errors.append("Final video failed the 1920x1080 H.264 requirement.")

    if not audio_streams:
        errors.append("Final video has no audio stream.")
    else:
        if audio_stream.get("codec_name") != "aac":
            errors.append("Final audio is not AAC.")
        if int(audio_stream.get("channels", 0) or 0) < 2:
            errors.append("Final audio is not stereo.")

    if voice_seconds <= 0 or video_seconds <= 0:
        errors.append("Could not determine a valid media duration.")
    elif duration_difference > 2.5:
        errors.append(
            f"Audio/video duration mismatch is {duration_difference:.2f}s (limit 2.5s)."
        )

    subtitle_count = 0
    if subtitle_path.exists():
        subtitle_text = subtitle_path.read_text(encoding="utf-8", errors="replace")
        subtitle_count = len(re.findall(r"(?m)^\d+\s*$", subtitle_text))
        if subtitle_count < 10:
            errors.append(f"Too few subtitle cues ({subtitle_count}); captions may be missing.")

    chapters_path = work / "chapters.txt"
    chapter_lines = []
    if chapters_path.exists():
        chapter_lines = [
            line.strip()
            for line in chapters_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip()
        ]
    if len(chapter_lines) < 3 or not chapter_lines[0].startswith("00:00"):
        warnings.append("YouTube chapters are missing or incomplete.")

    if word_count < 1250:
        warnings.append(f"Script is short for the target format ({word_count} words).")
    if voice_seconds:
        estimated_spoken_seconds = max(1.0, voice_seconds - 12.5)
        estimated_wpm = round(word_count / estimated_spoken_seconds * 60, 1)
    else:
        estimated_wpm = None
    if estimated_wpm is not None and not 115 <= estimated_wpm <= 165:
        warnings.append(
            f"Estimated speech pace is {estimated_wpm} WPM; review pacing and pauses."
        )
    if host_total < 20:
        warnings.append(f"Only {host_total} labeled dialogue turns were found.")
    if host_balance < 0.45:
        warnings.append(f"Host turn balance is uneven: {host_counts}.")

    audio_levels = _volume(video_path) if video_path.exists() and video_path.stat().st_size else {}
    if audio_levels.get("peak_volume_db") is not None and audio_levels["peak_volume_db"] > -0.1:
        warnings.append("Audio peak is close to 0 dBFS; listen for clipping.")
    if audio_levels.get("mean_volume_db") is not None and audio_levels["mean_volume_db"] < -30:
        warnings.append("Average audio level is very quiet; review playback volume.")

    report = {
        "status": "failed" if errors else ("passed_with_warnings" if warnings else "passed"),
        "word_count": word_count,
        "dialogue_turns": host_total,
        "host_turn_counts": host_counts,
        "host_balance_ratio": host_balance,
        "voice_duration_seconds": round(voice_seconds, 2),
        "final_video_duration_seconds": round(video_seconds, 2),
        "audio_video_duration_difference_seconds": duration_difference,
        "estimated_speech_wpm": estimated_wpm,
        "video": {
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "codec": video_stream.get("codec_name"),
        },
        "audio": {
            "codec": audio_stream.get("codec_name"),
            "channels": audio_stream.get("channels"),
            "sample_rate": audio_stream.get("sample_rate"),
            **audio_levels,
        },
        "subtitle_cues": subtitle_count,
        "chapters": chapter_lines,
        "warnings": warnings,
        "errors": errors,
    }

    json_path = work / "production_report.json"
    text_path = work / "production_report.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text_lines = [
        "THE TWO TAKES — FREE PRODUCTION QUALITY REPORT",
        f"Status: {report['status']}",
        f"Script words: {word_count}",
        f"Dialogue turns: {host_total} (Himel {host_counts['Himel']}, Niha {host_counts['Niha']})",
        f"Estimated speech pace: {estimated_wpm} WPM",
        f"Voice duration: {voice_seconds:.2f}s",
        f"Final video duration: {video_seconds:.2f}s",
        f"Audio/video difference: {duration_difference:.2f}s",
        f"Video: {video_stream.get('width')}x{video_stream.get('height')} {video_stream.get('codec_name')}",
        f"Audio: {audio_stream.get('codec_name')} / {audio_stream.get('channels')} channels / {audio_stream.get('sample_rate')} Hz",
        f"Subtitle cues: {subtitle_count}",
        f"Mean audio volume: {audio_levels.get('mean_volume_db')} dBFS",
        f"Peak audio volume: {audio_levels.get('peak_volume_db')} dBFS",
        "",
        "WARNINGS:",
        *(f"- {item}" for item in warnings) if warnings else ["- None"],
        "",
        "ERRORS:",
        *(f"- {item}" for item in errors) if errors else ["- None"],
    ]
    text_path.write_text("\n".join(text_lines) + "\n", encoding="utf-8")

    print(f"Production QC report: {json_path}")
    print(f"Production QC status: {report['status']}")
    for warning in warnings:
        print(f"QC WARNING: {warning}")
    if errors:
        raise RuntimeError(
            "Production quality gate failed before upload: " + "; ".join(errors)
        )
    print("Production quality gate passed.")
    return report
