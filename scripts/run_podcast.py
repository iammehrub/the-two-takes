import os
import json
import re
import time
import random
import requests
import build_podcast as app

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_TEXT_MODEL = "gemini-2.5-flash-lite"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_TEXT_MODEL}:generateContent"
)


def gemini_lite_generate(prompt, temperature=0.7):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 7000,
            "responseMimeType": "application/json",
        },
    }

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        print(f"Gemini {GEMINI_TEXT_MODEL} attempt {attempt}/{max_attempts}...")
        try:
            response = requests.post(
                GEMINI_URL,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": GEMINI_API_KEY,
                },
                json=payload,
                timeout=180,
            )
        except requests.RequestException as exc:
            if attempt >= max_attempts:
                raise RuntimeError(f"Gemini network request failed: {exc}") from exc
            delay = 5 * attempt + random.uniform(0, 2)
            print(f"Gemini network error. Retrying in {delay:.1f}s...")
            time.sleep(delay)
            continue

        if response.status_code == 429:
            try:
                message = response.json().get("error", {}).get("message", response.text)
            except Exception:
                message = response.text
            raise RuntimeError(f"Gemini quota/rate limit was hit. {message}")

        if response.status_code == 503:
            if attempt >= max_attempts:
                raise RuntimeError("Gemini is temporarily unavailable (503).")
            delay = 5 * attempt + random.uniform(0, 2)
            print(f"Gemini 503 temporary capacity error. Retrying in {delay:.1f}s...")
            time.sleep(delay)
            continue

        if response.status_code >= 400:
            raise RuntimeError(
                f"Gemini request failed with HTTP {response.status_code}: {response.text[:1200]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError("Gemini returned invalid JSON.") from exc

        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"Gemini returned no candidates: {response.text[:1200]}")
        text = "\n".join(
            part.get("text", "")
            for part in candidates[0].get("content", {}).get("parts", [])
            if part.get("text")
        )
        if not text.strip():
            raise RuntimeError("Gemini returned an empty response.")
        return text.strip()

    raise RuntimeError("Gemini generation failed.")


def _clean(text):
    return (text or "").strip().replace("\\r\\n", "\n").replace("\\n", "\n")


def _parse_json(text):
    clean = _clean(text)
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.I)
    clean = re.sub(r"\s*```$", "", clean).strip()
    try:
        obj = json.loads(clean)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    start = clean.find("{")
    end = clean.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(clean[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass
    return None


def _speaker_line(item):
    if not isinstance(item, dict):
        return ""
    speaker = str(item.get("speaker", "")).strip().lower()
    spoken = str(item.get("text", "")).strip()
    if speaker not in {"himel", "niha"} or not spoken:
        return ""
    return ("Himel: " if speaker == "himel" else "Niha: ") + spoken


def parse_dialogue(text):
    obj = _parse_json(text)
    if isinstance(obj, dict):
        dialogue = obj.get("dialogue", obj.get("script", []))
        if isinstance(dialogue, list):
            lines = [_speaker_line(x) for x in dialogue]
            lines = [x for x in lines if x]
            if lines:
                return "\n".join(lines)
        if isinstance(dialogue, str):
            nested = parse_dialogue(dialogue)
            if nested:
                return nested

    text = _clean(text)
    pattern = re.compile(r"(?im)^\s*(Himel|Niha)\s*:\s*(.*)$")
    lines = []
    for raw in text.splitlines():
        match = pattern.match(raw)
        if match:
            speaker = "Himel" if match.group(1).lower() == "himel" else "Niha"
            spoken = match.group(2).strip()
            if spoken:
                lines.append(f"{speaker}: {spoken}")
    return "\n".join(lines).strip()


def parse_full(text):
    obj = _parse_json(text)
    if isinstance(obj, dict):
        title = str(obj.get("title", obj.get("TITLE", ""))).strip()
        topic = str(obj.get("topic", obj.get("TOPIC", ""))).strip()
        hook = str(obj.get("description_hook", obj.get("DESCRIPTION_HOOK", obj.get("hook", "")))).strip()
        keywords_raw = obj.get("visual_keywords", obj.get("VISUAL_KEYWORDS", []))
        if isinstance(keywords_raw, list):
            keywords = ", ".join(str(x).strip() for x in keywords_raw if str(x).strip())
        else:
            keywords = str(keywords_raw or "").strip()
        return title, topic, keywords, hook, parse_dialogue(text)

    return "", "", "", "", parse_dialogue(text)


def make_episode(news):
    headline_block = "\n".join(
        f"{i + 1}. {x['title']} — {x['source']} ({x['pubDate']})"
        for i, x in enumerate(news)
    )

    prompt = f"""
You are the lead writer for a polished English YouTube podcast called THE TWO TAKES.
Hosts: Himel (male, curious, quick-witted, calm) and Niha (female, warm, sharp, thoughtful).
Audience: international young adults who like intelligent but easy-to-follow conversations.

CURRENT NEWS HEADLINES:
{headline_block}

Choose ONE genuinely current topic from the headlines.
Use only facts supported by the headlines or broadly established knowledge.
Do not invent quotes, statistics, events, sources, or breaking-news details.

Write an ORIGINAL 1,200–1,350 word two-host spoken podcast with:
- cold hook
- branded intro
- what happened and why it matters today
- main discussion with simple examples
- respectful disagreement
- practical takeaway
- short memorable outro

Every dialogue item must be a JSON object with speaker exactly Himel or Niha and a text string.
Do not include headings inside dialogue text.

Return ONLY valid JSON matching this schema:
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

    raw = gemini_lite_generate(prompt, 0.7)
    title, topic, keywords, hook, script = parse_full(raw)
    word_count = len(script.split())

    if not (title and topic and keywords and hook):
        debug = app.WORK / "gemini_episode_raw.txt"
        debug.write_text(raw, encoding="utf-8")
        raise RuntimeError(
            f"Gemini returned incomplete episode metadata. Raw output saved to {debug}"
        )

    if word_count < 1100:
        debug = app.WORK / "gemini_episode_raw.txt"
        debug.write_text(raw, encoding="utf-8")
        raise RuntimeError(
            f"Gemini returned only {word_count} dialogue words; need at least 1100. "
            f"Raw output saved to {debug}"
        )

    keyword_list = [
        re.sub(r"^[\-*\d.\)\s]+", "", item).strip("\"'")
        for item in keywords.split(",")
    ]
    keyword_list = [item for item in keyword_list if item][:5]
    print(f"Episode accepted: {word_count} dialogue words")
    return title[:100], topic[:300], keyword_list, hook[:500], script


app.make_episode = make_episode
app.main()
