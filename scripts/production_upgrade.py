"""Original studio-style production layer for Two Takes Podcast.

Designed around the English-learning podcast genre without copying another
channel's protected branding, artwork, scripts, characters, or exact voice.
"""

import html
import json
import re
import subprocess
import textwrap
import requests
import time
from pathlib import Path

import build_podcast as app
from audio_enhancements import build_chapters, generate_music_bed, select_short_windows

VIDEO_W = 1920
VIDEO_H = 1080
FPS = 30
ENCODE_PRESET = "ultrafast"
ENCODE_CRF = "23"


def _run(cmd, label="FFmpeg"):
    started = time.time()
    print(f"{label}: starting...")
    subprocess.run(cmd, check=True)
    print(f"{label}: finished in {(time.time() - started) / 60:.1f} min")


def _ts(seconds):
    ms = max(0, int(round(seconds * 1000)))
    h = ms // 3_600_000
    ms %= 3_600_000
    m = ms // 60_000
    ms %= 60_000
    s = ms // 1000
    ms %= 1000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _caption_chunks(text, max_words=5):
    words = re.findall(r"\S+", text.strip())
    return [" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words) if words[i:i + max_words]]


def _ass_ts(seconds):
    total_cs = max(0, int(round(float(seconds) * 100)))
    hours, remainder = divmod(total_cs, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{seconds:02}.{centiseconds:02}"


def make_srt(script, audio_seconds):
    """Write ordinary SRT for QA plus speaker-positioned ASS for the rendered video."""
    timing_path = Path(app.WORK) / "tts_segments.json"
    try:
        segments = json.loads(timing_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Missing or invalid TTS timing data: {exc}") from exc
    if not isinstance(segments, list) or not segments:
        raise RuntimeError("Missing exact TTS timing data; refusing to create drifting subtitles.")

    rows = []
    for seg in segments:
        start = float(seg["start"])
        end = float(seg["end"])
        text = str(seg.get("text", "")).strip()
        speaker = str(seg.get("speaker", "")).strip().title()
        if speaker not in {"Himel", "Niha"} or end <= start or not text:
            continue
        chunks = _caption_chunks(text, max_words=5)
        total_words = sum(len(chunk.split()) for chunk in chunks) or 1
        cursor = start
        for index, chunk in enumerate(chunks):
            share = len(chunk.split()) / total_words
            chunk_end = end if index == len(chunks) - 1 else cursor + (end - start) * share
            rows.append((
                max(0.0, cursor - 0.03),
                min(float(audio_seconds), chunk_end + 0.03),
                chunk,
                speaker,
            ))
            cursor = chunk_end
    if not rows:
        raise RuntimeError("No valid speaker-labelled captions could be generated.")

    srt_path = Path(app.WORK) / "captions.srt"
    with srt_path.open("w", encoding="utf-8") as file:
        for index, (start, end, caption, _speaker) in enumerate(rows, 1):
            file.write(f"{index}\n{_ts(start)} --> {_ts(end)}\n{caption}\n\n")

    ass_path = Path(app.WORK) / "captions.ass"
    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Himel,DejaVu Sans,36,&H00FFFFFF,&H0000FFFF,&H00101722,&H800A0A18,-1,0,0,0,100,100,0,0,3,8,1,5,25,25,20,1
Style: Niha,DejaVu Sans,36,&H00FFFFFF,&H0000FFFF,&H00101722,&H800A0A18,-1,0,0,0,100,100,0,0,3,8,1,5,25,25,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass_lines = [ass_header]
    for start, end, caption, speaker in rows:
        x_position = 470 if speaker == "Himel" else 1450
        # Position the label and its subtitle under the matching person in the supplied still artwork.
        accent = "&H0000D9FF&" if speaker == "Himel" else "&H00FFD000&"
        escaped = (
            caption.replace("\\", "\\\\")
            .replace("{", "\\{")
            .replace("}", "\\}")
            .replace("\r", " ")
            .replace("\n", " ")
        )
        ass_lines.append(
            f"Dialogue: 0,{_ass_ts(start)},{_ass_ts(end)},{speaker},,0,0,0,,"
            f"{{\\an5\\pos({x_position},775)\\fs27\\b1\\c{accent}}}{speaker.upper()}"
            f"\\N{{\\fs36\\b1\\c&H00FFFFFF&}}{escaped}\n"
        )
    ass_path.write_text("".join(ass_lines), encoding="utf-8")
    print(
        f"Created {len(rows)} precisely timed captions; "
        "Himel captions are under the left host and Niha captions under the right host."
    )
    return srt_path



def pexels_videos(keywords):
    """Download a small pool of topic footage for alternating studio/real-world scenes."""
    api_key = app.PEXELS
    if not api_key:
        print("Pexels API key missing; using studio-only fallback.")
        return []

    queries = [x for x in keywords if x][:4]
    clips = []
    seen = set()

    for kw in queries:
        print(f"Searching topic footage: {kw}")
        try:
            r = requests.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": api_key},
                params={"query": kw, "per_page": 5, "orientation": "landscape", "size": "medium"},
                timeout=30,
            )
            r.raise_for_status()
            for v in r.json().get("videos", []):
                files = [f for f in v.get("video_files", [])
                         if f.get("width", 0) >= 1000 and f.get("height", 0) >= 500]
                if not files:
                    continue
                files.sort(key=lambda x: abs((x.get("width",1920)/max(x.get("height",1080),1))-16/9))
                link = files[0].get("link")
                if not link or link in seen:
                    continue
                seen.add(link)
                clips.append((link, float(v.get("duration", 8)), v.get("url",""), v.get("user",{}).get("name","Pexels creator")))
                if len(clips) >= 6:
                    break
        except Exception as exc:
            print(f"Footage search failed for '{kw}': {exc}")
        if len(clips) >= 6:
            break

    out = []
    for i, (url, dur, page, creator) in enumerate(clips):
        path = Path(app.WORK) / f"topic_clip_{i}.mp4"
        print(f"Downloading topic footage {i+1}/{len(clips)}...")
        try:
            with requests.get(url, stream=True, timeout=60, headers={"User-Agent":"Mozilla/5.0"}) as rr:
                rr.raise_for_status()
                with path.open("wb") as f:
                    for chunk in rr.iter_content(1024*1024):
                        if chunk:
                            f.write(chunk)
            out.append((str(path), min(max(dur, 5), 12), page, creator))
        except Exception as exc:
            print(f"Download failed: {exc}")
    print(f"Downloaded {len(out)} topic clips.")
    return out



def _studio_svg():
    """Warm, illustrated English-learning studio artwork with original Two Takes branding."""
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080">
      <defs>
        <linearGradient id="paper" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#fff7e8"/>
          <stop offset="1" stop-color="#f4dfc2"/>
        </linearGradient>
        <linearGradient id="desk" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#3a2b24"/>
          <stop offset="1" stop-color="#1f1815"/>
        </linearGradient>
      </defs>

      <rect width="1920" height="1080" fill="url(#paper)"/>
      <rect width="1920" height="16" fill="#c94d1a"/>
      <circle cx="1640" cy="170" r="300" fill="#d96a2a" opacity=".08"/>
      <circle cx="250" cy="930" r="260" fill="#d96a2a" opacity=".06"/>

      <rect x="80" y="60" width="1760" height="920" rx="36"
            fill="#fffaf1" stroke="#d9b98e" stroke-width="3"/>
      <text x="130" y="125" font-family="DejaVu Sans" font-size="34"
            font-weight="800" fill="#1f1b18">TWO TAKES PODCAST</text>
      <rect x="130" y="150" width="270" height="42" rx="21" fill="#c94d1a"/>
      <text x="265" y="179" text-anchor="middle" font-family="DejaVu Sans"
            font-size="20" font-weight="800" fill="#ffffff">ENGLISH PODCAST</text>

      <text x="960" y="232" text-anchor="middle" font-family="DejaVu Sans"
            font-size="25" fill="#6b5444">Real conversations • useful phrases • speaking practice</text>

      <!-- Himel -->
      <g transform="translate(330,285)">
        <ellipse cx="285" cy="610" rx="270" ry="40" fill="#1d1613" opacity=".14"/>
        <circle cx="250" cy="170" r="128" fill="#c99170"/>
        <path d="M126 168 Q134 36 250 36 Q366 36 374 168 Q330 98 250 102 Q170 98 126 168Z" fill="#22252b"/>
        <circle cx="210" cy="182" r="10" fill="#1e252a"/>
        <circle cx="290" cy="182" r="10" fill="#1e252a"/>
        <path d="M213 233 Q250 255 287 233" fill="none" stroke="#6c3830" stroke-width="8" stroke-linecap="round"/>
        <path d="M145 342 Q250 300 355 342 L392 575 L108 575Z" fill="#385a7f"/>
        <rect x="355" y="238" width="26" height="148" rx="13" fill="#242322"/>
        <ellipse cx="368" cy="223" rx="48" ry="25" fill="#11100f"/>
        <rect x="80" y="540" width="340" height="18" rx="9" fill="#c94d1a"/>
        <text x="250" y="635" text-anchor="middle" font-family="DejaVu Sans"
              font-size="30" font-weight="800" fill="#2b211c">HIMEL</text>
      </g>

      <!-- Niha -->
      <g transform="translate(1050,300)">
        <ellipse cx="285" cy="595" rx="270" ry="40" fill="#1d1613" opacity=".14"/>
        <circle cx="250" cy="160" r="122" fill="#cc9574"/>
        <path d="M120 164 Q113 34 250 34 Q387 34 380 165 Q334 86 250 91 Q166 86 120 164Z" fill="#3c2a31"/>
        <path d="M114 160 Q98 355 125 400 L158 374 L144 205Z" fill="#3c2a31" opacity=".95"/>
        <path d="M386 160 Q402 355 375 400 L342 374 L356 205Z" fill="#3c2a31" opacity=".95"/>
        <circle cx="212" cy="172" r="9" fill="#1e252a"/>
        <circle cx="288" cy="172" r="9" fill="#1e252a"/>
        <path d="M218 220 Q250 240 282 220" fill="none" stroke="#6c3830" stroke-width="7" stroke-linecap="round"/>
        <path d="M150 330 Q250 288 350 330 L385 565 L115 565Z" fill="#a86779"/>
        <rect x="126" y="238" width="26" height="142" rx="13" fill="#242322"/>
        <ellipse cx="139" cy="223" rx="47" ry="24" fill="#11100f"/>
        <rect x="80" y="530" width="340" height="18" rx="9" fill="#c94d1a"/>
        <text x="250" y="620" text-anchor="middle" font-family="DejaVu Sans"
              font-size="30" font-weight="800" fill="#2b211c">NIHA</text>
      </g>

      <!-- Shared desk and small original icon -->
      <rect x="330" y="860" width="1260" height="82" rx="30" fill="url(#desk)"/>
      <rect x="430" y="895" width="1060" height="7" rx="3.5" fill="#c94d1a"/>
      <g transform="translate(890,365)">
        <circle cx="70" cy="70" r="54" fill="#c94d1a"/>
        <path d="M48 58 Q70 34 92 58 L92 79 Q70 101 48 79Z" fill="#fff7e8"/>
        <path d="M31 75 Q42 103 70 107 Q98 103 109 75" fill="none"
              stroke="#fff7e8" stroke-width="7" stroke-linecap="round"/>
      </g>

      <rect x="505" y="980" width="910" height="50" rx="25" fill="#f0d2af"/>
      <text x="960" y="1012" text-anchor="middle" font-family="DejaVu Sans"
            font-size="22" font-weight="800" fill="#7b3b1d">
        LISTEN • REPEAT • USE IT
      </text>
    </svg>'''

def _make_studio_png():
    svgfile = Path(app.WORK) / "studio.svg"
    pngfile = Path(app.WORK) / "studio.png"
    svgfile.write_text(_studio_svg(), encoding="utf-8")
    _run(["convert", "-background", "none", str(svgfile), "-quality", "96", str(pngfile)], label="Studio artwork")
    return pngfile


def _make_clip_segment(input_path, output_path, seconds, start=0):
    _run([
        "ffmpeg","-y","-ss",str(start),"-i",str(input_path),"-t",str(seconds),
        "-vf",f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=increase,crop={VIDEO_W}:{VIDEO_H},fps={FPS},setsar=1",
        "-an","-c:v","libx264","-preset",ENCODE_PRESET,"-crf",ENCODE_CRF,
        "-pix_fmt","yuv420p",str(output_path)
    ], label=f"Footage segment {output_path.name}")


def _drawtext_escape(value):
    value = str(value or "")
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")


def _make_studio_segment(studio, output_path, seconds, camera="wide", section="", speaker=""):
    """Create an illustrated studio shot with simple section and speaker labels."""
    if camera == "himel":
        vf = f"crop=1100:1080:80:0,scale={VIDEO_W}:{VIDEO_H}:flags=lanczos"
    elif camera == "niha":
        vf = f"crop=1100:1080:740:0,scale={VIDEO_W}:{VIDEO_H}:flags=lanczos"
    else:
        vf = f"scale={VIDEO_W}:{VIDEO_H}:flags=lanczos"

    # Keep labels short and consistent so every scene feels like one learning show.
    section = str(section or "").strip().upper()[:26]
    speaker = str(speaker or "").strip().upper()[:12]
    overlays = [
        "drawbox=x=0:y=0:w=iw:h=8:color=0xc94d1a@1:t=fill"
    ]

    if section:
        section_safe = _drawtext_escape(section)
        overlays += [
            "drawbox=x=70:y=54:w=330:h=52:color=0x2b211c@0.90:t=fill",
            "drawtext="
            "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"text='{section_safe}':"
            "x=92:y=69:fontsize=22:fontcolor=0xfffff7:"
            "borderw=0"
        ]

    if speaker in {"HIMEL", "NIHA"}:
        speaker_safe = _drawtext_escape(speaker)
        overlays += [
            "drawbox=x=70:y=h-128:w=190:h=54:color=0xc94d1a@0.95:t=fill",
            "drawtext="
            "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"text='{speaker_safe}':"
            "x=92:y=h-111:fontsize=24:fontcolor=0xfffff7:"
            "borderw=0"
        ]

    vf = ",".join([vf] + overlays)

    _run([
        "ffmpeg","-y","-loop","1","-i",str(studio),"-t",str(seconds),
        "-vf",vf,"-r",str(FPS),"-c:v","libx264","-preset",ENCODE_PRESET,"-crf",ENCODE_CRF,
        "-pix_fmt","yuv420p",str(output_path)
    ], label=f"Studio {camera} shot {output_path.name}")

def render_video(wav, clips, srt, title):
    """Render the supplied channel-opener image for the entire episode with host-aligned captions."""
    print("=== FULL-EPISODE OPENER + SPEAKER-POSITIONED CAPTIONS RENDER START ===")
    started = time.time()
    audio_duration = app.duration(wav)
    timing_path = Path(app.WORK) / "tts_segments.json"
    try:
        timing = json.loads(timing_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Missing or invalid TTS timing metadata: {exc}") from exc

    groups = []
    for item in timing:
        key = (item.get("turn_index"), item.get("speaker"), item.get("turn_type", "reaction"))
        if groups and groups[-1]["key"] == key:
            groups[-1]["end"] = float(item["end"])
            groups[-1]["text"] += " " + str(item.get("text", "")).strip()
        else:
            groups.append({
                "key": key,
                "start": float(item["start"]),
                "end": float(item["end"]),
                "speaker": item.get("speaker", "Himel"),
                "turn_type": item.get("turn_type", "reaction"),
                "text": str(item.get("text", "")).strip(),
            })
    if not groups:
        raise RuntimeError("No timed conversation turns were available for rendering.")

    chapter_lines = build_chapters(groups, audio_duration)
    chapter_path = Path(app.WORK) / "chapters.txt"
    chapter_path.write_text(
        "\n".join(chapter_lines) + ("\n" if chapter_lines else ""),
        encoding="utf-8",
    )
    print(f"Prepared {len(chapter_lines)} YouTube chapter markers.")

    # The user-supplied Two Takes opener is the only visual scene from 0:00 to the end.
    branded_asset = Path(app.ROOT) / "assets" / "two_takes_podcast_studio.avif"
    poster_png = Path(app.WORK) / "two_takes_podcast_studio_full_video.png"
    if branded_asset.is_file():
        _run(
            [
                "ffmpeg", "-v", "error", "-y", "-i", str(branded_asset),
                "-vf", "scale=1920:1080:flags=lanczos",
                "-frames:v", "1", "-update", "1", str(poster_png),
            ],
            label="Prepare full-video Two Takes opener",
        )
    else:
        print("WARNING: supplied opener asset is missing; using original studio fallback artwork.")
        poster_png = _make_studio_png()

    ass_path = Path(app.WORK) / "captions.ass"
    if not ass_path.is_file() or ass_path.stat().st_size == 0:
        make_srt("", audio_duration)
    if not ass_path.is_file() or ass_path.stat().st_size == 0:
        raise RuntimeError("Speaker-positioned ASS captions were not generated.")

    # No intro card, opening sting, B-roll, or scene cuts. Only subtitles change over the looped still.
    music_bed = Path(app.WORK) / "original_music_bed.wav"
    generate_music_bed(audio_duration, music_bed, sample_rate=24000)
    subtitle_path = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    input_args = [
        "-loop", "1", "-framerate", str(FPS), "-i", str(poster_png),
        "-i", str(wav),
        "-i", str(music_bed),
    ]
    video_filter = f"[0:v:0]format=yuv420p,subtitles='{subtitle_path}'[vout]"
    audio_filter = (
        "[1:a]asplit=2[voice_sc][voice_raw];"
        "[2:a]volume=1.1[music];"
        "[music][voice_sc]sidechaincompress="
        "threshold=0.08:ratio=2.5:attack=20:release=450[ducked_music];"
        "[voice_raw]pan=stereo|c0=c0|c1=c0,highpass=f=70,lowpass=f=12000,"
        "acompressor=threshold=-18dB:ratio=3:attack=5:release=80:makeup=2,"
        "volume=1.12[voice];"
        "[voice][ducked_music]amix=inputs=2:duration=first:dropout_transition=2,"
        "alimiter=limit=0.95,loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
    )
    final = Path(app.WORK) / "the_two_takes.mp4"
    _run(
        [
            "ffmpeg", "-hide_banner", "-y", *input_args,
            "-t", str(audio_duration),
            "-filter_complex", video_filter + ";" + audio_filter,
            "-map", "[vout]", "-map", "[aout]",
            "-r", str(FPS),
            "-c:v", "libx264", "-preset", ENCODE_PRESET, "-crf", ENCODE_CRF,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", str(final),
        ],
        label="Full episode with fixed opener and speaker-positioned captions",
    )
    quality_check(final)
    print(f"=== FULL-EPISODE STILL-IMAGE RENDER COMPLETE in {(time.time()-started)/60:.1f} min ===")
    return final



def _write_short_captions(timing, start_seconds, end_seconds, output_path):
    """Write subtitles relative to a selected excerpt, keeping captions on speech boundaries."""
    rows = []
    for segment in timing:
        try:
            segment_start = float(segment["start"])
            segment_end = float(segment["end"])
        except (KeyError, TypeError, ValueError):
            continue
        text = str(segment.get("text", "")).strip()
        if not text or segment_end <= start_seconds or segment_start >= end_seconds:
            continue

        clipped_start = max(start_seconds, segment_start) - start_seconds
        clipped_end = min(end_seconds, segment_end) - start_seconds
        if clipped_end <= clipped_start:
            continue

        chunks = _caption_chunks(text, max_words=5)
        total_words = sum(len(chunk.split()) for chunk in chunks) or 1
        cursor = clipped_start
        for index, chunk in enumerate(chunks):
            duration = (clipped_end - clipped_start) * len(chunk.split()) / total_words
            row_start = cursor
            row_end = clipped_end if index == len(chunks) - 1 else cursor + duration
            rows.append((row_start, row_end, chunk))
            cursor = row_end

    with Path(output_path).open("w", encoding="utf-8") as file:
        for index, (start, end, text) in enumerate(rows, 1):
            start = max(0.0, start - 0.02)
            end = max(start + 0.05, end + 0.03)
            file.write(f"{index}\n{_ts(start)} --> {_ts(end)}\n{text}\n\n")
    return len(rows)


def render_shorts(wav, title, topic):
    """Render up to three original, vertical Shorts excerpts from the finished episode."""
    print("=== CREATING VERTICAL SHORTS ASSETS ===")
    started = time.time()
    work = Path(app.WORK)
    base = work / "base_video.mp4"
    music = work / "original_music_bed.wav"
    timing_path = work / "tts_segments.json"

    if not base.exists() or not Path(wav).exists() or not timing_path.exists():
        raise RuntimeError("Cannot render Shorts: base video, voice WAV, or TTS timings are missing.")

    try:
        timing = json.loads(timing_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read TTS timings for Shorts: {exc}") from exc
    if not isinstance(timing, list) or not timing:
        raise RuntimeError("Cannot render Shorts: the TTS timing file contains no segments.")

    audio_duration = app.duration(wav)
    windows = select_short_windows(timing, audio_duration, max_clips=3)
    if not windows:
        print("No clean 18–35 second Shorts excerpts met the timing rules.")
        return []

    if not music.exists():
        generate_music_bed(audio_duration, music, sample_rate=24000)

    output_dir = work / "shorts"
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_file in output_dir.glob("short_*.mp4"):
        old_file.unlink()
    manifest = []

    label_map = {
        "hook": "Stop Making This English Mistake",
        "language_tip": "One Useful English Phrase",
        "practice": "Practice This English Pattern",
        "story": "Real-Life English Conversation",
        "question": "Ask Better Questions in English",
        "follow_up": "Keep the English Conversation Going",
    }

    for number, window in enumerate(windows, 1):
        clip_start = float(window["start"])
        clip_end = float(window["end"])
        clip_duration = clip_end - clip_start
        if clip_duration < 18 or clip_duration > 35:
            print(f"Skipping Shorts candidate {number}: invalid duration {clip_duration:.1f}s.")
            continue

        anchor_type = str(window.get("turn_type", "conversation")).lower()
        label = label_map.get(anchor_type, "Everyday English Tip")
        short_title = f"{label} | {topic}".strip(" |")[:95]
        slug = re.sub(r"[^a-z0-9]+", "_", anchor_type.lower()).strip("_") or "clip"
        stem = f"short_{number:02d}_{slug}"
        output_video = output_dir / f"{stem}.mp4"
        subtitle_file = output_dir / f"{stem}.srt"
        caption_count = _write_short_captions(
            timing, clip_start, clip_end, subtitle_file
        )
        if caption_count < 3:
            print(f"Skipping Shorts candidate {number}: too few timed captions.")
            continue

        subtitle_path = (
            str(subtitle_file.resolve())
            .replace("\\", "/")
            .replace(":", "\\:")
            .replace("'", "\\'")
        )
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        video_and_caption_filter = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=24:10,eq=brightness=-0.18[bg];"
            "[0:v]scale=1080:-2[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2-140,"
            "drawbox=x=48:y=50:w=984:h=124:color=0x211914@0.90:t=fill,"
            f"drawtext=fontfile={font}:text='TWO TAKES PODCAST':"
            "x=(w-text_w)/2:y=88:fontsize=42:fontcolor=white,"
            "drawbox=x=48:y=1710:w=984:h=132:color=0x211914@0.90:t=fill,"
            f"drawtext=fontfile={font}:text='FULL EPISODE ON CHANNEL':"
            "x=(w-text_w)/2:y=1750:fontsize=34:fontcolor=white,"
            f"subtitles='{subtitle_path}':force_style="
            "'FontName=DejaVu Sans,FontSize=46,Bold=1,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00101722,"
            "BorderStyle=1,Outline=4,Shadow=1,"
            "Alignment=2,MarginL=70,MarginR=70,MarginV=335,WrapStyle=2'"
            "[v]"
        )
        audio_filter = (
            "[1:a]asplit=2[voice_sc][voice_raw];"
            "[2:a]volume=1.1[music];"
            "[music][voice_sc]sidechaincompress="
            "threshold=0.08:ratio=2.5:attack=20:release=450[ducked_music];"
            "[voice_raw]pan=stereo|c0=c0|c1=c0,highpass=f=70,lowpass=f=12000,"
            "acompressor=threshold=-18dB:ratio=3:attack=5:release=80:makeup=2,"
            "volume=1.12[voice];"
            "[voice][ducked_music]amix=inputs=2:duration=first:dropout_transition=2,"
            "alimiter=limit=0.95,loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
        )
        command = [
            "ffmpeg", "-y",
            "-ss", f"{clip_start:.3f}", "-i", str(base),
            "-ss", f"{clip_start:.3f}", "-i", str(wav),
            "-ss", f"{clip_start:.3f}", "-i", str(music),
            "-t", f"{clip_duration:.3f}",
            "-filter_complex", video_and_caption_filter + ";" + audio_filter,
            "-map", "[v]", "-map", "[aout]",
            "-r", str(FPS),
            "-c:v", "libx264", "-preset", ENCODE_PRESET, "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k",
            "-shortest", "-movflags", "+faststart",
            str(output_video),
        ]
        _run(command, label=f"Vertical Short {number}")
        manifest.append({
            "file": output_video.name,
            "title": short_title,
            "description": (
                "Practice everyday English with Two Takes Podcast. "
                "Watch the full conversation on the channel and try the phrase yourself."
            ),
            "hashtag_suggestions": ["#Shorts", "#EnglishLearning", "#SpeakEnglish"],
            "source_episode_title": title,
            "topic": topic,
            "excerpt_type": anchor_type,
            "start_seconds": clip_start,
            "end_seconds": clip_end,
            "duration_seconds": round(clip_duration, 2),
            "captions_file": subtitle_file.name,
            "note": "Review the excerpt and title before publishing; no views are guaranteed.",
        })
        print(f"Created vertical Short: {output_video}")

    manifest_path = output_dir / "shorts_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"=== SHORTS COMPLETE: {len(manifest)} ready-to-review files "
        f"in {(time.time() - started) / 60:.1f} min ==="
    )
    return manifest



# VISUAL REFERENCE STYLE
# Warm English-learning podcast presentation with original Two Takes Podcast branding.
VISUAL_STYLE = {
    "thumbnail": "16:9 vibrant 2D cartoon podcast studio; bold white and yellow ENGLISH PODCAST / with TWO HOSTS! headline; bright blue LEARN DAILY DIALOGUES banner; Two Takes Podcast channel name; high contrast and clean outlines",
    "video": "Use the supplied Two Takes Podcast opener as the only background for the entire video; no intro card, no B-roll, no scene cuts; Himel dialogue captions under the left/male host and Niha dialogue captions under the right/female host.",
    "branding": "TWO TAKES PODCAST original branding; no copied logos, characters, artwork, or distinctive visual assets",
}

def _short_thumbnail_title(title, topic):
    concept_path = Path(app.WORK) / "thumbnail_text.txt"
    concept = ""
    if concept_path.exists():
        try:
            concept = concept_path.read_text(encoding="utf-8").strip()
        except Exception:
            concept = ""

    source = concept or title.strip() or topic.strip() or "SPEAK ENGLISH NATURALLY"
    source = re.sub(r"[^A-Za-z0-9'?! ]+", " ", source)
    words = source.split()
    return " ".join(words[:4]).upper()


def make_thumbnail(title, topic):
    """Warm educational thumbnail: large lesson phrase + original illustrated hosts."""
    # Prefer the channel's permanent studio artwork so every episode has consistent branding.
    branded_asset = Path(app.ROOT) / "assets" / "two_takes_podcast_studio.avif"
    if branded_asset.is_file():
        # Decode AVIF with FFmpeg first: ImageMagick builds on some runners do not
        # include an AVIF delegate. The final YouTube thumbnail remains JPEG.
        poster = Path(app.WORK) / "two_takes_podcast_studio_poster.png"
        _run(
            [
                "ffmpeg", "-y", "-i", str(branded_asset),
                "-vf", "scale=1280:720:flags=lanczos",
                "-frames:v", "1", "-update", "1", str(poster),
            ],
            label="Decode permanent Two Takes AVIF artwork",
        )
        jpg = Path(app.WORK) / "thumbnail.jpg"
        _run(
            ["convert", str(poster), "-resize", "1280x720!", "-strip", "-quality", "92", str(jpg)],
            label="Permanent Two Takes channel thumbnail",
        )
        print("Using the permanent Two Takes studio artwork for the YouTube thumbnail.")
        return jpg

    headline = _short_thumbnail_title(title, topic)
    lines = textwrap.wrap(headline, width=15)[:2]

    headline_svg = "".join(
        f'<text x="78" y="{300+i*94}" font-family="DejaVu Sans" '
        f'font-size="78" font-weight="900" fill="#c94d1a">{html.escape(line)}</text>'
        for i, line in enumerate(lines)
    )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">
      <defs>
        <linearGradient id="paper" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#fff7e8"/>
          <stop offset="1" stop-color="#f1dfc8"/>
        </linearGradient>
      </defs>

      <rect width="1280" height="720" fill="url(#paper)"/>
      <rect width="1280" height="12" fill="#c94d1a"/>
      <circle cx="1080" cy="120" r="220" fill="#c94d1a" opacity=".07"/>

      <rect x="52" y="45" width="1176" height="630" rx="30"
            fill="#fffaf1" stroke="#d9b98e" stroke-width="3"/>

      <text x="78" y="100" font-family="DejaVu Sans" font-size="25"
            font-weight="800" fill="#2b211c">TWO TAKES PODCAST</text>
      <text x="78" y="132" font-family="DejaVu Sans" font-size="18"
            font-weight="700" fill="#8d4b2a">ENGLISH PODCAST</text>
      <rect x="78" y="158" width="430" height="5" rx="2.5" fill="#c94d1a"/>

      <text x="78" y="222" font-family="DejaVu Sans" font-size="24"
            font-weight="700" fill="#6a584c">Learn English through real conversation</text>

      {headline_svg}

      <text x="78" y="565" font-family="DejaVu Sans" font-size="21"
            font-weight="700" fill="#4d4139">LISTEN • REPEAT • SPEAK</text>

      <g transform="translate(748,118)">
        <ellipse cx="250" cy="505" rx="280" ry="34" fill="#1d1613" opacity=".14"/>

        <!-- Himel -->
        <circle cx="145" cy="170" r="100" fill="#c99170"/>
        <path d="M50 165 Q55 65 145 65 Q235 65 240 165 Q203 112 145 116 Q87 112 50 165Z" fill="#22252b"/>
        <circle cx="118" cy="177" r="8" fill="#1e252a"/>
        <circle cx="172" cy="177" r="8" fill="#1e252a"/>
        <path d="M120 217 Q145 232 170 217" fill="none" stroke="#6c3830" stroke-width="6" stroke-linecap="round"/>
        <path d="M80 300 Q145 266 210 300 L233 448 L57 448Z" fill="#385a7f"/>
        <rect x="214" y="203" width="20" height="115" rx="10" fill="#242322"/>
        <ellipse cx="224" cy="190" rx="38" ry="19" fill="#11100f"/>

        <!-- Niha -->
        <circle cx="352" cy="173" r="96" fill="#cc9574"/>
        <path d="M260 170 Q257 75 352 75 Q447 75 444 171 Q407 116 352 119 Q297 116 260 170Z" fill="#3c2a31"/>
        <path d="M255 165 Q240 315 270 345 L294 323 L281 193Z" fill="#3c2a31"/>
        <path d="M449 165 Q464 315 434 345 L410 323 L423 193Z" fill="#3c2a31"/>
        <circle cx="327" cy="180" r="7" fill="#1e252a"/>
        <circle cx="377" cy="180" r="7" fill="#1e252a"/>
        <path d="M330 216 Q352 229 374 216" fill="none" stroke="#6c3830" stroke-width="5" stroke-linecap="round"/>
        <path d="M292 296 Q352 265 412 296 L436 448 L268 448Z" fill="#a86779"/>
        <rect x="262" y="210" width="20" height="110" rx="10" fill="#242322"/>
        <ellipse cx="272" cy="195" rx="37" ry="19" fill="#11100f"/>

        <rect x="95" y="470" width="390" height="46" rx="20" fill="#2b211c"/>
        <text x="290" y="500" text-anchor="middle" font-family="DejaVu Sans"
              font-size="21" font-weight="800" fill="#fff7e8">HIMEL × NIHA</text>

        <circle cx="290" cy="55" r="27" fill="#c94d1a"/>
        <path d="M276 48 Q290 34 304 48 L304 59 Q290 73 276 59Z" fill="#fff7e8"/>
      </g>
    </svg>'''

    svgfile = Path(app.WORK) / "thumbnail.svg"
    svgfile.write_text(svg, encoding="utf-8")
    jpg = Path(app.WORK) / "thumbnail.jpg"
    _run(["convert", "-background", "none", str(svgfile), "-quality", "96", str(jpg)], label="Warm educational thumbnail")
    return jpg

def quality_check(video):
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name,pix_fmt",
        "-of", "json", str(video)
    ], capture_output=True, text=True, check=True)
    data = json.loads(probe.stdout)
    stream = data.get("streams", [{}])[0]
    width = int(stream.get("width", 0))
    height = int(stream.get("height", 0))
    codec = stream.get("codec_name")
    if width < 1920 or height < 1080 or codec != "h264":
        raise RuntimeError(f"Video quality check failed: {width}x{height}, codec={codec}")

    audio_probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,channels,sample_rate",
        "-of", "json", str(video)
    ], capture_output=True, text=True, check=True)
    audio_streams = json.loads(audio_probe.stdout).get("streams", [])
    if not audio_streams:
        raise RuntimeError("Audio quality check failed: no final audio stream found.")
    audio = audio_streams[0]
    if audio.get("codec_name") != "aac":
        raise RuntimeError(f"Audio quality check failed: expected AAC, got {audio.get('codec_name')}")
    if int(audio.get("channels", 0)) < 2:
        raise RuntimeError("Audio quality check failed: expected stereo audio.")
    print(
        f"Quality check passed: {width}x{height} H.264 + "
        f"{audio.get('codec_name')} stereo audio at {audio.get('sample_rate')} Hz."
    )


import build_podcast as app
