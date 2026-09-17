import os
import json
import re
import time
import random
import requests
import build_podcast as app

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_TEXT_MODEL = "gemini-3.5-flash-lite"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TEXT_MODEL}:generateContent"


def gemini_generate(prompt, temperature=0.7):
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
    for attempt in range(1, 4):
        print(f"Gemini {GEMINI_TEXT_MODEL} attempt {attempt}/3...")
        try:
            r = requests.post(
                GEMINI_URL,
                headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
                json=payload,
                timeout=180,
            )
        except requests.RequestException as exc:
            if attempt == 3:
                raise RuntimeError(f"Gemini network request failed: {exc}") from exc
            time.sleep(4 * attempt + random.uniform(0, 2))
            continue
        if r.status_code == 429:
            raise RuntimeError(f"Gemini quota/rate limit was hit: {r.text[:1000]}")
        if r.status_code == 503 and attempt < 3:
            time.sleep(5 * attempt + random.uniform(0, 2))
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"Gemini request failed with HTTP {r.status_code}: {r.text[:1200]}")
        data = r.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "\n".join(p.get("text", "") for p in parts if p.get("text"))
        if text.strip():
            return text.strip()
        raise RuntimeError("Gemini returned an empty response.")
    raise RuntimeError("Gemini generation failed.")


def clean(text):
    return (text or "").strip().replace("\\r\\n", "\n").replace("\\n", "\n")


def parse_json(text):
    text = clean(text)
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        start, end = text.find("{"), text.rfind("}")
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
            lines = [speaker_line(x) for x in dialogue]
            lines = [x for x in lines if x]
            if lines:
                return "\n".join(lines)
    text = clean(raw)
    lines = []
    for raw_line in text.splitlines():
        m = re.match(r"^\s*(Himel|Niha)\s*:\s*(.+)$", raw_line, flags=re.I)
        if m:
            speaker = "Himel" if m.group(1).lower() == "himel" else "Niha"
            lines.append(f"{speaker}: {m.group(2).strip()}")
    if lines:
        return "\n".join(lines)

    # Last-resort extraction for partially truncated JSON.
    pattern = re.compile(r'"speaker"\s*:\s*"(Himel|Niha)"\s*,\s*"text"\s*:\s*"((?:\\.|[^"\\])*)"', re.I)
    found = []
    for m in pattern.finditer(text):
        try:
            spoken = json.loads('"' + m.group(2) + '"').strip()
        except Exception:
            spoken = m.group(2).replace('\\"', '"').replace('\\n', ' ').strip()
        if spoken:
            speaker = "Himel" if m.group(1).lower() == "himel" else "Niha"
            found.append(f"{speaker}: {spoken}")
    return "\n".join(found).strip()


def make_episode(news):
    headline_block = "\n".join(
        f"{i + 1}. {x['title']} — {x['source']} ({x['pubDate']})"
        for i, x in enumerate(news)
    )
    prompt = f"""
You are the lead writer for the English YouTube podcast THE TWO TAKES.
Hosts: Himel (male, curious, calm, quick-witted) and Niha (female, warm, sharp, thoughtful).

CURRENT NEWS HEADLINES:
{headline_block}

Choose ONE current topic from these headlines. Do not invent quotes, statistics, events, or sources.
Write an ORIGINAL 1,200–1,350 word two-host conversation with a cold hook, branded intro,
clear explanation of what happened and why it matters now, examples, respectful disagreement,
practical takeaway, and short outro.

Return ONLY valid JSON. Do not use markdown fences.
Every dialogue item must have speaker exactly Himel or Niha and a non-empty text string.
Use this shape:
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

    raw = gemini_generate(prompt)
    obj = parse_json(raw) or {}
    script = extract_dialogue(raw)
    word_count = len(script.split())

    # Metadata is useful but not allowed to kill an otherwise valid script.
    title = str(obj.get("title", "")).strip()
    topic = str(obj.get("topic", "")).strip()
    hook = str(obj.get("description_hook", obj.get("hook", ""))).strip()
    keywords_raw = obj.get("visual_keywords", [])
    if isinstance(keywords_raw, list):
        keywords = [str(x).strip() for x in keywords_raw if str(x).strip()]
    else:
        keywords = [x.strip() for x in str(keywords_raw or "").split(",") if x.strip()]

    if not script or word_count < 1100:
        debug = app.WORK / "gemini_episode_raw.txt"
        debug.write_text(raw, encoding="utf-8")
        raise RuntimeError(
            f"Gemini dialogue was too short ({word_count} words). Raw output saved to {debug}"
        )

    if not topic:
        topic = news[0]["title"] if news else "Today’s biggest technology story"
    if not title:
        title = f"The Two Takes: {topic}"
    if not keywords:
        keywords = ["technology", "artificial intelligence", "news", "innovation", "future"]
    if not hook:
        hook = f"Today on The Two Takes, we are unpacking {topic}."

    keywords = keywords[:5]
    print(f"Episode accepted: {word_count} dialogue words")
    print(f"Episode: {title}")
    print(f"Topic: {topic}")
    print(f"Script length: {word_count} words")
    return title[:100], topic[:300], keywords, hook[:500], script


app.make_episode = make_episode
app.main()
