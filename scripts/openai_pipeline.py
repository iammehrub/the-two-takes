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
4. Make it a REAL back-and-forth conversation: frequent short turns, reactions, follow-up questions, clarifications, agreement/disagreement, and natural topic changes. Avoid long monologues.
5. Himel and Niha should respond to what the other person JUST said. Do not write isolated mini-speeches.
6. Use natural spoken features: contractions ("I'm", "don't", "it's"), short reactions ("Really?", "Exactly.", "I know what you mean."), and occasional harmless fillers ("well", "actually", "you know") — but never overuse them.
7. Include useful everyday phrases naturally inside the conversation instead of stopping the conversation every few lines to teach.
8. Add a short "Speaking Practice" section near the end with 5 useful sentence patterns the viewer can repeat. Make it interactive: one host says a model line, the other gives a variation.
9. Add a short "Word Tour" section with 6 useful words/phrases: meaning plus one simple example each, delivered as a conversation between the hosts.
10. Finish with a warm recap and outro.

STYLE:
- Simple, natural, modern spoken English.
- Sound like two friends who genuinely know each other, not two presenters reading an essay.
- Give each host a distinct personality: Himel is calm/curious and Niha is warm/expressive.
- Include small reactions to each other's ideas and occasional light humor.
- Use short sentences and varied sentence lengths.
- Avoid repetitive "That's a good question" / "Exactly" patterns.
- Do not use narration, stage directions, bracketed emotions, or pronunciation notes in the spoken text.
- Do not sound like a textbook, formal lecture, interview transcript, or customer-service conversation.
- Do not use current-news stories.
- Do not invent research or statistics.
- Do not copy any existing episode.
- Do not use the phrase "English Leap Podcast" or another creator's branding.
- Most turns should be 1–3 sentences; only occasionally use a longer turn when it genuinely feels natural.
- Every reply should clearly connect to the previous reply.
- Make the conversation feel spontaneous while remaining easy for A2-B1/B1 learners to follow.

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

    # Save structured conversation metadata for semantic editing/rendering.
    dialogue_obj = obj.get("dialogue", []) if isinstance(obj, dict) else []
    valid_types = {"hook","question","story","reaction","follow_up","clarification","language_tip","practice","recap"}
    beats = []
    if isinstance(dialogue_obj, list):
        for item in dialogue_obj:
            if not isinstance(item, dict):
                continue
            speaker = str(item.get("speaker", "")).strip().title()
            text_value = str(item.get("text", "")).strip()
            turn_type = str(item.get("turn_type", "reaction")).strip().lower()
            if speaker in {"Himel", "Niha"} and text_value:
                if turn_type not in valid_types:
                    turn_type = "reaction"
                beats.append({"turn_index": len(beats), "speaker": speaker, "text": text_value, "turn_type": turn_type})
    if beats:
        (app.WORK / "conversation_beats.json").write_text(json.dumps(beats, indent=2, ensure_ascii=False), encoding="utf-8")
        (app.WORK / "dialogue_metadata.json").write_text(json.dumps(beats, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Script provider: OpenAI")
    print(f"Script length: {word_count} words")

    if not script or word_count < 1300:
        debug_file = app.WORK / "openai_episode_raw.txt"
        debug_file.write_text(raw, encoding="utf-8")
        raise RuntimeError(f"OpenAI dialogue was too short ({word_count} words). Raw output saved to {debug_file}")

    if beats:
        same_speaker_run = 0
        previous_speaker = None
        max_turn_words = 0
        for beat in beats:
            speaker = beat["speaker"]
            max_turn_words = max(max_turn_words, len(beat["text"].split()))
            same_speaker_run = same_speaker_run + 1 if speaker == previous_speaker else 1
            previous_speaker = speaker
            if same_speaker_run > 3:
                raise RuntimeError("Conversation quality check failed: too many consecutive turns by one host.")
        if max_turn_words > 95:
            raise RuntimeError("Conversation quality check failed: an individual turn is too long.")
        if len(beats) < 24:
            raise RuntimeError("Conversation quality check failed: too few dialogue turns.")

    title = str(obj.get("title", "")).strip() or "How to Speak English More Naturally"
    topic = str(obj.get("topic", "")).strip() or title
    hook = str(obj.get("description_hook", "")).strip() or f"Practice natural English with Himel and Niha as they talk about {topic}."
    keywords_raw = obj.get("visual_keywords", [])
    keywords = [str(x).strip() for x in keywords_raw if str(x).strip()] if isinstance(keywords_raw, list) else [x.strip() for x in str(keywords_raw or "").split(",") if x.strip()]
    if not keywords:
        keywords = ["english learning", "podcast studio", "conversation", "education", "speaking practice"]
    return title[:100], topic[:300], keywords[:5], hook[:500], script


def split_for_kokoro(script, max_chars=420):
    """Split dialogue into short TTS units while retaining conversation beat metadata."""
    chunks = []
    metadata = []
    metadata_path = app.WORK / "conversation_beats.json"
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            metadata = []
    meta_cursor = 0

    def split_sentences(text):
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return []
        sentences = re.split(r"(?<=[.!?])\s+", text)
        out = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) <= max_chars:
                out.append(sentence)
                continue
            pieces = re.split(r"(?<=[,;:])\s+", sentence)
            current = ""
            for piece in pieces:
                if not current:
                    current = piece
                elif len(current) + 1 + len(piece) <= max_chars:
                    current += " " + piece
                else:
                    out.append(current.strip())
                    current = piece
            if current:
                out.append(current.strip())
        return out

    for raw_line in script.splitlines():
        match = re.match(r"^\s*(Himel|Niha):\s*(.+)$", raw_line, flags=re.I)
        if not match:
            continue
        speaker = "Himel" if match.group(1).lower() == "himel" else "Niha"
        source_text = match.group(2).strip()
        turn_type = "reaction"
        turn_index = meta_cursor
        if meta_cursor < len(metadata) and metadata[meta_cursor].get("speaker") == speaker:
            turn_type = metadata[meta_cursor].get("turn_type", "reaction")
            turn_index = metadata[meta_cursor].get("turn_index", meta_cursor)
            meta_cursor += 1
        for sentence in split_sentences(source_text):
            chunks.append((speaker, sentence, turn_index, turn_type))
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
    print(f"Kokoro TTS: {len(segments)} short conversational segments.")
    audio_parts = []
    timing = []
    cursor = 0.0

    for i, (speaker, text, turn_index, turn_type) in enumerate(segments, 1):
        audio = kokoro_segment(speaker, text, i, len(segments))
        seg_seconds = len(audio) / KOKORO_SAMPLE_RATE

        timing.append({
            "speaker": speaker,
            "text": text,
            "start": cursor,
            "end": cursor + seg_seconds,
            "turn_index": turn_index,
            "turn_type": turn_type
        })
        audio_parts.append(audio)
        cursor += seg_seconds

        if i < len(segments):
            # A slightly longer pause when the speaker changes makes the exchange
            # feel conversational instead of like two continuous readings.
            next_speaker = segments[i][0]
            pause = 0.28 if next_speaker != speaker else 0.16
            silence = np.zeros(int(KOKORO_SAMPLE_RATE * pause), dtype=np.float32)
            audio_parts.append(silence)
            cursor += pause

    (app.WORK / "tts_segments.json").write_text(
        json.dumps(timing, indent=2),
        encoding="utf-8"
    )

    if not audio_parts:
        raise RuntimeError("Kokoro produced no audio segments")

    audio = np.concatenate(audio_parts)
    wav = app.WORK / "voice.wav"
    sf.write(str(wav), audio, KOKORO_SAMPLE_RATE)
    print(f"Combined conversational Kokoro TTS audio: {wav}")
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
print("Output: 1920x1080 H.264, mixed studio + topic footage, exact TTS-timed captions, practical English topics.")

app.main()
