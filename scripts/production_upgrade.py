"""Original studio-style production layer for The Two Takes.

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


def make_srt(script, audio_seconds):
    """Use exact TTS segment durations, then split each segment into short captions."""
    timing_path = Path(app.WORK) / "tts_segments.json"
    segments = []
    if timing_path.exists():
        try:
            segments = json.loads(timing_path.read_text(encoding="utf-8"))
        except Exception:
            segments = []

    if not segments:
        raise RuntimeError("Missing exact TTS timing data; refusing to create drifting subtitles.")

    rows = []
    for seg in segments:
        start = float(seg["start"])
        end = float(seg["end"])
        text = str(seg["text"]).strip()
        if end <= start or not text:
            continue
        chunks = _caption_chunks(text, max_words=5)
        total_words = sum(len(x.split()) for x in chunks) or 1
        cursor = start
        for idx, chunk in enumerate(chunks):
            share = len(chunk.split()) / total_words
            dur = (end - start) * share
            a = cursor
            b = end if idx == len(chunks) - 1 else cursor + dur
            rows.append((a, b, chunk))
            cursor = b

    path = Path(app.WORK) / "captions.srt"
    with path.open("w", encoding="utf-8") as f:
        for i, (a, b, text) in enumerate(rows, 1):
            # Tiny padding prevents flicker while keeping speech alignment tight.
            a = max(0.0, a - 0.03)
            b = min(audio_seconds, b + 0.03)
            f.write(f"{i}\n{_ts(a)} --> {_ts(b)}\n{text}\n\n")
    print(f"Created {len(rows)} tightly timed subtitle cues.")
    return path


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
            font-weight="800" fill="#1f1b18">THE TWO TAKES</text>
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
    """Render with semantic conversation-aware cuts.

    The TTS timing file carries turn_type/speaker metadata, so visual changes
    happen on real dialogue beats instead of arbitrary 28/38 second timers.
    """
    print("=== SEMANTIC STUDIO + TOPIC FOOTAGE RENDER START ===")
    started = time.time()
    audio_duration = app.duration(wav)
    studio = _make_studio_png()
    segment_dir = Path(app.WORK) / "video_segments"
    segment_dir.mkdir(exist_ok=True)

    timing_path = Path(app.WORK) / "tts_segments.json"
    try:
        timing = json.loads(timing_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Missing or invalid TTS timing metadata: {exc}") from exc

    # Group sentence-level TTS chunks back into complete conversational turns.
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
                "text": str(item.get("text", "")).strip()
            })

    if not groups:
        raise RuntimeError("No timed conversation turns were available for rendering.")

    camera_by_type = {
        "hook": "wide",
        "question": "himel",
        "follow_up": "himel",
        "story": "wide",
        "reaction": "niha",
        "clarification": "wide",
        "language_tip": "wide",
        "practice": "wide",
        "recap": "wide",
    }

    # Prefer a close-up of whoever is speaking for questions/stories, while
    # language-learning sections get a clean two-person/wide composition.
    def camera_for(group):
        turn_type = group["turn_type"]
        speaker = str(group["speaker"]).lower()
        if turn_type in {"question", "follow_up", "story"}:
            return "himel" if speaker == "himel" else "niha"
        if turn_type == "reaction":
            return "himel" if speaker == "himel" else "niha"
        return camera_by_type.get(turn_type, "wide")

    scenes = []
    footage_index = 0

    for index, group in enumerate(groups):
        seconds = max(0.25, min(audio_duration - group["start"], group["end"] - group["start"]))
        if seconds <= 0.25:
            continue

        turn_type = group["turn_type"]
        # Keep teaching sections in the illustrated studio; use B-roll only for
        # personal stories/examples so the show retains a calm learning-podcast identity.
        use_broll = bool(clips) and turn_type == "story" and seconds >= 4.0

        if use_broll:
            clip_path, clip_dur, _, _ = clips[footage_index % len(clips)]
            footage_index += 1
            out = segment_dir / f"scene_{index:03d}.mp4"
            footage_seconds = min(seconds, float(clip_dur), 10.0)
            _make_clip_segment(clip_path, out, footage_seconds, start=0)
            # If the clip is shorter than the spoken turn, cover the remainder
            # with a studio shot so scene timing stays exactly aligned.
            scenes.append(out)
            if footage_seconds < seconds - 0.05:
                studio_out = segment_dir / f"scene_{index:03d}_studio.mp4"
                _make_studio_segment(
                studio,
                studio_out,
                seconds - footage_seconds,
                camera="wide",
                section="STORY",
                speaker=group["speaker"],
            )
                scenes.append(studio_out)
        else:
            out = segment_dir / f"scene_{index:03d}.mp4"
            section_label = {
                "hook": "ENGLISH PODCAST",
                "question": "CONVERSATION",
                "follow_up": "CONVERSATION",
                "story": "STORY",
                "reaction": "CONVERSATION",
                "clarification": "CONVERSATION",
                "language_tip": "PHRASE TOUR",
                "practice": "SHADOWING PRACTICE",
                "recap": "RECAP",
            }.get(turn_type, "CONVERSATION")
            _make_studio_segment(
                studio,
                out,
                seconds,
                camera=camera_for(group),
                section=section_label,
                speaker=group["speaker"],
            )
            scenes.append(out)

    concat = Path(app.WORK) / "scenes.txt"
    with concat.open("w", encoding="utf-8") as f:
        for seg in scenes:
            f.write(f"file '{seg.as_posix()}'\n")

    base = Path(app.WORK) / "base_video.mp4"
    _run([
        "ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-t",str(audio_duration),
        "-an","-c:v","libx264","-preset",ENCODE_PRESET,"-crf",ENCODE_CRF,
        "-pix_fmt","yuv420p",str(base)
    ], label="Semantic scene assembly")

    final = Path(app.WORK) / "the_two_takes.mp4"
    subtitle_path = str(srt).replace("\\","/").replace(":","\\:").replace("'","\\'")
    vf = (
        f"subtitles='{subtitle_path}':force_style="
        "'FontName=DejaVu Sans,FontSize=30,Bold=1,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00101722,"
        "BorderStyle=1,Outline=3,Shadow=0,"
        "Alignment=2,MarginL=190,MarginR=190,MarginV=105,WrapStyle=2'"
    )
    _run([
        "ffmpeg","-y","-i",str(base),"-i",str(wav),"-t",str(audio_duration),
        "-vf",vf,"-map","0:v:0","-map","1:a:0","-r",str(FPS),
        "-c:v","libx264","-preset",ENCODE_PRESET,"-crf",ENCODE_CRF,
        "-pix_fmt","yuv420p","-c:a","aac","-b:a","160k",
        "-af","highpass=f=70,lowpass=f=12000,acompressor=threshold=-18dB:ratio=3:attack=5:release=80:makeup=2,volume=1.25",
        "-shortest","-movflags","+faststart",str(final)
    ], label="FINAL SEMANTIC MIXED VIDEO")
    print(f"=== SEMANTIC RENDER COMPLETE in {(time.time()-started)/60:.1f} min ===")
    return final



# VISUAL REFERENCE STYLE
# Warm English-learning podcast presentation inspired by the genre, while keeping
# The Two Takes original branding, characters and artwork.
VISUAL_STYLE = {
    "thumbnail": "warm cream paper background; orange-red lesson headline; illustrated two-host focus; small English Podcast label; clean educational typography; minimal clutter",
    "video": "warm illustrated learning-podcast studio; two-host wide shot and speaker close-ups; section labels for conversation, phrase tour, shadowing practice and recap; readable subtitles; B-roll only for stories",
    "branding": "THE TWO TAKES original branding; no copied logos, characters, artwork, or distinctive visual assets",
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
            font-weight="800" fill="#2b211c">THE TWO TAKES</text>
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
        raise RuntimeError(f"Quality check failed: {width}x{height}, codec={codec}")
    print(f"Quality check passed: {width}x{height} H.264")


import build_podcast as app
