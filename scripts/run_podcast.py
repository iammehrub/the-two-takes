import re
import build_podcast as app


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


def make_episode_robust(news):
    headline_block = "\n".join(
        f"{i + 1}. {x['title']} — {x['source']} ({x['pubDate']})"
        for i, x in enumerate(news)
    )

    base = f"""
You are the lead writer for a polished English YouTube podcast called THE TWO TAKES.
Hosts: Himel (male, curious, quick-witted, calm) and Niha (female, warm, sharp, thoughtful).
Audience: international young adults who like intelligent but easy-to-follow conversations.

CURRENT NEWS HEADLINES:
{headline_block}

Choose ONE genuinely current topic from these headlines.
Use only facts supported by the headlines or broadly established knowledge. Do not invent quotes, statistics, events, or sources.
Keep the conversation original, natural, factual and suitable for YouTube.
Every speaking line MUST begin exactly with Himel: or Niha:.
"""

    def parse_full(text):
        text = re.sub(r"```(?:text|txt|markdown)?", "", text, flags=re.I)
        text = text.replace("```", "").replace("\r\n", "\n").replace("\r", "\n").strip()

        def field(name, next_fields):
            pattern = (
                rf"(?im)^[ \t]*{re.escape(name)}[ \t]*:[ \t]*(.*?)(?=\n[ \t]*(?:"
                + "|".join(re.escape(x) for x in next_fields)
                + r")[ \t]*:|\Z)"
            )
            m = re.search(pattern, text, re.S)
            return m.group(1).strip() if m else ""

        title = field("TITLE", ["TOPIC", "VISUAL_KEYWORDS", "DESCRIPTION_HOOK", "SCRIPT"])
        topic = field("TOPIC", ["VISUAL_KEYWORDS", "DESCRIPTION_HOOK", "SCRIPT"])
        keywords = field("VISUAL_KEYWORDS", ["DESCRIPTION_HOOK", "SCRIPT"])
        hook = field("DESCRIPTION_HOOK", ["SCRIPT"])

        m = re.search(
            r"(?is)^[ \t]*SCRIPT[ \t]*:[ \t]*\n?(.*?)(?:^[ \t]*END_SCRIPT[ \t]*$|\Z)",
            text,
        )
        script_raw = m.group(1).strip() if m else ""
        script = parse_dialogue(script_raw)
        return title.strip(), topic.strip(), keywords.strip(), hook.strip(), script

    prompt = base + """

Write an ORIGINAL 1,350–1,550 word two-host podcast script.
Structure: cold hook, branded intro, why it matters today, main discussion, simple examples, respectful disagreement, useful takeaway, memorable outro.
Most speaking turns should be 1–4 sentences.

Return ONLY:
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

    print("Generating primary Gemini episode...")
    first = app.gemini_generate(prompt, 0.75)
    title, topic, keywords, hook, script = parse_full(first)

    if title and topic and keywords and hook and len(script.split()) >= 1100:
        print(f"Primary episode accepted: {len(script.split())} words")
        keyword_list = [re.sub(r"^[\-*\d.\)\s]+", "", k).strip("\"'") for k in keywords.split(",")]
        keyword_list = [k for k in keyword_list if k][:5]
        return title[:100], topic[:300], keyword_list, hook[:500], script

    print(f"Primary response was too short/incomplete ({len(script.split())} dialogue words). Using section fallback...")

    section_specs = [
        ("OPENING + SETUP", 450, 550, "Write the cold hook, branded intro, choose and establish ONE headline topic, and explain why it matters today."),
        ("MAIN DISCUSSION", 550, 650, "Continue directly. Explain the important ideas with simple examples and have Himel and Niha respectfully challenge each other. Do not restart the episode."),
        ("TAKEAWAY + OUTRO", 400, 500, "Continue directly to the useful takeaway, final perspective, and a short memorable outro. Do not restart the episode."),
    ]

    parts = []
    chosen_topic = None
    for name, low, high, instruction in section_specs:
        section_prompt = base + f"""

The episode topic must remain consistent across all sections. Use the same topic unless the headlines make it impossible.
SECTION: {name}
{instruction}
Produce about {low}-{high} words.
Return dialogue ONLY. Every line must begin exactly with Himel: or Niha:.
No headings, no bullets, no metadata, no Markdown.
"""
        raw = app.gemini_generate(section_prompt, 0.6)
        dialogue = parse_dialogue(raw)
        if dialogue:
            parts.append(dialogue)
        print(f"{name}: {len(dialogue.split())} words")

    combined = "\n".join(parts).strip()
    count = len(combined.split())
    if count < 1100:
        debug = app.WORK / "gemini_episode_raw.txt"
        debug.write_text(first + "\n\n--- FALLBACK ---\n" + combined, encoding="utf-8")
        raise RuntimeError(f"Gemini could not produce a complete episode ({count} words). Raw output: {debug}")

    first_topic = topic or "Current technology and world news"
    first_title = title or "The Two Takes — Today’s Big Story"
    first_hook = hook or "Today Himel and Niha break down one current story and what it means."
    keyword_list = ["technology", "AI", "news", "future", "discussion"]
    print(f"Section fallback accepted: {count} words")
    return first_title[:100], first_topic[:300], keyword_list, first_hook[:500], combined


app.make_episode = make_episode_robust
app.main()
