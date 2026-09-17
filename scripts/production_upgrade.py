"""Production-quality rendering upgrades for The Two Takes."""

import html
import json
import re
import subprocess
import textwrap
from pathlib import Path

import requests

VIDEO_W = 1920
VIDEO_H = 1080
FPS = 30


def _run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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


def make_srt(script, audio_seconds):
    """Short 2-5 word captions paced across the real audio duration."""
    chunks = _caption_chunks(script, max_words=5)
    if not chunks:
        raise RuntimeError("Could not create subtitle chunks from the dialogue")

    total_words = sum(len(text.split()) for _, text in chunks)
    available = max(0.5, audio_seconds - 0.25)
    cursor = 0.15
    rows = []

    for _, text in chunks:
        weight = len(text.split()) / max(total_words, 1)
        span = max(0.55, available * weight)
        start = cursor
        end = min(audio_seconds, start + span)
        rows.append((start, end, text))
        cursor = end
        if cursor >= audio_seconds:
            break

    if rows:
        a, _, text = rows[-1]
        rows[-1] = (a, audio_seconds, text)

    path = Path(app.WORK) / "captions.srt"
    with path.open("w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(rows, 1):
            f.write(f"{i}\n{_ts(start)} --> {_ts(end)}\n{text}\n\n")
    return path


def pexels_videos(keywords):
    """Prefer large landscape footage for a true 1080p render."""
    clips = []
    for kw in keywords[:5]:
        print(f"Searching high-quality Pexels footage: {kw}")
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": app.PEXELS},
            params={
                "query": kw,
                "per_page": 12,
                "orientation": "landscape",
                "size": "large",
            },
            timeout=30,
        )
        if r.status_code >= 400:
            print(f"Pexels search failed for '{kw}': {r.status_code}")
            continue

        for v in r.json().get("videos", []):
            files = [
                f for f in v.get("video_files", [])
                if f.get("width", 0) >= 1280 and f.get("height", 0) >= 720
            ]
            if not files:
                continue
            files.sort(key=lambda f: abs((f.get("width", 1920) / max(f.get("height", 1080), 1)) - 16 / 9))
            f = files[0]
            clips.append((
                f["link"],
                v.get("duration", 8),
                v.get("url", ""),
                v.get("user", {}).get("name", "Pexels creator"),
            ))
        if len(clips) >= 10:
            break

    seen = set()
    unique = []
    for item in clips:
        if item[0] not in seen:
            seen.add(item[0])
            unique.append(item)
    unique = unique[:10]

    downloaded = []
    for i, (url, dur, page, creator) in enumerate(unique):
        path = Path(app.WORK) / f"clip_{i}_hq.mp4"
        print(f"Downloading HD Pexels clip {i + 1}/{len(unique)}...")
        with requests.get(url, stream=True, timeout=90, headers={"User-Agent": "Mozilla/5.0"}) as rr:
            rr.raise_for_status()
            with path.open("wb") as f:
                for block in rr.iter_content(1024 * 1024):
                    if block:
                        f.write(block)
        downloaded.append((str(path), dur, page, creator))

    if not downloaded:
        raise RuntimeError("No high-quality Pexels clips were returned.")
    return downloaded


def render_video(wav, clips, srt, title):
    """Render a clean 1080p master with higher-quality encoding and captions."""
    processed = []
    for i, (src, dur, _, _) in enumerate(clips):
        out = Path(app.WORK) / f"hq_{i}.mp4"
        clip_len = min(max(float(dur), 5.0), 12.0)
        _run([
            "ffmpeg", "-y", "-i", src, "-t", str(clip_len),
            "-vf", f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=increase,crop={VIDEO_W}:{VIDEO_H},setsar=1,fps={FPS}",
            "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
        ])
        processed.append(out)

    audio_duration = app.duration(wav)
    concat = Path(app.WORK) / "concat_hq.txt"
    with concat.open("w", encoding="utf-8") as f:
        for _ in range(30):
            for p in processed:
                f.write(f"file '{p.as_posix()}'\n")

    bg = Path(app.WORK) / "bg_hq.mp4"
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
        "-t", str(audio_duration + 0.5), "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(bg),
    ])

    final = Path(app.WORK) / "the_two_takes.mp4"
    subtitle_path = str(srt).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    vf = (
        "drawbox=x=0:y=0:w=iw:h=86:color=black@0.48:t=fill,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        "text='THE TWO TAKES':x=48:y=27:fontsize=34:fontcolor=white,"
        f"subtitles='{subtitle_path}':force_style="
        "'FontName=DejaVu Sans,FontSize=26,Bold=1,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,"
        "BorderStyle=3,BackColour=&H99000000,Outline=3,Shadow=0,"
        "Alignment=2,MarginL=90,MarginR=90,MarginV=58,WrapStyle=2'"
    )

    _run([
        "ffmpeg", "-y", "-i", str(bg), "-i", str(wav),
        "-t", str(audio_duration), "-vf", vf,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-shortest", "-movflags", "+faststart", str(final),
    ])
    return final


