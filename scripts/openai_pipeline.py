import os
import re
import json
import subprocess
import time
import random
from pathlib import Path

import requests
import build_podcast as app


OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_TEXT_MODEL = "gpt-5.6-luna"
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_SPEECH_URL = "https://api.openai.com/v1/audio/speech"


if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY GitHub secret")


HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json",
}


def request_with_retries(url, payload, label, timeout=(30, 240), attempts=3):
    last_error = None
    for attempt in range(1, attempts + 1):
        print(f"{label} attempt {attempt}/{attempts}...")
        try:
            r = requests.post(
                url,
                headers=HEADERS,
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt < attempts:
                time.sleep(4 * attempt + random.uniform(0, 2))
                continue
            break

        if r.status_code in {429, 500, 502, 503, 504}:
            last_error = f"HTTP {r.status_code}: {r.text[:800]}"
            if attempt < attempts:
                wait = min(30, 5 * attempt + random.uniform(0, 3))
                print(f"  Temporary OpenAI error. Retrying in {wait:.1f}s...")
                time.sleep(wait)
                continue

        if r.status_code >= 400:
            raise RuntimeError(f"{label} failed with HTTP {r.status_code}: {r.text[:1200]}")

        return r

    raise RuntimeError(f"{label} failed after {attempts} attempts. Last error: {last_error}")


def openai_generate(prompt):
    payload = {
        "model": OPENAI_TEXT_MODEL,
        "input": prompt,
        "max_output_tokens": 9000,
    }
    r = request_with_retries(
        OPENAI_RESPONSES_URL,
        payload,
        f"OpenAI {OPENAI_TEXT_MODEL}",
    )
    data = r.json()

    text = data.get("output_text", "")
    if not text:
        chunks = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    chunks.append(content["text"])
        text = "\n".join(chunks)

    if not text.strip():
        raise RuntimeError("OpenAI returned an empty script response")

    return text.strip()


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                obj = json.loads(text[start:end + 1])
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None
    return None


def speaker_line(item):
    if not isinstance(item, dict):
        return ""
    speaker = str(item.get("speaker", "")).strip().lower()
    spoken = str(item.get("text", "")).strip()
    if speaker not in {"himel", "niha"} or not spoken:
        return ""
    return ("Himel: " if speaker == "himel" else "Niha: ") + spoken


def extract_dialogue(raw):
    obj = parse_json(raw)
    if isinstance(obj, dict):
        dialogue = obj.get("dialogue", obj.get("script", []))
        if isinstance(dialogue, list):
            lines = [speaker_line(item) for item in dialogue]
            lines = [line for line in lines if line]
            if lines:
                return "\n".join(lines)

    lines = []
    for raw_line in raw.splitlines():
        m = re.match(r"^\s*(Himel|Niha)\s*:\s*(.+)$", raw_line, flags=re.I)
        if m:
            speaker = "Himel" if m.group(1).lower() == "himel" else "Niha"
            lines.append(f"{speaker}: {m.group(2).strip()}")
    return "\n".join(lines).strip()


def make_episode(news):
    headline_block = "\n".join(
        f"{i + 1}. {x['title']} — {x['source']} ({x['pubDate']})"
        for i, x in enumerate(news)
    )

    prompt = f"""
You are the lead writer for the polished English YouTube podcast THE TWO TAKES.

Hosts:
Himel — male, curious, calm, quick-witted.
Niha — female, warm, sharp, thoughtful.

CURRENT NEWS HEADLINES:
{headline_block}

Choose ONE genuinely current topic from these headlines.
Do not invent quotes, statistics, events, sources, or facts that are not supported by the selected story.
Write an ORIGINAL 1,350–1,550 word two-host conversation suitable for roughly 10 minutes.

The conversation must include:
- a strong 10–20 second cold hook
- a short branded intro
- a clear explanation of what happened and why it matters now
- simple examples for difficult ideas
- frequent speaker turns
- one respectful disagreement/challenge
- natural reactions without excessive filler
- a useful practical takeaway
- a short memorable outro

STYLE:
- Natural spoken English, not an essay.
- Most turns should be 1–4 sentences.
- Avoid repetitive phrasing.
- Avoid misleading clickbait.
- Keep Himel and Niha clearly distinct.

RETURN ONLY VALID JSON with exactly this shape:
{{
  "title": "...",
  "topic": "...",
  "visual_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "description_hook": "...",
  "dialogue": [
    {{"speaker": "Himel", "text": "..."}},
    {{"speaker": "Niha", "text": "..."}}
  ]
}}
"""

    raw = openai_generate(prompt)
    obj = parse_json(raw) or {}
    script = extract_dialogue(raw)
    word_count = len(script.split())

    print("Script provider: OpenAI")
    print(f"Script length: {word_count} words")

    if not script or word_count < 1100:
        debug_file = app.WORK / "openai_episode_raw.txt"
        debug_file.write_text(raw, encoding="utf-8")
        raise RuntimeError(
            f"OpenAI dialogue was too short ({word_count} words). Raw output saved to {debug_file}"
        )

    title = str(obj.get("title", "")).strip() or f"The Two Takes: {news[0]['title']}"
    topic = str(obj.get("topic", "")).strip() or (news[0]["title"] if news else "Today’s biggest story")
    hook = str(obj.get("description_hook", "")).strip() or f"Today on The Two Takes, we are unpacking {topic}."

    keywords_raw = obj.get("visual_keywords", [])
    if isinstance(keywords_raw, list):
        keywords = [str(x).strip() for x in keywords_raw if str(x).strip()]
    else:
        keywords = [x.strip() for x in str(keywords_raw or "").split(",") if x.strip()]
    if not keywords:
        keywords = ["technology", "AI", "news", "innovation", "future"]

    return title[:100], topic[:300], keywords[:5], hook[:500], script


def split_for_openai_tts(script, max_chars=3600):
    segments = []
    current_speaker = None
    current_text = []

    def flush():
        nonlocal current_text, current_speaker
        if not current_speaker or not current_text:
            return
        text = " ".join(current_text).strip()
        if text:
            segments.append((current_speaker, text))
        current_text = []

    for raw_line in script.splitlines():
        line = raw_line.strip()
        m = re.match(r"^(Himel|Niha):\s*(.+)$", line, flags=re.I)
        if not m:
            continue
        speaker = "Himel" if m.group(1).lower() == "himel" else "Niha"
        text = m.group(2).strip()
        if speaker != current_speaker:
            flush()
            current_speaker = speaker
        current_text.append(text)
    flush()

    final = []
    for speaker, text in segments:
        while len(text) > max_chars:
            cut = text.rfind(". ", 0, max_chars)
            if cut < 800:
                cut = text.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            final.append((speaker, text[:cut + (1 if text[cut:cut + 2] == ". " else 0)].strip()))
            text = text[cut + 1:].strip()
        if text:
            final.append((speaker, text))

    return final


def tts(script):
    segments = split_for_openai_tts(script)
    print(f"OpenAI TTS: {len(segments)} speaker segments.")

    pcm_parts = []
    for i, (speaker, text) in enumerate(segments, 1):
        voice = "cedar" if speaker == "Himel" else "marin"
        print(f"OpenAI TTS segment {i}/{len(segments)} — {speaker} / {voice} ({len(text)} chars)...")

        payload = {
            "model": OPENAI_TTS_MODEL,
            "voice": voice,
            "input": text,
            "instructions": (
                "Natural polished podcast delivery. "
                + ("Confident, curious, youthful male host." if speaker == "Himel" else "Warm, intelligent, expressive female host.")
                + " Keep the wording exactly as provided. Do not add or omit words."
            ),
            "response_format": "mp3",
            "speed": 1.0,
        }

        r = request_with_retries(
            OPENAI_SPEECH_URL,
            payload,
            f"OpenAI TTS {speaker}",
            timeout=(30, 180),
            attempts=3,
        )

        mp3_path = app.WORK / f"openai_tts_{i:03d}.mp3"
        wav_path = app.WORK / f"openai_tts_{i:03d}.pcm"
        mp3_path.write_bytes(r.content)

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(mp3_path),
                "-f", "s16le",
                "-ar", "24000",
                "-ac", "1",
                "-",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        pcm_parts.append(result.stdout)

    if not pcm_parts:
        raise RuntimeError("OpenAI TTS produced no audio segments")

    pcm_path = app.WORK / "voice.pcm"
    wav_path = app.WORK / "voice.wav"
    pcm_path.write_bytes(b"".join(pcm_parts))

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "s16le",
            "-ar", "24000",
            "-ac", "1",
            "-i", str(pcm_path),
            str(wav_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    print(f"Combined OpenAI TTS audio: {wav_path}")
    return wav_path


# Replace both Gemini-backed runtime functions before app.main().
app.make_episode = make_episode
app.tts = tts

print("=== OPENAI-ONLY PIPELINE ENABLED ===")
print(f"Script model: {OPENAI_TEXT_MODEL}")
print(f"TTS model: {OPENAI_TTS_MODEL}")
print("Gemini is not used for script generation or TTS in this runner.")

app.main()
