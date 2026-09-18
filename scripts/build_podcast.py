import os
import re
import json
import base64
import subprocess
import html
import time
import random
import sys
from pathlib import Path
from datetime import datetime, timezone

import requests
import xml.etree.ElementTree as ET


# ============================================================
# PATHS / ENVIRONMENT
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
WORK.mkdir(exist_ok=True)

GEMINI = os.environ.get("GEMINI_API_KEY")
PEXELS = os.environ.get("PEXELS_API_KEY")
YT_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")
YT_REFRESH = os.environ.get("YOUTUBE_REFRESH_TOKEN")

if not GEMINI:
    raise RuntimeError("Missing GEMINI_API_KEY GitHub secret")

if not PEXELS:
    raise RuntimeError("Missing PEXELS_API_KEY GitHub secret")

for n, v in [
    ("YOUTUBE_CLIENT_ID", YT_CLIENT_ID),
    ("YOUTUBE_CLIENT_SECRET", YT_CLIENT_SECRET),
    ("YOUTUBE_REFRESH_TOKEN", YT_REFRESH),
]:
    if not v:
        raise RuntimeError(f"Missing {n} GitHub secret")


# ============================================================
# GEMINI MODELS
# ============================================================

GEMINI_TEXT_MODEL = "gemini-2.5-flash"
GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"


# ============================================================
# GEMINI TEXT GENERATION
# ============================================================

