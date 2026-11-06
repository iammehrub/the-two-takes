"""Free, deterministic editorial checks for generated Two Takes dialogue.

This is a heuristic assistant, not a substitute for listening to the episode.
It uses only the Python standard library and makes no paid API calls.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


_FILLERS = (
    "exactly",
    "absolutely",
    "that's interesting",
    "that is interesting",
    "great question",
    "that's a good question",
    "that is a good question",
    "you know",
)


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9']+", " ", str(text or "").casefold()).strip()


def evaluate_dialogue(beats: list[dict]) -> dict:
    """Score dialogue structure and repetition using explainable local heuristics."""
    valid = [
        beat for beat in beats
        if isinstance(beat, dict)
        and str(beat.get("speaker", "")).title() in {"Himel", "Niha"}
        and str(beat.get("text", "")).strip()
    ]
    texts = [str(beat["text"]).strip() for beat in valid]
    speakers = [str(beat["speaker"]).title() for beat in valid]
    counts = Counter(speakers)
    total = len(valid)
    host_balance = (
        round(min(counts.get("Himel", 0), counts.get("Niha", 0)) /
              max(counts.get("Himel", 0), counts.get("Niha", 0)), 3)
        if max(counts.get("Himel", 0), counts.get("Niha", 0)) else 0.0
    )

    warnings: list[str] = []
    deductions = 0

    normalized_lines = [_normalise(text) for text in texts]
    duplicates = [
        line for line, count in Counter(normalized_lines).items()
        if line and count > 1 and len(line.split()) >= 5
    ]
    if duplicates:
        warnings.append(f"{len(duplicates)} repeated dialogue line(s) detected.")
        deductions += min(20, 6 * len(duplicates))

    joined = " ".join(texts).casefold()
    filler_hits = sum(joined.count(phrase) for phrase in _FILLERS)
    if filler_hits > 4:
        warnings.append(f"Repeated generic reactions detected ({filler_hits} instances).")
        deductions += min(14, (filler_hits - 4) * 2)

    long_turns = [len(text.split()) for text in texts if len(text.split()) > 65]
    if long_turns:
        warnings.append(f"{len(long_turns)} dialogue turn(s) exceed 65 words.")
        deductions += min(15, 3 * len(long_turns))

    sentence_lengths = []
    for text in texts:
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            words = re.findall(r"\b[\w’'-]+\b", sentence)
            if words:
                sentence_lengths.append(len(words))
    average_sentence_words = (
        round(sum(sentence_lengths) / len(sentence_lengths), 1)
        if sentence_lengths else 0.0
    )
    if average_sentence_words > 24:
        warnings.append(
            f"Average sentence length is high ({average_sentence_words} words); "
            "consider shorter spoken lines."
        )
        deductions += 8

    question_count = sum(text.count("?") for text in texts)
    if total >= 20 and question_count < 6:
        warnings.append("Few direct questions; the conversation may feel one-sided.")
        deductions += 7

    if host_balance < 0.45:
        warnings.append(f"Host balance is uneven ({counts.get('Himel', 0)} vs {counts.get('Niha', 0)} turns).")
        deductions += 8

    max_run = 0
    current_run = 0
    previous = None
    for speaker in speakers:
        current_run = current_run + 1 if speaker == previous else 1
        previous = speaker
        max_run = max(max_run, current_run)
    if max_run > 3:
        warnings.append(f"One host speaks for {max_run} consecutive turns.")
        deductions += min(12, (max_run - 3) * 4)

    turn_types = Counter(str(beat.get("turn_type", "")).lower() for beat in valid)
    if turn_types.get("follow_up", 0) + turn_types.get("clarification", 0) < 3:
        warnings.append("Few follow-up or clarification turns; add more host-to-host interaction.")
        deductions += 5

    if total < 24:
        warnings.append(f"Only {total} dialogue turns were found.")
        deductions += 10

    score = max(0, 100 - deductions)
    grade = "strong" if score >= 85 else "good" if score >= 70 else "review" if score >= 55 else "weak"

    return {
        "score": score,
        "grade": grade,
        "review_type": "local heuristic; human listening review still required",
        "dialogue_turns": total,
        "host_turn_counts": {
            "Himel": counts.get("Himel", 0),
            "Niha": counts.get("Niha", 0),
        },
        "host_balance_ratio": host_balance,
        "question_count": question_count,
        "average_sentence_words": average_sentence_words,
        "long_turn_count": len(long_turns),
        "repeated_line_count": len(duplicates),
        "generic_reaction_count": filler_hits,
        "max_consecutive_turns": max_run,
        "turn_type_counts": dict(turn_types),
        "warnings": warnings,
    }


def write_report(work_dir: str | Path, report: dict) -> Path:
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    path = work / "dialogue_qc.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Dialogue QC: {report['score']}/100 ({report['grade']}); "
        f"{len(report['warnings'])} warning(s)."
    )
    for warning in report["warnings"]:
        print(f"DIALOGUE QC WARNING: {warning}")
    return path
