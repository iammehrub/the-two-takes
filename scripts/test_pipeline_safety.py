"""Static regression checks for production workflow safety and evergreen mode."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PipelineSafetyTests(unittest.TestCase):
    def test_production_workflow_is_not_push_triggered(self):
        workflow = (ROOT / ".github/workflows/daily-podcast.yml").read_text(encoding="utf-8")
        self.assertNotIn("\n  push:\n", workflow)
        self.assertIn("  workflow_dispatch:", workflow)
        self.assertIn("  schedule:", workflow)

    def test_evergreen_pipeline_skips_news_rss(self):
        pipeline = (ROOT / "scripts/openai_pipeline.py").read_text(encoding="utf-8")
        builder = (ROOT / "scripts/build_podcast.py").read_text(encoding="utf-8")
        self.assertIn("app.REQUIRES_NEWS = False", pipeline)
        self.assertIn("app.fetch_news = skip_external_news_for_evergreen_show", pipeline)
        self.assertIn("if not news and REQUIRES_NEWS:", builder)

    def test_upload_preflight_has_target_channel_check(self):
        preflight = (ROOT / "scripts/youtube_upload_preflight.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/daily-podcast.yml").read_text(encoding="utf-8")
        self.assertIn("EXPECTED_YOUTUBE_CHANNEL_ID", preflight)
        self.assertIn("YOUTUBE_ANALYTICS_REFRESH_TOKEN", preflight)
        self.assertIn("EXPECTED_YOUTUBE_CHANNEL_ID: UCnCATEnOPcnaZQvX2zwZjOA", workflow)


if __name__ == "__main__":
    unittest.main()
