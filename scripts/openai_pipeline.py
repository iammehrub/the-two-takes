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



def load_recent_content():
    try:
        from content_guard import load_history
        return load_history(app.ROOT)
    except Exception as exc:
        print(f"Content history unavailable: {exc}")
        return []


def recent_content_context(limit=20):
    try:
        from content_guard import recent_context
        return recent_context(app.ROOT, limit=limit)
    except Exception:
        return "(No prior published content is recorded yet.)"


def youtube_demand_snapshot():
    """Use a small YouTube search sample to steer topic selection toward active demand.
    This is a directional signal, not a guarantee of views.
    """
    try:
        from datetime import datetime, timedelta, timezone
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        if not all([
            getattr(app, "YT_CLIENT_ID", None),
            getattr(app, "YT_CLIENT_SECRET", None),
            getattr(app, "YT_REFRESH", None),
        ]):
            return []

        creds = Credentials(
            None,
            refresh_token=app.YT_REFRESH,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=app.YT_CLIENT_ID,
            client_secret=app.YT_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/youtube.readonly"],
        )
        creds.refresh(Request())
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

        published_after = (
            datetime.now(timezone.utc) - timedelta(days=180)
        ).isoformat().replace("+00:00", "Z")

        queries = [
            "learn English speaking",
            "English conversation practice",
            "speak English naturally",
        ]

        rows = []
        for query in queries:
            search = yt.search().list(
                part="snippet",
                q=query,
                type="video",
                order="viewCount",
                maxResults=5,
                publishedAfter=published_after,
                relevanceLanguage="en",
            ).execute()

            ids = [
                item.get("id", {}).get("videoId")
                for item in search.get("items", [])
                if item.get("id", {}).get("videoId")
            ]
            if not ids:
                continue

            stats = yt.videos().list(
                part="snippet,statistics",
                id=",".join(ids),
            ).execute()

            for item in stats.get("items", []):
                title = item.get("snippet", {}).get("title", "").strip()
                views = int(
                    item.get("statistics", {}).get("viewCount", 0) or 0
                )
                if title:
                    rows.append({
                        "query": query,
                        "title": title,
                        "views": views,
                    })

        rows.sort(key=lambda x: x["views"], reverse=True)
        return rows[:10]

    except Exception as exc:
        print(f"YouTube demand snapshot skipped: {exc}")
        return []


def format_demand(rows):
    if not rows:
        return "(No demand snapshot available; rely on topic quality and audience fit.)"
    return "\n".join(
        f"- {row['query']}: {row['title']} ({row['views']:,} views)"
        for row in rows
    )



def audience_profile_context():
    path = app.ROOT / "data" / "youtube_audience_insights.json"
    if not path.exists():
        return "(No processed YouTube audience profile is available yet.)"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        parts = [f"Analytics window: {data.get('window', 'unknown')}"]
        countries = data.get("countries", [])
        if countries:
            parts.append("Top countries by views: " + ", ".join(
                f"{x.get('country')} ({x.get('views', 0):,})" for x in countries[:7]
            ))
        traffic = data.get("traffic_sources", [])
        if traffic:
            parts.append("Top traffic sources: " + ", ".join(
                f"{x.get('source')} ({x.get('views', 0):,})" for x in traffic[:7]
            ))
        age_gender = data.get("age_gender", [])
        if age_gender:
            parts.append("Largest reported audience groups: " + ", ".join(
                f"{x.get('age_group')} {x.get('gender')} ({x.get('viewer_percentage', 0):.1f}%)"
                for x in age_gender[:7]
            ))
        return "\n".join(parts)
    except Exception as exc:
        return f"(Audience profile could not be read: {exc})"


