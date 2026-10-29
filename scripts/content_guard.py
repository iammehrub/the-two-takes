import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def normalize_text(value):
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def fingerprint_script(script):
    normalized = re.sub(r"\s+", " ", str(script or "").strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_history(root):
    root = Path(root)
    records = []
    history_path = root / "data" / "content_history.json"

    value = _read_json(history_path, [])
    if isinstance(value, dict):
        value = value.get("items", [])
    if isinstance(value, list):
        records.extend(x for x in value if isinstance(x, dict))

    # Also inspect upload records so the guard works even if an older
    # workflow did not create content_history.json yet.
    upload_dir = root / "data" / "youtube_uploads"
    if upload_dir.exists():
        for path in sorted(upload_dir.glob("*.json")):
            value = _read_json(path, {})
            if isinstance(value, dict) and value.get("video_id"):
                records.append(value)

    unique = {}
    for record in records:
        key = str(record.get("video_id") or "").strip()
        if not key:
            key = "|".join(
                [
                    normalize_text(record.get("title")),
                    normalize_text(record.get("topic")),
                ]
            )
        unique[key] = record

    return list(unique.values())


def recent_context(root, limit=20):
    records = load_history(root)
    records.sort(key=lambda x: str(x.get("published") or x.get("recorded_at") or ""))
    lines = []

    for record in records[-limit:]:
        title = str(record.get("title") or "").strip()
        topic = str(record.get("topic") or "").strip()
        kind = str(record.get("kind") or "YouTube").strip()
        if title or topic:
            lines.append(f"- [{kind}] {title} — {topic}")

    return "\n".join(lines) if lines else "(No prior published content is recorded yet.)"


def _token_set(value):
    return set(normalize_text(value).split())


# These words are common in English-learning channel titles. They should not,
# by themselves, make two different episodes look like duplicates.
_SIMILARITY_STOPWORDS = {
    "a", "an", "the", "of", "to", "for", "and", "or", "but", "with",
    "in", "on", "at", "by", "from", "about", "into", "through",
    "is", "are", "was", "were", "be", "been", "being", "do", "does",
    "did", "how", "what", "why", "when", "where", "who", "which",
    "can", "could", "will", "would", "should", "might", "may",
    "you", "your", "yours", "me", "my", "our", "we", "they", "them",
    "their", "this", "that", "these", "those", "it", "its", "as",
    "more", "most", "very", "much", "just", "than", "then",
    "english", "speak", "speaking", "spoken", "conversation",
    "conversations", "learning", "learn", "learned", "practice",
    "practise", "practicing", "practising", "natural", "naturally",
    "fluently", "fluent", "improve", "improving", "tips", "guide",
    "everyday", "daily", "useful", "phrases", "phrase", "words",
    "word", "easy", "simple", "beginner", "beginners", "talk", "talking",
}


def _similar(a, b):
    # Exclude generic channel vocabulary and numeric list counts before
    # comparing. Use Jaccard similarity rather than dividing by the shorter
    # title, which previously rejected many unrelated titles after 4 retries.
    a_tokens = {
        token for token in _token_set(a) - _SIMILARITY_STOPWORDS
        if not token.isdigit()
    }
    b_tokens = {
        token for token in _token_set(b) - _SIMILARITY_STOPWORDS
        if not token.isdigit()
    }
    if not a_tokens or not b_tokens:
        return False

    shared = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)
    # Require at least three meaningful shared terms. Exact title/topic
    # duplicates are detected separately by is_duplicate().
    return shared >= 3 and (shared / max(1, union)) >= 0.60


def is_duplicate(root, title, topic, script):
    title_key = normalize_text(title)
    topic_key = normalize_text(topic)
    script_hash = fingerprint_script(script)

    for record in load_history(root):
        old_title = normalize_text(record.get("title"))
        old_topic = normalize_text(record.get("topic"))
        old_hash = str(record.get("script_sha256") or "").strip()

        if title_key and old_title and title_key == old_title:
            return True, "duplicate title"

        if topic_key and old_topic and topic_key == old_topic:
            return True, "duplicate topic"

        if title_key and old_title and _similar(title_key, old_title):
            return True, "very similar title"

        if topic_key and old_topic and _similar(topic_key, old_topic):
            return True, "very similar topic"

        if old_hash and old_hash == script_hash:
            return True, "duplicate script"

    return False, ""


def record_content(root, video_id, title, topic, script, kind, published=None):
    root = Path(root)
    path = root / "data" / "content_history.json"
    records = load_history(root)

    published = published or datetime.now(timezone.utc).isoformat()
    item = {
        "video_id": str(video_id).strip(),
        "title": str(title).strip()[:100],
        "topic": str(topic).strip()[:300],
        "kind": str(kind).strip() or "YouTube",
        "published": published,
        "script_sha256": fingerprint_script(script),
    }

    kept = [
        x for x in records
        if str(x.get("video_id") or "").strip() != item["video_id"]
    ]
    kept.append(item)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(kept[-200:], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return item