def gemini_generate(prompt, temperature=0.9):
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_TEXT_MODEL}:generateContent"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 5000
        }
    }

    retry_statuses = {429, 500, 502, 503, 504}
    last_error = None

    for attempt in range(1, 5):
        try:
            print(f"Gemini text attempt {attempt}/4...")

            r = requests.post(
                url,
                headers={
                    "x-goog-api-key": GEMINI,
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=(30, 240)
            )

            if r.status_code in retry_statuses:
                last_error = (
                    f"Gemini text temporary error "
                    f"{r.status_code}: {r.text[:500]}"
                )
                wait_time = 5 * attempt
                print(
                    f"Temporary Gemini error. "
                    f"Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
                continue

            if r.status_code >= 400:
                raise RuntimeError(
                    f"Gemini text API {r.status_code}: "
                    f"{r.text[:1000]}"
                )

            data = r.json()
            candidates = data.get("candidates", [])

            if not candidates:
                raise RuntimeError("Gemini text returned no candidates")

            parts = (
                candidates[0]
                .get("content", {})
                .get("parts", [])
            )

            text_parts = [
                part.get("text", "")
                for part in parts
                if part.get("text")
            ]

            if not text_parts:
                raise RuntimeError("Gemini text returned no text content")

            return "".join(text_parts).strip()

        except requests.exceptions.Timeout as e:
            last_error = f"Gemini text timeout on attempt {attempt}: {e}"
            wait_time = 5 * attempt
            print(
                f"Gemini text timed out. "
                f"Retrying in {wait_time}s..."
            )
            time.sleep(wait_time)

        except requests.exceptions.RequestException as e:
            last_error = f"Gemini text network error: {e}"
            wait_time = 5 * attempt
            print(
                f"Network error. Retrying in {wait_time}s..."
            )
            time.sleep(wait_time)

    raise RuntimeError(
        "Gemini text generation failed after 4 attempts. "
        f"Last error: {last_error}"
    )


# ============================================================
# CURRENT NEWS
# ============================================================

def fetch_news():
    q = (
        "(AI OR technology OR science OR business OR gaming "
        "OR entertainment OR space)"
    )

    url = "https://news.google.com/rss"

    params = {
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
        "q": q
    }

    r = requests.get(
        url,
        params=params,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    r.raise_for_status()
    root = ET.fromstring(r.text)
    items = []

    for item in root.findall(".//item")[:30]:
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        pub = item.findtext("pubDate") or ""
        source = item.findtext("source") or ""

        if title:
            items.append(
                {
                    "title": title,
                    "source": source,
                    "pubDate": pub,
                    "link": link
                }
            )

    return items[:20]


# ============================================================
# EPISODE GENERATION
# ============================================================

def make_episode(news):

    headline_block = "\n".join(
        f"{i + 1}. {x['title']} — {x['source']} ({x['pubDate']})"
        for i, x in enumerate(news)
    )

    prompt = f"""
You are the lead writer for a polished English YouTube podcast called THE TWO TAKES.

Hosts:
Himel (male, curious, quick-witted, calm)
Niha (female, warm, sharp, thoughtful)

Audience:
International young adults who like intelligent but easy-to-follow conversations.

CURRENT NEWS HEADLINES:
{headline_block}

Choose ONE genuinely current topic from these headlines.

It must have enough substance for about 10 minutes.

Do not pretend to know facts that are not supported by the headlines or your general knowledge.
If a headline is too uncertain, choose another.

Write an ORIGINAL 1,350–1,550 word two-host podcast script.

This is not an essay.
It must sound like two real people talking.

STRUCTURE:

1) 10–20 second cold hook:
surprising question, tension, or intriguing claim.

2) Short branded intro for The Two Takes.

3) Clear setup:
why this matters TODAY.

4) Main conversation with frequent turns between Himel and Niha.

5) Explain difficult ideas with simple examples.

6) Include at least one moment where the hosts disagree or challenge each other respectfully.

7) Add a few natural reactions, but never overuse fake laughter or filler.

8) Give viewers a useful takeaway.

9) Short memorable outro and invitation to return.

STYLE RULES:

- Natural, confident, polished spoken English.
- No textbook language.
- No long monologues.
- Most turns should be 1–4 sentences.
- Do not repeat the same phrases, hook patterns, or conversation structure used in previous episodes.
- No invented quotes, statistics, events, or sources.
- No copyrighted article copying.
- Avoid sensational clickbait that misrepresents the story.
- Make the title compelling but accurate.
- Keep Himel and Niha clearly labeled on every speaking turn.

IMPORTANT:
Return ONLY the following fields.
Do not use Markdown code fences.
Do not add explanations before or after the fields.

TITLE: ...
TOPIC: ...
VISUAL_KEYWORDS: keyword1, keyword2, keyword3, keyword4, keyword5
DESCRIPTION_HOOK: one short sentence
SCRIPT:
Himel: ...
Niha: ...
...
END_SCRIPT
"""

    text = gemini_generate(prompt, 0.85)

    if not text:
        raise RuntimeError("Gemini returned an empty episode response")

    print("\nGemini episode response received.")
    print(f"Response length: {len(text)} characters")

    text = re.sub(r"```(?:text|txt|markdown)?", "", text, flags=re.I)
    text = text.replace("```", "").strip()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.strip()

    def extract_field(name, next_fields):
        pattern = (
            rf"(?im)^[ \t]*{re.escape(name)}[ \t]*:"
            rf"[ \t]*(.*?)(?=\n[ \t]*(?:"
            + "|".join(re.escape(x) for x in next_fields)
            + r")[ \t]*:|\Z)"
        )
        match = re.search(pattern, text, re.S)
        return match.group(1).strip() if match else ""

    title = extract_field(
        "TITLE",
        ["TOPIC", "VISUAL_KEYWORDS", "DESCRIPTION_HOOK", "SCRIPT"]
    )
    topic = extract_field(
        "TOPIC",
        ["VISUAL_KEYWORDS", "DESCRIPTION_HOOK", "SCRIPT"]
    )
    keywords = extract_field(
        "VISUAL_KEYWORDS",
        ["DESCRIPTION_HOOK", "SCRIPT"]
    )
    hook = extract_field("DESCRIPTION_HOOK", ["SCRIPT"])

    script_match = re.search(
        r"(?is)^[ \t]*SCRIPT[ \t]*:[ \t]*\n?(.*?)(?:^[ \t]*END_SCRIPT[ \t]*$|\Z)",
        text
    )

    script = script_match.group(1).strip() if script_match else ""

    if not script:
        fallback = re.search(
            r"(?is)SCRIPT\s*:\s*(.*?)(?:END_SCRIPT|$)",
            text
        )
        if fallback:
            script = fallback.group(1).strip()

    script = re.sub(
        r"(?im)^[ \t]*END_SCRIPT[ \t]*$",
        "",
        script
    ).strip()

    missing = []
    if not title:
        missing.append("TITLE")
    if not topic:
        missing.append("TOPIC")
    if not keywords:
        missing.append("VISUAL_KEYWORDS")
    if not hook:
        missing.append("DESCRIPTION_HOOK")
    if not script:
        missing.append("SCRIPT")

    if missing:
        debug_file = WORK / "gemini_episode_raw.txt"
        debug_file.write_text(text, encoding="utf-8")
        raise RuntimeError(
            "Gemini episode response was incomplete. "
            f"Missing: {', '.join(missing)}. "
            f"Raw response saved to: {debug_file}"
        )

    title = re.sub(r"\s+", " ", title).strip().strip('"').strip("'").strip()
    topic = re.sub(r"\s+", " ", topic).strip().strip('"').strip("'").strip()
    hook = re.sub(r"\s+", " ", hook).strip().strip('"').strip("'").strip()

    keyword_list = []
    for k in keywords.split(","):
        k = k.strip()
        k = re.sub(r"^[\-\*\d\.\)\s]+", "", k).strip()
        k = k.strip('"').strip("'").strip()
        if k:
            keyword_list.append(k)

    keyword_list = keyword_list[:5]

    if not keyword_list:
        keyword_list = [
            "technology",
            "news",
            "discussion",
            "future",
            "people talking"
        ]

    script_lines = []
    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if re.match(r"^(Himel|Niha)\s*:", line, re.I):
            line = re.sub(
                r"^(Himel|Niha)\s*:\s*",
                lambda m: (
                    "Himel: "
                    if m.group(1).lower() == "himel"
                    else "Niha: "
                ),
                line,
                flags=re.I
            )
            script_lines.append(line)

    script = "\n".join(script_lines).strip()
    word_count = len(script.split())

    print(f"Parsed episode: {word_count} script words")

    if word_count < 1100:
        debug_file = WORK / "gemini_episode_raw.txt"
        debug_file.write_text(text, encoding="utf-8")
        raise RuntimeError(
            f"Generated script was too short ({word_count} words); refusing to publish. "
            f"Raw response saved to: {debug_file}"
        )

    return (
        title[:100],
        topic[:300],
        keyword_list,
        hook[:500],
        script
    )


# ============================================================
# TTS CHUNKING
# ============================================================

def split_script_for_tts(script, max_chars=6000):
    dialogue_lines = []

    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^(Himel|Niha):", line, re.I):
            dialogue_lines.append(line)

    if not dialogue_lines:
        raise RuntimeError("Could not find Himel/Niha dialogue in generated script")

    chunks = []
    current = []
    current_length = 0

    for line in dialogue_lines:
        line_length = len(line) + 1
        if current and current_length + line_length > max_chars:
            chunks.append("\n".join(current))
            current = []
            current_length = 0
        current.append(line)
        current_length += line_length

    if current:
        chunks.append("\n".join(current))

    return chunks


# ============================================================
# GEMINI TTS SINGLE CHUNK
# ============================================================

def tts_chunk(chunk_text, chunk_number, total_chunks):
    print(f"TTS chunk {chunk_number}/{total_chunks} ({len(chunk_text)} characters)...")

    prompt = f"""
Perform this podcast conversation as a natural, polished two-person English show.

Himel should sound confident, curious and youthful.

Niha should sound warm, intelligent and expressive.

Use subtle conversational rhythm, natural pauses and emphasis.

Do not add words that are not in the transcript.

Keep the speaker identities exactly as written.

TRANSCRIPT:

{chunk_text}
"""

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_TTS_MODEL}:generateContent"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "multiSpeakerVoiceConfig": {
                    "speakerVoiceConfigs": [
                        {
                            "speaker": "Himel",
                            "voiceConfig": {
                                "prebuiltVoiceConfig": {
                                    "voiceName": "Puck"
                                }
                            }
                        },
                        {
                            "speaker": "Niha",
                            "voiceConfig": {
                                "prebuiltVoiceConfig": {
                                    "voiceName": "Kore"
                                }
                            }
                        }
                    ]
                },
                "languageCode": "en-US"
            }
        }
    }

    retry_statuses = {429, 500, 502, 503, 504}
    last_error = None

    for attempt in range(1, 5):
        try:
            print(f"  Gemini TTS attempt {attempt}/4...")

            r = requests.post(
                url,
                headers={
                    "x-goog-api-key": GEMINI,
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=(30, 150)
            )

            if r.status_code in retry_statuses:
                last_error = (
                    f"Gemini TTS temporary error "
                    f"{r.status_code}: {r.text[:500]}"
                )
                wait_time = 5 * attempt + random.uniform(0, 3)
                print(
                    f"  Temporary Gemini error. "
                    f"Retrying in {wait_time:.1f}s..."
                )
                time.sleep(wait_time)
                continue

            if r.status_code >= 400:
                raise RuntimeError(
                    f"Gemini TTS API {r.status_code}: {r.text[:1200]}"
                )

            data = r.json()
            candidates = data.get("candidates", [])

            if not candidates:
                raise RuntimeError("Gemini TTS returned no candidates")

            parts = candidates[0].get("content", {}).get("parts", [])
            audio_parts = []

            for part in parts:
                inline = part.get("inlineData")
                if inline and inline.get("data"):
                    audio_parts.append(base64.b64decode(inline["data"]))

            if not audio_parts:
                raise RuntimeError("Gemini TTS returned no audio data")

            return b"".join(audio_parts)

        except requests.exceptions.Timeout as e:
            last_error = f"Gemini TTS timeout on attempt {attempt}: {e}"
            wait_time = 5 * attempt
            print(f"  TTS timed out. Retrying in {wait_time}s...")
            time.sleep(wait_time)

        except requests.exceptions.RequestException as e:
            last_error = f"Gemini TTS network error: {e}"
            wait_time = 5 * attempt
            print(f"  Network error. Retrying in {wait_time}s...")
            time.sleep(wait_time)

    raise RuntimeError(
        f"Gemini TTS failed after 4 attempts. Last error: {last_error}"
    )


# ============================================================
# TTS FULL PODCAST
# ============================================================

def tts(script):
    chunks = split_script_for_tts(script, max_chars=6000)
    print(f"Splitting podcast into {len(chunks)} TTS chunks.")

    all_pcm = bytearray()

    for i, chunk in enumerate(chunks, 1):
        pcm_data = tts_chunk(chunk, i, len(chunks))
        all_pcm.extend(pcm_data)
        if i < len(chunks):
            time.sleep(2)

    pcm = WORK / "voice.pcm"
    pcm.write_bytes(bytes(all_pcm))

    wav = WORK / "voice.wav"

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "s16le",
            "-ar", "24000",
            "-ac", "1",
            "-i", str(pcm),
            str(wav)
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    print(f"Combined TTS audio: {wav}")
    return wav


# ============================================================
# PEXELS VIDEOS
# ============================================================

def pexels_videos(keywords):
    clips = []

    for kw in keywords[:4]:
        print(f"Searching Pexels for: {kw}")

        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": PEXELS},
            params={
                "query": kw,
                "per_page": 8,
                "orientation": "landscape",
                "size": "medium"
            },
            timeout=30
        )

        if r.status_code >= 400:
            print(
                f"Pexels search failed for '{kw}': {r.status_code}"
            )
            continue

        for v in r.json().get("videos", []):
            files = v.get("video_files", [])
            files = [
                f for f in files
                if f.get("width", 0) >= 1000
                and f.get("height", 0) >= 500
            ]

            if not files:
                continue

            files = sorted(
                files,
                key=lambda x: abs(
                    (
                        x.get("width", 1920)
                        / max(x.get("height", 1080), 1)
                    ) - 16 / 9
                )
            )

            f = files[0]

            clips.append(
                (
                    f["link"],
                    v.get("duration", 8),
                    v.get("url", ""),
                    v.get("user", {}).get("name", "Pexels creator")
                )
            )

        if len(clips) >= 8:
            break

    seen = set()
    out = []

    for x in clips:
        if x[0] not in seen:
            seen.add(x[0])
            out.append(x)

    out = out[:8]

    for i, (url, dur, page, creator) in enumerate(out):
        print(f"Downloading Pexels clip {i + 1}/{len(out)}...")
        p = WORK / f"clip_{i}.mp4"

        with requests.get(
            url,
            stream=True,
            timeout=60,
            headers={"User-Agent": "Mozilla/5.0"}
        ) as rr:
            rr.raise_for_status()
            with open(p, "wb") as f:
                for chunk in rr.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)

        out[i] = (str(p), dur, page, creator)

    if not out:
        raise RuntimeError(
            "No Pexels clips were returned. Check PEXELS_API_KEY or try again later."
        )

    print(f"Downloaded {len(out)} Pexels clips.")
    return out


