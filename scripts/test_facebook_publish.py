import json
import tempfile
import unittest
from pathlib import Path

from scripts.facebook_publish import build_reel_description, select_matching_short


class FacebookPublishingTests(unittest.TestCase):
    def test_reel_caption_links_to_the_facebook_full_episode(self):
        url = "https://www.facebook.com/123/videos/456/"
        caption = build_reel_description("Why learning English feels hard", url)
        self.assertIn(url, caption)
        self.assertIn("Watch the full podcast on this Facebook Page", caption)
        self.assertNotIn("youtu.be/", caption)

    def test_matching_short_is_the_first_manifest_item(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "short_01.mp4").write_bytes(b"test")
            (folder / "short_02.mp4").write_bytes(b"test")
            manifest = folder / "shorts_manifest.json"
            manifest.write_text(json.dumps([
                {"file": "short_01.mp4", "duration_seconds": 25.0, "title": "Short 1"},
                {"file": "short_02.mp4", "duration_seconds": 24.0, "title": "Short 2"},
            ]), encoding="utf-8")

            selected_path, selected_item = select_matching_short(manifest)
            self.assertEqual(selected_path.name, "short_01.mp4")
            self.assertEqual(selected_item["title"], "Short 1")

    def test_missing_short_does_not_silently_select_another_file(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            manifest = folder / "shorts_manifest.json"
            manifest.write_text(json.dumps([
                {"file": "not_rendered.mp4", "duration_seconds": 25.0}
            ]), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                select_matching_short(manifest)


if __name__ == "__main__":
    unittest.main()
