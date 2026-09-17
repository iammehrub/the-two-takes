"""Original studio-style production layer for The Two Takes.

Designed around the English-learning podcast genre without copying another
channel's protected branding, artwork, scripts, characters, or exact voice.
"""

import html
import json
import re
import subprocess
import textwrap
import time
from pathlib import Path

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


def _caption_chunks(script, max_words=5):
    chunks = []
    for raw in script.splitlines():
        m = re.match(r"^(Himel|Niha):\s*(.+)$", raw.strip(), re.I)
        if not m:
            continue
        speaker = "Himel" if m.group(1).lower() == "himel" else "Niha"
        words = re.findall(r"\S+", m.group(2).strip())
        for i in range(0, len(words), max_words):
            part = " ".join(words[i:i + max_words]).strip()
            if part:
                chunks.append((speaker, part))
    return chunks


def _speech_intervals(wav, total_duration):
    """Find major pauses so caption timing does not drift through silence."""
    cmd = [
        "ffmpeg", "-hide_banner", "-i", str(wav), "-af",
        "silencedetect=noise=-34dB:d=0.22", "-f", "null", "-"
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    silence_starts = []
    silence_ends = []
    for line in (p.stderr or "").splitlines():
        m = re.search(r"silence_start:\s*([0-9.]+)", line)
        if m:
            silence_starts.append(float(m.group(1)))
        m = re.search(r"silence_end:\s*([0-9.]+)", line)
        if m:
            silence_ends.append(float(m.group(1)))

    intervals = []
    cursor = 0.0
    for start, end in zip(silence_starts, silence_ends):
        if start - cursor >= 0.35:
            intervals.append((cursor, min(start, total_duration)))
        cursor = max(cursor, end)
    if total_duration - cursor >= 0.35:
        intervals.append((cursor, total_duration))
    return intervals or [(0.15, total_duration)]


def make_srt(script, audio_seconds):
    """Create short captions anchored to detected speech windows."""
    chunks = _caption_chunks(script, max_words=5)
    if not chunks:
        raise RuntimeError("Could not create subtitle chunks from dialogue")

    intervals = _speech_intervals(app.WORK / "voice.wav", audio_seconds)
    total_words = sum(len(text.split()) for _, text in chunks) or 1
    total_speech = sum(max(0.2, b - a) for a, b in intervals)
    rows = []
    interval_index = 0
    interval_pos = intervals[0][0]

    for speaker, text in chunks:
        need = max(0.55, total_speech * len(text.split()) / total_words)
        remaining = need
        while remaining > 0 and interval_index < len(intervals):
            a, b = intervals[interval_index]
            start = max(interval_pos, a)
            available = max(0.05, b - start)
            take = min(remaining, available)
            if take >= 0.35:
                rows.append((start, start + take, speaker, text if not rows or rows[-1][3] != text else text))
            remaining -= take
            interval_pos = start + take
            if interval_pos >= b - 0.03:
                interval_index += 1
                if interval_index < len(intervals):
                    interval_pos = intervals[interval_index][0]
        if interval_index >= len(intervals):
            break

    # If a chunk crossed a pause, merge its pieces into one readable caption.
    merged = []
    for a, b, speaker, text in rows:
        if merged and merged[-1][2] == speaker and merged[-1][3] == text and a - merged[-1][1] < 0.5:
            merged[-1] = (merged[-1][0], b, speaker, text)
        else:
            merged.append((a, b, speaker, text))

    path = Path(app.WORK) / "captions.srt"
    with path.open("w", encoding="utf-8") as f:
        for i, (start, end, speaker, text) in enumerate(merged, 1):
            f.write(f"{i}\n{_ts(start)} --> {_ts(end)}\n{speaker}\n{text}\n\n")
    return path


def pexels_videos(keywords):
    """Keep the existing pipeline contract but stop downloading stock footage."""
    print("Studio mode: skipping Pexels and all external background footage.")
    # render_video ignores the placeholder path. The tuple keeps the old main()
    # interface compatible and avoids changing the upload workflow.
    return [("__ORIGINAL_STUDIO__", 600, "", "")]


def _studio_svg():
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080">
      <defs>
        <linearGradient id="wall" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#111827"/><stop offset="1" stop-color="#26354a"/></linearGradient>
        <radialGradient id="light1"><stop offset="0" stop-color="#f3d6a0" stop-opacity=".42"/><stop offset="1" stop-color="#f3d6a0" stop-opacity="0"/></radialGradient>
        <radialGradient id="light2"><stop offset="0" stop-color="#9ec5ff" stop-opacity=".28"/><stop offset="1" stop-color="#9ec5ff" stop-opacity="0"/></radialGradient>
      </defs>
      <rect width="1920" height="1080" fill="url(#wall)"/>
      <rect y="0" width="1920" height="180" fill="#0b1220" opacity=".5"/>
      <circle cx="350" cy="250" r="390" fill="url(#light1)"/>
      <circle cx="1570" cy="240" r="430" fill="url(#light2)"/>
      <rect x="85" y="90" width="1750" height="760" rx="36" fill="#ffffff" opacity=".035" stroke="#ffffff" stroke-opacity=".11" stroke-width="3"/>
      <text x="960" y="150" text-anchor="middle" font-family="DejaVu Sans" font-size="42" font-weight="700" fill="#ffffff" opacity=".95">THE TWO TAKES</text>
      <text x="960" y="205" text-anchor="middle" font-family="DejaVu Sans" font-size="24" fill="#d9e2f0">English conversations • listening • speaking practice</text>

      <g transform="translate(410,300)">
        <circle cx="250" cy="170" r="132" fill="#c98f6b"/>
        <path d="M125 165 Q135 35 250 35 Q365 35 375 165 Q335 100 250 105 Q165 100 125 165Z" fill="#20242b"/>
        <circle cx="210" cy="180" r="11" fill="#18212c"/><circle cx="290" cy="180" r="11" fill="#18212c"/>
        <path d="M215 232 Q250 250 285 232" fill="none" stroke="#60332e" stroke-width="8" stroke-linecap="round"/>
        <path d="M145 330 Q250 285 355 330 L400 585 L100 585Z" fill="#314b70"/>
        <rect x="365" y="210" width="28" height="160" rx="14" fill="#222b38"/>
        <ellipse cx="379" cy="195" rx="54" ry="30" fill="#171d26"/>
        <circle cx="250" cy="145" r="150" fill="none" stroke="#ffffff" stroke-opacity=".13" stroke-width="6"/>
        <text x="250" y="635" text-anchor="middle" font-family="DejaVu Sans" font-size="30" font-weight="700" fill="#ffffff">HIMEL</text>
      </g>

      <g transform="translate(1100,315)">
        <circle cx="250" cy="155" r="125" fill="#c99070"/>
        <path d="M120 155 Q112 28 250 28 Q388 28 380 160 Q335 85 250 88 Q165 85 120 155Z" fill="#3a2830"/>
        <circle cx="212" cy="168" r="10" fill="#18212c"/><circle cx="288" cy="168" r="10" fill="#18212c"/>
        <path d="M218 220 Q250 238 282 220" fill="none" stroke="#60332e" stroke-width="8" stroke-linecap="round"/>
        <path d="M150 315 Q250 275 350 315 L390 580 L110 580Z" fill="#865f70"/>
        <rect x="100" y="210" width="28" height="150" rx="14" fill="#222b38"/>
        <ellipse cx="114" cy="195" rx="52" ry="29" fill="#171d26"/>
        <circle cx="250" cy="140" r="143" fill="none" stroke="#ffffff" stroke-opacity=".11" stroke-width="6"/>
        <text x="250" y="630" text-anchor="middle" font-family="DejaVu Sans" font-size="30" font-weight="700" fill="#ffffff">NIHA</text>
      </g>

      <rect x="245" y="840" width="1430" height="125" rx="35" fill="#101722" stroke="#ffffff" stroke-opacity=".12" stroke-width="3"/>
      <rect x="390" y="875" width="1140" height="8" rx="4" fill="#ffffff" opacity=".1"/>
      <circle cx="960" cy="920" r="25" fill="#ffffff" opacity=".12"/>
      <text x="960" y="925" text-anchor="middle" font-family="DejaVu Sans" font-size="22" fill="#cbd5e1">A calm place to practice real English.</text>
    </svg>'''


def _make_studio_png():
    svgfile = Path(app.WORK) / "studio.svg"
    pngfile = Path(app.WORK) / "studio.png"
    svgfile.write_text(_studio_svg(), encoding="utf-8")
    _run(["convert", "-background", "none", str(svgfile), "-quality", "96", str(pngfile)], label="Studio artwork")
    return pngfile


def render_video(wav, clips, srt, title):
    print("=== STUDIO 1080P RENDER START ===")
    started = time.time()
    audio_duration = app.duration(wav)
    studio = _make_studio_png()
    final = Path(app.WORK) / "the_two_takes.mp4"

    subtitle_path = str(srt).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    vf = (
        f"scale={VIDEO_W}:{VIDEO_H},"
        "drawbox=x=0:y=0:w=iw:h=1080:color=black@0.04:t=fill,"
        f"subtitles='{subtitle_path}':force_style="
        "'FontName=DejaVu Sans,FontSize=30,Bold=1,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00101722,"
        "BorderStyle=3,BackColour=&HC0101722,Outline=2,Shadow=0,"
        "Alignment=2,MarginL=170,MarginR=170,MarginV=120,WrapStyle=2'"
    )

    _run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(studio),
        "-i", str(wav),
        "-t", str(audio_duration),
        "-vf", vf,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-r", str(FPS),
        "-c:v", "libx264",
        "-preset", ENCODE_PRESET,
        "-crf", ENCODE_CRF,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "160k",
        "-af", "highpass=f=70,lowpass=f=12000,acompressor=threshold=-18dB:ratio=3:attack=5:release=80:makeup=2,volume=1.25",
        "-shortest",
        "-movflags", "+faststart",
        str(final),
    ], label="FINAL STUDIO VIDEO")

    print(f"=== STUDIO RENDER COMPLETE in {(time.time() - started) / 60:.1f} min ===")
    return final


def _short_thumbnail_title(title, topic):
    source = title.strip() or topic.strip() or "SPEAK ENGLISH NATURALLY"
    source = re.sub(r"[^A-Za-z0-9'?! ]+", " ", source)
    return " ".join(source.split()[:7]).upper()


def make_thumbnail(title, topic):
    headline = _short_thumbnail_title(title, topic)
    lines = textwrap.wrap(headline, width=20)[:3]
    headline_svg = "".join(
        f'<text x="70" y="{265 + i * 82}" font-family="DejaVu Sans" font-size="70" font-weight="900" fill="#ffffff">{html.escape(line)}</text>'
        for i, line in enumerate(lines)
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">
      <rect width="1280" height="720" fill="#182234"/>
      <circle cx="1090" cy="130" r="250" fill="#ffffff" opacity=".08"/>
      <rect x="35" y="35" width="1210" height="650" rx="32" fill="#ffffff" opacity=".04" stroke="#ffffff" stroke-opacity=".14"/>
      <text x="70" y="100" font-family="DejaVu Sans" font-size="31" font-weight="800" fill="#ffffff">THE TWO TAKES</text>
      <text x="70" y="145" font-family="DejaVu Sans" font-size="22" fill="#cbd5e1">ENGLISH PODCAST • REAL CONVERSATIONS</text>
      {headline_svg}
      <text x="70" y="585" font-family="DejaVu Sans" font-size="25" font-weight="700" fill="#d9e2f0">LISTEN • SPEAK • PRACTICE</text>
      <g transform="translate(930,185)">
        <circle cx="105" cy="105" r="82" fill="#c98f6b"/><path d="M28 110 Q35 28 105 28 Q175 28 182 110 Q155 68 105 70 Q55 68 28 110Z" fill="#20242b"/>
        <circle cx="80" cy="112" r="7"/><circle cx="130" cy="112" r="7"/><path d="M82 145 Q105 158 128 145" fill="none" stroke="#60332e" stroke-width="6"/>
        <path d="M45 200 Q105 170 165 200 L190 340 L20 340Z" fill="#314b70"/>
        <ellipse cx="190" cy="140" rx="38" ry="20" fill="#171d26"/>
      </g>
      <g transform="translate(1080,285)">
        <circle cx="75" cy="75" r="65" fill="#c99070"/><path d="M10 80 Q5 18 75 18 Q145 18 140 82 Q118 50 75 50 Q32 50 10 80Z" fill="#3a2830"/>
        <circle cx="55" cy="82" r="6"/><circle cx="95" cy="82" r="6"/><path d="M57 108 Q75 120 93 108" fill="none" stroke="#60332e" stroke-width="5"/>
        <path d="M25 150 Q75 125 125 150 L145 270 L5 270Z" fill="#865f70"/>
        <ellipse cx="0" cy="112" rx="30" ry="16" fill="#171d26"/>
      </g>
    </svg>'''
    svgfile = Path(app.WORK) / "thumbnail.svg"
    svgfile.write_text(svg, encoding="utf-8")
    jpg = Path(app.WORK) / "thumbnail.jpg"
    _run(["convert", "-background", "none", str(svgfile), "-quality", "96", str(jpg)], label="Thumbnail")
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
        raise RuntimeError(f"Quality check failed: {width}x{height}, codec={codec}")
    print(f"Quality check passed: {width}x{height} H.264")


import build_podcast as app