# ============================================================
# SUBTITLES
# ============================================================

def make_srt(script, audio_seconds):
    lines = []

    for line in script.splitlines():
        line = line.strip()
        if re.match(r"^(Himel|Niha):", line, re.I):
            lines.append(
                re.sub(r"^(Himel|Niha):\s*", "", line, flags=re.I)
            )

    words = sum(len(x.split()) for x in lines) or 1
    t = 0.0
    s = []

    for text in lines:
        dur = max(
            2.0,
            audio_seconds * (len(text.split()) / words)
        )
        start = t
        end = min(audio_seconds, t + dur)
        if end - start > 18:
            end = start + 18

        s.append((start, end, text))
        t = end

        if t >= audio_seconds:
            break

    def ts(x):
        ms = int(round(x * 1000))
        h = ms // 3600000
        ms %= 3600000
        m = ms // 60000
        ms %= 60000
        sec = ms // 1000
        ms %= 1000
        return f"{h:02}:{m:02}:{sec:02},{ms:03}"

    srt_path = WORK / "captions.srt"

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, (a, b, text) in enumerate(s, 1):
            f.write(
                f"{i}\n"
                f"{ts(a)} --> {ts(b)}\n"
                f"{text}\n\n"
            )

    return srt_path


# ============================================================
# MEDIA DURATION
# ============================================================

