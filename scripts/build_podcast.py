# ============================================================
# EPISODE GENERATION
# ============================================================

def make_episode(news):

    headline_block = "\n".join(
        f"{i + 1}. {x['title']} — {x['source']} ({x['pubDate']})"
        for i, x in enumerate(news)
    )

    prompt = f"""
You are the lead writer for a polished English YouTube podcast called THE TWO TAKES.

Hosts:
Himel (male, curious, quick-witted, calm)
Niha (female, warm, sharp, thoughtful)

Audience:
International young adults who like intelligent but easy-to-follow conversations.

CURRENT NEWS HEADLINES:
{headline_block}

Choose ONE genuinely current topic from these headlines.

It must have enough substance for about 10 minutes.

Do not pretend to know facts that are not supported by the headlines or your general knowledge.
If a headline is too uncertain, choose another.

Write an ORIGINAL 1,350–1,550 word two-host podcast script.

This is not an essay.
It must sound like two real people talking.

STRUCTURE:

1) 10–20 second cold hook:
surprising question, tension, or intriguing claim.

2) Short branded intro for The Two Takes.

3) Clear setup:
why this matters TODAY.

4) Main conversation with frequent turns between Himel and Niha.

5) Explain difficult ideas with simple examples.

6) Include at least one moment where the hosts disagree or challenge each other respectfully.

7) Add a few natural reactions, but never overuse fake laughter or filler.

8) Give viewers a useful takeaway.

9) Short memorable outro and invitation to return.

STYLE RULES:

- Natural, confident, polished spoken English.
- No textbook language.
- No long monologues.
- Most turns should be 1–4 sentences.
- Do not repeat the same phrases, hook patterns, or conversation structure used in previous episodes.
- No invented quotes, statistics, events, or sources.
- No copyrighted article copying.
- Avoid sensational clickbait that misrepresents the story.
- Make the title compelling but accurate.
- Keep Himel and Niha clearly labeled on every speaking turn.

IMPORTANT:
Return ONLY the following fields.
Do not use Markdown code fences.
Do not add explanations before or after the fields.

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

    text = gemini_generate(prompt, 0.85)

    # --------------------------------------------------------
    # CLEAN GEMINI RESPONSE
    # --------------------------------------------------------

    if not text:
        raise RuntimeError(
            "Gemini returned an empty episode response"
        )

    print("\nGemini episode response received.")
    print(f"Response length: {len(text)} characters")

    # Remove accidental Markdown code fences.
    text = re.sub(
        r"```(?:text|txt|markdown)?",
        "",
        text,
        flags=re.I
    )

    text = text.replace("```", "").strip()

    # Normalize Windows line endings.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove accidental leading/trailing whitespace.
    text = text.strip()

    # --------------------------------------------------------
    # HELPER: EXTRACT A FIELD
    # --------------------------------------------------------

    def extract_field(name, next_fields):

        pattern = (
            rf"(?im)^[ \t]*{re.escape(name)}[ \t]*:"
            rf"[ \t]*(.*?)(?=\n[ \t]*(?:"
            + "|".join(
                re.escape(x)
                for x in next_fields
            )
            + r")[ \t]*:|\Z)"
        )

        match = re.search(
            pattern,
            text,
            re.S
        )

        if not match:
            return ""

        return match.group(1).strip()

    # --------------------------------------------------------
    # EXTRACT BASIC FIELDS
    # --------------------------------------------------------

    title = extract_field(
        "TITLE",
        [
            "TOPIC",
            "VISUAL_KEYWORDS",
            "DESCRIPTION_HOOK",
            "SCRIPT"
        ]
    )

    topic = extract_field(
        "TOPIC",
        [
            "VISUAL_KEYWORDS",
            "DESCRIPTION_HOOK",
            "SCRIPT"
        ]
    )

    keywords = extract_field(
        "VISUAL_KEYWORDS",
        [
            "DESCRIPTION_HOOK",
            "SCRIPT"
        ]
    )

    hook = extract_field(
        "DESCRIPTION_HOOK",
        [
            "SCRIPT"
        ]
    )

    # --------------------------------------------------------
    # EXTRACT SCRIPT
    # --------------------------------------------------------

    script_match = re.search(
        r"(?is)"
        r"^[ \t]*SCRIPT[ \t]*:[ \t]*\n?"
        r"(.*?)"
        r"(?:^[ \t]*END_SCRIPT[ \t]*$|\Z)",
        text
    )

    script = (
        script_match.group(1).strip()
        if script_match
        else ""
    )

    # --------------------------------------------------------
    # FALLBACK SCRIPT EXTRACTION
    # --------------------------------------------------------

    # Sometimes Gemini writes END_SCRIPT but formatting differs.
    if not script:

        fallback = re.search(
            r"(?is)"
            r"SCRIPT\s*:\s*(.*?)(?:END_SCRIPT|$)",
            text
        )

        if fallback:
            script = fallback.group(1).strip()

    # --------------------------------------------------------
    # REMOVE ACCIDENTAL FIELD HEADERS FROM SCRIPT
    # --------------------------------------------------------

    script = re.sub(
        r"(?im)^[ \t]*END_SCRIPT[ \t]*$",
        "",
        script
    ).strip()

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    missing = []

    if not title:
        missing.append("TITLE")

    if not topic:
        missing.append("TOPIC")

    if not keywords:
        missing.append("VISUAL_KEYWORDS")

    if not hook:
        missing.append("DESCRIPTION_HOOK")

    if not script:
        missing.append("SCRIPT")

    if missing:

        # Save the raw Gemini response so the next failure
        # can be diagnosed instead of losing the response.
        debug_file = WORK / "gemini_episode_raw.txt"

        debug_file.write_text(
            text,
            encoding="utf-8"
        )

        raise RuntimeError(
            "Gemini episode response was incomplete. "
            f"Missing: {', '.join(missing)}. "
            f"Raw response saved to: {debug_file}"
        )

    # --------------------------------------------------------
    # CLEAN TITLE
    # --------------------------------------------------------

    title = re.sub(
        r"\s+",
        " ",
        title
    ).strip()

    # Remove accidental surrounding quotes.
    title = title.strip('"').strip("'").strip()

    # --------------------------------------------------------
    # CLEAN TOPIC
    # --------------------------------------------------------

    topic = re.sub(
        r"\s+",
        " ",
        topic
    ).strip()

    topic = topic.strip('"').strip("'").strip()

    # --------------------------------------------------------
    # CLEAN HOOK
    # --------------------------------------------------------

    hook = re.sub(
        r"\s+",
        " ",
        hook
    ).strip()

    hook = hook.strip('"').strip("'").strip()

    # --------------------------------------------------------
    # CLEAN KEYWORDS
    # --------------------------------------------------------

    keyword_list = []

    for k in keywords.split(","):

        k = k.strip()

        # Remove bullets/numbers accidentally generated.
        k = re.sub(
            r"^[\-\*\d\.\)\s]+",
            "",
            k
        ).strip()

        k = k.strip('"').strip("'").strip()

        if k:
            keyword_list.append(k)

    keyword_list = keyword_list[:5]

    # If Gemini somehow returns no usable keywords,
    # derive a few safe visual search terms from the topic.
    if not keyword_list:

        keyword_list = [
            "technology",
            "news",
            "discussion",
            "future",
            "people talking"
        ]

    # --------------------------------------------------------
    # CLEAN SCRIPT
    # --------------------------------------------------------

    script_lines = []

    for raw_line in script.splitlines():

        line = raw_line.strip()

        if not line:
            continue

        # Accept only actual host dialogue.
        if re.match(
            r"^(Himel|Niha)\s*:",
            line,
            re.I
        ):

            line = re.sub(
                r"^(Himel|Niha)\s*:\s*",
                lambda m: (
                    "Himel: "
                    if m.group(1).lower() == "himel"
                    else "Niha: "
                ),
                line,
                flags=re.I
            )

            script_lines.append(line)

    script = "\n".join(script_lines).strip()

    # --------------------------------------------------------
    # SCRIPT VALIDATION
    # --------------------------------------------------------

    word_count = len(script.split())

    print(
        f"Parsed episode: {word_count} script words"
    )

    if word_count < 1100:

        debug_file = WORK / "gemini_episode_raw.txt"

        debug_file.write_text(
            text,
            encoding="utf-8"
        )

        raise RuntimeError(
            f"Generated script was too short "
            f"({word_count} words); refusing to publish. "
            f"Raw response saved to: {debug_file}"
        )

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    return (
        title[:100],
        topic[:300],
        keyword_list,
        hook[:500],
        script
    )
