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


def _make_clip_segment(input_path, output_path, seconds, start=0):
    _run([
        "ffmpeg","-y","-ss",str(start),"-i",str(input_path),"-t",str(seconds),
        "-vf",f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=increase,crop={VIDEO_W}:{VIDEO_H},fps={FPS},setsar=1",
        "-an","-c:v","libx264","-preset",ENCODE_PRESET,"-crf",ENCODE_CRF,
        "-pix_fmt","yuv420p",str(output_path)
    ], label=f"Footage segment {output_path.name}")


def _make_studio_segment(studio, output_path, seconds, camera="wide"):
    # Use different crops of the same original studio artwork to simulate a
    # simple multi-camera edit without expensive animation.
    if camera == "himel":
        vf = f"crop=1100:1080:80:0,scale={VIDEO_W}:{VIDEO_H}:flags=lanczos"
    elif camera == "niha":
        vf = f"crop=1100:1080:740:0,scale={VIDEO_W}:{VIDEO_H}:flags=lanczos"
    else:
        vf = f"scale={VIDEO_W}:{VIDEO_H}:flags=lanczos"

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
        # Use topic footage as B-roll when the content is naturally visual.
        # Keep questions/reactions in the studio so the hosts remain the focus.
        use_broll = bool(clips) and turn_type in {"story", "language_tip"} and seconds >= 3.5

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
                _make_studio_segment(studio, studio_out, seconds - footage_seconds, camera="wide")
                scenes.append(studio_out)
        else:
            out = segment_dir / f"scene_{index:03d}.mp4"
            _make_studio_segment(studio, out, seconds, camera=camera_for(group))
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
    headline = _short_thumbnail_title(title, topic)
    lines = textwrap.wrap(headline, width=17)[:3]
    headline_svg = "".join(
        f'<text x="70" y="{265+i*82}" font-family="DejaVu Sans" font-size="68" font-weight="900" fill="#ffffff">{html.escape(line)}</text>'
        for i,line in enumerate(lines)
    )
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">
      <defs>
        <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0b1220"/><stop offset=".58" stop-color="#243b63"/><stop offset="1" stop-color="#111827"/></linearGradient>
        <linearGradient id="card" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffffff" stop-opacity=".12"/><stop offset="1" stop-color="#ffffff" stop-opacity=".03"/></linearGradient>
      </defs>
      <rect width="1280" height="720" fill="url(#bg)"/>
      <circle cx="1040" cy="130" r="290" fill="#ffffff" opacity=".07"/>
      <circle cx="1180" cy="650" r="260" fill="#ffffff" opacity=".05"/>
      <rect x="34" y="34" width="1212" height="652" rx="34" fill="url(#card)" stroke="#ffffff" stroke-opacity=".18" stroke-width="3"/>
      <rect x="70" y="66" width="270" height="48" rx="24" fill="#ffffff" opacity=".12"/>
      <text x="205" y="99" text-anchor="middle" font-family="DejaVu Sans" font-size="23" font-weight="800" fill="#fff">THE TWO TAKES</text>
      <rect x="70" y="175" width="510" height="410" rx="28" fill="#000000" opacity=".16"/>
      {headline_svg}
      <rect x="70" y="585" width="360" height="48" rx="24" fill="#ffffff" opacity=".13"/>
      <text x="250" y="617" text-anchor="middle" font-family="DejaVu Sans" font-size="22" font-weight="800" fill="#fff">LEARN • SPEAK • PRACTICE</text>
      <g transform="translate(760,155)">
        <ellipse cx="210" cy="450" rx="280" ry="42" fill="#000" opacity=".25"/>
        <circle cx="125" cy="125" r="110" fill="#c98f6b"/><path d="M20 130 Q28 15 125 15 Q222 15 230 130 Q190 72 125 75 Q60 72 20 130Z" fill="#20242b"/>
        <circle cx="92" cy="135" r="9"/><circle cx="158" cy="135" r="9"/><path d="M95 180 Q125 198 155 180" fill="none" stroke="#60332e" stroke-width="8"/>
        <path d="M55 265 Q125 225 195 265 L225 430 L25 430Z" fill="#314b70"/>
        <rect x="220" y="170" width="24" height="155" rx="12" fill="#171d26"/><ellipse cx="232" cy="155" rx="48" ry="24" fill="#10151d"/>
        <circle cx="370" cy="165" r="100" fill="#c99070"/><path d="M275 165 Q270 55 370 55 Q470 55 465 165 Q430 105 370 108 Q310 105 275 165Z" fill="#3a2830"/>
        <circle cx="342" cy="175" r="8"/><circle cx="398" cy="175" r="8"/><path d="M344 215 Q370 230 396 215" fill="none" stroke="#60332e" stroke-width="7"/>
        <path d="M305 300 Q370 265 435 300 L460 430 L280 430Z" fill="#865f70"/>
        <rect x="255" y="190" width="22" height="145" rx="11" fill="#171d26"/><ellipse cx="266" cy="175" rx="44" ry="22" fill="#10151d"/>
        <rect x="95" y="445" width="390" height="48" rx="20" fill="#0b1220" stroke="#ffffff" stroke-opacity=".15"/>
        <text x="290" y="477" text-anchor="middle" font-family="DejaVu Sans" font-size="22" font-weight="800" fill="#fff">HIMEL × NIHA</text>
      </g>
    </svg>'''
    svgfile=Path(app.WORK)/"thumbnail.svg"
    svgfile.write_text(svg,encoding="utf-8")
    jpg=Path(app.WORK)/"thumbnail.jpg"
    _run(["convert","-background","none",str(svgfile),"-quality","96",str(jpg)],label="Professional thumbnail")
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
