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

    max_attempts = 4
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
                raise RuntimeError(
                    f"Gemini network request failed after {max_attempts} attempts: {exc}"
                ) from exc
            delay = min(60, 5 * (2 ** (attempt - 1))) + random.uniform(0, 2)
            print(f"Gemini network error. Retrying in {delay:.1f}s...")
            time.sleep(delay)
            continue

        if response.status_code == 503:
            if attempt >= max_attempts:
                raise RuntimeError(
                    "Gemini remained unavailable (503) after "
                    f"{max_attempts} attempts."
                )
            delay = min(60, 5 * (2 ** (attempt - 1))) + random.uniform(0, 2)
            print(f"Gemini 503 temporary capacity error. Retrying in {delay:.1f}s...")
            time.sleep(delay)
            continue

        if response.status_code == 429:
            try:
                data = response.json()
                message = data.get("error", {}).get("message", response.text)
            except Exception:
                message = response.text
            raise RuntimeError(
                "Gemini quota/rate limit was hit; not retrying 429. "
                f"Details: {message}"
            )

        if response.status_code >= 500:
            raise RuntimeError(
                f"Gemini server error {response.status_code}: {response.text[:1200]}"
            )

        if response.status_code >= 400:
            raise RuntimeError(
                f"Gemini request failed with HTTP {response.status_code}: "
                f"{response.text[:1200]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Gemini returned invalid JSON: {response.text[:1200]}"
            ) from exc

        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"Gemini returned no candidates: {response.text[:1200]}")

        parts = candidates[0].get("content", {}).get("parts", [])
        text = "\n".join(p.get("text", "") for p in parts if p.get("text"))
        if not text.strip():
            raise RuntimeError("Gemini returned an empty response.")
        return text.strip()

    raise RuntimeError("Gemini generation failed.")


def _clean_json_text(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _json_object_from_text(text):
    clean = _clean_json_text(text)
    try:
        obj = json.loads(clean)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    start = clean.find("{")
    end = clean.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(clean[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _speaker_line(speaker, text):
    speaker = str(speaker or "").strip().lower()
    if speaker not in {"himel", "niha"}:
        return ""
    text = str(text or "").strip()
    if not text:
        return ""
    return ("Himel: " if speaker == "himel" else "Niha: ") + text


def parse_dialogue(text):
    obj = _json_object_from_text(text)
    if isinstance(obj, dict):
        dialogue = obj.get("dialogue", obj.get("script", ""))
        if isinstance(dialogue, list):
            lines = []
            for item in dialogue:
                if isinstance(item, dict):
                    line = _speaker_line(item.get("speaker"), item.get("text"))
                    if line:
                        lines.append(line)
                elif isinstance(item, str):
                    nested = parse_dialogue(item)
                    if nested:
                        lines.append(nested)
            if lines:
                return "\n".join(lines).strip()
        elif isinstance(dialogue, str):
            parsed = parse_dialogue(dialogue)
            if parsed:
                return parsed

    text = (text or "").replace("\\n", "\n").replace("\\\"", '"')
    matches = list(
        re.finditer(
            r"(?im)(?:^|[\n\r\"'\[\{,])\s*\**(Himel|Niha)\s*:\s*\**",
            text,
        )
    )
    if not matches:
        return ""

    lines = []
    for i, match in enumerate(matches):
        speaker = "Himel" if match.group(1).lower() == "himel" else "Niha"
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        spoken = text[start:end].strip().strip(' ,}]\"')
        spoken = re.sub(r"\s+", " ", spoken).strip()
        if spoken:
            lines.append(f"{speaker}: {spoken}")
    return "\n".join(lines).strip()


def parse_full(text):
    obj = _json_object_from_text(text)
    if isinstance(obj, dict):
        title = str(obj.get("title", obj.get("TITLE", ""))).strip()
        topic = str(obj.get("topic", obj.get("TOPIC", ""))).strip()
        hook = str(
            obj.get("description_hook", obj.get("DESCRIPTION_HOOK", obj.get("hook", "")))
        ).strip()
        keywords_raw = obj.get("visual_keywords", obj.get("VISUAL_KEYWORDS", []))
        if isinstance(keywords_raw, list):
            keywords = ", ".join(str(x).strip() for x in keywords_raw if str(x).strip())
        else:
            keywords = str(keywords_raw or "").strip()
        script = parse_dialogue(text)
        return title, topic, keywords, hook, script

    text = _clean_json_text(text).replace("\r\n", "\n").replace("\r", "\n")

    def field(name, next_fields):
        pattern = (
            rf"(?im)^[ \t]*{re.escape(name)}[ \t]*:[ \t]*(.*?)(?=\n[ \t]*(?:"
            + "|".join(re.escape(x) for x in next_fields)
            + r")[ \t]*:|\Z)"
        )
        match = re.search(pattern, text, re.S)
        return match.group(1).strip() if match else ""

    title = field("TITLE", ["TOPIC", "VISUAL_KEYWORDS", "DESCRIPTION_HOOK", "SCRIPT"])
    topic = field("TOPIC", ["VISUAL_KEYWORDS", "DESCRIPTION_HOOK", "SCRIPT"])
    keywords = field("VISUAL_KEYWORDS", ["DESCRIPTION_HOOK", "SCRIPT"])
    hook = field("DESCRIPTION_HOOK", ["SCRIPT"])
    match = re.search(
        r"(?is)^[ \t]*SCRIPT[ \t]*:[ \t]*(.*?)(?:^[ \t]*END_SCRIPT[ \t]*$|\Z)",
        text,
    )
    script_raw = match.group(1).strip() if match else ""
    script = parse_dialogue(script_raw)
    return title, topic, keywords, hook, script


def make_episode(news):
    headline_block = "\n".join(
        f"{i + 1}. {x['title']} — {x['source']} ({x['pubDate']})"
        for i, x in enumerate(news)
    )

    prompt = f"""
You are the lead writer for a polished English YouTube podcast called THE TWO TAKES.

Hosts:
- Himel: male, curious, quick-witted, calm.
- Niha: female, warm, sharp, thoughtful.

Audience: international young adults who like intelligent but easy-to-follow conversations.

CURRENT NEWS HEADLINES:
{headline_block}

Choose ONE genuinely current topic from the headlines above.
Use only facts supported by the headlines or broadly established knowledge.
Do not invent quotes, statistics, events, sources, or breaking-news details.
Make the discussion original, natural, factual, balanced, and suitable for YouTube.

Write an ORIGINAL 1,200–1,350 word two-host spoken podcast.
Structure it as:
1. Cold hook
2. Branded intro
3. What happened and why it matters today
4. Main discussion with simple examples
5. Respectful disagreement between the hosts
6. Practical takeaway
7. Short memorable outro

Most speaking turns should be 1–4 sentences. Do not use stage directions.
Every dialogue item must contain a speaker of exactly Himel or Niha and a text string.

Return ONLY valid JSON. Use exactly this structure:
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
