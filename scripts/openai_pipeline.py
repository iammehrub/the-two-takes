import os
import re
import json
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
import requests
import build_podcast as app
from kokoro import KPipeline

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_TEXT_MODEL = "gpt-5.6-luna"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"

KOKORO_HIMEL_VOICE = "am_michael"
KOKORO_NIHA_VOICE = "af_heart"
KOKORO_SAMPLE_RATE = 24000

if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY GitHub secret")

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json",
}

print("=== INITIALIZING KOKORO TTS ===")
KOKORO_PIPELINE = KPipeline(lang_code="a")
print("Kokoro pipeline initialized")
print(f"Himel voice: {KOKORO_HIMEL_VOICE}")
print(f"Niha voice: {KOKORO_NIHA_VOICE}")


def openai_generate(prompt):
    payload = {"model": OPENAI_TEXT_MODEL, "input": prompt, "max_output_tokens": 9000}
    last_error = None
    for attempt in range(1, 4):
        print(f"OpenAI {OPENAI_TEXT_MODEL} attempt {attempt}/3...")
        try:
            r = requests.post(OPENAI_RESPONSES_URL, headers=HEADERS, json=payload, timeout=(30, 240))
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt < 3:
                continue
            raise RuntimeError(f"OpenAI network request failed: {exc}") from exc
        if r.status_code >= 400:
            last_error = f"HTTP {r.status_code}: {r.text[:1200]}"
            if r.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                print("Temporary OpenAI error; retrying...")
                continue
            raise RuntimeError(f"OpenAI script generation failed: {last_error}")
        data = r.json()
        text = data.get("output_text", "")
        if not text:
            chunks = []
            for item in data.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text" and content.get("text"):
                        chunks.append(content["text"])
            text = "\n".join(chunks)
        if text.strip():
            return text.strip()
        last_error = "OpenAI returned an empty script response"
    raise RuntimeError(f"OpenAI script generation failed: {last_error}")


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
    topic_bank = [
        "How to Talk About Your Daily Routine in English",
        "How to Talk About Your Day Naturally in English",
        "How to Be More Confident When Speaking English",
        "How to Stop Translating in Your Head and Speak More Naturally",
        "How to Build Better English Sentences Faster",
        "How to Keep a Conversation Going in English",
        "How to Talk About School, Work and Your Busy Day",
        "How to Make Friends and Start Conversations in English",
        "How to Talk About Your Weekend Plans in English",
        "How to Talk About Your Dreams and Goals in English",
        "How to Stay Motivated While Learning English",
        "How to Build a Simple Morning Routine in English",
        "How to Talk About Family and Relationships in English",
        "How to Talk About Travel and Holidays in English",
        "How to Handle Small Talk in English",
        "How to Talk About Food and Eating Habits in English",
        "How to Talk About Hobbies and Free Time in English",
        "How to Stop Being Afraid of Making English Mistakes",
        "How to Become More Disciplined and Consistent",
        "How to Talk About Money and Saving in Everyday English",
    ]

    prompt = f"""
You are the lead writer for an ORIGINAL English-learning YouTube conversation show called THE TWO TAKES.

The reference genre is polished English-learning podcast content: practical everyday topics, calm two-person conversation, clear spoken English, useful vocabulary, and a short practice section. Do NOT copy any creator's wording, characters, scripts, branding, thumbnails, or signature phrases.

Hosts:
Himel — male, calm, curious, friendly, natural.
Niha — female, warm, thoughtful, expressive, natural.

Choose ONE topic from this topic bank, preferably one that has not been used recently:
{chr(10).join('- ' + x for x in topic_bank)}

Write an ORIGINAL 1,500–1,800 word episode for English learners around A2-B1/B1 level. Aim for 12–15 minutes of clear, comfortable listening rather than a news podcast.

STRUCTURE:
1. Very short hook using a relatable everyday question or situation.
2. Warm branded introduction to The Two Takes.
3. Natural conversation about the topic using real-life examples.
4. Frequent short turns; avoid long monologues.
5. Include useful everyday phrases naturally in the dialogue.
6. Add a short "Speaking Practice" section near the end with 5 useful sentence patterns the viewer can repeat.
7. Add a short "Word Tour" section with 6 useful words/phrases: meaning plus one simple example each.
8. Finish with a warm recap and outro.

STYLE:
- Simple, natural, modern spoken English.
- Calm and clear, with occasional light humor.
- Useful for listening, shadowing, speaking practice and vocabulary.
- Do not sound like a textbook or a formal lecture.
- Do not use current-news stories.
- Do not invent research or statistics.
- Do not copy any existing episode.
- Do not use the phrase "English Leap Podcast" or another creator's branding.
- Keep most turns 1–4 sentences.
- Make the conversation feel like two friends recording in a small studio.

RETURN ONLY VALID JSON:
{{
  "title": "...",
  "topic": "...",
  "visual_keywords": ["english learning", "podcast studio", "conversation", "education", "speaking practice"],
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

    if not script or word_count < 1300:
        debug_file = app.WORK / "openai_episode_raw.txt"
        debug_file.write_text(raw, encoding="utf-8")
        raise RuntimeError(f"OpenAI dialogue was too short ({word_count} words). Raw output saved to {debug_file}")

    title = str(obj.get("title", "")).strip() or "How to Speak English More Naturally"
    topic = str(obj.get("topic", "")).strip() or title
    hook = str(obj.get("description_hook", "")).strip() or f"Practice natural English with Himel and Niha as they talk about {topic}."
    keywords_raw = obj.get("visual_keywords", [])
    keywords = [str(x).strip() for x in keywords_raw if str(x).strip()] if isinstance(keywords_raw, list) else [x.strip() for x in str(keywords_raw or "").split(",") if x.strip()]
    if not keywords:
        keywords = ["english learning", "podcast studio", "conversation", "education", "speaking practice"]
    return title[:100], topic[:300], keywords[:5], hook[:500], script


def split_for_kokoro(script, max_chars=1800):
    chunks = []
    current_speaker = None
    current_parts = []
    current_length = 0

    def flush():
        nonlocal current_parts, current_length
        if current_speaker and current_parts:
            text = " ".join(current_parts).strip()
            if text:
                chunks.append((current_speaker, text))
        current_parts = []
        current_length = 0

    for raw_line in script.splitlines():
        line = raw_line.strip()
        match = re.match(r"^(Himel|Niha):\s*(.+)$", line, flags=re.I)
        if not match:
            continue
        speaker = "Himel" if match.group(1).lower() == "himel" else "Niha"
        text = match.group(2).strip()
        if speaker != current_speaker:
            flush()
            current_speaker = speaker
        while text:
            remaining = max_chars - current_length - 1
            if remaining <= 0:
                flush()
                continue
            if len(text) <= remaining:
                current_parts.append(text)
                current_length += len(text) + 1
                text = ""
                continue
            cut = text.rfind(". ", 0, remaining)
            if cut < 200:
                cut = text.rfind(" ", 0, remaining)
            if cut <= 0:
                cut = remaining
            part = text[:cut + (1 if text[cut:cut + 2] == ". " else 0)].strip()
            text = text[len(part):].strip()
            current_parts.append(part)
            current_length += len(part) + 1
            flush()
    flush()
    return chunks


def kokoro_segment(speaker, text, index, total):
    voice = KOKORO_HIMEL_VOICE if speaker == "Himel" else KOKORO_NIHA_VOICE
    print(f"Kokoro TTS segment {index}/{total} — {speaker} / {voice} ({len(text)} chars)...")
    for attempt in range(1, 3):
        try:
            generator = KOKORO_PIPELINE(text, voice=voice, speed=0.95)
            audio_parts = [np.asarray(audio, dtype=np.float32) for _, _, audio in generator]
            if not audio_parts:
                raise RuntimeError("Kokoro returned no audio")
            return np.concatenate(audio_parts)
        except Exception as exc:
            print(f"  Kokoro attempt {attempt}/2 failed: {exc}")
            if attempt == 2:
                raise RuntimeError(f"Kokoro TTS failed for {speaker} segment {index}: {exc}") from exc
    raise RuntimeError("Kokoro TTS failed unexpectedly")


def tts(script):
    segments = split_for_kokoro(script)
    print(f"Kokoro TTS: {len(segments)} speaker segments.")
    audio_parts = []
    silence = np.zeros(int(KOKORO_SAMPLE_RATE * 0.16), dtype=np.float32)
    for i, (speaker, text) in enumerate(segments, 1):
        audio_parts.append(kokoro_segment(speaker, text, i, len(segments)))
        if i < len(segments):
            audio_parts.append(silence)
    if not audio_parts:
        raise RuntimeError("Kokoro produced no audio segments")
    audio = np.concatenate(audio_parts)
    wav = app.WORK / "voice.wav"
    sf.write(str(wav), audio, KOKORO_SAMPLE_RATE)
    print(f"Combined Kokoro TTS audio: {wav}")
    return wav


app.make_episode = make_episode
app.tts = tts

import production_upgrade as visual_upgrade
app.pexels_videos = visual_upgrade.pexels_videos
app.make_srt = visual_upgrade.make_srt
app.render_video = visual_upgrade.render_video
app.make_thumbnail = visual_upgrade.make_thumbnail

print("=== ENGLISH-LEARNING STUDIO PRODUCTION ENABLED ===")
print(f"Script model: {OPENAI_TEXT_MODEL}")
print(f"Kokoro Himel: {KOKORO_HIMEL_VOICE}")
print(f"Kokoro Niha: {KOKORO_NIHA_VOICE}")
print("Output: 1920x1080 H.264, studio visual, paced captions, practical English topics.")

app.main()