def _short_thumbnail_title(title, topic):
    source = title.strip() or topic.strip() or "TODAY'S BIG STORY"
    source = re.sub(r"[^A-Za-z0-9'?! ]+", " ", source)
    words = source.split()
    return " ".join(words[:5]).upper()


def make_thumbnail(title, topic):
    """Original 1280x720 thumbnail with a consistent two-host illustrated identity."""
    headline = _short_thumbnail_title(title, topic)
    lines = textwrap.wrap(headline, width=17)[:3]
    headline_svg = "".join(
        f'<text x="80" y="{250 + i * 78}" font-family="DejaVu Sans" font-size="66" font-weight="900" fill="#ffffff">{html.escape(line)}</text>'
        for i, line in enumerate(lines)
    )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">
      <defs>
        <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#101827"/><stop offset="1" stop-color="#26364f"/></linearGradient>
        <linearGradient id="card" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffffff" stop-opacity=".16"/><stop offset="1" stop-color="#ffffff" stop-opacity=".05"/></linearGradient>
      </defs>
      <rect width="1280" height="720" fill="url(#bg)"/>
      <circle cx="1120" cy="120" r="260" fill="#ffffff" opacity=".06"/>
      <circle cx="930" cy="700" r="330" fill="#ffffff" opacity=".04"/>
      <rect x="55" y="55" width="1170" height="610" rx="38" fill="url(#card)" stroke="#ffffff" stroke-opacity=".12"/>
      <text x="80" y="115" font-family="DejaVu Sans" font-size="30" font-weight="700" fill="#ffffff">THE TWO TAKES</text>
      <rect x="80" y="135" width="150" height="8" rx="4" fill="#ffffff" opacity=".8"/>
      {headline_svg}
      <text x="82" y="560" font-family="DejaVu Sans" font-size="25" font-weight="600" fill="#d9e2f0">HIMEL × NIHA  •  ENGLISH PODCAST</text>

      <g transform="translate(875,125)">
        <circle cx="145" cy="160" r="126" fill="#d9a77d"/>
        <path d="M35 145 Q48 28 145 28 Q242 28 255 145 Q225 92 145 95 Q65 92 35 145Z" fill="#20252d"/>
        <circle cx="105" cy="165" r="10" fill="#17202b"/><circle cx="185" cy="165" r="10" fill="#17202b"/>
        <path d="M112 215 Q145 235 178 215" fill="none" stroke="#572f2a" stroke-width="8" stroke-linecap="round"/>
        <path d="M70 295 Q145 245 220 295 L245 475 L45 475Z" fill="#26364f"/>
        <circle cx="145" cy="130" r="145" fill="none" stroke="#ffffff" stroke-opacity=".22" stroke-width="6"/>
      </g>

      <g transform="translate(1040,220)">
        <circle cx="115" cy="125" r="105" fill="#d39a73"/>
        <path d="M15 150 Q12 5 115 5 Q220 5 215 155 Q185 75 115 72 Q45 75 15 150Z" fill="#3b2630"/>
        <circle cx="82" cy="135" r="8" fill="#17202b"/><circle cx="148" cy="135" r="8" fill="#17202b"/>
        <path d="M86 178 Q115 194 144 178" fill="none" stroke="#572f2a" stroke-width="7" stroke-linecap="round"/>
        <path d="M55 240 Q115 205 175 240 L200 410 L30 410Z" fill="#8b5a68"/>
        <circle cx="115" cy="112" r="122" fill="none" stroke="#ffffff" stroke-opacity=".18" stroke-width="5"/>
      </g>

      <circle cx="1030" cy="535" r="54" fill="#ffffff" opacity=".12"/>
      <text x="998" y="547" font-family="DejaVu Sans" font-size="34" font-weight="900" fill="#ffffff">▶</text>
    </svg>'''

    svgfile = Path(app.WORK) / "thumbnail.svg"
    svgfile.write_text(svg, encoding="utf-8")
    jpg = Path(app.WORK) / "thumbnail.jpg"
    _run(["convert", "-background", "none", str(svgfile), "-quality", "96", str(jpg)])
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