def duration(path):
    p = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path)
        ],
        capture_output=True,
        text=True,
        check=True
    )

    return float(p.stdout.strip())


# ============================================================
# VIDEO RENDER
# ============================================================

def render_video(wav, clips, srt, title):
    processed = []

    for i, (p, dur, page, creator) in enumerate(clips):
        out = WORK / f"v_{i}.mp4"

        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", p,
                "-t", str(min(max(float(dur), 5), 14)),
                "-vf",
                (
                    "scale=1280:720:"
                    "force_original_aspect_ratio=increase,"
                    "crop=1280:720,"
                    "setsar=1,"
                    "fps=30"
                ),
                "-an",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "28",
                str(out)
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        processed.append(out)

    if not processed:
        raise RuntimeError("No processed video clips available.")

    concat = WORK / "concat.txt"
    with open(concat, "w", encoding="utf-8") as f:
        for _ in range(20):
            for p in processed:
                f.write(f"file '{p.as_posix()}'\n")

    bg = WORK / "bg.mp4"
    audio_duration = duration(wav)

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat),
            "-t", str(audio_duration + 1),
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            str(bg)
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    final = WORK / "the_two_takes.mp4"

    subtitle_path = str(srt).replace("\\", "/").replace("'", "\\'")

    vf = (
        "drawbox="
        "x=0:y=0:w=iw:h=72:"
        "color=black@0.68:t=fill,"
        "drawtext="
        "fontfile=/usr/share/fonts/"
        "truetype/dejavu/"
        "DejaVuSans-Bold.ttf:"
        "text='THE TWO TAKES':"
        "x=36:y=22:"
        "fontsize=30:"
        "fontcolor=white,"
        f"subtitles='{subtitle_path}':"
        "force_style="
        "'FontName=DejaVu Sans,"
        "FontSize=18,"
        "Outline=2,"
        "Shadow=1,"
        "Alignment=2,"
        "MarginV=34'"
    )

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(bg),
            "-i", str(wav),
            "-t", str(audio_duration),
            "-vf", vf,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            str(final)
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    return final


