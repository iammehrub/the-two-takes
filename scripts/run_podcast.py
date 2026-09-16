import os
import re
import requests
import build_podcast as app


# Use Flash-Lite for the episode-writing call so one episode does not burn
# several Gemini Flash requests through the old fallback loop.
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
        },
    }

    print(f"Generating episode with {GEMINI_TEXT_MODEL}...")
    response = requests.post(
        GEMINI_URL,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
        json=payload,
        timeout=180,
    )

    if response.status_code == 429:
        try:
            data = response.json()
            message = data.get("error", {}).get("message", response.text)
        except Exception:
            message = response.text
        raise RuntimeError(
            "Gemini quota is currently exhausted for the episode-writing call. "
            "Wait for the quota reset or use a Gemini API key/project with available quota. "
            f"Details: {message}"
        )

    if response.status_code >= 500:
        raise RuntimeError(
            f"Gemini server error {response.status_code}. "
            "Please run the workflow again later."
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Gemini request failed with HTTP {response.status_code}: {response.text[:1000]}"
        )

    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {response.text[:1000]}")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "\n".join(p.get("text", "") for p in parts if p.get("text"))
    if not text.strip():
        raise RuntimeError("Gemini returned an empty episode response.")

    return text.strip()


def parse_dialogue(text):
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if re.match(r"^(Himel|Niha)\s*:", line, re.I):
            line = re.sub(
                r"^(Himel|Niha)\s*:\s*",
                lambda m: "Himel: " if m.group(1).lower() == "himel" else "Niha: ",
                line,
            )
            lines.append(line)
    return "\n".join(lines).strip()


def parse_full(text):
    text = re.sub(r"```(?:text|txt|markdown)?", "", text, flags=re.I)
    text = text.replace("```", "").replace("\r\n", "\n").replace("\r", "\n").strip()

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
        r"(?is)^[ \t]*SCRIPT[ \t]*:[ \t]*\n?(.*?)(?:^[ \t]*END_SCRIPT[ \t]*$|\Z)",
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
Every speaking line MUST begin exactly with Himel: or Niha:.

Return ONLY this format:
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


# Replace only the episode-writing function. The original builder still handles
# news fetching, TTS, visuals, FFmpeg, thumbnail creation, and YouTube upload.
app.make_episode = make_episode
app.main()