def make_episode(news):
    topic_bank = [
        "Stop Translating in Your Head: Speak English More Naturally",
        "How to Speak English With Confidence Even When You Make Mistakes",
        "What to Say When You Do Not Understand Someone in English",
        "How to Start a Conversation With Someone You Just Met",
        "How to Keep a Conversation Going When You Run Out of Things to Say",
        "How to Make Small Talk Without Feeling Awkward",
        "How to Sound More Natural in Everyday English",
        "English Phrases You Can Use in Real Conversations",
        "How to Remember New English Words and Actually Use Them",
        "How to Build English Sentences Faster",
        "How to Agree and Disagree Politely in English",
        "How to Explain Your Opinion Clearly in English",
        "How to Tell a Story in English Without Getting Stuck",
        "How to Ask for Help Naturally in English",
        "How to Refuse a Request Politely in English",
        "How to Apologize Naturally in English",
        "How to Talk About Your Studies in English",
        "How to Talk About Your Work in English",
        "How to Talk About Your Hobbies in English",
        "How to Talk About Travel in Everyday English",
        "How to Talk About Food and Eating Habits in English",
        "How to Talk About Movies and TV in English",
        "How to Talk About Gaming in English",
        "How to Talk About Money and Saving in English",
        "How to Talk About Stress and a Busy Day in English",
        "How to Talk About Your Plans for the Future in English",
        "How to Express Feelings in Everyday English",
        "How to Handle an Awkward Silence in English",
        "How to Sound Friendly Instead of Too Formal in English",
        "How to End a Conversation Naturally in English",
        "How to Improve Your Listening When People Speak Fast",
        "How to Think in English More Often",
        "How to Stop Saying 'Umm' So Much in English",
        "How to Ask Better Questions in English",
        "How to Give Better Answers in English",
        "How to Sound Clear on the Phone in English",
        "How to Make Your English More Natural With Simple Phrases",
        "How to Describe People and Places in English",
        "How to Talk About Your Goals in English",
        "How to Talk About Daily Problems in English",
    ]

    recent_context = recent_content_context(20)
    demand_rows = youtube_demand_snapshot()
    demand_context = format_demand(demand_rows)
    audience_context = audience_profile_context()

    prompt = f"""
You are the lead writer for THE TWO TAKES, an original English-learning YouTube conversation show.

REFERENCE STYLE: SPEAK ENGLISH WITH CLASS — ADAPT, DO NOT COPY
- Match the overall learning experience: calm podcast conversation, friendly teacher-like delivery, practical everyday English, clear B1-B2 language, and a clean educational presentation.
- Do NOT copy their scripts, exact phrases, episode titles, thumbnails, artwork, characters, branding, or distinctive wording.
- INTRO: start with a natural 5-15 second hook about the learner's problem. Then a short friendly greeting and tell the viewer what they will learn. Never spend the opening on a long branded intro.
- VOICE/DIALOGUE: sound like two real people teaching through conversation, not two actors reading an essay. Use warm, relaxed, clear delivery. Himel is calm/curious; Niha is warm/thoughtful. Alternate naturally, with short turns and real reactions.
- ENGLISH LEVEL: mainly B1-B2. Prefer common words and explain harder phrases in simple English. Avoid academic wording unless it is the teaching point.
- TOPIC SELECTION: choose practical, relatable speaking situations and questions learners actually face: confidence, habits, work/study, travel, friendships, daily problems, opinions, small talk, stories, and useful conversation situations. Give each episode one clear learning outcome.
- LESSON FEEL: the conversation should teach naturally. Highlight useful phrases after they appear, then give examples and a short speaking/shadowing practice section.
- PACING: calm but never flat. Use examples, reactions, mini-stories, questions and small changes of angle every 45-90 seconds.
- ENDING: brief recap of useful phrases/ideas, then a natural invitation to practice and return. Avoid repetitive YouTube filler.

PRIMARY GOAL:
Create a video concept that a new viewer can understand instantly and has a clear reason to click and keep watching.

Audience:
A2-B1/B1 English learners worldwide, especially people who want to speak more naturally in real life.

Hosts:
Himel — calm, curious, friendly, quick-witted.
Niha — warm, thoughtful, expressive.

DO NOT reuse any topic that appears in RECENTLY PUBLISHED CONTENT below.
RECENTLY PUBLISHED CONTENT:
{recent_context}

DIRECTIONAL YOUTUBE DEMAND SNAPSHOT:
{demand_context}

AVAILABLE TOPIC BANK:
{chr(10).join('- ' + x for x in topic_bank)}

Use the channel audience profile as a signal, not a rule. Prioritize topics that fit the actual audience while still attracting English learners worldwide.\n\nChoose ONE fresh topic. You may create a new angle around a topic-bank idea, but it must be meaningfully different from recent content.

TITLE/PACKAGING RULES:
- Produce 3 distinct title options.
- Put the main searchable phrase or problem near the beginning.
- Keep each title concise, preferably under 65 characters.
- Do not start the title with "The Two Takes".
- Do not use episode numbers.
- Make the title accurate, specific, and useful; no misleading clickbait.
- One title should be clearly searchable.
- One title should be curiosity-driven but still accurate.
- One title should combine search clarity with curiosity.
- Choose the strongest primary title as "title".
- Produce "thumbnail_text" with only 2–4 short words, different wording from the full title when possible.
- Thumbnail text must be truthful to the actual episode.

CONTENT / RETENTION RULES:
- Write an original 1,500–1,750 word two-host conversation.
- The first 15 seconds must state a relatable problem/question and promise a concrete payoff.
- Avoid a generic branded intro before the hook.
- Get to the useful conversation immediately.
- Make Himel and Niha react to each other frequently.
- Most turns should be 1–3 sentences.
- Add natural follow-up questions, examples, disagreement, clarification, and small moments of humor.
- Every 45–90 seconds, introduce a fresh example, question, mini-challenge, or change of angle so the conversation does not flatten.
- Include a practical "Speaking Practice" section with 5 repeatable sentence patterns.
- Include a short "Word Tour" with 6 useful words or phrases and simple examples.
- End with a concise recap and a reason to return.
- Do not pad the episode just to reach a length target.
- Avoid repetitive openings, repetitive outro lines, or the same conversation pattern as recent episodes.
- No copied scripts, quotes, statistics, or invented research.
- No stage directions or narration in the spoken dialogue.
- No current-news discussion.

DISCOVERY METADATA:
- Return 3–6 natural search phrases based on the actual topic.
- Return 3–5 relevant hashtags.
- The description hook should clearly explain the viewer benefit in one sentence.

RETURN ONLY VALID JSON:
{{
  "title": "...",
  "title_options": ["...", "...", "..."],
  "thumbnail_text": "...",
  "topic": "...",
  "visual_keywords": ["...", "...", "...", "...", "..."],
  "search_phrases": ["...", "...", "..."],
  "hashtags": ["#...", "#...", "#..."],
  "description_hook": "...",
  "dialogue": [
    {{"speaker": "Himel", "turn_type": "hook", "text": "..."}},
    {{"speaker": "Niha", "turn_type": "reaction", "text": "..."}}
  ]
}}
"""

    from content_guard import is_duplicate

    last_problem = None

    for generation_attempt in range(1, 5):
        print(
            f"Generating fresh episode {generation_attempt}/4 "
            f"with duplicate protection..."
        )

        attempt_prompt = prompt
        if generation_attempt > 1:
            attempt_prompt += f"""

REGENERATION REQUIREMENT:
The previous draft was rejected because it was too similar to an existing topic/title.
Pick a clearly different topic and angle.
Do not use these rejected candidates:
{recent_context}
"""

        raw = openai_generate(attempt_prompt)
        obj = parse_json(raw) or {}
        script = extract_dialogue(raw)
        word_count = len(script.split())

        if not script or word_count < 1300:
            last_problem = f"dialogue too short ({word_count} words)"
            print(last_problem)
            continue

        dialogue_obj = obj.get("dialogue", []) if isinstance(obj, dict) else []
        valid_types = {
            "hook", "question", "story", "reaction", "follow_up",
            "clarification", "language_tip", "practice", "recap"
        }

        beats = []
        if isinstance(dialogue_obj, list):
            for item in dialogue_obj:
                if not isinstance(item, dict):
                    continue
                speaker = str(item.get("speaker", "")).strip().title()
                text_value = str(item.get("text", "")).strip()
                turn_type = str(
                    item.get("turn_type", "reaction")
                ).strip().lower()

                if speaker in {"Himel", "Niha"} and text_value:
                    if turn_type not in valid_types:
                        turn_type = "reaction"
                    beats.append({
                        "turn_index": len(beats),
                        "speaker": speaker,
                        "text": text_value,
                        "turn_type": turn_type,
                    })

        if len(beats) < 24:
            last_problem = f"too few dialogue turns ({len(beats)})"
            print(last_problem)
            continue

        same_speaker_run = 0
        previous_speaker = None
        max_turn_words = 0

        for beat in beats:
            speaker = beat["speaker"]
            max_turn_words = max(
                max_turn_words,
                len(beat["text"].split())
            )
            same_speaker_run = (
                same_speaker_run + 1
                if speaker == previous_speaker
                else 1
            )
            previous_speaker = speaker

            if same_speaker_run > 3:
                last_problem = "too many consecutive turns by one host"
                print(last_problem)
                break
        else:
            if max_turn_words > 95:
                last_problem = "an individual turn is too long"
                print(last_problem)
            else:
                title = (
                    str(obj.get("title", "")).strip()
                    or "Speak English More Naturally"
                )
                topic = str(obj.get("topic", "")).strip() or title
                duplicate, reason = is_duplicate(
                    app.ROOT, title, topic, script
                )

                if duplicate:
                    last_problem = f"duplicate protection: {reason}"
                    print(last_problem)
                    recent_context = (
                        recent_context
                        + f"\n- [REJECTED THIS RUN] {title} — {topic}"
                    )
                    continue

                keywords_raw = obj.get("visual_keywords", [])
                if isinstance(keywords_raw, list):
                    keywords = [
                        str(x).strip()
                        for x in keywords_raw
                        if str(x).strip()
                    ]
                else:
                    keywords = [
                        x.strip()
                        for x in str(
                            keywords_raw or ""
                        ).split(",")
                        if x.strip()
                    ]

                if not keywords:
                    keywords = [
                        "english learning",
                        "conversation",
                        "speaking practice",
                        "study",
                        "communication",
                    ]

                hook = (
                    str(obj.get("description_hook", "")).strip()
                    or f"Practice natural English with Himel and Niha "
                       f"as they talk about {topic}."
                )

                title_options = obj.get("title_options", [])
                if not isinstance(title_options, list):
                    title_options = []
                title_options = [
                    str(x).strip()[:100]
                    for x in title_options
                    if str(x).strip()
                ][:3] or [title]

                thumbnail_text = str(
                    obj.get("thumbnail_text", "")
                ).strip()
                if not thumbnail_text:
                    thumbnail_text = "SPEAK MORE NATURALLY"

                search_phrases = obj.get("search_phrases", [])
                if not isinstance(search_phrases, list):
                    search_phrases = []
                search_phrases = [
                    str(x).strip()
                    for x in search_phrases
                    if str(x).strip()
                ][:6]

                hashtags = obj.get("hashtags", [])
                if not isinstance(hashtags, list):
                    hashtags = []
                hashtags = [
                    str(x).strip()
                    for x in hashtags
                    if str(x).strip().startswith("#")
                ][:5]

                (app.WORK / "conversation_beats.json").write_text(
                    json.dumps(
                        beats,
                        indent=2,
                        ensure_ascii=False
                    ),
                    encoding="utf-8",
                )
                (app.WORK / "dialogue_metadata.json").write_text(
                    json.dumps(
                        beats,
                        indent=2,
                        ensure_ascii=False
                    ),
                    encoding="utf-8",
                )
                (app.WORK / "title_options.json").write_text(
                    json.dumps(
                        title_options,
                        indent=2,
                        ensure_ascii=False
                    ),
                    encoding="utf-8",
                )
                (app.WORK / "thumbnail_text.txt").write_text(
                    thumbnail_text[:60],
                    encoding="utf-8",
                )
                (app.WORK / "hashtags.json").write_text(
                    json.dumps(
                        hashtags,
                        indent=2,
                        ensure_ascii=False
                    ),
                    encoding="utf-8",
                )
                (app.WORK / "youtube_metadata.json").write_text(
                    json.dumps(
                        {
                            "title": title[:100],
                            "title_options": title_options,
                            "thumbnail_text": thumbnail_text[:60],
                            "topic": topic[:300],
                            "search_phrases": search_phrases,
                            "hashtags": hashtags,
                            "description_hook": hook[:500],
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                print("Script provider: OpenAI")
                print(f"Script length: {word_count} words")
                print(f"Primary title: {title}")
                print(f"Thumbnail text: {thumbnail_text}")

                return (
                    title[:100],
                    topic[:300],
                    keywords[:5],
                    hook[:500],
                    script,
                )

    raise RuntimeError(
        "Could not generate a fresh unique episode after 4 attempts. "
        f"Last problem: {last_problem}"
    )


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