# ============================================================
# THUMBNAIL
# ============================================================

def make_thumbnail(title, topic):
    safe = html.escape(title[:62])
    topic_safe = html.escape(topic[:90])

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">
    <defs>
        <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0"/>
            <stop offset="1" stop-color="#303030"/>
        </linearGradient>
    </defs>

    <rect width="1280" height="720" fill="url(#g)"/>

    <circle cx="1050" cy="150" r="220" fill="#ffffff" opacity=".06"/>
    <circle cx="170" cy="620" r="260" fill="#ffffff" opacity=".04"/>

    <text x="70" y="90" font-family="DejaVu Sans" font-size="34" font-weight="bold" fill="#fff">
        THE TWO TAKES
    </text>

    <text x="70" y="260" font-family="DejaVu Sans" font-size="64" font-weight="bold" fill="#fff">
        {safe}
    </text>

    <text x="70" y="390" font-family="DejaVu Sans" font-size="30" fill="#ddd">
        {topic_safe}
    </text>

    <text x="70" y="650" font-family="DejaVu Sans" font-size="28" fill="#aaa">
        HIMEL × NIHA • NEW EPISODE
    </text>
</svg>'''

    svgfile = WORK / "thumb.svg"
    svgfile.write_text(svg, encoding="utf-8")

    jpg = WORK / "thumbnail.jpg"
    subprocess.run(
        ["convert", str(svgfile), str(jpg)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    return jpg


# ============================================================
# YOUTUBE UPLOAD
# ============================================================

def youtube_upload(video, thumb, title, topic, script, hook, credits):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    print("Authenticating with YouTube...")

    creds = Credentials(
        None,
        refresh_token=YT_REFRESH,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YT_CLIENT_ID,
        client_secret=YT_CLIENT_SECRET,
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload"
        ]
    )

    creds.refresh(Request())

    yt = build("youtube", "v3", credentials=creds)

    description = (
        f"{hook}\n\n"
        "A fresh conversation with Himel and Niha "
        "from The Two Takes.\n\n"
        f"Topic: {topic}\n\n"
        "#TheTwoTakes #Podcast #News #Discussion\n\n"
        "Visual credits: Pexels (used via the Pexels API)."
    )


    body = {
        "snippet": {
            "title": title,
            "description": description[:4900],
            "categoryId": "22",
            "tags": [
                "The Two Takes",
                "podcast",
                "Himel",
                "Niha",
                "learn English",
                "English speaking",
                "English conversation",
                "spoken English",
                "English listening"
            ]
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    print(f"Uploading video: {video}")

    req = yt.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(
            str(video),
            chunksize=-1,
            resumable=True
        )
    )

    resp = req.execute()
    vid = resp["id"]

    print(f"YouTube upload complete. Video ID: {vid}")

    print("Uploading thumbnail...")

    yt.thumbnails().set(
        videoId=vid,
        media_body=MediaFileUpload(
            str(thumb),
            mimetype="image/jpeg"
        )
    ).execute()

    print(f"Published: https://youtu.be/{vid}")



# ============================================================
# GROWTH PACK
# ============================================================

def create_growth_pack(title, topic, script, hook):
    """Create upload/promotion assets without artificial engagement."""
    title_options = [title]
    title_file = WORK / "title_options.json"
    if title_file.exists():
        try:
            data = json.loads(title_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                title_options = [str(x).strip() for x in data if str(x).strip()][:3] or [title]
            elif isinstance(data, dict):
                raw = data.get("titles") or data.get("title_options") or []
                if isinstance(raw, list):
                    title_options = [str(x).strip() for x in raw if str(x).strip()][:3] or [title]
        except (json.JSONDecodeError, OSError):
            pass

    hashtags = ["#EnglishLearning", "#SpeakEnglish", "#EnglishSpeaking"]
    hashtag_file = WORK / "hashtags.json"
    if hashtag_file.exists():
        try:
            data = json.loads(hashtag_file.read_text(encoding="utf-8"))
            raw = data if isinstance(data, list) else (
                data.get("hashtags") or data.get("items") or []
            )
            if isinstance(raw, list):
                cleaned = []
                for item in raw:
                    tag = str(item).strip()
                    if tag and not tag.startswith("#"):
                        tag = "#" + re.sub(r"[^A-Za-z0-9_]", "", tag)
                    if tag and tag not in cleaned:
                        cleaned.append(tag)
                if cleaned:
                    hashtags = cleaned[:5]
        except (json.JSONDecodeError, OSError):
            pass

    lines = [line.strip() for line in script.splitlines() if line.strip()]
    short_candidates = []
    for line in lines:
        if len(line) >= 45 and len(line) <= 180:
            short_candidates.append(line)
    shorts = short_candidates[:5]

    pack = {
        "episode_title": title,
        "title_options": title_options,
        "topic": topic,
        "hook": hook,
        "hashtags": hashtags,
        "shorts_ideas": [
            {
                "hook": item,
                "source": "episode dialogue",
                "note": "Use only if this line matches the final rendered episode."
            }
            for item in shorts
        ],
        "pinned_comment": (
            "What part of this conversation was most useful for your English? "
            "Tell us one phrase you want to practice."
        ),
        "next_video_cta": (
            "If this conversation helped you, subscribe for the next "
            "English-learning episode from The Two Takes."
        ),
        "description": (
            f"{hook}\\n\\n"
            "A practical English-learning conversation with Himel and Niha.\\n\\n"
            f"Topic: {topic}\\n\\n"
            + " ".join(hashtags)
        ),
        "discovery_note": (
            "Keep titles accurate and concise. Use relevant hashtags only; "
            "do not rely on keyword stuffing or artificial engagement."
        )
    }

    (WORK / "growth_pack.json").write_text(
        json.dumps(pack, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    (WORK / "growth_pack.txt").write_text(
        "THE TWO TAKES — GROWTH PACK\\n\\n"
        f"Primary title: {title}\\n\\n"
        "Title options:\\n" +
        "\\n".join(f"- {x}" for x in title_options) +
        "\\n\\nHashtags:\\n" +
        " ".join(hashtags) +
        "\\n\\nPinned comment:\\n" +
        pack["pinned_comment"] +
        "\\n\\nNext-video CTA:\\n" +
        pack["next_video_cta"] +
        "\\n\\nShorts candidates:\\n" +
        "\\n".join(f"- {x}" for x in shorts),
        encoding="utf-8"
    )

    print(f"Growth pack created: {WORK / 'growth_pack.json'}")


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("THE TWO TAKES — DAILY PODCAST BUILDER")
    print("=" * 60)

    print("\nFetching current headlines...")
    news = fetch_news()
    print(f"Got {len(news)} headlines")

    if not news:
        raise RuntimeError("No current news headlines were returned.")

    title, topic, keywords, hook, script = make_episode(news)

    print("\nEpisode:")
    print(title)
    print(f"Topic: {topic}")
    print(f"Script length: {len(script.split())} words")

    (WORK / "script.txt").write_text(script, encoding="utf-8")

    print("\nGenerating AI voices...")
    wav = tts(script)

    secs = duration(wav)
    print(f"Audio duration: {secs / 60:.1f} minutes")

    if secs < 8 * 60 or secs > 12.5 * 60:
        print(
            "WARNING: Audio duration is outside the 8–12.5 minute target range."
        )
        print("Continuing with generated result.")

    print("\nGenerating subtitles...")
    srt = make_srt(script, secs)

    print("\nGetting Pexels visuals...")
    clips = pexels_videos(keywords)

    print("\nRendering final video...")
    final = render_video(wav, clips, srt, title)
    print(f"Final video created: {final}")

    print("\nCreating thumbnail...")
    thumb = make_thumbnail(title, topic)

    print("\nCreating growth pack...")
    create_growth_pack(title, topic, script, hook)

    print("\nUploading to YouTube...")
    youtube_upload(
        final,
        thumb,
        title,
        topic,
        script,
        hook,
        clips
    )

    print("\n" + "=" * 60)
    print("EPISODE COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
