"""Regression tests for episode-history duplicate protection."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.content_guard import fingerprint_script, is_duplicate


class ContentGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.history_path = self.root / "data" / "content_history.json"
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_history(self, records):
        self.history_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def test_common_english_learning_words_do_not_cause_false_duplicate(self):
        old_script = "Himel: Let us practise introducing ourselves at work."
        self.write_history([{
            "video_id": "old-video-1",
            "title": "Speak English More Naturally: 5 Daily Phrases",
            "topic": "Talking to a new colleague",
            "script_sha256": fingerprint_script(old_script),
        }])

        duplicate, reason = is_duplicate(
            self.root,
            "Practice English Naturally with Useful Everyday Conversation",
            "Asking for directions at an airport",
            "Niha: Today we will ask for directions in a busy airport.",
        )
        self.assertFalse(duplicate, reason)

    def test_same_specific_title_is_rejected_when_only_filler_words_change(self):
        self.write_history([{
            "video_id": "old-video-2",
            "title": "How to Handle Small Talk at Work",
            "topic": "Professional introductions",
            "script_sha256": fingerprint_script("Old script."),
        }])

        duplicate, reason = is_duplicate(
            self.root,
            "Handle Small Talk at Work: 5 Useful Tips",
            "Making a doctor's appointment",
            "A completely different script about appointments.",
        )
        self.assertTrue(duplicate)
        self.assertEqual(reason, "very similar title")

    def test_exact_duplicate_topic_is_still_rejected(self):
        self.write_history([{
            "video_id": "old-video-3",
            "title": "A different title",
            "topic": "Giving directions at an airport",
            "script_sha256": fingerprint_script("Old script."),
        }])

        duplicate, reason = is_duplicate(
            self.root,
            "Find Your Way Through a Busy Airport",
            "Giving directions at an airport",
            "A new script about airport directions.",
        )
        self.assertTrue(duplicate)
        self.assertEqual(reason, "duplicate topic")

    def test_duplicate_script_hash_is_still_rejected(self):
        same_script = "Himel: Let us practise this conversation together."
        self.write_history([{
            "video_id": "old-video-4",
            "title": "An unrelated stored title",
            "topic": "An unrelated stored topic",
            "script_sha256": fingerprint_script(same_script),
        }])

        duplicate, reason = is_duplicate(
            self.root,
            "A different specific title",
            "A completely new subject",
            same_script,
        )
        self.assertTrue(duplicate)
        self.assertEqual(reason, "duplicate script")


if __name__ == "__main__":
    unittest.main()
