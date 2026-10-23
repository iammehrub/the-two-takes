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

KOKORO_HIMEL_VOICE = "am_eric"
KOKORO_NIHA_VOICE = "af_bella"
KOKORO_SAMPLE_RATE = 24000

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json",
} if OPENAI_API_KEY else {}

print("=== INITIALIZING KOKORO TTS ===")
KOKORO_PIPELINE = KPipeline(lang_code="a")
print("Kokoro pipeline initialized")
print(f"Himel voice: {KOKORO_HIMEL_VOICE}")
print(f"Niha voice: {KOKORO_NIHA_VOICE}")


def openai_generate(prompt):
    """Use Gemini by default; only call the potentially paid OpenAI API when opted in."""
    use_openai = os.environ.get("USE_OPENAI_FOR_SCRIPT", "").strip().lower() in {
        "1", "true", "yes", "on"
    }
    if not OPENAI_API_KEY or not use_openai:
        print("Free-first mode: using configured Gemini text generation.")
        return app.gemini_generate(prompt, temperature=0.8)

    payload = {
        "model": OPENAI_TEXT_MODEL,
        "input": prompt,
        "max_output_tokens": 9000,
    }
    last_error = None

    for attempt in range(1, 4):
        print(f"OpenAI {OPENAI_TEXT_MODEL} attempt {attempt}/3...")
        try:
            r = requests.post(
                OPENAI_RESPONSES_URL,
                headers=HEADERS,
                json=payload,
                timeout=(30, 240),
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt < 3:
                continue
            print("OpenAI network failed; falling back to Gemini.")
            return app.gemini_generate(prompt, temperature=0.8)

        if r.status_code >= 400:
            body = r.text[:1500]
            last_error = f"HTTP {r.status_code}: {body}"

            # A depleted OpenAI balance is a provider/account problem, not a
            # content problem. Do not waste three retries; use the Gemini key
            # already required by the production pipeline.
            if r.status_code == 429 and any(
                marker in body.lower()
                for marker in (
                    "insufficient_quota",
                    "credit_balance_exhausted",
                    "no credits remaining",
                )
            ):
                print("OpenAI credits exhausted; falling back to Gemini.")
                return app.gemini_generate(prompt, temperature=0.8)

            if r.status_code in {401, 403, 404}:
                print(
                    f"OpenAI unavailable (HTTP {r.status_code}); "
                    "falling back to Gemini."
                )
                return app.gemini_generate(prompt, temperature=0.8)

            if r.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                print("Temporary OpenAI error; retrying...")
                continue

            print("OpenAI generation failed; falling back to Gemini.")
            return app.gemini_generate(prompt, temperature=0.8)

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

    print(f"OpenAI generation failed: {last_error}; falling back to Gemini.")
    return app.gemini_generate(prompt, temperature=0.8)

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

        # Search/read-only discovery needs a read-scoped credential. The
        # upload token may have only youtube.upload and then fails invalid_scope.
        demand_client_id = (
            os.environ.get("YOUTUBE_ANALYTICS_CLIENT_ID", "").strip()
            or getattr(app, "YT_CLIENT_ID", None)
        )
        demand_client_secret = (
            os.environ.get("YOUTUBE_ANALYTICS_CLIENT_SECRET", "").strip()
            or getattr(app, "YT_CLIENT_SECRET", None)
        )
        demand_refresh = (
            os.environ.get("YOUTUBE_ANALYTICS_REFRESH_TOKEN", "").strip()
            or getattr(app, "YT_REFRESH", None)
        )
        if not all([demand_client_id, demand_client_secret, demand_refresh]):
            return []

        creds = Credentials(
            None,
            refresh_token=demand_refresh,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=demand_client_id,
            client_secret=demand_client_secret,
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
    # Fresh headlines are the primary topic pool. Evergreen English topics are
    # used only if the current-news feed has no usable stories.
    fallback_topic_bank = [
        "Stop Translating in Your Head: Speak English More Naturally",
        "How to Speak English With Confidence Even When You Make Mistakes",
        "How to Keep a Conversation Going When You Run Out of Things to Say",
        "How to Make Small Talk Without Feeling Awkward",
        "How to Remember New English Words and Actually Use Them",
        "How to Agree and Disagree Politely in English",
        "How to Improve Your Listening When People Speak Fast",
        "How to Think in English More Often",
    ]

    current_stories = []
    seen_story_keys = set()
    for item in news or []:
        if not isinstance(item, dict):
            continue
        headline = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()
        source = re.sub(r"\s+", " ", str(item.get("source") or "")).strip()
        pub_date = re.sub(r"\s+", " ", str(item.get("pubDate") or "")).strip()
        if len(headline) < 15 or len(headline) > 180:
            continue
        story_key = re.sub(r"[^a-z0-9]+", " ", headline.lower()).strip()
        if not story_key or story_key in seen_story_keys:
            continue
        seen_story_keys.add(story_key)
        current_stories.append({
            "title": headline,
            "source": source,
            "pubDate": pub_date,
        })
        if len(current_stories) >= 12:
            break

    trend_context = "\n".join(
        f"{i + 1}. {item['title']} — {item['source']} ({item['pubDate']})"
        for i, item in enumerate(current_stories)
    ) or "(No usable current headlines were returned; use an evergreen topic only as a fallback.)"

    topic_bank = [item["title"] for item in current_stories] or fallback_topic_bank

    recent_context = recent_content_context(20)
    demand_rows = youtube_demand_snapshot()
    demand_context = format_demand(demand_rows)
    audience_context = audience_profile_context()

    prompt = f"""
You are the lead writer for TWO TAKES PODCAST: a trending-story English-learning conversation show.

REFERENCE FORMAT: SPEAK ENGLISH WITH CLASS / ENGLISH-LEARNING PODCAST GENRE — ADAPT THE FORMAT, KEEP EVERYTHING ORIGINAL
- Recreate the same broad viewer experience: a calm, friendly English-learning podcast built around natural conversation, relatable life topics, vocabulary teaching, and speaking practice.
- Do NOT copy their scripts, exact wording, recurring catchphrases, episode titles, thumbnail artwork, logos, characters, or distinctive branding. Two Takes Podcast must remain original.
- OPENING: begin with a relatable learner problem, natural question, or useful phrase. Make the first spoken line the hook, then continue directly into the conversation.
- NO INTRO: do not greet or welcome viewers, introduce the hosts or channel, announce the episode, or insert an opening music sting. No spoken branding before the conversation.
- MAIN CONVERSATION: Himel and Niha should feel like real friends/teachers talking about one continuous topic. Use personal examples, questions, follow-up questions, light disagreement, clarification, and natural reactions. Do not read a lecture.
- LESSON ARCHITECTURE: Hook -> real conversation -> phrase tour -> speaking/shadowing practice -> recap -> concise sign-off.
- MAIN DISCUSSION: aim for 0:35–3:30, using stories, follow-up questions, gentle disagreement, clarification and natural reactions.
- TRANSITION: the production system supplies the short instrumental interlude automatically; do not add a host line saying "music plays".
- PHRASE TOUR: teach exactly 6 useful everyday phrases/words in the middle/late middle. Mark explanation turns "language_tip"; explain meaning simply and give natural examples.
- SPEAKING PRACTICE: include 5 practical sentence patterns with short model lines and invitations to repeat/personalize. Mark these turns "practice".
- QUICK TIP: include one memorable rule or common mistake near the end.
- OUTRO: finish with a brief recap marked "recap", then a friendly sign-off and one specific comment question marked "outro". The production system adds 7 seconds of instrumental fade-out after the final spoken line.
- Target about 10 minutes at 130–150 words per minute. Avoid padding; keep the hook and outro concise.
- PACING: natural conversational English at a comfortable everyday speed, not slow or sleepy. Vary energy with the moment: lively curiosity, relaxed storytelling, quick reactions, thoughtful pauses, and encouraging practice. Change the conversational focus every 45-90 seconds with a new example, question, mini-story, phrase, or practice task.
- OUTRO: give a short recap of the main lesson and useful language, then a natural practice/subscribe invitation. Never use a long generic outro.
- VISUALS: the supplied Two Takes Podcast opener remains on screen for the entire video. Keep it as one static background with no B-roll, scene cuts, title cards, or animated visual changes; captions appear beneath the host who is speaking.
- Keep the actual vocabulary, stories, examples, dialogue, and packaging newly generated for Two Takes Podcast.

PRIMARY GOAL:
Turn a genuinely current story into a useful, entertaining English-learning conversation. The news topic attracts interest; natural English, useful phrases, and speaking practice are the channel's core value. Do not drift into generic news commentary.

Audience:
A2-B1 and B1-B2 English learners worldwide, especially people who want to speak more naturally in everyday life.

Hosts:
Himel — a friendly, curious young man with quick timing, gentle dry humor, honest reactions, and the confidence to admit when he is wrong. He sounds like a real person, not a presenter reading a lesson.
Niha — warm, perceptive, expressive, and quietly witty. She notices small details, asks sharp follow-up questions, sometimes playfully challenges Himel, and can show real excitement or empathy without becoming theatrical.

NATURAL HUMAN PERFORMANCE (IMPORTANT):
- Write for the ear, not for an essay. Use contractions, varied sentence lengths, specific everyday details, and the occasional short sentence or unfinished thought where a real speaker would use one.
- Make each reply respond to the exact thought before it. Hosts should remember details from each other's mini-stories, ask genuine follow-up questions, disagree gently sometimes, and change their minds when persuaded.
- Give the conversation an emotional shape: curiosity at the start, discovery or a small surprise in the middle, then warmth and confidence near the end. Let the topic determine the feeling.
- Add a few small, specific, kind moments of humor across the whole episode. Do not force a joke into every turn. Let the other host react naturally when a joke lands.
- Avoid repetitive “That's interesting,” “Exactly,” “Absolutely,” fake enthusiasm, constant praise, generic laughter, motivational slogans, repeated summaries, and perfectly balanced textbook exchanges.
- Do not make every sentence a complete polished explanation. Use natural spoken transitions, short reactions, occasional gentle teasing, and realistic pauses shown with normal punctuation. Do not write stage directions such as [laughs], [smiles], or [excited].
- Make Himel and Niha sound distinct in word choice and conversational habits, while keeping both easy for A2-B1 learners to understand.
- For every dialogue item, add a non-spoken "delivery" label chosen from: warm, curious, amused, surprised, thoughtful, reassuring, excited, emphatic, calm, playful, neutral. Choose the feeling that genuinely fits that line; do not label everything warm or neutral. This label guides subtle speaking pace only and must never appear in the spoken text.

DO NOT reuse any topic that appears in RECENTLY PUBLISHED CONTENT below.
RECENTLY PUBLISHED CONTENT:
{recent_context}

DIRECTIONAL YOUTUBE DEMAND SNAPSHOT:
{demand_context}

CURRENT TRENDING NEWS HEADLINES (most recent candidates first; headlines are leads, not complete reporting):
{trend_context}

AVAILABLE TOPIC BANK:
{chr(10).join('- ' + x for x in topic_bank)}

Use the channel audience profile and YouTube demand snapshot as signals, not guarantees. When current headlines are available, choose ONE story with broad curiosity and clear everyday relevance. Explain the story's general context in plain English and teach language viewers can use to discuss it. Do not simply read the headline or produce a generic vocabulary lesson. Do not invent details that the supplied headlines do not establish. If the story is developing or ambiguous, explicitly use cautious wording. Use an evergreen topic only when no usable current headlines exist. Avoid topics substantially overlapping recent uploads.

TITLE/PACKAGING RULES:
- Produce 3 distinct title options.
- Lead with the trending subject or the viewer's real question, then signal the English-learning benefit where natural. Examples: "Can AI Take Your Job? | English Conversation Practice" or "What This New Tech Story Means | English Podcast". Avoid awkward forced wording.
- Put the main searchable phrase or learner problem near the beginning.
- Keep titles clear and reasonably concise; do not force awkwardly short titles.
- Do not start the title with "Two Takes Podcast".
- Do not use episode numbers.
- Make the title accurate, specific, and useful; no misleading clickbait.
- One title should be clearly searchable.
- One title should feel like a natural podcast episode title.
- Make at least one title earn the click with a concrete tension, surprising contrast, or clear consequence from the actual story; avoid generic labels and empty suspense.
- Keep the English-learning benefit visible in the title set, but don't force the same suffix onto every option.
- Choose the strongest primary title as "title".
- Produce "thumbnail_text" with only 2–4 short words, different wording from the full title when possible.
- Thumbnail text must be truthful to the actual episode.

CONTENT / RETENTION RULES:
- Write an original 1,300–1,450 word two-host conversation, aiming for approximately 9–11 minutes of spoken audio before the short musical tail.
- First turn: one sharp, concrete 8–14-word hook tied to the actual story, marked "hook", delivered with curious energy rather than announcer hype. Start the spoken audio at 0:00.
- Opening 25 seconds: hook -> the other host reacts or asks the viewer's real question -> give one useful, supported insight quickly. Make the stakes relatable without inventing details.
- Create one honest curiosity loop that the discussion answers within about 90 seconds. Never hide the basic answer or promise a reveal the episode cannot deliver.
- Vary the hook shape across episodes (specific dilemma, counterintuitive contrast, or vivid everyday consequence); don't default to "Can X do Y?" or "What if...?"
- Do not include a welcome, host/channel introduction, episode announcement, or opening music sting. The second turn should continue naturally into the topic.
- Use this flow: Hook -> Real Conversation -> Phrase Tour -> Quick Tip -> Speaking/Shadowing Practice -> Recap -> Outro.
- The Real Conversation should be the largest section and should feel like a genuine discussion, not a lesson script.
- Phrase Tour: include exactly 6 useful words or phrases that appeared naturally in the discussion and fit the chosen trend/story. Give each a simple meaning and one natural example. Avoid unrelated textbook vocabulary.
- Speaking/Shadowing Practice: include 5 short sentence patterns. Model each one naturally and invite the learner to repeat or personalize it.
- Make Himel and Niha react to each other frequently. Most turns should be 1–3 sentences.
- Add natural follow-up questions, examples, disagreement, clarification, personal mini-stories, and small moments of humor.
- Every 25–45 seconds, introduce a fresh example, question, mini-challenge, useful phrase, or change of angle so the conversation does not flatten. Use a natural curiosity loop, then answer it honestly; never promise a reveal the episode does not deliver.
- Use clear turn_type labels: hook, question, story, reaction, follow_up, clarification, language_tip, practice, recap, and outro. Use "hook" only for the direct opening line and "outro" for the final sign-off.
- The first dialogue item must be type "hook"; do not create any "welcome" turn; include multiple language_tip and practice turns; include at least one recap and one final outro turn.
- End with a concise recap, one concrete practice task, one specific comment question, and a natural sign-off. No generic long outro.
- Do not pad the episode just to reach a length target.
- Include one natural mid-episode question that invites viewers to compare the idea with their own experience, plus one specific comment question at the end.
- Make the title and thumbnail promise the same clear viewer benefit; keep thumbnail text at 2–4 readable words and avoid vague clickbait.
- Use a strong opening, quick first payoff, clear chapter changes, and a concrete final practice task to support retention.
- Avoid repetitive openings, repetitive outro lines, or the same conversation pattern as recent episodes.
- No copied scripts, quotes, statistics, or invented research.
- No stage directions or narration in the spoken dialogue.
- The selected current story must be a meaningful part of the conversation, not just a passing mention. Distinguish confirmed headline information from interpretation. Do not claim to have verified article details you have not been given.

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
    {{"speaker": "Himel", "turn_type": "hook", "delivery": "curious", "text": "..."}},
    {{"speaker": "Niha", "turn_type": "reaction", "delivery": "amused", "text": "..."}}
  ]
}}
"""

    from content_guard import is_duplicate, normalize_text

    # Build a deterministic pool of unused topics so the model cannot get
    # stuck regenerating the same rejected subject four times.
    recent_normalized = normalize_text(recent_context)
    fresh_topics = [
        topic for topic in topic_bank
        if normalize_text(topic) not in recent_normalized
    ]
    if not fresh_topics:
        fresh_topics = list(topic_bank)

    last_problem = None

    for generation_attempt in range(1, 5):
        forced_topic = fresh_topics[(generation_attempt - 1) % len(fresh_topics)]
        print(
            f"Generating fresh episode {generation_attempt}/4 "
            f"with duplicate protection..."
        )

        attempt_prompt = prompt + f"""

MANDATORY TOPIC FOR THIS ATTEMPT:
{forced_topic}

You must build the entire episode around this topic.
Set the JSON "topic" to this topic or a very close natural wording.
Do not switch to another topic.
"""
        if generation_attempt > 1:
            attempt_prompt += f"""

REGENERATION REQUIREMENT:
The previous draft failed validation. Keep the mandatory topic above,
but make the dialogue structurally different and fully valid.
Do not reuse any previously published topic/title.
"""

        raw = openai_generate(attempt_prompt)
        obj = parse_json(raw) or {}
        script = extract_dialogue(raw)
        word_count = len(script.split())

        # Gemini can return a structurally sound but undersized first draft.
        # Ask it to expand that same episode before discarding the topic and
        # spending another generation attempt. This preserves the topic and
        # improves reliability without opting into a paid provider.
        if (
            script
            and word_count < 1250
            and isinstance(obj, dict)
            and isinstance(obj.get("dialogue"), list)
        ):
            print(
                f"Short draft ({word_count} words); requesting a focused "
                "expansion before retrying the topic..."
            )
            expansion_prompt = f"""
Rewrite and expand the podcast draft below. Return ONLY valid JSON, using
the exact same top-level field names and dialogue item structure.

MANDATORY TOPIC: {forced_topic}
TARGET: 1,350–1,500 words in the spoken dialogue, enough for a roughly
9–11 minute educational English conversation at a natural pace.
Do not count JSON keys, metadata, or speaker labels as spoken content.

Keep Himel and Niha's voices conversational, warm, witty, and distinct.
Preserve the required flow: hook, direct-to-topic conversation,
six useful phrases with simple meanings and examples, a quick practical
tip, five short shadowing/practice patterns, recap, one specific question
for comments, and a concise natural sign-off.
Use 30–45 short, natural turns; no more than three consecutive turns by
the same host. Give the real conversation most of the time. Expand with
specific mini-stories, realistic reactions, helpful examples, clarifying
questions, and natural back-and-forth—not filler or repeated explanations.
Keep the first turn as "hook", do not add any welcome or intro turn, include at least three "language_tip" turns, at least three
"practice" turns, at least one "recap", and finish with "outro".
The topic must stay the mandatory topic. Keep metadata accurate to the
rewritten dialogue. Do not invent facts, statistics, citations, or research.

CURRENT DRAFT JSON:
{json.dumps(obj, ensure_ascii=False)}
"""
            try:
                expanded_raw = openai_generate(expansion_prompt)
                expanded_obj = parse_json(expanded_raw)
                expanded_script = extract_dialogue(expanded_raw)
                expanded_word_count = len(expanded_script.split())
                if (
                    isinstance(expanded_obj, dict)
                    and expanded_script
                    and expanded_word_count > word_count
                ):
                    raw = expanded_raw
                    obj = expanded_obj
                    script = expanded_script
                    word_count = expanded_word_count
                    print(f"Expanded draft length: {word_count} words")
                else:
                    print(
                        "Expansion did not improve the draft; retaining the "
                        f"original {word_count}-word version."
                    )
            except Exception as exc:
                print(f"Draft expansion failed safely: {exc}")

        if not script or word_count < 1250:
            last_problem = f"dialogue too short ({word_count} words)"
            print(last_problem)
            continue

        dialogue_obj = obj.get("dialogue", []) if isinstance(obj, dict) else []
        valid_types = {
            "hook", "question", "story", "reaction", "follow_up",
            "clarification", "language_tip", "practice", "recap", "outro"
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
                    delivery = str(item.get("delivery", "neutral")).strip().lower()
                    valid_deliveries = {
                        "warm", "curious", "amused", "surprised", "thoughtful",
                        "reassuring", "excited", "emphatic", "calm", "playful", "neutral",
                    }
                    if delivery not in valid_deliveries:
                        delivery = "neutral"
                    beats.append({
                        "turn_index": len(beats),
                        "speaker": speaker,
                        "text": text_value,
                        "turn_type": turn_type,
                        "delivery": delivery,
                    })

        turn_types = [beat["turn_type"] for beat in beats]
        first_three_turns = " ".join(beat["text"] for beat in beats[:3])
        unwanted_intro = re.compile(
            r"\b(?:welcome\s+(?:back\s+)?(?:to|everyone|everybody)|"
            r"this\s+is\s+(?:the\s+)?two\s+takes\s+podcast|"
            r"you['’]re\s+listening\s+to|on\s+today['’]s\s+episode|"
            r"my\s+name\s+is\s+(?:himel|niha)|i['’]m\s+(?:himel|niha))\b",
            re.I,
        )
        required_structure_ok = (
            bool(beats)
            and turn_types[0] == "hook"
            and "welcome" not in turn_types[:5]
            and turn_types.count("language_tip") >= 3
            and turn_types.count("practice") >= 3
            and "recap" in turn_types
            and turn_types[-1] == "outro"
            and not unwanted_intro.search(first_three_turns)
        )
        if not required_structure_ok:
            last_problem = "episode is missing the direct hook/phrase/practice/recap/outro structure or contains an unwanted intro"
            print(last_problem)
            continue

        if len(beats) < 24 or len(beats) > 60:
            last_problem = f"dialogue turn count outside 24–60 ({len(beats)})"
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
                topic = str(obj.get("topic", "")).strip() or forced_topic

                # If the model ignored the mandatory topic, reject this draft
                # before the duplicate guard and move to the next deterministic topic.
                forced_tokens = set(normalize_text(forced_topic).split())
                generated_tokens = set(normalize_text(topic).split())
                if (
                    forced_tokens
                    and generated_tokens
                    and len(forced_tokens & generated_tokens) / max(1, min(len(forced_tokens), len(generated_tokens))) < 0.50
                ):
                    last_problem = f"model ignored mandatory topic: {topic}"
                    print(last_problem)
                    continue

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

                print("Script generation and validation completed.")
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
        delivery = "neutral"
        turn_index = meta_cursor
        if meta_cursor < len(metadata) and metadata[meta_cursor].get("speaker") == speaker:
            turn_type = metadata[meta_cursor].get("turn_type", "reaction")
            delivery = metadata[meta_cursor].get("delivery", "neutral")
            turn_index = metadata[meta_cursor].get("turn_index", meta_cursor)
            meta_cursor += 1
        for sentence in split_sentences(source_text):
            chunks.append((speaker, sentence, turn_index, turn_type, delivery))
    return chunks


def delivery_speed(turn_type, delivery):
    """Use small speed differences to support tone; Kokoro has no emotion-control input."""
    delivery_speeds = {
        "warm": 0.97,
        "curious": 1.00,
        "amused": 1.02,
        "surprised": 1.02,
        "thoughtful": 0.93,
        "reassuring": 0.94,
        "excited": 1.03,
        "emphatic": 0.98,
        "calm": 0.95,
        "playful": 1.02,
        "neutral": 0.98,
    }
    if delivery in delivery_speeds and delivery != "neutral":
        return delivery_speeds[delivery]
    return {
        "hook": 1.01,
        "question": 1.00,
        "story": 0.95,
        "reaction": 1.01,
        "follow_up": 1.00,
        "clarification": 0.96,
        "language_tip": 0.97,
        "practice": 0.94,
        "recap": 0.97,
    }.get(turn_type, 0.98)


def kokoro_segment(speaker, text, index, total, turn_type="reaction", delivery="neutral"):
    voice = KOKORO_HIMEL_VOICE if speaker == "Himel" else KOKORO_NIHA_VOICE
    speed = delivery_speed(turn_type, delivery)
    print(
        f"Kokoro TTS segment {index}/{total} — {speaker} / {voice} "
        f"/ {delivery} / speed={speed:.2f} ({len(text)} chars)..."
    )
    for attempt in range(1, 3):
        try:
            generator = KOKORO_PIPELINE(text, voice=voice, speed=speed)
            audio_parts = [np.asarray(audio, dtype=np.float32) for _, _, audio in generator]
            if not audio_parts:
                raise RuntimeError("Kokoro returned no audio")
            return np.concatenate(audio_parts)
        except Exception as exc:
            print(f"  Kokoro attempt {attempt}/2 failed: {exc}")
            if attempt == 2:
                raise RuntimeError(
                    f"Kokoro TTS failed for {speaker} segment {index}: {exc}"
                ) from exc
    raise RuntimeError("Kokoro TTS failed unexpectedly")


def tts(script):
    segments = split_for_kokoro(script)
    print(f"Kokoro TTS: {len(segments)} short conversational segments.")
    audio_parts = []
    timing = []
    cursor = 0.0

    for i, (speaker, text, turn_index, turn_type, delivery) in enumerate(segments, 1):
        audio = kokoro_segment(
            speaker, text, i, len(segments), turn_type=turn_type, delivery=delivery
        )
        seg_seconds = len(audio) / KOKORO_SAMPLE_RATE

        timing.append({
            "speaker": speaker,
            "text": text,
            "start": cursor,
            "end": cursor + seg_seconds,
            "turn_index": turn_index,
            "turn_type": turn_type,
            "delivery": delivery,
        })
        audio_parts.append(audio)
        cursor += seg_seconds

        if i < len(segments):
            next_speaker, next_text, next_turn_index, next_turn_type, next_delivery = segments[i]
            # Natural timing: responses hand off more quickly; a new thought gets
            # a little air, and ellipses are reserved for genuine hesitation.
            if text.endswith("...") or text.endswith("…"):
                pause = 0.34
            elif next_turn_index != turn_index:
                pause = 0.34 if next_speaker != speaker else 0.24
            elif next_speaker != speaker:
                pause = 0.29
            elif text.endswith("?"):
                pause = 0.22
            elif text.endswith("!"):
                pause = 0.20
            else:
                pause = 0.15
            silence = np.zeros(int(KOKORO_SAMPLE_RATE * pause), dtype=np.float32)
            audio_parts.append(silence)
            cursor += pause

    (app.WORK / "tts_segments.json").write_text(
        json.dumps(timing, indent=2),
        encoding="utf-8"
    )

    if not audio_parts:
        raise RuntimeError("Kokoro produced no audio segments")

    # Seven seconds of music-only tail; the locally generated score fades during
    # its final 2.2 seconds for a clean, non-abrupt sign-off.
    outro_silence_seconds = 7.0
    audio_parts.append(
        np.zeros(int(KOKORO_SAMPLE_RATE * outro_silence_seconds), dtype=np.float32)
    )
    cursor += outro_silence_seconds

    audio = np.concatenate(audio_parts)
    wav = app.WORK / "voice.wav"
    sf.write(str(wav), audio, KOKORO_SAMPLE_RATE)
    print(
        f"Combined conversational Kokoro TTS audio: {wav}; "
        f"added {outro_silence_seconds:.1f}s outro music tail."
    )
    return wav



app.make_episode = make_episode
app.tts = tts

import production_upgrade as visual_upgrade
app.pexels_videos = lambda _keywords: []  # One supplied still image is used throughout; skip B-roll downloads.
app.make_srt = visual_upgrade.make_srt
app.render_video = visual_upgrade.render_video
app.render_shorts = visual_upgrade.render_shorts
app.make_thumbnail = visual_upgrade.make_thumbnail

print("=== ENGLISH-LEARNING STUDIO PRODUCTION ENABLED ===")
print(f"Script model: {OPENAI_TEXT_MODEL}")
print(f"Kokoro Himel: {KOKORO_HIMEL_VOICE}")
print(f"Kokoro Niha: {KOKORO_NIHA_VOICE}")
print("Output: 1920x1080 H.264, supplied opener as full-video background, speaker-positioned captions, no intro sting.")

app.main()
